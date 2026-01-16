"""
Paper Trading Account Simulation.
模拟交易账户

Provides a simulated trading environment for strategy testing without real money.
Uses real market data but simulates order execution.
"""

from datetime import datetime
from threading import Thread, Lock
from typing import Any
from collections import defaultdict
import time
import random

from vnpy.event import EventEngine
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    TickData, BarData, OrderData, TradeData, PositionData, AccountData,
    ContractData, OrderRequest, CancelRequest, SubscribeRequest,
    Exchange
)
from vnpy.trader.constant import (
    Direction, Offset, Status, Product, OrderType
)

from ..utils.logger import get_logger

logger = get_logger("paper_account")


class PaperPosition:
    """Simulated position tracking."""

    def __init__(self, symbol: str, exchange: Exchange):
        self.symbol = symbol
        self.exchange = exchange
        self.volume: float = 0
        self.frozen: float = 0
        self.avg_price: float = 0
        self.pnl: float = 0

    def update_trade(self, direction: Direction, volume: float, price: float) -> None:
        """Update position based on trade."""
        if direction == Direction.LONG:
            # Buying
            total_cost = self.avg_price * self.volume + price * volume
            self.volume += volume
            if self.volume > 0:
                self.avg_price = total_cost / self.volume
        else:
            # Selling
            self.volume -= volume
            if self.volume <= 0:
                self.volume = 0
                self.avg_price = 0

    def calculate_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L."""
        if self.volume > 0 and self.avg_price > 0:
            self.pnl = (current_price - self.avg_price) * self.volume
        else:
            self.pnl = 0
        return self.pnl


class PaperAccount(BaseGateway):
    """
    Paper Trading Account for strategy simulation.
    模拟交易账户，用于策略测试

    Features:
    - Simulates order execution with configurable slippage
    - Tracks positions and P&L
    - Supports limit and market orders
    - Can use real market data from another gateway or datafeed
    """

    default_name: str = "PAPER"

    default_setting: dict = {
        "初始资金": 1000000,           # Initial capital
        "手续费率": 0.0003,            # Commission rate (0.03%)
        "印花税率": 0.001,             # Stamp duty (0.1%, sell only)
        "滑点": 0.001,                 # Slippage (0.1%)
        "成交延迟(毫秒)": 100,         # Execution delay in ms
    }

    exchanges: list[Exchange] = [Exchange.SSE, Exchange.SZSE]

    def __init__(self, event_engine: EventEngine, gateway_name: str = "PAPER"):
        """Initialize paper trading account."""
        super().__init__(event_engine, gateway_name)

        # Account state
        self.initial_capital: float = 1000000
        self.balance: float = 1000000
        self.frozen: float = 0
        self.commission_rate: float = 0.0003
        self.stamp_duty_rate: float = 0.001
        self.slippage: float = 0.001
        self.execution_delay: int = 100

        # Position tracking
        self.positions: dict[str, PaperPosition] = {}
        self.position_lock = Lock()

        # Order tracking
        self.orders: dict[str, OrderData] = {}
        self.active_orders: dict[str, OrderData] = {}
        self.order_count: int = 0
        self.trade_count: int = 0
        self.order_lock = Lock()

        # Market data
        self.ticks: dict[str, TickData] = {}
        self.subscribed_symbols: set[str] = set()

        # Thread control
        self._active: bool = False
        self._execution_thread: Thread | None = None

        # Statistics
        self.total_commission: float = 0
        self.total_trades: int = 0
        self.winning_trades: int = 0

    def connect(self, setting: dict) -> None:
        """
        Initialize paper trading account.

        Args:
            setting: Account settings
        """
        self.initial_capital = float(setting.get("初始资金", 1000000))
        self.balance = self.initial_capital
        self.commission_rate = float(setting.get("手续费率", 0.0003))
        self.stamp_duty_rate = float(setting.get("印花税率", 0.001))
        self.slippage = float(setting.get("滑点", 0.001))
        self.execution_delay = int(setting.get("成交延迟(毫秒)", 100))

        # Start execution thread
        self._active = True
        self._execution_thread = Thread(target=self._run_execution_loop)
        self._execution_thread.daemon = True
        self._execution_thread.start()

        self.write_log(f"Paper account initialized with capital: {self.initial_capital:,.2f}")

        # Push initial account data
        self._push_account()

    def close(self) -> None:
        """Close paper trading account."""
        self._active = False

        if self._execution_thread and self._execution_thread.is_alive():
            self._execution_thread.join(timeout=3)

        self.write_log("Paper account closed")

    def subscribe(self, req: SubscribeRequest) -> None:
        """
        Subscribe to market data.
        Note: In paper trading, this tracks which symbols we're interested in.
        Actual data should be pushed via update_tick().
        """
        vt_symbol = f"{req.symbol}.{req.exchange.value}"
        self.subscribed_symbols.add(vt_symbol)
        self.write_log(f"Subscribed to {vt_symbol}")

    def send_order(self, req: OrderRequest) -> str:
        """
        Send a simulated order.

        Args:
            req: Order request

        Returns:
            vt_orderid string
        """
        with self.order_lock:
            self.order_count += 1
            orderid = f"PAPER_{self.order_count}"

            # Create order data
            order = req.create_order_data(orderid, self.gateway_name)
            order.status = Status.SUBMITTING
            order.datetime = datetime.now()

            # Validate order
            vt_symbol = f"{req.symbol}.{req.exchange.value}"
            is_valid, error_msg = self._validate_order(req, vt_symbol)

            if not is_valid:
                order.status = Status.REJECTED
                self.on_order(order)
                self.write_log(f"Order rejected: {error_msg}")
                return ""

            # Freeze funds for buy orders
            if req.direction == Direction.LONG:
                order_value = req.price * req.volume
                commission = order_value * self.commission_rate
                total_frozen = order_value + commission

                self.frozen += total_frozen
                self.balance -= total_frozen

            # Store order
            self.orders[orderid] = order
            self.active_orders[orderid] = order

            # Update status to submitted
            order.status = Status.NOTTRADED
            self.on_order(order)

            self.write_log(f"Order submitted: {vt_symbol} {req.direction.value} "
                          f"volume={req.volume} price={req.price:.2f}")

            return order.vt_orderid

    def cancel_order(self, req: CancelRequest) -> None:
        """
        Cancel an active order.

        Args:
            req: Cancel request
        """
        with self.order_lock:
            orderid = req.orderid

            if orderid not in self.active_orders:
                self.write_log(f"Order not found or not active: {orderid}")
                return

            order = self.active_orders[orderid]

            # Unfreeze funds for buy orders
            if order.direction == Direction.LONG:
                remaining_volume = order.volume - order.traded
                order_value = order.price * remaining_volume
                commission = order_value * self.commission_rate
                total_unfrozen = order_value + commission

                self.frozen -= total_unfrozen
                self.balance += total_unfrozen

            # Update order status
            order.status = Status.CANCELLED
            order.datetime = datetime.now()

            del self.active_orders[orderid]

            self.on_order(order)
            self._push_account()

            self.write_log(f"Order cancelled: {orderid}")

    def query_account(self) -> None:
        """Query and push account data."""
        self._push_account()

    def query_position(self) -> None:
        """Query and push position data."""
        with self.position_lock:
            for vt_symbol, pos in self.positions.items():
                if pos.volume > 0:
                    position = PositionData(
                        symbol=pos.symbol,
                        exchange=pos.exchange,
                        direction=Direction.LONG,
                        volume=pos.volume,
                        frozen=pos.frozen,
                        price=pos.avg_price,
                        pnl=pos.pnl,
                        gateway_name=self.gateway_name
                    )
                    self.on_position(position)

    def update_tick(self, tick: TickData) -> None:
        """
        Update market data and trigger order matching.
        Call this method to provide real-time or simulated market data.

        Args:
            tick: Latest tick data
        """
        vt_symbol = tick.vt_symbol
        self.ticks[vt_symbol] = tick

        # Update position P&L
        with self.position_lock:
            if vt_symbol in self.positions:
                self.positions[vt_symbol].calculate_pnl(tick.last_price)

        # Trigger order matching
        self._match_orders(vt_symbol, tick)

        # Forward tick to strategy
        self.on_tick(tick)

    def _validate_order(self, req: OrderRequest, vt_symbol: str) -> tuple[bool, str]:
        """Validate order before submission."""
        # Check minimum volume (100 shares for A-shares)
        if req.volume < 100:
            return False, "Volume must be at least 100 shares"

        # Check volume is multiple of 100
        if req.volume % 100 != 0:
            return False, "Volume must be multiple of 100"

        # Check buy order has sufficient funds
        if req.direction == Direction.LONG:
            order_value = req.price * req.volume
            commission = order_value * self.commission_rate
            required = order_value + commission

            available = self.balance - self.frozen
            if required > available:
                return False, f"Insufficient funds: need {required:.2f}, have {available:.2f}"

        # Check sell order has sufficient position
        elif req.direction == Direction.SHORT:
            with self.position_lock:
                pos = self.positions.get(vt_symbol)
                if not pos or pos.volume < req.volume:
                    current_vol = pos.volume if pos else 0
                    return False, f"Insufficient position: need {req.volume}, have {current_vol}"

        return True, ""

    def _match_orders(self, vt_symbol: str, tick: TickData) -> None:
        """Match active orders against current market price."""
        with self.order_lock:
            orders_to_remove = []

            for orderid, order in self.active_orders.items():
                order_vt_symbol = f"{order.symbol}.{order.exchange.value}"

                if order_vt_symbol != vt_symbol:
                    continue

                # Check if order can be filled
                can_fill = False
                fill_price = 0

                if order.type == OrderType.MARKET:
                    can_fill = True
                    if order.direction == Direction.LONG:
                        fill_price = tick.ask_price_1 if tick.ask_price_1 > 0 else tick.last_price
                    else:
                        fill_price = tick.bid_price_1 if tick.bid_price_1 > 0 else tick.last_price

                elif order.type == OrderType.LIMIT:
                    if order.direction == Direction.LONG:
                        # Buy limit: fill if ask <= order price
                        if tick.ask_price_1 > 0 and tick.ask_price_1 <= order.price:
                            can_fill = True
                            fill_price = order.price
                        elif tick.last_price <= order.price:
                            can_fill = True
                            fill_price = order.price
                    else:
                        # Sell limit: fill if bid >= order price
                        if tick.bid_price_1 > 0 and tick.bid_price_1 >= order.price:
                            can_fill = True
                            fill_price = order.price
                        elif tick.last_price >= order.price:
                            can_fill = True
                            fill_price = order.price

                if can_fill:
                    # Apply slippage
                    if order.direction == Direction.LONG:
                        fill_price = fill_price * (1 + self.slippage)
                    else:
                        fill_price = fill_price * (1 - self.slippage)

                    self._execute_trade(order, fill_price)
                    orders_to_remove.append(orderid)

            # Remove filled orders
            for orderid in orders_to_remove:
                del self.active_orders[orderid]

    def _execute_trade(self, order: OrderData, price: float) -> None:
        """Execute a trade and update positions."""
        self.trade_count += 1
        tradeid = f"TRADE_{self.trade_count}"

        volume = order.volume - order.traded
        trade_value = price * volume

        # Calculate costs
        commission = trade_value * self.commission_rate
        stamp_duty = trade_value * self.stamp_duty_rate if order.direction == Direction.SHORT else 0
        total_cost = commission + stamp_duty

        self.total_commission += total_cost

        # Create trade data
        trade = TradeData(
            symbol=order.symbol,
            exchange=order.exchange,
            orderid=order.orderid,
            tradeid=tradeid,
            direction=order.direction,
            offset=Offset.NONE,
            price=price,
            volume=volume,
            datetime=datetime.now(),
            gateway_name=self.gateway_name
        )

        # Update position
        vt_symbol = f"{order.symbol}.{order.exchange.value}"

        with self.position_lock:
            if vt_symbol not in self.positions:
                self.positions[vt_symbol] = PaperPosition(order.symbol, order.exchange)

            pos = self.positions[vt_symbol]
            pos.update_trade(order.direction, volume, price)

        # Update balance
        if order.direction == Direction.LONG:
            # Buying: unfreeze and pay actual cost
            order_value = order.price * volume
            commission_frozen = order_value * self.commission_rate
            total_unfrozen = order_value + commission_frozen

            self.frozen -= total_unfrozen
            self.balance += total_unfrozen
            self.balance -= (trade_value + total_cost)

        else:
            # Selling: receive proceeds minus costs
            self.balance += (trade_value - total_cost)

        # Update order status
        order.traded += volume
        if order.traded >= order.volume:
            order.status = Status.ALLTRADED
        else:
            order.status = Status.PARTTRADED

        order.datetime = datetime.now()

        # Push updates
        self.on_trade(trade)
        self.on_order(order)
        self._push_account()
        self._push_position(vt_symbol)

        self.total_trades += 1

        self.write_log(f"Trade executed: {vt_symbol} {order.direction.value} "
                      f"volume={volume} price={price:.2f} cost={total_cost:.2f}")

    def _push_account(self) -> None:
        """Push account data update."""
        # Calculate total position value
        position_value = 0
        with self.position_lock:
            for vt_symbol, pos in self.positions.items():
                if vt_symbol in self.ticks:
                    position_value += pos.volume * self.ticks[vt_symbol].last_price
                else:
                    position_value += pos.volume * pos.avg_price

        account = AccountData(
            accountid="PAPER",
            balance=self.balance + self.frozen + position_value,
            frozen=self.frozen,
            gateway_name=self.gateway_name
        )
        self.on_account(account)

    def _push_position(self, vt_symbol: str) -> None:
        """Push position data update for a symbol."""
        with self.position_lock:
            if vt_symbol not in self.positions:
                return

            pos = self.positions[vt_symbol]

            position = PositionData(
                symbol=pos.symbol,
                exchange=pos.exchange,
                direction=Direction.LONG,
                volume=pos.volume,
                frozen=pos.frozen,
                price=pos.avg_price,
                pnl=pos.pnl,
                gateway_name=self.gateway_name
            )
            self.on_position(position)

    def _run_execution_loop(self) -> None:
        """Background thread for simulated execution."""
        while self._active:
            # Periodically push account updates
            self._push_account()
            time.sleep(1)

    def get_statistics(self) -> dict[str, Any]:
        """Get paper trading statistics."""
        total_pnl = 0
        with self.position_lock:
            for pos in self.positions.values():
                total_pnl += pos.pnl

        return {
            "initial_capital": self.initial_capital,
            "current_balance": self.balance,
            "frozen": self.frozen,
            "total_pnl": total_pnl,
            "total_commission": self.total_commission,
            "total_trades": self.total_trades,
            "return_pct": (self.balance + total_pnl - self.initial_capital) / self.initial_capital * 100
        }

    def reset(self) -> None:
        """Reset paper account to initial state."""
        with self.position_lock:
            self.positions.clear()

        with self.order_lock:
            self.orders.clear()
            self.active_orders.clear()

        self.balance = self.initial_capital
        self.frozen = 0
        self.total_commission = 0
        self.total_trades = 0
        self.order_count = 0
        self.trade_count = 0

        self.write_log("Paper account reset to initial state")
        self._push_account()
