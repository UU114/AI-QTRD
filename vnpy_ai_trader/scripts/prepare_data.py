"""
Data Preparation Script for Backtesting.
回测数据准备脚本

Downloads historical data from AData and saves to AlphaLab Parquet format.
"""

import sys
from pathlib import Path
from datetime import datetime
import argparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest, BarData
from vnpy.alpha.lab import AlphaLab

from src.datafeed.adata_datafeed import AdataDatafeed
from src.utils.logger import setup_logger, get_logger

# Setup logging
setup_logger(level="INFO")
logger = get_logger("prepare_data")


# Common A-share stock lists for testing
DEMO_SYMBOLS = [
    "000001",  # Ping An Bank
    "000002",  # Vanke A
    "000063",  # ZTE
    "000333",  # Midea
    "000651",  # Gree Electric
    "000858",  # Wuliangye
    "002415",  # Hikvision
    "600000",  # Pudong Bank
    "600036",  # CMB
    "600519",  # Moutai
]


def get_exchange(symbol: str) -> Exchange:
    """
    Determine exchange based on stock code prefix.

    Args:
        symbol: 6-digit stock code

    Returns:
        Exchange enum (SSE or SZSE)
    """
    if symbol.startswith(("6", "5", "9")):
        return Exchange.SSE
    else:
        return Exchange.SZSE


def download_and_save_data(
    symbols: list[str],
    start_date: datetime,
    end_date: datetime,
    interval: Interval,
    lab_path: str,
    datafeed: AdataDatafeed
) -> dict[str, int]:
    """
    Download data from AData and save to AlphaLab format.

    Args:
        symbols: List of stock symbols
        start_date: Start date for data
        end_date: End date for data
        interval: Data interval (DAILY or MINUTE)
        lab_path: Path to AlphaLab data directory
        datafeed: Initialized AdataDatafeed instance

    Returns:
        Dict mapping symbol to number of bars saved
    """
    # Initialize AlphaLab
    lab = AlphaLab(lab_path)

    results = {}
    total_symbols = len(symbols)

    for idx, symbol in enumerate(symbols, 1):
        exchange = get_exchange(symbol)
        vt_symbol = f"{symbol}.{exchange.value}"

        logger.info(f"[{idx}/{total_symbols}] Downloading {vt_symbol}...")

        # Create history request
        req = HistoryRequest(
            symbol=symbol,
            exchange=exchange,
            start=start_date,
            end=end_date,
            interval=interval
        )

        # Download data
        bars = datafeed.query_bar_history(req, output=lambda x: logger.debug(x))

        if not bars:
            logger.warning(f"No data for {vt_symbol}")
            results[vt_symbol] = 0
            continue

        # Save to AlphaLab format
        lab.save_bar_data(bars)
        results[vt_symbol] = len(bars)

        logger.info(f"Saved {len(bars)} bars for {vt_symbol}")

    return results


def setup_contract_settings(lab_path: str, symbols: list[str]) -> None:
    """
    Setup A-share contract settings (commission rates, etc).

    Args:
        lab_path: Path to AlphaLab data directory
        symbols: List of stock symbols
    """
    lab = AlphaLab(lab_path)

    for symbol in symbols:
        exchange = get_exchange(symbol)
        vt_symbol = f"{symbol}.{exchange.value}"

        # A-share standard settings:
        # - Commission: 0.025% (min 5 yuan per trade, handled by strategy)
        # - Stamp duty: 0.1% (sell only, simplified to 0.05% both sides)
        # - No short selling for regular stocks
        lab.add_contract_setting(
            vt_symbol=vt_symbol,
            long_rate=0.0003,   # 0.03% total (commission + fees)
            short_rate=0.0013,  # 0.13% (includes 0.1% stamp duty)
            size=1,             # 1 share per unit
            pricetick=0.01      # Price tick 0.01 yuan
        )

    logger.info(f"Contract settings configured for {len(symbols)} symbols")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Prepare historical data for backtesting"
    )

    parser.add_argument(
        "--symbols",
        type=str,
        default=",".join(DEMO_SYMBOLS),
        help="Comma-separated stock symbols (default: demo list)"
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
        default="2024-12-01",
        help="End date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--interval",
        type=str,
        choices=["daily", "minute"],
        default="daily",
        help="Data interval"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="./data/lab",
        help="AlphaLab data directory"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable AData cache (force fresh download)"
    )

    args = parser.parse_args()

    # Parse arguments
    symbols = [s.strip() for s in args.symbols.split(",")]
    start_date = datetime.strptime(args.start, "%Y-%m-%d")
    end_date = datetime.strptime(args.end, "%Y-%m-%d")
    interval = Interval.DAILY if args.interval == "daily" else Interval.MINUTE

    print("=" * 60)
    print("VNPy AI Trader - Data Preparation")
    print("=" * 60)
    print(f"Symbols: {len(symbols)}")
    print(f"Period: {args.start} to {args.end}")
    print(f"Interval: {args.interval}")
    print(f"Data directory: {args.data_dir}")
    print("=" * 60)

    # Initialize datafeed
    datafeed = AdataDatafeed()
    datafeed.cache_enabled = not args.no_cache

    if not datafeed.init():
        logger.error("Failed to initialize AData datafeed")
        print("\nError: AData library not available.")
        print("Please install: pip install adata")
        sys.exit(1)

    # Download and save data
    logger.info("Starting data download...")
    results = download_and_save_data(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        lab_path=args.data_dir,
        datafeed=datafeed
    )

    # Setup contract settings
    setup_contract_settings(args.data_dir, symbols)

    # Print summary
    print("\n" + "=" * 60)
    print("DOWNLOAD SUMMARY")
    print("=" * 60)

    success_count = 0
    total_bars = 0

    for vt_symbol, bar_count in results.items():
        status = "OK" if bar_count > 0 else "FAILED"
        print(f"{vt_symbol}: {bar_count} bars [{status}]")
        if bar_count > 0:
            success_count += 1
            total_bars += bar_count

    print("-" * 60)
    print(f"Total: {success_count}/{len(symbols)} symbols, {total_bars} bars")
    print(f"Data saved to: {Path(args.data_dir).absolute()}")
    print("=" * 60)

    if success_count == 0:
        logger.error("No data downloaded!")
        sys.exit(1)

    print("\nData preparation complete. You can now run backtests.")


if __name__ == "__main__":
    main()
