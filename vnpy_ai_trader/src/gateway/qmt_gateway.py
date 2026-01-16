"""
QMT (迅投) Gateway Adapter for A-share Stock Trading.
QMT交易网关适配器

Implements vnpy BaseGateway interface using xtquant SDK.
Supports both simulation and live trading modes.

References:
- https://dict.thinktrader.net/nativeApi/xtdata.html
- https://github.com/ai4trade/XtQuant
"""

from datetime import datetime
from threading import Thread
from typing import Any
import time

from vnpy.event import EventEngine
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    TickData, OrderData, TradeData, PositionData, AccountData,
    ContractData, OrderRequest, CancelRequest, SubscribeRequest,
    Exchange
)
from vnpy.trader.constant import (
    Direction, Offset, Status, Product, OrderType
)

from ..utils.logger import get_logger

logger = get_logger("qmt_gateway")

# Try to import xtquant SDK
try:
    from xtquant import xtdata
    from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
    from xtquant.xttype import StockAccount
    from xtquant import xtconstant
    XTQUANT_AVAILABLE = True
except ImportError:
    XTQUANT_AVAILABLE = False
    logger.warning("xtquant SDK not installed. QMT Gateway will not be available.")


# Direction mapping
DIRECTION_VT2XT = {
    Direction.LONG: "buy",
    Direction.SHORT: "sell",
}

DIRECTION_XT2VT = {
    "buy": Direction.LONG,
    "sell": Direction.SHORT,
    48: Direction.LONG,   # xtconstant.STOCK_BUY
    49: Direction.SHORT,  # xtconstant.STOCK_SELL
}

# Order status mapping
STATUS_XT2VT = {
    48: Status.SUBMITTING,      # 未报
    49: Status.SUBMITTING,      # 待报
    50: Status.NOTTRADED,       # 已报
    51: Status.NOTTRADED,       # 已报待撤
    52: Status.PARTTRADED,      # 部成待撤
    53: Status.PARTTRADED,      # 部撤
    54: Status.CANCELLED,       # 已撤
    55: Status.REJECTED,        # 废单
    56: Status.ALLTRADED,       # 已成
}

# Exchange mapping
EXCHANGE_VT2XT = {
    Exchange.SSE: "SH",
    Exchange.SZSE: "SZ",
}

EXCHANGE_XT2VT = {
    "SH": Exchange.SSE,
    "SZ": Exchange.SZSE,
}


class QmtGatewayCallback(XtQuantTraderCallback if XTQUANT_AVAILABLE else object):
    """
    Callback class for QMT trading events.
    处理QMT交易事件的回调类
    """

    def __init__(self, gateway: "QmtGateway"):
        """Initialize callback with gateway reference."""
        if XTQUANT_AVAILABLE:
            super().__init__()
        self.gateway = gateway

    def on_disconnected(self) -> None:
        """Connection disconnected callback."""
        self.gateway.write_log("QMT connection disconnected")
        self.gateway.connected = False

    def on_stock_order(self, order_info: dict) -> None:
        """
        Order status update callback.
        委托回报推送
        """
        try:
            self.gateway.on_order_callback(order_info)
        except Exception as e:
            self.gateway.write_log(f"Order callback error: {e}")

    def on_stock_trade(self, trade_info: dict) -> None:
        """
        Trade execution callback.
        成交回报推送
        """
        try:
            self.gateway.on_trade_callback(trade_info)
        except Exception as e:
            self.gateway.write_log(f"Trade callback error: {e}")

    def on_stock_position(self, position_info: dict) -> None:
        """
        Position update callback.
        持仓变动推送
        """
        try:
            self.gateway.on_position_callback(position_info)
        except Exception as e:
            self.gateway.write_log(f"Position callback error: {e}")

    def on_stock_asset(self, asset_info: dict) -> None:
        """
        Account asset update callback.
        资金变动推送
        """
        try:
            self.gateway.on_account_callback(asset_info)
        except Exception as e:
            self.gateway.write_log(f"Asset callback error: {e}")

    def on_order_error(self, order_error: dict) -> None:
        """
        Order error callback.
        委托失败推送
        """
        self.gateway.write_log(f"Order error: {order_error}")

    def on_cancel_error(self, cancel_error: dict) -> None:
        """
        Cancel error callback.
        撤单失败推送
        """
        self.gateway.write_log(f"Cancel error: {cancel_error}")


class QmtGateway(BaseGateway):
    """
    QMT Gateway implementation for A-share trading.
    QMT交易网关实现

    Supports:
    - Real-time market data subscription
    - Order execution (limit/market orders)
    - Position and account queries
    - Both simulation and live trading modes

    Prerequisites:
    - MiniQMT client must be running and logged in
    - xtquant SDK must be installed
    """

    default_name: str = "QMT"

    default_setting: dict = {
        "账号": "",                    # Trading account number
        "会话ID": 1,                   # Session ID (must be unique)
        "QMT路径": "",                 # Path to MiniQMT userdata_mini folder
        "行情模式": "订阅",            # "订阅" (subscribe) or "全推" (full push)
    }

    exchanges: list[Exchange] = [Exchange.SSE, Exchange.SZSE]

    def __init__(self, event_engine: EventEngine, gateway_name: str = "QMT"):
        """Initialize QMT Gateway."""
        super().__init__(event_engine, gateway_name)

        self.trader: Any = None
        self.account: Any = None
        self.callback: QmtGatewayCallback | None = None

        # State tracking
        self.connected: bool = False
        self.subscribed_symbols: set[str] = set()
        self.orders: dict[str, OrderData] = {}
        self.order_count: int = 0

        # Threads
        self._active: bool = False
        self._quote_thread: Thread | None = None

        # Settings
        self.account_id: str = ""
        self.session_id: int = 1
        self.qmt_path: str = ""
        self.quote_mode: str = "订阅"

    def connect(self, setting: dict) -> None:
        """
        Connect to QMT server.

        Args:
            setting: Connection settings dict
        """
        if not XTQUANT_AVAILABLE:
            self.write_log("xtquant SDK not installed. Please install it first.")
            self.write_log("Download from: https://dict.thinktrader.net/nativeApi/download_xtquant.html")
            return

        # Parse settings
        self.account_id = setting.get("账号", "")
        self.session_id = int(setting.get("会话ID", 1))
        self.qmt_path = setting.get("QMT路径", "")
        self.quote_mode = setting.get("行情模式", "订阅")

        if not self.account_id:
            self.write_log("Error: Account number is required")
            return

        if not self.qmt_path:
            self.write_log("Error: QMT path is required")
            return

        try:
            # Create trader instance
            self.trader = XtQuantTrader(self.qmt_path, self.session_id)

            # Create account
            self.account = StockAccount(self.account_id)

            # Create and register callback
            self.callback = QmtGatewayCallback(self)
            self.trader.register_callback(self.callback)

            # Start trader thread
            self.trader.start()

            # Connect to MiniQMT
            connect_result = self.trader.connect()
            if connect_result != 0:
                self.write_log(f"QMT connection failed, error code: {connect_result}")
                self.write_log("Please ensure MiniQMT client is running and logged in")
                return

            # Subscribe to account
            subscribe_result = self.trader.subscribe(self.account)
            if subscribe_result != 0:
                self.write_log(f"Account subscription failed, error code: {subscribe_result}")
                return

            self.connected = True
            self.write_log(f"QMT Gateway connected successfully. Account: {self.account_id}")

            # Start quote thread
            self._active = True
            self._quote_thread = Thread(target=self._run_quote_loop)
            self._quote_thread.daemon = True
            self._quote_thread.start()

            # Query initial data
            self.query_account()
            self.query_position()
            self.query_contracts()

        except Exception as e:
            self.write_log(f"QMT connection error: {e}")
            logger.exception("QMT connection failed")

    def close(self) -> None:
        """Close gateway connection."""
        self._active = False

        if self._quote_thread and self._quote_thread.is_alive():
            self._quote_thread.join(timeout=3)

        if self.trader:
            try:
                self.trader.stop()
            except Exception as e:
                logger.error(f"Error stopping trader: {e}")

        self.connected = False
        self.write_log("QMT Gateway disconnected")

    def subscribe(self, req: SubscribeRequest) -> None:
        """
        Subscribe to market data.

        Args:
            req: Subscribe request with symbol and exchange
        """
        if not XTQUANT_AVAILABLE:
            return

        # Convert to QMT symbol format
        xt_symbol = self._to_xt_symbol(req.symbol, req.exchange)

        if xt_symbol in self.subscribed_symbols:
            return

        try:
            # Subscribe to tick data
            xtdata.subscribe_quote(
                stock_code=xt_symbol,
                period="tick",
                count=-1  # Real-time only
            )

            self.subscribed_symbols.add(xt_symbol)
            self.write_log(f"Subscribed to {xt_symbol}")

        except Exception as e:
            self.write_log(f"Subscribe failed for {xt_symbol}: {e}")

    def send_order(self, req: OrderRequest) -> str:
        """
        Send new order.

        Args:
            req: Order request

        Returns:
            vt_orderid string
        """
        if not self.connected or not self.trader:
            self.write_log("Not connected, cannot send order")
            return ""

        # Generate order ID
        self.order_count += 1
        orderid = f"{self.gateway_name}_{self.order_count}"

        # Convert to QMT format
        xt_symbol = self._to_xt_symbol(req.symbol, req.exchange)

        # Determine order type
        if req.direction == Direction.LONG:
            order_type = xtconstant.STOCK_BUY if XTQUANT_AVAILABLE else 23
        else:
            order_type = xtconstant.STOCK_SELL if XTQUANT_AVAILABLE else 24

        # Determine price type
        if req.type == OrderType.MARKET:
            price_type = xtconstant.LATEST_PRICE if XTQUANT_AVAILABLE else 5
            price = 0
        else:
            price_type = xtconstant.FIX_PRICE if XTQUANT_AVAILABLE else 11
            price = req.price

        try:
            # Submit order
            seq = self.trader.order_stock(
                account=self.account,
                stock_code=xt_symbol,
                order_type=order_type,
                order_volume=int(req.volume),
                price_type=price_type,
                price=price,
                strategy_name="vnpy_ai_trader",
                order_remark=orderid
            )

            # Create order data
            order = req.create_order_data(orderid, self.gateway_name)
            order.status = Status.SUBMITTING
            order.datetime = datetime.now()

            self.orders[orderid] = order
            self.on_order(order)

            self.write_log(f"Order submitted: {xt_symbol} {req.direction.value} "
                          f"volume={req.volume} price={price}")

            return order.vt_orderid

        except Exception as e:
            self.write_log(f"Order submission failed: {e}")
            logger.exception("Order submission error")
            return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """
        Cancel existing order.

        Args:
            req: Cancel request
        """
        if not self.connected or not self.trader:
            self.write_log("Not connected, cannot cancel order")
            return

        try:
            # Extract order ID
            orderid = req.orderid

            # Find the order
            if orderid not in self.orders:
                self.write_log(f"Order not found: {orderid}")
                return

            # Cancel via QMT
            # Note: QMT uses system order ID, we need to track the mapping
            self.trader.cancel_order_stock(self.account, int(orderid))

            self.write_log(f"Cancel request sent for order: {orderid}")

        except Exception as e:
            self.write_log(f"Cancel order failed: {e}")

    def query_account(self) -> None:
        """Query account balance."""
        if not self.connected or not self.trader:
            return

        try:
            asset = self.trader.query_stock_asset(self.account)

            if asset:
                account = AccountData(
                    accountid=self.account_id,
                    balance=float(asset.total_asset),
                    frozen=float(asset.frozen_cash),
                    gateway_name=self.gateway_name
                )
                self.on_account(account)

        except Exception as e:
            self.write_log(f"Account query failed: {e}")

    def query_position(self) -> None:
        """Query holding positions."""
        if not self.connected or not self.trader:
            return

        try:
            positions = self.trader.query_stock_positions(self.account)

            for pos in positions:
                # Parse symbol and exchange
                stock_code = pos.stock_code
                symbol, exchange = self._from_xt_symbol(stock_code)

                position = PositionData(
                    symbol=symbol,
                    exchange=exchange,
                    direction=Direction.LONG,
                    volume=float(pos.volume),
                    frozen=float(pos.frozen_volume),
                    price=float(pos.avg_price),
                    pnl=float(pos.market_value - pos.volume * pos.avg_price),
                    yd_volume=float(pos.yesterday_volume) if hasattr(pos, 'yesterday_volume') else 0,
                    gateway_name=self.gateway_name
                )
                self.on_position(position)

        except Exception as e:
            self.write_log(f"Position query failed: {e}")

    def query_contracts(self) -> None:
        """Query available contracts/instruments."""
        if not XTQUANT_AVAILABLE:
            return

        try:
            # Get stock list for SSE and SZSE
            for market, exchange in [("SH", Exchange.SSE), ("SZ", Exchange.SZSE)]:
                stocks = xtdata.get_stock_list_in_sector(f"沪深A股")

                for stock_code in stocks[:100]:  # Limit for performance
                    if stock_code.endswith(f".{market}"):
                        symbol = stock_code.replace(f".{market}", "")

                        contract = ContractData(
                            symbol=symbol,
                            exchange=exchange,
                            name=symbol,  # Would need to query actual name
                            product=Product.EQUITY,
                            size=1,
                            pricetick=0.01,
                            min_volume=100,
                            gateway_name=self.gateway_name
                        )
                        self.on_contract(contract)

        except Exception as e:
            self.write_log(f"Contract query failed: {e}")

    def _run_quote_loop(self) -> None:
        """Background thread for processing market data."""
        while self._active:
            try:
                self._process_quotes()
            except Exception as e:
                logger.error(f"Quote processing error: {e}")

            time.sleep(0.5)

    def _process_quotes(self) -> None:
        """Process subscribed quote data."""
        if not XTQUANT_AVAILABLE or not self.subscribed_symbols:
            return

        for xt_symbol in list(self.subscribed_symbols):
            try:
                # Get latest tick data
                tick_data = xtdata.get_full_tick([xt_symbol])

                if xt_symbol in tick_data:
                    data = tick_data[xt_symbol]
                    tick = self._convert_tick(xt_symbol, data)
                    if tick:
                        self.on_tick(tick)

            except Exception as e:
                logger.debug(f"Tick processing error for {xt_symbol}: {e}")

    def _convert_tick(self, xt_symbol: str, data: dict) -> TickData | None:
        """Convert QMT tick data to vnpy TickData."""
        try:
            symbol, exchange = self._from_xt_symbol(xt_symbol)

            tick = TickData(
                symbol=symbol,
                exchange=exchange,
                datetime=datetime.now(),
                last_price=float(data.get("lastPrice", 0)),
                volume=float(data.get("volume", 0)),
                turnover=float(data.get("amount", 0)),
                open_price=float(data.get("open", 0)),
                high_price=float(data.get("high", 0)),
                low_price=float(data.get("low", 0)),
                pre_close=float(data.get("lastClose", 0)),
                bid_price_1=float(data.get("bidPrice", [0])[0]) if data.get("bidPrice") else 0,
                ask_price_1=float(data.get("askPrice", [0])[0]) if data.get("askPrice") else 0,
                bid_volume_1=float(data.get("bidVol", [0])[0]) if data.get("bidVol") else 0,
                ask_volume_1=float(data.get("askVol", [0])[0]) if data.get("askVol") else 0,
                gateway_name=self.gateway_name
            )

            # Add more bid/ask levels if available
            for i in range(1, 5):
                if data.get("bidPrice") and len(data["bidPrice"]) > i:
                    setattr(tick, f"bid_price_{i+1}", float(data["bidPrice"][i]))
                    setattr(tick, f"bid_volume_{i+1}", float(data["bidVol"][i]))
                if data.get("askPrice") and len(data["askPrice"]) > i:
                    setattr(tick, f"ask_price_{i+1}", float(data["askPrice"][i]))
                    setattr(tick, f"ask_volume_{i+1}", float(data["askVol"][i]))

            return tick

        except Exception as e:
            logger.debug(f"Tick conversion error: {e}")
            return None

    def on_order_callback(self, order_info: dict) -> None:
        """Process order update from QMT."""
        try:
            stock_code = order_info.get("stock_code", "")
            symbol, exchange = self._from_xt_symbol(stock_code)

            # Get order ID from remark or generate
            orderid = order_info.get("order_remark", str(order_info.get("order_id", "")))

            order = OrderData(
                symbol=symbol,
                exchange=exchange,
                orderid=orderid,
                direction=DIRECTION_XT2VT.get(order_info.get("order_type"), Direction.LONG),
                offset=Offset.NONE,
                type=OrderType.LIMIT,
                price=float(order_info.get("price", 0)),
                volume=float(order_info.get("order_volume", 0)),
                traded=float(order_info.get("traded_volume", 0)),
                status=STATUS_XT2VT.get(order_info.get("order_status"), Status.SUBMITTING),
                datetime=datetime.now(),
                gateway_name=self.gateway_name
            )

            self.orders[orderid] = order
            self.on_order(order)

        except Exception as e:
            logger.error(f"Order callback processing error: {e}")

    def on_trade_callback(self, trade_info: dict) -> None:
        """Process trade update from QMT."""
        try:
            stock_code = trade_info.get("stock_code", "")
            symbol, exchange = self._from_xt_symbol(stock_code)

            trade = TradeData(
                symbol=symbol,
                exchange=exchange,
                orderid=str(trade_info.get("order_id", "")),
                tradeid=str(trade_info.get("traded_id", "")),
                direction=DIRECTION_XT2VT.get(trade_info.get("order_type"), Direction.LONG),
                offset=Offset.NONE,
                price=float(trade_info.get("traded_price", 0)),
                volume=float(trade_info.get("traded_volume", 0)),
                datetime=datetime.now(),
                gateway_name=self.gateway_name
            )

            self.on_trade(trade)

        except Exception as e:
            logger.error(f"Trade callback processing error: {e}")

    def on_position_callback(self, position_info: dict) -> None:
        """Process position update from QMT."""
        self.query_position()

    def on_account_callback(self, asset_info: dict) -> None:
        """Process account update from QMT."""
        self.query_account()

    def _to_xt_symbol(self, symbol: str, exchange: Exchange) -> str:
        """Convert vnpy symbol to QMT format (e.g., 000001.SZ)."""
        market = EXCHANGE_VT2XT.get(exchange, "SZ")
        return f"{symbol}.{market}"

    def _from_xt_symbol(self, xt_symbol: str) -> tuple[str, Exchange]:
        """Convert QMT symbol to vnpy format."""
        parts = xt_symbol.split(".")
        if len(parts) == 2:
            symbol = parts[0]
            exchange = EXCHANGE_XT2VT.get(parts[1], Exchange.SZSE)
            return symbol, exchange
        return xt_symbol, Exchange.SZSE
