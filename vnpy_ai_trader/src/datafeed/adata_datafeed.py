"""
AData Free Data Source Adapter.
AData免费数据源适配器

Implements vnpy BaseDatafeed interface using AData open-source library.
AData GitHub: https://github.com/1nchaos/adata
"""

from datetime import datetime
from collections.abc import Callable
from pathlib import Path
import pickle

from vnpy.trader.datafeed import BaseDatafeed
from vnpy.trader.object import BarData, TickData, HistoryRequest
from vnpy.trader.constant import Exchange, Interval

from ..utils.logger import get_logger

logger = get_logger("adata_datafeed")

# Try to import adata library
try:
    import adata
    ADATA_AVAILABLE = True
except ImportError:
    ADATA_AVAILABLE = False
    logger.warning("AData library not installed. Run: pip install adata")


class AdataDatafeed(BaseDatafeed):
    """
    AData datafeed implementation for A-share stock data.
    Provides free historical bar data using AData library.

    Features:
    - Free A-share stock data
    - Daily and intraday bar data
    - Local data caching
    """

    def __init__(self, cache_dir: str | Path | None = None):
        """
        Initialize AData datafeed.

        Args:
            cache_dir: Directory for caching data locally
        """
        self.inited: bool = False
        self.cache_enabled: bool = True

        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path("./data/cache")

        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def init(self, output: Callable = print) -> bool:
        """
        Initialize datafeed connection.

        Args:
            output: Output function for logging

        Returns:
            True if initialization successful
        """
        if not ADATA_AVAILABLE:
            output("AData library not installed. Run: pip install adata")
            return False

        self.inited = True
        output("AData datafeed initialized successfully")
        logger.info("AData datafeed initialized")
        return True

    def query_bar_history(
        self,
        req: HistoryRequest,
        output: Callable = print
    ) -> list[BarData]:
        """
        Query historical bar data.

        Args:
            req: HistoryRequest containing symbol, exchange, interval, start, end
            output: Output function for logging

        Returns:
            List of BarData objects
        """
        if not self.inited:
            if not self.init(output):
                return []

        # Check cache first
        cache_key = self._get_cache_key(req)
        cached_data = self._load_from_cache(cache_key)
        if cached_data is not None:
            output(f"Loaded {len(cached_data)} bars from cache for {req.symbol}")
            return cached_data

        # Convert symbol format
        adata_symbol = self._convert_symbol(req.symbol, req.exchange)

        # Determine k_type based on interval
        k_type = self._convert_interval(req.interval)

        try:
            # Query data from AData
            df = adata.stock.market.get_market(
                stock_code=adata_symbol,
                start_date=req.start.strftime("%Y-%m-%d"),
                end_date=req.end.strftime("%Y-%m-%d") if req.end else None,
                k_type=k_type
            )

            if df is None or len(df) == 0:
                output(f"No data returned for {req.symbol}")
                return []

            # Convert DataFrame to BarData list
            bars: list[BarData] = []

            for _, row in df.iterrows():
                try:
                    bar = BarData(
                        symbol=req.symbol,
                        exchange=req.exchange,
                        datetime=self._parse_datetime(row.get("trade_date") or row.get("date")),
                        interval=req.interval,
                        open_price=float(row.get("open", 0)),
                        high_price=float(row.get("high", 0)),
                        low_price=float(row.get("low", 0)),
                        close_price=float(row.get("close", 0)),
                        volume=float(row.get("volume", 0)),
                        turnover=float(row.get("amount", 0) or row.get("turnover", 0)),
                        open_interest=0,
                        gateway_name="ADATA"
                    )
                    bars.append(bar)
                except Exception as e:
                    logger.debug(f"Failed to parse row: {e}")
                    continue

            # Cache the data
            if bars and self.cache_enabled:
                self._save_to_cache(cache_key, bars)

            output(f"Downloaded {len(bars)} bars for {req.symbol}")
            return bars

        except Exception as e:
            output(f"Failed to query data: {str(e)}")
            logger.error(f"AData query failed: {e}")
            return []

    def query_tick_history(
        self,
        req: HistoryRequest,
        output: Callable = print
    ) -> list[TickData]:
        """
        Query historical tick data.
        Note: AData free version may not fully support tick data.

        Args:
            req: HistoryRequest
            output: Output function

        Returns:
            List of TickData (currently returns empty list)
        """
        output("Tick data query not fully supported by free AData")
        logger.warning("Tick data not available in AData free version")
        return []

    def _convert_symbol(self, symbol: str, exchange: Exchange) -> str:
        """
        Convert vnpy symbol format to AData format.

        Args:
            symbol: vnpy symbol (e.g., "000001" or "000001.SZSE")
            exchange: Exchange enum

        Returns:
            AData symbol format (6-digit code)
        """
        # Extract pure stock code
        if "." in symbol:
            return symbol.split(".")[0]
        return symbol

    def _convert_interval(self, interval: Interval | None) -> int:
        """
        Convert vnpy Interval to AData k_type.

        Args:
            interval: vnpy Interval enum

        Returns:
            AData k_type integer
        """
        if interval is None:
            return 101  # Default to daily

        interval_map = {
            Interval.MINUTE: 1,      # 1 minute
            Interval.HOUR: 60,       # 60 minutes
            Interval.DAILY: 101,     # Daily
            Interval.WEEKLY: 102,    # Weekly
        }
        return interval_map.get(interval, 101)

    def _parse_datetime(self, date_value) -> datetime:
        """
        Parse date value to datetime object.

        Args:
            date_value: Date string or datetime object

        Returns:
            datetime object
        """
        if isinstance(date_value, datetime):
            return date_value

        date_str = str(date_value)

        # Try different date formats
        formats = [
            "%Y-%m-%d",
            "%Y%m%d",
            "%Y-%m-%d %H:%M:%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Default to today if parsing fails
        logger.warning(f"Failed to parse date: {date_str}")
        return datetime.now()

    def _get_cache_key(self, req: HistoryRequest) -> str:
        """Generate cache key for a request."""
        interval_str = req.interval.value if req.interval else "daily"
        start_str = req.start.strftime("%Y%m%d")
        end_str = req.end.strftime("%Y%m%d") if req.end else "now"
        return f"{req.symbol}_{req.exchange.value}_{interval_str}_{start_str}_{end_str}"

    def _load_from_cache(self, cache_key: str) -> list[BarData] | None:
        """Load data from local cache."""
        cache_file = self.cache_dir / f"{cache_key}.pkl"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logger.debug(f"Cache load failed: {e}")
            return None

    def _save_to_cache(self, cache_key: str, data: list[BarData]) -> None:
        """Save data to local cache."""
        cache_file = self.cache_dir / f"{cache_key}.pkl"

        try:
            with open(cache_file, "wb") as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.debug(f"Cache save failed: {e}")


# Alias for vnpy module discovery (vnpy_{name} convention)
Datafeed = AdataDatafeed
