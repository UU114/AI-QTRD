"""
Data Preparation Service.
数据准备服务

Handles historical data download and local data management.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Callable, Coroutine
import json

import polars as pl

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest
from vnpy.alpha.lab import AlphaLab

from ...datafeed.adata_datafeed import AdataDatafeed
from ...utils.logger import get_logger
from ..models import JobStatus, LocalSymbolInfo

logger = get_logger("data_service")


class DataService:
    """
    Service for data preparation operations.
    数据准备服务类

    Handles:
    - Download historical data from AData
    - Save to AlphaLab Parquet format
    - Manage contract settings
    - Query local data status
    """

    def __init__(self, data_dir: str = "./data/lab"):
        """
        Initialize data service.

        Args:
            data_dir: AlphaLab data directory path
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.lab = AlphaLab(str(self.data_dir))
        self.datafeed: AdataDatafeed | None = None

    def _ensure_datafeed(self) -> bool:
        """Ensure datafeed is initialized"""
        if self.datafeed is None:
            self.datafeed = AdataDatafeed()
            return self.datafeed.init(output=lambda x: logger.debug(x))
        return True

    @staticmethod
    def get_exchange(symbol: str) -> Exchange:
        """
        Determine exchange from stock code prefix.

        Args:
            symbol: 6-digit stock code

        Returns:
            Exchange enum (SSE or SZSE)
        """
        if symbol.startswith(("6", "5", "9")):
            return Exchange.SSE
        return Exchange.SZSE

    async def download_data(
        self,
        symbols: list[str],
        start_date: datetime,
        end_date: datetime,
        interval: Interval = Interval.DAILY,
        progress_callback: Callable[[dict], Coroutine] | None = None
    ) -> dict:
        """
        Download historical data for symbols.

        Args:
            symbols: List of stock symbols
            start_date: Start date
            end_date: End date
            interval: Data interval (DAILY or MINUTE)
            progress_callback: Async callback for progress updates

        Returns:
            Dict with download results
        """
        if not self._ensure_datafeed():
            raise RuntimeError("Failed to initialize AData datafeed")

        completed_symbols = []
        failed_symbols = []
        total = len(symbols)

        for idx, symbol in enumerate(symbols):
            exchange = self.get_exchange(symbol)
            vt_symbol = f"{symbol}.{exchange.value}"

            # Send progress update
            if progress_callback:
                await progress_callback({
                    "status": JobStatus.RUNNING.value,
                    "current_symbol": vt_symbol,
                    "current_index": idx + 1,
                    "total_symbols": total,
                    "completed_symbols": completed_symbols.copy(),
                    "failed_symbols": failed_symbols.copy(),
                    "progress_percent": (idx / total) * 100
                })

            # Download data (run in thread pool to avoid blocking)
            try:
                bars = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._download_symbol,
                    symbol,
                    exchange,
                    start_date,
                    end_date,
                    interval
                )

                if bars:
                    # Save to AlphaLab format
                    self.lab.save_bar_data(bars)
                    completed_symbols.append(vt_symbol)
                    logger.info(f"Downloaded {len(bars)} bars for {vt_symbol}")
                else:
                    failed_symbols.append(vt_symbol)
                    logger.warning(f"No data for {vt_symbol}")

            except Exception as e:
                failed_symbols.append(vt_symbol)
                logger.error(f"Failed to download {vt_symbol}: {e}")

        # Configure contract settings for completed symbols
        if completed_symbols:
            self._configure_contracts([s.split(".")[0] for s in completed_symbols])

        # Final progress update
        if progress_callback:
            await progress_callback({
                "status": JobStatus.COMPLETED.value,
                "current_symbol": None,
                "current_index": total,
                "total_symbols": total,
                "completed_symbols": completed_symbols,
                "failed_symbols": failed_symbols,
                "progress_percent": 100.0
            })

        return {
            "completed_symbols": completed_symbols,
            "failed_symbols": failed_symbols,
            "total_bars": sum(1 for _ in completed_symbols)  # Simplified
        }

    def _download_symbol(
        self,
        symbol: str,
        exchange: Exchange,
        start_date: datetime,
        end_date: datetime,
        interval: Interval
    ) -> list:
        """Synchronous download for a single symbol"""
        req = HistoryRequest(
            symbol=symbol,
            exchange=exchange,
            start=start_date,
            end=end_date,
            interval=interval
        )
        return self.datafeed.query_bar_history(req, output=lambda x: None)

    def _configure_contracts(self, symbols: list[str]) -> None:
        """Configure default A-share contract settings"""
        for symbol in symbols:
            exchange = self.get_exchange(symbol)
            vt_symbol = f"{symbol}.{exchange.value}"

            self.lab.add_contract_setting(
                vt_symbol=vt_symbol,
                long_rate=0.0003,   # 0.03% commission
                short_rate=0.0013,  # 0.13% (with stamp duty)
                size=1,
                pricetick=0.01
            )

    def configure_contracts(
        self,
        symbols: list[str],
        long_rate: float = 0.0003,
        short_rate: float = 0.0013,
        size: float = 1.0,
        pricetick: float = 0.01
    ) -> None:
        """
        Configure contract settings for symbols.

        Args:
            symbols: List of stock symbols
            long_rate: Long commission rate
            short_rate: Short commission rate (includes stamp duty)
            size: Contract size
            pricetick: Price tick
        """
        for symbol in symbols:
            exchange = self.get_exchange(symbol)
            vt_symbol = f"{symbol}.{exchange.value}"

            self.lab.add_contract_setting(
                vt_symbol=vt_symbol,
                long_rate=long_rate,
                short_rate=short_rate,
                size=size,
                pricetick=pricetick
            )

        logger.info(f"Configured contracts for {len(symbols)} symbols")

    def get_contract_settings(self) -> dict:
        """Get all contract settings"""
        return self.lab.load_contract_setttings()

    def get_local_symbols(self, interval: str = "daily") -> list[LocalSymbolInfo]:
        """
        Get list of symbols with local data.

        Args:
            interval: Data interval ('daily' or 'minute')

        Returns:
            List of LocalSymbolInfo objects
        """
        if interval == "daily":
            data_path = self.lab.daily_path
        else:
            data_path = self.lab.minute_path

        symbols = []

        if not data_path.exists():
            return symbols

        for file_path in data_path.glob("*.parquet"):
            try:
                # Parse symbol from filename
                vt_symbol = file_path.stem
                parts = vt_symbol.split(".")
                symbol = parts[0]
                exchange = parts[1] if len(parts) > 1 else "UNKNOWN"

                # Read parquet metadata
                df = pl.read_parquet(file_path)
                bar_count = len(df)

                start_date = None
                end_date = None
                if bar_count > 0 and "datetime" in df.columns:
                    dates = df["datetime"].sort()
                    start_date = str(dates[0])[:10]
                    end_date = str(dates[-1])[:10]

                # Get file size
                file_size_kb = file_path.stat().st_size / 1024

                symbols.append(LocalSymbolInfo(
                    symbol=symbol,
                    exchange=exchange,
                    vt_symbol=vt_symbol,
                    interval=interval,
                    bar_count=bar_count,
                    start_date=start_date,
                    end_date=end_date,
                    file_size_kb=round(file_size_kb, 2)
                ))

            except Exception as e:
                logger.warning(f"Failed to read {file_path}: {e}")

        # Sort by symbol
        symbols.sort(key=lambda x: x.symbol)
        return symbols

    def delete_symbol_data(self, symbol: str, interval: str = "daily") -> bool:
        """
        Delete local data for a symbol.

        Args:
            symbol: Stock symbol (can be vt_symbol format)
            interval: Data interval

        Returns:
            True if deleted successfully
        """
        if interval == "daily":
            data_path = self.lab.daily_path
        else:
            data_path = self.lab.minute_path

        # Handle both symbol and vt_symbol formats
        if "." not in symbol:
            exchange = self.get_exchange(symbol)
            vt_symbol = f"{symbol}.{exchange.value}"
        else:
            vt_symbol = symbol

        file_path = data_path / f"{vt_symbol}.parquet"

        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted data file: {file_path}")
            return True

        return False

    def check_data_exists(
        self,
        symbols: list[str],
        interval: str = "daily"
    ) -> dict[str, bool]:
        """
        Check if data exists for symbols.

        Args:
            symbols: List of symbols to check
            interval: Data interval

        Returns:
            Dict mapping vt_symbol to existence status
        """
        if interval == "daily":
            data_path = self.lab.daily_path
        else:
            data_path = self.lab.minute_path

        result = {}
        for symbol in symbols:
            if "." not in symbol:
                exchange = self.get_exchange(symbol)
                vt_symbol = f"{symbol}.{exchange.value}"
            else:
                vt_symbol = symbol

            file_path = data_path / f"{vt_symbol}.parquet"
            result[vt_symbol] = file_path.exists()

        return result
