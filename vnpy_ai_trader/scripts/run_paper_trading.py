"""
Paper Trading Runner Script.
模拟交易运行脚本

Run paper trading with AI-enhanced strategy using simulated account.
使用模拟账户运行AI增强策略进行模拟交易。

Usage:
    # With natural language strategy
    python run_paper_trading.py \
        --strategy "沪深300成分股，RSI低于30时买入，盈利10%或亏损5%卖出" \
        --symbols "000001,000002,000063" \
        --capital 1000000

    # With JSON config file
    python run_paper_trading.py \
        --config "path/to/strategy.json" \
        --symbols "000001,000002"

    # Replay historical data for testing
    python run_paper_trading.py \
        --strategy "RSI超卖策略" \
        --symbols "000001" \
        --replay \
        --start "2024-01-01" \
        --end "2024-03-01"
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread, Event
import signal

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from vnpy.event import EventEngine
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import SubscribeRequest, BarData, TickData

from src.gateway.paper_account import PaperAccount
from src.datafeed.adata_datafeed import AdataDatafeed
from src.strategy.ai_alpha_strategy import AIAlphaStrategy
from src.utils.logger import get_logger

logger = get_logger("paper_trading")


class PaperTradingRunner:
    """
    Paper Trading Runner.
    模拟交易运行器

    Orchestrates paper trading with:
    - PaperAccount for simulated order execution
    - AdataDatafeed for market data
    - AIAlphaStrategy for trading signals
    """

    def __init__(
        self,
        strategy_config: dict | str,
        symbols: list[str],
        initial_capital: float = 1000000,
        commission_rate: float = 0.0003,
        stamp_duty_rate: float = 0.001,
        slippage: float = 0.001,
        deepseek_api_key: str | None = None,
    ):
        """
        Initialize paper trading runner.

        Args:
            strategy_config: Strategy configuration (dict or natural language string)
            symbols: List of stock symbols to trade
            initial_capital: Starting capital
            commission_rate: Commission rate per trade
            stamp_duty_rate: Stamp duty rate (sell only)
            slippage: Slippage rate
            deepseek_api_key: DeepSeek API key for natural language parsing
        """
        self.symbols = symbols
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.stamp_duty_rate = stamp_duty_rate
        self.slippage = slippage
        self.deepseek_api_key = deepseek_api_key or os.getenv("DEEPSEEK_API_KEY", "")

        # Parse strategy if natural language
        if isinstance(strategy_config, str):
            self.strategy_config = self._parse_strategy(strategy_config)
        else:
            self.strategy_config = strategy_config

        # Initialize components
        self.event_engine = EventEngine()
        self.paper_account: PaperAccount | None = None
        self.datafeed: AdataDatafeed | None = None
        self.strategy: AIAlphaStrategy | None = None

        # Control flags
        self._running = False
        self._stop_event = Event()

        # Statistics
        self.start_time: datetime | None = None
        self.tick_count = 0
        self.bar_count = 0

    def _parse_strategy(self, description: str) -> dict:
        """Parse natural language strategy to JSON config."""
        from src.ai_core.strategy_parser import StrategyParser

        if not self.deepseek_api_key:
            raise ValueError("DeepSeek API key required for natural language strategy")

        parser = StrategyParser(self.deepseek_api_key)
        config, errors = parser.parse_and_validate(description)

        if config is None:
            raise ValueError(f"Failed to parse strategy: {errors}")

        logger.info(f"Strategy parsed successfully: {config.get('strategy_name', 'unnamed')}")
        return config

    def _init_components(self) -> None:
        """Initialize trading components."""
        # Start event engine
        self.event_engine.start()

        # Initialize paper account
        self.paper_account = PaperAccount(self.event_engine, "PAPER")

        paper_settings = {
            "初始资金": self.initial_capital,
            "手续费率": self.commission_rate,
            "印花税率": self.stamp_duty_rate,
            "滑点": self.slippage,
            "成交延迟(毫秒)": 100,
        }
        self.paper_account.connect(paper_settings)

        # Initialize datafeed
        self.datafeed = AdataDatafeed()
        self.datafeed.init(output=logger.info)

        # Initialize strategy
        self.strategy = AIAlphaStrategy(
            alpha_engine=None,  # Not using alpha engine in paper trading
            strategy_name=self.strategy_config.get("strategy_name", "paper_strategy"),
            vt_symbols=[self._to_vt_symbol(s) for s in self.symbols],
            strategy_config=self.strategy_config,
            deepseek_api_key=self.deepseek_api_key,
        )

        logger.info("All components initialized")

    def _to_vt_symbol(self, symbol: str) -> str:
        """Convert symbol to vt_symbol format."""
        # Determine exchange based on symbol prefix
        if symbol.startswith("6"):
            exchange = Exchange.SSE
        else:
            exchange = Exchange.SZSE
        return f"{symbol}.{exchange.value}"

    def _to_symbol_exchange(self, symbol: str) -> tuple[str, Exchange]:
        """Convert symbol to (symbol, exchange) tuple."""
        if symbol.startswith("6"):
            return symbol, Exchange.SSE
        return symbol, Exchange.SZSE

    def run_replay(
        self,
        start_date: str,
        end_date: str,
        interval: Interval = Interval.MINUTE,
        speed: float = 1.0,
    ) -> dict:
        """
        Run paper trading with historical data replay.
        使用历史数据回放进行模拟交易

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Data interval
            speed: Replay speed multiplier (1.0 = real-time, 10.0 = 10x faster)

        Returns:
            Trading statistics
        """
        logger.info(f"Starting paper trading replay: {start_date} to {end_date}")

        self._init_components()
        self._running = True
        self.start_time = datetime.now()

        try:
            # Subscribe to symbols
            for symbol in self.symbols:
                sym, exchange = self._to_symbol_exchange(symbol)
                req = SubscribeRequest(symbol=sym, exchange=exchange)
                self.paper_account.subscribe(req)

            # Load historical data
            from vnpy.trader.object import HistoryRequest

            all_bars: dict[str, list[BarData]] = {}

            for symbol in self.symbols:
                sym, exchange = self._to_symbol_exchange(symbol)
                req = HistoryRequest(
                    symbol=sym,
                    exchange=exchange,
                    start=datetime.strptime(start_date, "%Y-%m-%d"),
                    end=datetime.strptime(end_date, "%Y-%m-%d"),
                    interval=interval,
                )
                bars = self.datafeed.query_bar_history(req, output=logger.debug)
                if bars:
                    all_bars[self._to_vt_symbol(symbol)] = bars
                    logger.info(f"Loaded {len(bars)} bars for {symbol}")

            if not all_bars:
                raise ValueError("No historical data loaded")

            # Replay data
            self._replay_bars(all_bars, speed)

        except KeyboardInterrupt:
            logger.info("Paper trading interrupted by user")

        finally:
            self._running = False
            self._cleanup()

        return self._get_results()

    def _replay_bars(self, all_bars: dict[str, list[BarData]], speed: float) -> None:
        """Replay historical bars as ticks."""
        # Create time-sorted list of all bars
        bar_events = []
        for vt_symbol, bars in all_bars.items():
            for bar in bars:
                bar_events.append((bar.datetime, vt_symbol, bar))

        bar_events.sort(key=lambda x: x[0])

        if not bar_events:
            logger.warning("No bar events to replay")
            return

        logger.info(f"Replaying {len(bar_events)} bar events...")

        # Calculate delay between bars based on speed
        base_delay = 0.1 / speed  # 100ms between bars at 1x speed

        prev_time = None
        for dt, vt_symbol, bar in bar_events:
            if self._stop_event.is_set():
                break

            # Simulate time delay
            if prev_time:
                time_diff = (dt - prev_time).total_seconds()
                delay = min(time_diff / speed, base_delay)
                if delay > 0:
                    time.sleep(delay)

            prev_time = dt

            # Convert bar to tick for paper account
            tick = self._bar_to_tick(bar)
            self.paper_account.update_tick(tick)

            # Call strategy with bar data
            self._process_bar(vt_symbol, bar)

            self.bar_count += 1

            # Log progress every 100 bars
            if self.bar_count % 100 == 0:
                stats = self.paper_account.get_statistics()
                logger.info(
                    f"Processed {self.bar_count} bars, "
                    f"Balance: {stats['current_balance']:,.2f}, "
                    f"Trades: {stats['total_trades']}"
                )

    def _bar_to_tick(self, bar: BarData) -> TickData:
        """Convert bar data to tick data for order matching."""
        return TickData(
            symbol=bar.symbol,
            exchange=bar.exchange,
            datetime=bar.datetime,
            name=bar.symbol,
            volume=bar.volume,
            turnover=bar.turnover,
            last_price=bar.close_price,
            open_price=bar.open_price,
            high_price=bar.high_price,
            low_price=bar.low_price,
            pre_close=bar.open_price,  # Approximation
            bid_price_1=bar.close_price * 0.999,  # Simulated bid
            ask_price_1=bar.close_price * 1.001,  # Simulated ask
            bid_volume_1=10000,
            ask_volume_1=10000,
            gateway_name="PAPER",
        )

    def _process_bar(self, vt_symbol: str, bar: BarData) -> None:
        """Process a single bar through the strategy."""
        if not self.strategy:
            return

        # Simplified strategy signal check
        # In a full implementation, this would use the complete AIAlphaStrategy logic
        try:
            # Check for exit signals on existing positions
            position = self.paper_account.positions.get(vt_symbol)
            if position and position.volume > 0:
                exit_signal, reason = self._check_exit(
                    vt_symbol, position.avg_price, bar.close_price
                )
                if exit_signal:
                    self._execute_sell(vt_symbol, position.volume, bar)
                    logger.info(f"Exit signal for {vt_symbol}: {reason}")

            # Check for entry signals
            else:
                entry_signal, size = self._check_entry(vt_symbol, bar)
                if entry_signal and size > 0:
                    self._execute_buy(vt_symbol, size, bar)

        except Exception as e:
            logger.error(f"Error processing bar for {vt_symbol}: {e}")

    def _check_entry(self, vt_symbol: str, bar: BarData) -> tuple[bool, int]:
        """Check for entry signal. Returns (should_enter, volume)."""
        # Get entry rules from config
        entry_rules = self.strategy_config.get("entry_rules", {})

        # Simplified logic: check if any basic conditions are met
        # In production, this would use the full RuleEngine
        conditions = entry_rules.get("conditions", [])

        # For demo, use a simple condition based on price movement
        # Real implementation would calculate indicators
        should_enter = len(conditions) > 0  # Placeholder

        if should_enter:
            # Calculate position size based on risk control
            risk_control = self.strategy_config.get("risk_control", {})
            position_size_pct = risk_control.get("position_size", 0.1)

            available = self.paper_account.balance - self.paper_account.frozen
            position_value = available * position_size_pct
            volume = int(position_value / bar.close_price / 100) * 100  # Round to 100 shares

            return volume >= 100, volume

        return False, 0

    def _check_exit(
        self, vt_symbol: str, entry_price: float, current_price: float
    ) -> tuple[bool, str]:
        """Check for exit signal. Returns (should_exit, reason)."""
        exit_rules = self.strategy_config.get("exit_rules", {})

        # Check take profit
        take_profit = exit_rules.get("take_profit", 0.1)
        if current_price >= entry_price * (1 + take_profit):
            return True, f"Take profit at {take_profit*100:.1f}%"

        # Check stop loss
        stop_loss = exit_rules.get("stop_loss", 0.05)
        if current_price <= entry_price * (1 - stop_loss):
            return True, f"Stop loss at {stop_loss*100:.1f}%"

        return False, ""

    def _execute_buy(self, vt_symbol: str, volume: int, bar: BarData) -> None:
        """Execute buy order."""
        from vnpy.trader.object import OrderRequest
        from vnpy.trader.constant import Direction, OrderType

        symbol = vt_symbol.split(".")[0]
        exchange_str = vt_symbol.split(".")[1]
        exchange = Exchange.SSE if exchange_str == "SSE" else Exchange.SZSE

        req = OrderRequest(
            symbol=symbol,
            exchange=exchange,
            direction=Direction.LONG,
            type=OrderType.LIMIT,
            volume=float(volume),
            price=bar.close_price,
        )

        vt_orderid = self.paper_account.send_order(req)
        if vt_orderid:
            logger.info(f"Buy order sent: {vt_symbol} {volume} @ {bar.close_price:.2f}")

    def _execute_sell(self, vt_symbol: str, volume: float, bar: BarData) -> None:
        """Execute sell order."""
        from vnpy.trader.object import OrderRequest
        from vnpy.trader.constant import Direction, OrderType

        symbol = vt_symbol.split(".")[0]
        exchange_str = vt_symbol.split(".")[1]
        exchange = Exchange.SSE if exchange_str == "SSE" else Exchange.SZSE

        # Round volume to nearest 100
        sell_volume = int(volume / 100) * 100
        if sell_volume <= 0:
            return

        req = OrderRequest(
            symbol=symbol,
            exchange=exchange,
            direction=Direction.SHORT,
            type=OrderType.LIMIT,
            volume=float(sell_volume),
            price=bar.close_price,
        )

        vt_orderid = self.paper_account.send_order(req)
        if vt_orderid:
            logger.info(f"Sell order sent: {vt_symbol} {sell_volume} @ {bar.close_price:.2f}")

    def run_live(self, duration_hours: float = 4.0) -> dict:
        """
        Run paper trading with live market data simulation.
        使用实时行情模拟进行模拟交易

        Note: This requires a real-time data source. For testing,
        it simulates with periodic random price updates.

        Args:
            duration_hours: How long to run (in hours)

        Returns:
            Trading statistics
        """
        logger.info(f"Starting live paper trading for {duration_hours} hours")
        logger.warning("Live mode uses simulated random price updates for demo")

        self._init_components()
        self._running = True
        self.start_time = datetime.now()

        try:
            # Subscribe to symbols
            for symbol in self.symbols:
                sym, exchange = self._to_symbol_exchange(symbol)
                req = SubscribeRequest(symbol=sym, exchange=exchange)
                self.paper_account.subscribe(req)

            # Get initial prices from historical data
            initial_prices = self._get_initial_prices()

            # Run simulation loop
            end_time = datetime.now() + timedelta(hours=duration_hours)

            while datetime.now() < end_time and not self._stop_event.is_set():
                # Generate simulated tick updates
                for symbol in self.symbols:
                    vt_symbol = self._to_vt_symbol(symbol)
                    if vt_symbol in initial_prices:
                        tick = self._simulate_tick(vt_symbol, initial_prices[vt_symbol])
                        self.paper_account.update_tick(tick)
                        initial_prices[vt_symbol] = tick.last_price  # Update price

                        self.tick_count += 1

                # Log status periodically
                if self.tick_count % 10 == 0:
                    self._log_status()

                # Sleep for 1 second between updates
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Paper trading interrupted by user")

        finally:
            self._running = False
            self._cleanup()

        return self._get_results()

    def _get_initial_prices(self) -> dict[str, float]:
        """Get initial prices from recent historical data."""
        from vnpy.trader.object import HistoryRequest

        prices = {}
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)

        for symbol in self.symbols:
            sym, exchange = self._to_symbol_exchange(symbol)
            req = HistoryRequest(
                symbol=sym,
                exchange=exchange,
                start=start_date,
                end=end_date,
                interval=Interval.DAILY,
            )
            bars = self.datafeed.query_bar_history(req, output=logger.debug)
            if bars:
                prices[self._to_vt_symbol(symbol)] = bars[-1].close_price
            else:
                prices[self._to_vt_symbol(symbol)] = 10.0  # Default price

        return prices

    def _simulate_tick(self, vt_symbol: str, last_price: float) -> TickData:
        """Simulate a tick with random price movement."""
        import random

        # Random price change within ±0.5%
        change_pct = random.uniform(-0.005, 0.005)
        new_price = last_price * (1 + change_pct)

        symbol = vt_symbol.split(".")[0]
        exchange_str = vt_symbol.split(".")[1]
        exchange = Exchange.SSE if exchange_str == "SSE" else Exchange.SZSE

        return TickData(
            symbol=symbol,
            exchange=exchange,
            datetime=datetime.now(),
            name=symbol,
            volume=random.randint(1000, 10000),
            turnover=0,
            last_price=new_price,
            open_price=last_price,
            high_price=max(last_price, new_price),
            low_price=min(last_price, new_price),
            pre_close=last_price,
            bid_price_1=new_price * 0.999,
            ask_price_1=new_price * 1.001,
            bid_volume_1=random.randint(1000, 5000),
            ask_volume_1=random.randint(1000, 5000),
            gateway_name="PAPER",
        )

    def _log_status(self) -> None:
        """Log current trading status."""
        if not self.paper_account:
            return

        stats = self.paper_account.get_statistics()
        elapsed = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0

        logger.info(
            f"[{elapsed:.0f}s] "
            f"Ticks: {self.tick_count}, "
            f"Bars: {self.bar_count}, "
            f"Trades: {stats['total_trades']}, "
            f"Balance: {stats['current_balance']:,.2f}, "
            f"Return: {stats['return_pct']:.2f}%"
        )

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self.paper_account:
            self.paper_account.close()

        if self.event_engine:
            self.event_engine.stop()

        logger.info("Paper trading stopped")

    def _get_results(self) -> dict:
        """Get final trading results."""
        if not self.paper_account:
            return {}

        stats = self.paper_account.get_statistics()

        results = {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": datetime.now().isoformat(),
            "symbols": self.symbols,
            "initial_capital": self.initial_capital,
            "final_balance": stats["current_balance"],
            "total_pnl": stats["total_pnl"],
            "total_commission": stats["total_commission"],
            "total_trades": stats["total_trades"],
            "return_pct": stats["return_pct"],
            "tick_count": self.tick_count,
            "bar_count": self.bar_count,
        }

        # Log final results
        logger.info("=" * 50)
        logger.info("Paper Trading Results / 模拟交易结果")
        logger.info("=" * 50)
        logger.info(f"Initial Capital / 初始资金: {self.initial_capital:,.2f}")
        logger.info(f"Final Balance / 最终余额: {stats['current_balance']:,.2f}")
        logger.info(f"Total P&L / 总盈亏: {stats['total_pnl']:,.2f}")
        logger.info(f"Return / 收益率: {stats['return_pct']:.2f}%")
        logger.info(f"Total Trades / 总交易次数: {stats['total_trades']}")
        logger.info(f"Total Commission / 总手续费: {stats['total_commission']:,.2f}")
        logger.info("=" * 50)

        return results

    def stop(self) -> None:
        """Stop paper trading gracefully."""
        logger.info("Stopping paper trading...")
        self._stop_event.set()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run paper trading with AI strategy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Natural language strategy with replay mode
  python run_paper_trading.py \\
      --strategy "RSI低于30买入，盈利10%卖出" \\
      --symbols "000001,000002" \\
      --replay \\
      --start "2024-01-01" \\
      --end "2024-03-01"

  # JSON config with live simulation
  python run_paper_trading.py \\
      --config "strategy.json" \\
      --symbols "000001" \\
      --live \\
      --duration 1
        """,
    )

    # Strategy configuration
    strategy_group = parser.add_mutually_exclusive_group(required=True)
    strategy_group.add_argument(
        "--strategy", "-s", type=str, help="Natural language strategy description"
    )
    strategy_group.add_argument(
        "--config", "-c", type=str, help="Path to JSON strategy config file"
    )

    # Symbols
    parser.add_argument(
        "--symbols",
        "-y",
        type=str,
        required=True,
        help="Comma-separated list of stock symbols",
    )

    # Trading mode
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--replay",
        "-r",
        action="store_true",
        help="Replay historical data for testing",
    )
    mode_group.add_argument(
        "--live",
        "-l",
        action="store_true",
        help="Run with live (simulated) data",
    )

    # Replay mode options
    parser.add_argument(
        "--start",
        type=str,
        help="Start date for replay (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date for replay (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=10.0,
        help="Replay speed multiplier (default: 10.0)",
    )

    # Live mode options
    parser.add_argument(
        "--duration",
        type=float,
        default=1.0,
        help="Duration in hours for live mode (default: 1.0)",
    )

    # Account settings
    parser.add_argument(
        "--capital",
        type=float,
        default=1000000,
        help="Initial capital (default: 1000000)",
    )
    parser.add_argument(
        "--commission",
        type=float,
        default=0.0003,
        help="Commission rate (default: 0.0003)",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=0.001,
        help="Slippage rate (default: 0.001)",
    )

    # Output
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file for results (JSON)",
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Parse symbols
    symbols = [s.strip() for s in args.symbols.split(",")]

    # Load strategy configuration
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            strategy_config = json.load(f)
        logger.info(f"Loaded strategy config from {args.config}")
    else:
        strategy_config = args.strategy

    # Create runner
    runner = PaperTradingRunner(
        strategy_config=strategy_config,
        symbols=symbols,
        initial_capital=args.capital,
        commission_rate=args.commission,
        slippage=args.slippage,
    )

    # Set up signal handler for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Received interrupt signal")
        runner.stop()

    signal.signal(signal.SIGINT, signal_handler)

    # Run paper trading
    if args.replay:
        if not args.start or not args.end:
            parser.error("--start and --end are required for replay mode")

        results = runner.run_replay(
            start_date=args.start,
            end_date=args.end,
            speed=args.speed,
        )
    else:
        # Default to live simulation mode
        results = runner.run_live(duration_hours=args.duration)

    # Save results if output file specified
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
