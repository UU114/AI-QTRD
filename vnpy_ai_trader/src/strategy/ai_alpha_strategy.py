"""
AI-Enhanced Alpha Strategy.
AI增强型Alpha策略

Combines rule-based signals with real-time LLM analysis for A-share trading.
"""

from collections import defaultdict
from typing import Any
from datetime import datetime

import polars as pl

from vnpy.trader.object import BarData, TradeData
from vnpy.trader.constant import Direction
from vnpy.alpha.strategy.template import AlphaStrategy

from ..ai_core.deepseek_client import DeepSeekClient
from ..ai_core.news_analyzer import NewsAnalyzer
from ..ai_core.strategy_parser import StrategyParser
from .rule_engine import RuleEngine
from .risk_manager import RiskManager
from ..utils.logger import get_logger

logger = get_logger("ai_alpha_strategy")


class AIAlphaStrategy(AlphaStrategy):
    """
    AI-enhanced Alpha strategy that combines:
    1. Rule-based signals from JSON configuration (parsed from natural language)
    2. Real-time LLM analysis for fuzzy judgments (news, sentiment)

    Parameters defined in strategy_config JSON will be used for trading decisions.
    """

    # Strategy parameters (can be overridden via setting dict)
    strategy_config: dict = {}          # Parsed strategy configuration
    ai_enabled: bool = True             # Enable AI-enhanced judgment
    top_k: int = 30                     # Maximum positions
    min_holding_days: int = 1           # Minimum holding days
    cash_ratio: float = 0.95            # Cash utilization ratio
    price_add: float = 0.01             # Price adjustment for execution

    # AI configuration
    deepseek_api_key: str = ""          # DeepSeek API key
    rule_weight: float = 0.7            # Weight for rule-based signals
    ai_weight: float = 0.3              # Weight for AI signals
    ai_call_interval: int = 5           # Minimum bars between AI calls

    def __init__(self, *args, **kwargs):
        """Initialize AI Alpha Strategy."""
        super().__init__(*args, **kwargs)

        # AI components (initialized in on_init)
        self.deepseek_client: DeepSeekClient | None = None
        self.news_analyzer: NewsAnalyzer | None = None
        self.rule_engine: RuleEngine | None = None
        self.risk_manager: RiskManager | None = None

        # State tracking
        self.holding_days: dict[str, int] = defaultdict(int)
        self.entry_prices: dict[str, float] = {}
        self.bars_since_ai_call: int = 0

        # Performance tracking
        self.trade_count: int = 0
        self.win_count: int = 0

    def on_init(self) -> None:
        """Strategy initialization callback."""
        # Initialize holding days tracker
        self.holding_days = defaultdict(int)
        self.entry_prices = {}

        # Load strategy config if not already set
        if not self.strategy_config:
            self.write_log("Warning: No strategy configuration provided")
            self.strategy_config = self._get_default_config()

        # Initialize rule engine with strategy configuration
        self.rule_engine = RuleEngine(self.strategy_config)

        # Initialize risk manager
        risk_config = self.strategy_config.get("risk_control", {})
        self.risk_manager = RiskManager(risk_config)

        # Update parameters from config
        self._apply_config_params()

        # Initialize AI components if enabled
        if self.ai_enabled:
            self._init_ai_components()

        self.write_log(f"AI Alpha Strategy initialized: {self.strategy_config.get('strategy_name', 'unnamed')}")
        self.write_log(f"AI enabled: {self.ai_enabled}, Max positions: {self.top_k}")

    def _apply_config_params(self) -> None:
        """Apply parameters from strategy configuration."""
        risk_config = self.strategy_config.get("risk_control", {})

        if "max_positions" in risk_config:
            self.top_k = risk_config["max_positions"]

        if "position_size" in risk_config:
            self.cash_ratio = 1.0 - risk_config["position_size"]

        # Entry rules AI settings
        entry_config = self.strategy_config.get("entry_rules", {})
        self.ai_enabled = entry_config.get("ai_enhanced", False)

        if "ai_weight" in entry_config:
            self.ai_weight = entry_config["ai_weight"]
            self.rule_weight = 1.0 - self.ai_weight

    def _init_ai_components(self) -> None:
        """Initialize AI-related components."""
        api_key = self.deepseek_api_key or self.strategy_config.get("deepseek_api_key", "")

        if api_key:
            try:
                self.deepseek_client = DeepSeekClient(api_key=api_key)
                self.news_analyzer = NewsAnalyzer(deepseek_client=self.deepseek_client)
                self.write_log("AI components initialized successfully")
            except Exception as e:
                self.write_log(f"Failed to initialize AI components: {e}")
                self.ai_enabled = False
        else:
            self.write_log("DeepSeek API key not provided, AI features disabled")
            self.ai_enabled = False

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K-line slice callback - main strategy logic.

        Args:
            bars: Dict mapping vt_symbol to BarData
        """
        if not bars:
            return

        # Update holding days for existing positions
        for vt_symbol, pos in self.pos_data.items():
            if pos != 0:
                self.holding_days[vt_symbol] += 1

        # Step 1: Get rule-based signals
        rule_signals = self._get_rule_signals()

        # Step 2: Get AI-enhanced signals if enabled
        if self.ai_enabled and self._should_call_ai():
            ai_signals = self._get_ai_signals(bars)
            combined_signals = self._merge_signals(rule_signals, ai_signals)
            self.bars_since_ai_call = 0
        else:
            combined_signals = rule_signals
            self.bars_since_ai_call += 1

        # Step 3: Apply risk management filters
        if self.risk_manager:
            portfolio_value = self.get_portfolio_value()
            filtered_signals = self.risk_manager.apply_filters(
                combined_signals,
                dict(self.pos_data),
                portfolio_value
            )
        else:
            filtered_signals = combined_signals

        # Step 4: Generate trading decisions
        self._execute_strategy(bars, filtered_signals)

    def _get_rule_signals(self) -> pl.DataFrame:
        """
        Get signals from rule-based engine.

        Returns:
            DataFrame with columns [vt_symbol, signal]
        """
        # Get model prediction signals (from parent AlphaStrategy)
        try:
            model_signals: pl.DataFrame = self.get_signal()
        except Exception:
            # If no signal available, create empty DataFrame
            model_signals = pl.DataFrame({
                "vt_symbol": [],
                "signal": []
            })

        # Apply rule engine conditions if available
        if self.rule_engine and len(model_signals) > 0:
            return self.rule_engine.evaluate(model_signals)

        return model_signals

    def _get_ai_signals(self, bars: dict[str, BarData]) -> pl.DataFrame:
        """
        Get AI-enhanced signals from news analysis.

        Args:
            bars: Current bar data

        Returns:
            DataFrame with columns [vt_symbol, ai_score]
        """
        if not self.news_analyzer:
            return pl.DataFrame({"vt_symbol": [], "ai_score": []})

        symbols = list(bars.keys())

        try:
            # Get sentiment scores for symbols
            # Note: In production, you would fetch actual news data here
            ai_scores = self.news_analyzer.analyze_batch(symbols)

            return pl.DataFrame({
                "vt_symbol": list(ai_scores.keys()),
                "ai_score": list(ai_scores.values())
            })
        except Exception as e:
            self.write_log(f"AI signal generation failed: {e}")
            return pl.DataFrame({"vt_symbol": [], "ai_score": []})

    def _merge_signals(
        self,
        rule_signals: pl.DataFrame,
        ai_signals: pl.DataFrame
    ) -> pl.DataFrame:
        """
        Merge rule-based and AI signals with configurable weights.

        Args:
            rule_signals: Rule-based signal DataFrame
            ai_signals: AI signal DataFrame

        Returns:
            Merged DataFrame with final_signal column
        """
        if len(rule_signals) == 0:
            return rule_signals

        if len(ai_signals) == 0:
            # No AI signals, use rule signals directly
            return rule_signals.with_columns(
                pl.col("signal").alias("final_signal")
            )

        # Merge DataFrames
        merged = rule_signals.join(
            ai_signals,
            on="vt_symbol",
            how="left"
        )

        # Calculate weighted final signal
        merged = merged.with_columns(
            (
                pl.col("signal") * self.rule_weight +
                pl.col("ai_score").fill_null(0.5) * self.ai_weight
            ).alias("final_signal")
        )

        # Sort by final signal descending
        return merged.sort("final_signal", descending=True)

    def _should_call_ai(self) -> bool:
        """Check if we should make an AI API call."""
        return self.bars_since_ai_call >= self.ai_call_interval

    def _execute_strategy(
        self,
        bars: dict[str, BarData],
        signals: pl.DataFrame
    ) -> None:
        """
        Execute trading based on signals.

        Args:
            bars: Current bar data
            signals: Processed signal DataFrame
        """
        if signals is None or len(signals) == 0:
            return

        # Get current positions
        pos_symbols: list[str] = [
            vt_symbol for vt_symbol, pos in self.pos_data.items() if pos != 0
        ]

        # Determine sell list based on exit rules
        sell_symbols = self._get_sell_symbols(bars, pos_symbols)

        # Determine buy list based on signals
        buy_symbols = self._get_buy_symbols(signals, pos_symbols, sell_symbols)

        # Execute sells first
        for vt_symbol in sell_symbols:
            if vt_symbol in bars:
                self.set_target(vt_symbol, target=0)

        # Execute buys
        cash_available = self.get_cash_available()
        buy_value_per_stock = cash_available * self.cash_ratio / max(1, len(buy_symbols))

        for vt_symbol in buy_symbols:
            if vt_symbol in bars:
                bar = bars[vt_symbol]
                buy_price = bar.close_price
                buy_volume = self._calculate_volume(buy_value_per_stock, buy_price)

                if buy_volume > 0:
                    self.set_target(vt_symbol, buy_volume)
                    self.entry_prices[vt_symbol] = buy_price

        # Execute trading with price adjustment
        self.execute_trading(bars, price_add=self.price_add)

    def _get_sell_symbols(
        self,
        bars: dict[str, BarData],
        pos_symbols: list[str]
    ) -> list[str]:
        """
        Determine which positions should be sold.

        Args:
            bars: Current bar data
            pos_symbols: List of currently held symbols

        Returns:
            List of symbols to sell
        """
        sell_list = []

        for vt_symbol in pos_symbols:
            if vt_symbol not in bars:
                continue

            bar = bars[vt_symbol]
            entry_price = self.entry_prices.get(vt_symbol, bar.close_price)
            holding = self.holding_days.get(vt_symbol, 0)

            # Check exit rules
            if self.rule_engine:
                should_exit, reason = self.rule_engine.check_exit_signal(
                    symbol=vt_symbol,
                    entry_price=entry_price,
                    current_price=bar.close_price,
                    holding_days=holding
                )

                if should_exit:
                    self.write_log(f"Exit signal for {vt_symbol}: {reason}")
                    sell_list.append(vt_symbol)

        return sell_list

    def _get_buy_symbols(
        self,
        signals: pl.DataFrame,
        pos_symbols: list[str],
        sell_symbols: list[str]
    ) -> list[str]:
        """
        Determine which symbols to buy.

        Args:
            signals: Signal DataFrame
            pos_symbols: Currently held symbols
            sell_symbols: Symbols being sold

        Returns:
            List of symbols to buy
        """
        # Calculate available slots
        current_count = len(pos_symbols) - len(sell_symbols)
        available_slots = self.top_k - current_count

        if available_slots <= 0:
            return []

        # Get top signals excluding current positions
        buy_candidates = signals.filter(
            ~pl.col("vt_symbol").is_in(pos_symbols)
        )

        if "final_signal" in buy_candidates.columns:
            buy_candidates = buy_candidates.sort("final_signal", descending=True)
        elif "signal" in buy_candidates.columns:
            buy_candidates = buy_candidates.sort("signal", descending=True)

        # Take top N candidates
        top_candidates = buy_candidates.head(available_slots)

        return top_candidates["vt_symbol"].to_list()

    def _calculate_volume(self, value: float, price: float, lot_size: int = 100) -> float:
        """Calculate trading volume rounded to lot size."""
        if price <= 0:
            return 0

        shares = value / price
        volume = int(shares / lot_size) * lot_size

        return float(max(0, volume))

    def on_trade(self, trade: TradeData) -> None:
        """Trade execution callback."""
        self.trade_count += 1

        if trade.direction == Direction.SHORT:
            # Selling - check if profitable
            entry_price = self.entry_prices.pop(trade.vt_symbol, 0)
            if entry_price > 0 and trade.price > entry_price:
                self.win_count += 1

            # Clear holding days
            self.holding_days.pop(trade.vt_symbol, None)

        self.write_log(
            f"Trade: {trade.vt_symbol} {trade.direction.value} "
            f"volume={trade.volume} price={trade.price:.2f}"
        )

    def _get_default_config(self) -> dict:
        """Return default strategy configuration."""
        return {
            "strategy_name": "default_ai_strategy",
            "universe": {
                "type": "custom_list",
                "symbols": []
            },
            "entry_rules": {
                "conditions": [],
                "ai_enhanced": False
            },
            "exit_rules": {
                "take_profit": 0.10,
                "stop_loss": 0.05,
                "holding_days": 20
            },
            "risk_control": {
                "max_positions": 30,
                "position_size": 0.03
            }
        }

    @classmethod
    def from_natural_language(
        cls,
        description: str,
        deepseek_api_key: str,
        **kwargs
    ) -> "AIAlphaStrategy":
        """
        Create strategy instance from natural language description.

        Args:
            description: Natural language strategy description
            deepseek_api_key: DeepSeek API key
            **kwargs: Additional arguments for strategy

        Returns:
            Configured AIAlphaStrategy instance
        """
        # Parse natural language to config
        client = DeepSeekClient(api_key=deepseek_api_key)
        parser = StrategyParser(deepseek_client=client)

        config, errors = parser.parse_and_validate(description)

        if errors:
            raise ValueError(f"Strategy parsing failed: {errors}")

        # Create strategy with parsed config
        kwargs["strategy_config"] = config
        kwargs["deepseek_api_key"] = deepseek_api_key

        return cls(**kwargs)

    def get_strategy_info(self) -> dict[str, Any]:
        """Get strategy information and statistics."""
        win_rate = self.win_count / self.trade_count if self.trade_count > 0 else 0

        return {
            "name": self.strategy_config.get("strategy_name", "unnamed"),
            "description": self.strategy_config.get("description", ""),
            "ai_enabled": self.ai_enabled,
            "position_count": len([p for p in self.pos_data.values() if p != 0]),
            "max_positions": self.top_k,
            "trade_count": self.trade_count,
            "win_rate": f"{win_rate:.1%}",
            "cash_available": self.get_cash_available(),
            "portfolio_value": self.get_portfolio_value()
        }
