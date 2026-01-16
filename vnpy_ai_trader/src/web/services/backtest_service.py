"""
Backtesting Service.
回测服务

Handles backtest execution, result storage, and equity curve generation.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Coroutine, Any
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import polars as pl

from vnpy.trader.constant import Interval, Exchange
from vnpy.alpha.lab import AlphaLab
from vnpy.alpha.strategy.backtesting import BacktestingEngine

from ...ai_core.deepseek_client import DeepSeekClient
from ...ai_core.strategy_parser import StrategyParser
from ...strategy.ai_alpha_strategy import AIAlphaStrategy
from ...utils.logger import get_logger
from ..models import (
    JobStatus,
    BacktestStatistics,
    BacktestResult,
    EquityCurveData
)

logger = get_logger("backtest_service")


class BacktestService:
    """
    Service for backtest operations.
    回测服务类

    Handles:
    - Running backtests asynchronously
    - Strategy parsing (NL or JSON)
    - Result calculation and storage
    - Equity curve generation
    """

    def __init__(
        self,
        data_dir: str = "./data/lab",
        results_dir: str = "./data/backtest_results"
    ):
        """
        Initialize backtest service.

        Args:
            data_dir: AlphaLab data directory
            results_dir: Directory for saving results
        """
        self.data_dir = Path(data_dir)
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        self._executor = ThreadPoolExecutor(max_workers=2)

    @staticmethod
    def get_exchange(symbol: str) -> Exchange:
        """Determine exchange from symbol"""
        if symbol.startswith(("6", "5", "9")):
            return Exchange.SSE
        return Exchange.SZSE

    async def parse_strategy(
        self,
        description: str,
        api_key: str | None = None
    ) -> dict:
        """
        Parse natural language strategy to JSON config.

        Args:
            description: Natural language strategy description
            api_key: DeepSeek API key (uses env var if not provided)

        Returns:
            Strategy configuration dict
        """
        api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DeepSeek API key required")

        client = DeepSeekClient(api_key=api_key)
        parser = StrategyParser(deepseek_client=client)

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        config, errors = await loop.run_in_executor(
            self._executor,
            parser.parse_and_validate,
            description
        )

        if errors:
            raise ValueError(f"Strategy parsing failed: {errors}")

        return config

    async def run_backtest(
        self,
        strategy_config: dict,
        symbols: list[str],
        start_date: datetime,
        end_date: datetime,
        capital: int = 1_000_000,
        interval: Interval = Interval.DAILY,
        progress_callback: Callable[[dict], Coroutine] | None = None
    ) -> dict:
        """
        Run backtest with progress updates.

        Args:
            strategy_config: Strategy configuration
            symbols: List of symbols to trade
            start_date: Start date
            end_date: End date
            capital: Initial capital
            interval: Data interval
            progress_callback: Async callback for progress

        Returns:
            Dict with statistics and daily results
        """
        loop = asyncio.get_event_loop()

        # Create sync progress callback wrapper
        def sync_progress(progress: dict):
            if progress_callback:
                asyncio.run_coroutine_threadsafe(
                    progress_callback(progress),
                    loop
                )

        # Run backtest in thread pool
        result = await loop.run_in_executor(
            self._executor,
            self._run_backtest_sync,
            strategy_config,
            symbols,
            start_date,
            end_date,
            capital,
            interval,
            sync_progress
        )

        return result

    def _run_backtest_sync(
        self,
        strategy_config: dict,
        symbols: list[str],
        start_date: datetime,
        end_date: datetime,
        capital: int,
        interval: Interval,
        progress_callback: Callable[[dict], None] | None
    ) -> dict:
        """Synchronous backtest execution"""

        # Phase 1: Initialize
        if progress_callback:
            progress_callback({
                "status": JobStatus.RUNNING.value,
                "phase": "initializing",
                "progress_percent": 5.0,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d")
            })

        # Initialize AlphaLab
        lab = AlphaLab(str(self.data_dir))
        engine = BacktestingEngine(lab)

        # Convert symbols to vt_symbol format
        vt_symbols = []
        for s in symbols:
            exchange = self.get_exchange(s)
            vt_symbols.append(f"{s}.{exchange.value}")

        # Set parameters
        engine.set_parameters(
            vt_symbols=vt_symbols,
            interval=interval,
            start=start_date,
            end=end_date,
            capital=capital,
            risk_free=0.03,
            annual_days=240
        )

        # Phase 2: Generate signals
        if progress_callback:
            progress_callback({
                "status": JobStatus.RUNNING.value,
                "phase": "generating_signals",
                "progress_percent": 15.0
            })

        # Generate signal DataFrame
        signal_df = self._generate_signals(vt_symbols, start_date, end_date)

        # Add strategy
        setting = {
            "strategy_config": strategy_config,
            "ai_enabled": strategy_config.get("entry_rules", {}).get("ai_enhanced", False),
            "top_k": strategy_config.get("risk_control", {}).get("max_positions", 30)
        }

        engine.add_strategy(
            strategy_class=AIAlphaStrategy,
            setting=setting,
            signal_df=signal_df
        )

        # Phase 3: Load data
        if progress_callback:
            progress_callback({
                "status": JobStatus.RUNNING.value,
                "phase": "loading_data",
                "progress_percent": 25.0
            })

        engine.load_data()

        # Check if data loaded
        if not engine.history_data:
            raise ValueError("No historical data available. Run data preparation first.")

        # Phase 4: Run backtest
        if progress_callback:
            progress_callback({
                "status": JobStatus.RUNNING.value,
                "phase": "running",
                "progress_percent": 40.0
            })

        engine.run_backtesting()

        # Phase 5: Calculate results
        if progress_callback:
            progress_callback({
                "status": JobStatus.RUNNING.value,
                "phase": "calculating",
                "progress_percent": 85.0
            })

        result_df = engine.calculate_result()

        if result_df is None:
            return {
                "success": False,
                "error": "No trades executed during backtest period",
                "statistics": None,
                "daily_df": None
            }

        statistics = engine.calculate_statistics()

        # Extract daily data for equity curve
        daily_data = None
        if hasattr(engine, 'daily_df') and engine.daily_df is not None:
            df = engine.daily_df
            daily_data = {
                "dates": df["date"].cast(pl.Utf8).to_list(),
                "balance": df["balance"].to_list(),
                "drawdown": df["drawdown"].to_list() if "drawdown" in df.columns else [],
                "daily_pnl": df["net_pnl"].to_list(),
                "daily_return": df["return"].to_list() if "return" in df.columns else []
            }

        if progress_callback:
            progress_callback({
                "status": JobStatus.COMPLETED.value,
                "phase": "completed",
                "progress_percent": 100.0
            })

        return {
            "success": True,
            "statistics": statistics,
            "daily_data": daily_data,
            "strategy_name": strategy_config.get("strategy_name", "unnamed")
        }

    def _generate_signals(
        self,
        vt_symbols: list[str],
        start_date: datetime,
        end_date: datetime
    ) -> pl.DataFrame:
        """Generate signal DataFrame for backtest"""
        # Generate trading days
        trading_days = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                trading_days.append(current)
            current += timedelta(days=1)

        # Generate signals
        np.random.seed(42)
        signal_data = []
        for dt in trading_days:
            for vt_symbol in vt_symbols:
                signal_data.append({
                    "datetime": dt,
                    "vt_symbol": vt_symbol,
                    "signal": np.random.uniform(0.3, 0.9)
                })

        return pl.DataFrame(signal_data)

    def save_result(
        self,
        job_id: str,
        result: dict,
        strategy_config: dict,
        symbols: list[str]
    ) -> None:
        """
        Save backtest result to disk.

        Args:
            job_id: Job ID
            result: Backtest result dict
            strategy_config: Strategy configuration used
            symbols: Symbols traded
        """
        file_path = self.results_dir / f"{job_id}.json"

        save_data = {
            "job_id": job_id,
            "created_at": datetime.now().isoformat(),
            "strategy_config": strategy_config,
            "symbols": symbols,
            "success": result.get("success", False),
            "error": result.get("error"),
            "strategy_name": result.get("strategy_name", "unnamed"),
            "statistics": result.get("statistics"),
            "daily_data": result.get("daily_data")
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"Saved backtest result: {file_path}")

    def load_result(self, job_id: str) -> dict | None:
        """Load backtest result from disk"""
        file_path = self.results_dir / f"{job_id}.json"

        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_results(self) -> list[BacktestResult]:
        """List all saved backtest results"""
        results = []

        for file_path in self.results_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                stats = None
                if data.get("statistics"):
                    stats = BacktestStatistics(**data["statistics"])

                results.append(BacktestResult(
                    job_id=data["job_id"],
                    status=JobStatus.COMPLETED if data.get("success") else JobStatus.FAILED,
                    strategy_name=data.get("strategy_name", "unnamed"),
                    strategy_config=data.get("strategy_config"),
                    symbols=data.get("symbols", []),
                    statistics=stats,
                    created_at=data.get("created_at", ""),
                    completed_at=data.get("created_at"),
                    error=data.get("error")
                ))

            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")

        # Sort by created_at descending
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results

    def delete_result(self, job_id: str) -> bool:
        """Delete a saved backtest result"""
        file_path = self.results_dir / f"{job_id}.json"

        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted backtest result: {job_id}")
            return True

        return False

    def get_equity_curve(self, job_id: str) -> EquityCurveData | None:
        """Get equity curve data for a backtest result"""
        result = self.load_result(job_id)

        if not result or not result.get("daily_data"):
            return None

        daily = result["daily_data"]

        return EquityCurveData(
            dates=daily.get("dates", []),
            balance=daily.get("balance", []),
            drawdown=daily.get("drawdown", []),
            daily_pnl=daily.get("daily_pnl", []),
            daily_return=daily.get("daily_return", [])
        )
