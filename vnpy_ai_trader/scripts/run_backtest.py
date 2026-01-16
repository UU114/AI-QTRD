"""
Backtesting Runner Script.
回测运行脚本

Run backtesting for AI Alpha Strategy with natural language or JSON configuration.
"""

import sys
from pathlib import Path
from datetime import datetime
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from vnpy.trader.constant import Interval
from vnpy.alpha.lab import AlphaLab
from vnpy.alpha.strategy.backtesting import BacktestingEngine

from src.strategy.ai_alpha_strategy import AIAlphaStrategy
from src.ai_core.strategy_parser import StrategyParser
from src.ai_core.deepseek_client import DeepSeekClient
from src.datafeed.adata_datafeed import AdataDatafeed
from src.utils.logger import setup_logger, get_logger

# Setup logging
setup_logger(level="INFO")
logger = get_logger("backtest")


def load_or_parse_strategy(
    config_path: str | None = None,
    natural_language: str | None = None,
    deepseek_api_key: str | None = None
) -> dict:
    """
    Load strategy configuration from file or parse from natural language.

    Args:
        config_path: Path to JSON config file
        natural_language: Natural language strategy description
        deepseek_api_key: DeepSeek API key for parsing

    Returns:
        Strategy configuration dict
    """
    if config_path:
        logger.info(f"Loading strategy from: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    if natural_language and deepseek_api_key:
        logger.info("Parsing strategy from natural language...")
        client = DeepSeekClient(api_key=deepseek_api_key)
        parser = StrategyParser(deepseek_client=client)

        config, errors = parser.parse_and_validate(natural_language)
        if errors:
            raise ValueError(f"Strategy parsing failed: {errors}")

        return config

    raise ValueError("Either config_path or (natural_language + api_key) must be provided")


def run_backtest(
    strategy_config: dict,
    symbols: list[str],
    start_date: datetime,
    end_date: datetime,
    interval: Interval = Interval.DAILY,
    capital: int = 1_000_000,
    data_dir: str = "./data/lab"
) -> dict:
    """
    Run backtesting for the AI Alpha Strategy.

    Args:
        strategy_config: Parsed strategy configuration
        symbols: List of stock symbols to trade
        start_date: Backtest start date
        end_date: Backtest end date
        interval: Data interval
        capital: Initial capital
        data_dir: AlphaLab data directory

    Returns:
        Backtesting statistics dict
    """
    logger.info(f"Starting backtest: {strategy_config.get('strategy_name', 'unnamed')}")
    logger.info(f"Period: {start_date.date()} to {end_date.date()}")
    logger.info(f"Symbols: {len(symbols)}, Capital: {capital:,}")

    # Initialize AlphaLab
    lab = AlphaLab(data_dir)

    # Initialize backtesting engine
    engine = BacktestingEngine(lab)

    # Set parameters
    vt_symbols = [f"{s}.SSE" if s.startswith("6") else f"{s}.SZSE" for s in symbols]

    engine.set_parameters(
        vt_symbols=vt_symbols,
        interval=interval,
        start=start_date,
        end=end_date,
        capital=capital,
        risk_free=0.03,
        annual_days=240
    )

    # Add strategy with configuration
    setting = {
        "strategy_config": strategy_config,
        "ai_enabled": strategy_config.get("entry_rules", {}).get("ai_enhanced", False),
        "top_k": strategy_config.get("risk_control", {}).get("max_positions", 30)
    }

    # Generate signal DataFrame with datetime column for each trading day
    # In production, this would come from a trained model
    import polars as pl
    import numpy as np
    from datetime import timedelta

    # Generate dates between start and end
    trading_days = []
    current_date = start_date
    while current_date <= end_date:
        # Skip weekends (simple approximation)
        if current_date.weekday() < 5:
            trading_days.append(current_date)
        current_date += timedelta(days=1)

    # Create signal DataFrame with datetime, vt_symbol, and signal columns
    # Generate random signals for demonstration (in production, use model predictions)
    np.random.seed(42)  # For reproducibility
    signal_data = []
    for dt in trading_days:
        for vt_symbol in vt_symbols:
            signal_data.append({
                "datetime": dt,
                "vt_symbol": vt_symbol,
                "signal": np.random.uniform(0.3, 0.9)  # Random signal between 0.3 and 0.9
            })

    signal_df = pl.DataFrame(signal_data)
    logger.info(f"Generated {len(signal_df)} signal records for {len(trading_days)} trading days")

    engine.add_strategy(
        strategy_class=AIAlphaStrategy,
        setting=setting,
        signal_df=signal_df
    )

    # Load data
    logger.info("Loading historical data...")
    engine.load_data()

    # Check if data was loaded successfully
    if not engine.history_data:
        print("\n" + "=" * 60)
        print("ERROR: No historical data available!")
        print("=" * 60)
        print("\nPossible causes:")
        print("1. Data files not found in the data directory")
        print("2. No data for the specified symbols/date range")
        print("\nSolution:")
        print("Run the data preparation script first:")
        print(f"  python scripts/prepare_data.py --symbols {','.join([s.split('.')[0] for s in vt_symbols])}")
        print(f"  --start {start_date.strftime('%Y-%m-%d')} --end {end_date.strftime('%Y-%m-%d')}")
        print("=" * 60 + "\n")
        return {"error": "No data available"}

    # Run backtest
    logger.info("Running backtest...")
    engine.run_backtesting()

    # Calculate results
    result_df = engine.calculate_result()

    # Check if any trades occurred
    if result_df is None:
        print("\n" + "=" * 60)
        print("BACKTEST RESULTS / 回测结果")
        print("=" * 60)
        print("No trades executed during backtest period.")
        print("This may indicate:")
        print("  - Entry conditions were never met")
        print("  - Data quality issues")
        print("  - Strategy parameters too restrictive")
        print("=" * 60 + "\n")
        return {
            "status": "no_trades",
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "symbols": len(vt_symbols),
            "total_trades": 0
        }

    # Calculate statistics
    statistics = engine.calculate_statistics()

    # Print results
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS / 回测结果")
    print("=" * 60)

    for key, value in statistics.items():
        if isinstance(value, float):
            print(f"{key}: {value:.4f}")
        else:
            print(f"{key}: {value}")

    print("=" * 60 + "\n")

    return statistics


def main():
    """Main entry point for backtesting."""
    import argparse

    parser = argparse.ArgumentParser(description="AI Alpha Strategy Backtester")

    parser.add_argument(
        "--config",
        type=str,
        help="Path to strategy JSON config file"
    )
    parser.add_argument(
        "--strategy",
        type=str,
        help="Natural language strategy description"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="DeepSeek API key (or set DEEPSEEK_API_KEY env var)"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="000001,000002,000063,000333,000651",
        help="Comma-separated stock symbols"
    )
    parser.add_argument(
        "--start",
        type=str,
        default="2023-01-01",
        help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        type=str,
        default="2024-01-01",
        help="End date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--capital",
        type=int,
        default=1000000,
        help="Initial capital"
    )

    args = parser.parse_args()

    # Parse dates
    start_date = datetime.strptime(args.start, "%Y-%m-%d")
    end_date = datetime.strptime(args.end, "%Y-%m-%d")

    # Parse symbols
    symbols = [s.strip() for s in args.symbols.split(",")]

    # Load or parse strategy
    if args.config:
        strategy_config = load_or_parse_strategy(config_path=args.config)
    elif args.strategy:
        import os
        api_key = args.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("Error: DeepSeek API key required for natural language parsing")
            print("Set --api-key or DEEPSEEK_API_KEY environment variable")
            sys.exit(1)

        strategy_config = load_or_parse_strategy(
            natural_language=args.strategy,
            deepseek_api_key=api_key
        )
    else:
        # Use default demo strategy
        strategy_config = {
            "strategy_name": "demo_rsi_strategy",
            "description": "RSI oversold rebound strategy",
            "entry_rules": {
                "conditions": [
                    {"indicator": "RSI", "params": {"period": 14}, "operator": "<", "value": 30}
                ],
                "ai_enhanced": False
            },
            "exit_rules": {
                "take_profit": 0.10,
                "stop_loss": 0.05,
                "holding_days": 20
            },
            "risk_control": {
                "max_positions": 10,
                "position_size": 0.1
            }
        }
        print("Using demo strategy configuration")

    # Run backtest
    try:
        statistics = run_backtest(
            strategy_config=strategy_config,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            capital=args.capital
        )
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise


if __name__ == "__main__":
    main()
