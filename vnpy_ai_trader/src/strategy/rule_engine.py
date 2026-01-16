"""
JSON Rule Execution Engine.
JSON规则执行引擎

Evaluates strategy rules defined in JSON configuration against market data.
"""

from typing import Any
from dataclasses import dataclass
from enum import Enum

import polars as pl

from ..utils.logger import get_logger

logger = get_logger("rule_engine")


class Operator(Enum):
    """Comparison operators for rule conditions."""
    GT = ">"
    LT = "<"
    GE = ">="
    LE = "<="
    EQ = "=="
    NE = "!="
    CROSS_ABOVE = "cross_above"
    CROSS_BELOW = "cross_below"


@dataclass
class RuleCondition:
    """Represents a single rule condition."""
    indicator: str
    params: dict[str, Any]
    operator: str
    value: float | str
    logic: str = "and"


class RuleEngine:
    """
    Evaluates trading rules defined in JSON strategy configuration.
    Generates trading signals based on technical indicators and conditions.
    """

    def __init__(self, strategy_config: dict[str, Any]):
        """
        Initialize rule engine with strategy configuration.

        Args:
            strategy_config: Parsed strategy JSON configuration
        """
        self.config = strategy_config
        self.entry_rules = self._parse_rules(strategy_config.get("entry_rules", {}))
        self.exit_rules = self._parse_rules(strategy_config.get("exit_rules", {}))

        logger.info(f"Rule engine initialized with {len(self.entry_rules)} entry rules")

    def _parse_rules(self, rules_config: dict) -> list[RuleCondition]:
        """Parse rule conditions from config dict."""
        conditions = rules_config.get("conditions", [])
        parsed = []

        for cond in conditions:
            try:
                rule = RuleCondition(
                    indicator=cond.get("indicator", ""),
                    params=cond.get("params", {}),
                    operator=cond.get("operator", ""),
                    value=cond.get("value", 0),
                    logic=cond.get("logic", "and")
                )
                parsed.append(rule)
            except Exception as e:
                logger.warning(f"Failed to parse condition: {e}")

        return parsed

    def evaluate(
        self,
        signals_df: pl.DataFrame,
        indicator_data: dict[str, pl.DataFrame] | None = None
    ) -> pl.DataFrame:
        """
        Evaluate entry rules and adjust signal scores.

        Args:
            signals_df: DataFrame with columns [vt_symbol, signal]
            indicator_data: Dict mapping indicators to DataFrames

        Returns:
            DataFrame with adjusted signals based on rules
        """
        if signals_df is None or len(signals_df) == 0:
            return signals_df

        # Start with original signals
        result_df = signals_df.clone()

        # Apply each entry rule as a filter/adjustment
        for rule in self.entry_rules:
            try:
                result_df = self._apply_rule(result_df, rule, indicator_data)
            except Exception as e:
                logger.warning(f"Failed to apply rule {rule.indicator}: {e}")

        return result_df

    def _apply_rule(
        self,
        df: pl.DataFrame,
        rule: RuleCondition,
        indicator_data: dict[str, pl.DataFrame] | None
    ) -> pl.DataFrame:
        """
        Apply a single rule to the signals DataFrame.

        Args:
            df: Current signals DataFrame
            rule: Rule condition to apply
            indicator_data: Indicator data for evaluation

        Returns:
            Modified DataFrame
        """
        # If we have indicator data, use it for evaluation
        if indicator_data and rule.indicator in indicator_data:
            ind_df = indicator_data[rule.indicator]
            # Merge indicator values with signals
            # This is a simplified implementation - real version would need
            # proper indicator calculation and joining
            pass

        # For now, just pass through - actual indicator evaluation
        # would be implemented based on available data
        return df

    def check_entry_signal(
        self,
        symbol: str,
        bar_data: dict[str, Any],
        indicator_values: dict[str, float]
    ) -> tuple[bool, float]:
        """
        Check if entry conditions are met for a symbol.

        Args:
            symbol: Stock symbol
            bar_data: Current bar data
            indicator_values: Pre-calculated indicator values

        Returns:
            Tuple of (should_enter, signal_strength)
        """
        if not self.entry_rules:
            return False, 0.0

        # Evaluate each condition
        conditions_met = []
        logic_operators = []

        for rule in self.entry_rules:
            result = self._evaluate_condition(rule, indicator_values)
            conditions_met.append(result)
            logic_operators.append(rule.logic)

        # Combine results based on logic operators
        final_result = conditions_met[0] if conditions_met else False

        for i in range(1, len(conditions_met)):
            if logic_operators[i - 1] == "and":
                final_result = final_result and conditions_met[i]
            else:  # "or"
                final_result = final_result or conditions_met[i]

        # Calculate signal strength based on how many conditions are met
        strength = sum(conditions_met) / len(conditions_met) if conditions_met else 0.0

        return final_result, strength

    def check_exit_signal(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        holding_days: int,
        indicator_values: dict[str, float] | None = None
    ) -> tuple[bool, str]:
        """
        Check if exit conditions are met.

        Args:
            symbol: Stock symbol
            entry_price: Entry price
            current_price: Current price
            holding_days: Number of days held
            indicator_values: Pre-calculated indicator values

        Returns:
            Tuple of (should_exit, exit_reason)
        """
        exit_config = self.config.get("exit_rules", {})

        # Check take profit
        take_profit = exit_config.get("take_profit")
        if take_profit and entry_price > 0:
            pnl_pct = (current_price - entry_price) / entry_price
            if pnl_pct >= take_profit:
                return True, f"take_profit ({pnl_pct:.2%})"

        # Check stop loss
        stop_loss = exit_config.get("stop_loss")
        if stop_loss and entry_price > 0:
            pnl_pct = (current_price - entry_price) / entry_price
            if pnl_pct <= -stop_loss:
                return True, f"stop_loss ({pnl_pct:.2%})"

        # Check holding days
        max_holding_days = exit_config.get("holding_days")
        if max_holding_days and holding_days >= max_holding_days:
            return True, f"max_holding_days ({holding_days})"

        # Check trailing stop
        trailing_stop = exit_config.get("trailing_stop")
        if trailing_stop:
            # Would need to track highest price since entry
            pass

        # Check additional conditions
        for rule in self.exit_rules:
            if indicator_values:
                result = self._evaluate_condition(rule, indicator_values)
                if result:
                    return True, f"condition_{rule.indicator}"

        return False, ""

    def _evaluate_condition(
        self,
        rule: RuleCondition,
        indicator_values: dict[str, float]
    ) -> bool:
        """
        Evaluate a single condition against indicator values.

        Args:
            rule: Rule condition to evaluate
            indicator_values: Dict of indicator name to value

        Returns:
            True if condition is met
        """
        if rule.indicator not in indicator_values:
            logger.debug(f"Indicator {rule.indicator} not available")
            return False

        current_value = indicator_values[rule.indicator]
        compare_value = rule.value

        # If compare_value is a string, it might reference another indicator
        if isinstance(compare_value, str) and compare_value in indicator_values:
            compare_value = indicator_values[compare_value]

        try:
            compare_value = float(compare_value)
        except (ValueError, TypeError):
            logger.warning(f"Invalid compare value: {compare_value}")
            return False

        # Evaluate based on operator
        op = rule.operator
        if op == ">" or op == "gt":
            return current_value > compare_value
        elif op == "<" or op == "lt":
            return current_value < compare_value
        elif op == ">=" or op == "ge":
            return current_value >= compare_value
        elif op == "<=" or op == "le":
            return current_value <= compare_value
        elif op == "==" or op == "eq":
            return abs(current_value - compare_value) < 0.0001
        elif op == "!=" or op == "ne":
            return abs(current_value - compare_value) >= 0.0001
        elif op == "cross_above" or op == "cross_below":
            # Would need previous values for crossover detection
            logger.debug(f"Crossover detection requires historical data")
            return False
        else:
            logger.warning(f"Unknown operator: {op}")
            return False
