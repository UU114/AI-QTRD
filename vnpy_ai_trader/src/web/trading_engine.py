"""
Web Trading Engine.
Web交易引擎

Manages trading operations for the web interface, integrating:
- Paper trading account
- Strategy execution
- Real-time updates via WebSocket
"""

import asyncio
import os
from datetime import datetime
from typing import Any

from vnpy.event import EventEngine, Event
from vnpy.trader.constant import Exchange, Direction, OrderType, Interval
from vnpy.trader.object import (
    TickData, BarData, OrderData, TradeData, PositionData, AccountData,
    OrderRequest, CancelRequest, SubscribeRequest, HistoryRequest
)

from .websocket_manager import WebSocketManager
from ..gateway.paper_account import PaperAccount
from ..datafeed.adata_datafeed import AdataDatafeed
from ..ai_core.strategy_parser import StrategyParser
from ..strategy.ai_alpha_strategy import AIAlphaStrategy
from ..utils.logger import get_logger

logger = get_logger("trading_engine")


class TradingEngine:
    """
    Web Trading Engine.
    Web交易引擎

    Central hub for:
    - Managing paper trading account
    - Executing strategies
    - Pushing real-time updates to web clients
    """

    def __init__(self, ws_manager: WebSocketManager):
        """
        Initialize trading engine.

        Args:
            ws_manager: WebSocket manager for real-time updates
        """
        self.ws_manager = ws_manager

        # Core components
        self.event_engine: EventEngine | None = None
        self.paper_account: PaperAccount | None = None
        self.datafeed: AdataDatafeed | None = None

        # Strategy management
        self.strategies: dict[str, dict] = {}  # {strategy_id: config}
        self.active_strategy: str | None = None

        # State
        self._initialized = False
        self._running = False

        # API key from environment
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")

    async def initialize(self) -> None:
        """Initialize trading engine components."""
        if self._initialized:
            return

        logger.info("Initializing trading engine...")

        # Initialize event engine
        self.event_engine = EventEngine()
        self.event_engine.start()

        # Register event handlers
        self._register_event_handlers()

        # Initialize paper account
        self.paper_account = PaperAccount(self.event_engine, "PAPER")
        paper_settings = {
            "初始资金": 1000000,
            "手续费率": 0.0003,
            "印花税率": 0.001,
            "滑点": 0.001,
        }
        self.paper_account.connect(paper_settings)

        # Initialize datafeed
        self.datafeed = AdataDatafeed()
        self.datafeed.init(output=logger.info)

        self._initialized = True
        logger.info("Trading engine initialized successfully")

    async def shutdown(self) -> None:
        """Shutdown trading engine."""
        logger.info("Shutting down trading engine...")

        self._running = False

        if self.paper_account:
            self.paper_account.close()

        if self.event_engine:
            self.event_engine.stop()

        self._initialized = False
        logger.info("Trading engine shutdown complete")

    def _register_event_handlers(self) -> None:
        """Register event handlers for vnpy events."""
        if not self.event_engine:
            return

        # Register handlers for trading events
        self.event_engine.register("eOrder", self._on_order)
        self.event_engine.register("eTrade", self._on_trade)
        self.event_engine.register("ePosition", self._on_position)
        self.event_engine.register("eAccount", self._on_account)
        self.event_engine.register("eTick", self._on_tick)

    def _on_order(self, event: Event) -> None:
        """Handle order update event."""
        order: OrderData = event.data
        asyncio.create_task(self._async_on_order(order))

    async def _async_on_order(self, order: OrderData) -> None:
        """Async handler for order updates."""
        order_dict = {
            "orderid": order.orderid,
            "symbol": order.symbol,
            "exchange": order.exchange.value,
            "direction": order.direction.value,
            "type": order.type.value if order.type else None,
            "price": order.price,
            "volume": order.volume,
            "traded": order.traded,
            "status": order.status.value,
            "datetime": order.datetime.isoformat() if order.datetime else None,
        }
        await self.ws_manager.send_order_update(order_dict)

    def _on_trade(self, event: Event) -> None:
        """Handle trade execution event."""
        trade: TradeData = event.data
        asyncio.create_task(self._async_on_trade(trade))

    async def _async_on_trade(self, trade: TradeData) -> None:
        """Async handler for trade updates."""
        trade_dict = {
            "tradeid": trade.tradeid,
            "orderid": trade.orderid,
            "symbol": trade.symbol,
            "exchange": trade.exchange.value,
            "direction": trade.direction.value,
            "price": trade.price,
            "volume": trade.volume,
            "datetime": trade.datetime.isoformat() if trade.datetime else None,
        }
        await self.ws_manager.send_trade_update(trade_dict)

    def _on_position(self, event: Event) -> None:
        """Handle position update event."""
        position: PositionData = event.data
        asyncio.create_task(self._async_on_position(position))

    async def _async_on_position(self, position: PositionData) -> None:
        """Async handler for position updates."""
        pos_dict = {
            "symbol": position.symbol,
            "exchange": position.exchange.value,
            "direction": position.direction.value,
            "volume": position.volume,
            "frozen": position.frozen,
            "price": position.price,
            "pnl": position.pnl,
        }
        await self.ws_manager.send_position_update(pos_dict)

    def _on_account(self, event: Event) -> None:
        """Handle account update event."""
        account: AccountData = event.data
        asyncio.create_task(self._async_on_account(account))

    async def _async_on_account(self, account: AccountData) -> None:
        """Async handler for account updates."""
        account_dict = {
            "accountid": account.accountid,
            "balance": account.balance,
            "frozen": account.frozen,
            "available": account.balance - account.frozen,
        }
        await self.ws_manager.send_account_update(account_dict)

    def _on_tick(self, event: Event) -> None:
        """Handle tick data event."""
        tick: TickData = event.data
        asyncio.create_task(self._async_on_tick(tick))

    async def _async_on_tick(self, tick: TickData) -> None:
        """Async handler for tick updates."""
        tick_dict = {
            "symbol": tick.symbol,
            "exchange": tick.exchange.value,
            "last_price": tick.last_price,
            "volume": tick.volume,
            "bid_price_1": tick.bid_price_1,
            "ask_price_1": tick.ask_price_1,
            "datetime": tick.datetime.isoformat() if tick.datetime else None,
        }
        await self.ws_manager.send_tick(tick.vt_symbol, tick_dict)

    # ========== Strategy Management ==========

    async def parse_strategy(self, description: str) -> dict[str, Any]:
        """
        Parse natural language strategy to JSON config.

        Args:
            description: Natural language strategy description

        Returns:
            Parsed strategy configuration
        """
        if not self.deepseek_api_key:
            raise ValueError("DeepSeek API key not configured")

        parser = StrategyParser(self.deepseek_api_key)
        config, errors = parser.parse_and_validate(description)

        if config is None:
            raise ValueError(f"Failed to parse strategy: {errors}")

        return config

    async def create_strategy(
        self,
        strategy_id: str,
        config: dict,
        description: str = ""
    ) -> dict[str, Any]:
        """
        Create and store a new strategy.

        Args:
            strategy_id: Unique strategy identifier
            config: Strategy configuration
            description: Optional description

        Returns:
            Created strategy info
        """
        if strategy_id in self.strategies:
            raise ValueError(f"Strategy {strategy_id} already exists")

        self.strategies[strategy_id] = {
            "id": strategy_id,
            "config": config,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "status": "inactive",
        }

        logger.info(f"Strategy created: {strategy_id}")
        return self.strategies[strategy_id]

    async def get_strategy(self, strategy_id: str) -> dict[str, Any] | None:
        """Get strategy by ID."""
        return self.strategies.get(strategy_id)

    async def list_strategies(self) -> list[dict[str, Any]]:
        """List all strategies."""
        return list(self.strategies.values())

    async def delete_strategy(self, strategy_id: str) -> bool:
        """Delete a strategy."""
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
            logger.info(f"Strategy deleted: {strategy_id}")
            return True
        return False

    async def activate_strategy(self, strategy_id: str) -> bool:
        """Activate a strategy for trading."""
        if strategy_id not in self.strategies:
            raise ValueError(f"Strategy {strategy_id} not found")

        # Deactivate current strategy
        if self.active_strategy:
            self.strategies[self.active_strategy]["status"] = "inactive"

        self.active_strategy = strategy_id
        self.strategies[strategy_id]["status"] = "active"
        logger.info(f"Strategy activated: {strategy_id}")
        return True

    async def deactivate_strategy(self, strategy_id: str) -> bool:
        """Deactivate a strategy."""
        if strategy_id in self.strategies:
            self.strategies[strategy_id]["status"] = "inactive"
            if self.active_strategy == strategy_id:
                self.active_strategy = None
            logger.info(f"Strategy deactivated: {strategy_id}")
            return True
        return False

    # ========== Trading Operations ==========

    def send_order(
        self,
        symbol: str,
        exchange: str,
        direction: str,
        order_type: str,
        volume: float,
        price: float,
    ) -> str:
        """
        Send a trading order.

        Args:
            symbol: Stock symbol
            exchange: Exchange (SSE or SZSE)
            direction: LONG or SHORT
            order_type: LIMIT or MARKET
            volume: Order volume
            price: Order price

        Returns:
            Order ID
        """
        if not self.paper_account:
            raise RuntimeError("Trading engine not initialized")

        exchange_enum = Exchange.SSE if exchange.upper() == "SSE" else Exchange.SZSE
        direction_enum = Direction.LONG if direction.upper() == "LONG" else Direction.SHORT
        type_enum = OrderType.LIMIT if order_type.upper() == "LIMIT" else OrderType.MARKET

        req = OrderRequest(
            symbol=symbol,
            exchange=exchange_enum,
            direction=direction_enum,
            type=type_enum,
            volume=volume,
            price=price,
        )

        vt_orderid = self.paper_account.send_order(req)
        logger.info(f"Order sent: {vt_orderid}")
        return vt_orderid

    def cancel_order(self, orderid: str) -> None:
        """
        Cancel an active order.

        Args:
            orderid: Order ID to cancel
        """
        if not self.paper_account:
            raise RuntimeError("Trading engine not initialized")

        # Parse orderid to get symbol/exchange if needed
        req = CancelRequest(
            orderid=orderid,
            symbol="",  # Paper account looks up by orderid
            exchange=Exchange.SSE,
        )

        self.paper_account.cancel_order(req)
        logger.info(f"Order cancel requested: {orderid}")

    def get_orders(self) -> list[dict]:
        """Get all orders."""
        if not self.paper_account:
            return []

        orders = []
        for orderid, order in self.paper_account.orders.items():
            orders.append({
                "orderid": order.orderid,
                "symbol": order.symbol,
                "exchange": order.exchange.value,
                "direction": order.direction.value,
                "type": order.type.value if order.type else None,
                "price": order.price,
                "volume": order.volume,
                "traded": order.traded,
                "status": order.status.value,
                "datetime": order.datetime.isoformat() if order.datetime else None,
            })
        return orders

    def get_active_orders(self) -> list[dict]:
        """Get active orders only."""
        if not self.paper_account:
            return []

        orders = []
        for orderid, order in self.paper_account.active_orders.items():
            orders.append({
                "orderid": order.orderid,
                "symbol": order.symbol,
                "exchange": order.exchange.value,
                "direction": order.direction.value,
                "type": order.type.value if order.type else None,
                "price": order.price,
                "volume": order.volume,
                "traded": order.traded,
                "status": order.status.value,
                "datetime": order.datetime.isoformat() if order.datetime else None,
            })
        return orders

    # ========== Account & Position ==========

    def get_account(self) -> dict:
        """Get account information."""
        if not self.paper_account:
            return {}

        stats = self.paper_account.get_statistics()
        return {
            "initial_capital": stats["initial_capital"],
            "balance": stats["current_balance"],
            "frozen": stats["frozen"],
            "available": stats["current_balance"] - stats["frozen"],
            "total_pnl": stats["total_pnl"],
            "total_commission": stats["total_commission"],
            "total_trades": stats["total_trades"],
            "return_pct": stats["return_pct"],
        }

    def get_positions(self) -> list[dict]:
        """Get all positions."""
        if not self.paper_account:
            return []

        positions = []
        for vt_symbol, pos in self.paper_account.positions.items():
            if pos.volume > 0:
                positions.append({
                    "symbol": pos.symbol,
                    "exchange": pos.exchange.value,
                    "volume": pos.volume,
                    "frozen": pos.frozen,
                    "avg_price": pos.avg_price,
                    "pnl": pos.pnl,
                    "vt_symbol": vt_symbol,
                })
        return positions

    def reset_account(self) -> dict:
        """Reset paper trading account."""
        if not self.paper_account:
            raise RuntimeError("Trading engine not initialized")

        self.paper_account.reset()
        logger.info("Paper account reset")
        return self.get_account()

    # ========== Market Data ==========

    async def get_history(
        self,
        symbol: str,
        exchange: str,
        start: str,
        end: str,
        interval: str = "1d"
    ) -> list[dict]:
        """
        Get historical market data.

        Args:
            symbol: Stock symbol
            exchange: Exchange
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)
            interval: Data interval (1m, 5m, 15m, 30m, 1h, 1d)

        Returns:
            List of bar data dictionaries
        """
        if not self.datafeed:
            return []

        exchange_enum = Exchange.SSE if exchange.upper() == "SSE" else Exchange.SZSE

        interval_map = {
            "1m": Interval.MINUTE,
            "5m": Interval.MINUTE,
            "15m": Interval.MINUTE,
            "30m": Interval.MINUTE,
            "1h": Interval.HOUR,
            "1d": Interval.DAILY,
        }
        interval_enum = interval_map.get(interval, Interval.DAILY)

        req = HistoryRequest(
            symbol=symbol,
            exchange=exchange_enum,
            start=datetime.strptime(start, "%Y-%m-%d"),
            end=datetime.strptime(end, "%Y-%m-%d"),
            interval=interval_enum,
        )

        bars = self.datafeed.query_bar_history(req, output=logger.debug)

        return [
            {
                "datetime": bar.datetime.isoformat(),
                "open": bar.open_price,
                "high": bar.high_price,
                "low": bar.low_price,
                "close": bar.close_price,
                "volume": bar.volume,
                "turnover": bar.turnover,
            }
            for bar in bars
        ]

    def update_tick(self, tick_data: dict) -> None:
        """
        Update market tick data (for simulation).

        Args:
            tick_data: Tick data dictionary
        """
        if not self.paper_account:
            return

        exchange = Exchange.SSE if tick_data.get("exchange", "").upper() == "SSE" else Exchange.SZSE

        tick = TickData(
            symbol=tick_data["symbol"],
            exchange=exchange,
            datetime=datetime.now(),
            name=tick_data.get("name", tick_data["symbol"]),
            last_price=tick_data["last_price"],
            bid_price_1=tick_data.get("bid_price_1", tick_data["last_price"] * 0.999),
            ask_price_1=tick_data.get("ask_price_1", tick_data["last_price"] * 1.001),
            bid_volume_1=tick_data.get("bid_volume_1", 10000),
            ask_volume_1=tick_data.get("ask_volume_1", 10000),
            gateway_name="PAPER",
        )

        self.paper_account.update_tick(tick)
