"""
Risk Management Module.
风险管理模块

Implements position sizing, drawdown control, and risk limits.
"""

from typing import Any
from dataclasses import dataclass
from collections import defaultdict

import polars as pl

from ..utils.logger import get_logger

logger = get_logger("risk_manager")


@dataclass
class RiskLimits:
    """Risk control parameters."""
    max_positions: int = 30
    position_size: float = 0.03
    max_drawdown: float = 0.15
    daily_loss_limit: float = 0.05
    sector_concentration: float = 0.3


class RiskManager:
    """
    Manages trading risk including position sizing and exposure limits.
    """

    def __init__(self, risk_config: dict[str, Any] | None = None):
        """
        Initialize risk manager.

        Args:
            risk_config: Risk control configuration from strategy JSON
        """
        config = risk_config or {}

        self.limits = RiskLimits(
            max_positions=config.get("max_positions", 30),
            position_size=config.get("position_size", 0.03),
            max_drawdown=config.get("max_drawdown", 0.15),
            daily_loss_limit=config.get("daily_loss_limit", 0.05),
            sector_concentration=config.get("sector_concentration", 0.3)
        )

        # Track current state
        self.peak_portfolio_value: float = 0
        self.daily_start_value: float = 0
        self.current_drawdown: float = 0
        self.daily_pnl: float = 0

        # Sector tracking
        self.sector_exposure: dict[str, float] = defaultdict(float)

        logger.info(f"Risk manager initialized: max_positions={self.limits.max_positions}, "
                   f"position_size={self.limits.position_size:.1%}")

    def apply_filters(
        self,
        signals: pl.DataFrame,
        current_positions: dict[str, float],
        portfolio_value: float
    ) -> pl.DataFrame:
        """
        Apply risk filters to trading signals.

        Args:
            signals: DataFrame with columns [vt_symbol, signal, ...]
            current_positions: Dict of symbol to position size
            portfolio_value: Current total portfolio value

        Returns:
            Filtered signals DataFrame
        """
        if signals is None or len(signals) == 0:
            return signals

        # Update tracking
        self._update_tracking(portfolio_value)

        # Check if trading is allowed based on risk limits
        if not self._is_trading_allowed():
            logger.warning("Trading blocked due to risk limits")
            return signals.filter(pl.lit(False))  # Return empty

        # Calculate available slots for new positions
        current_count = len([v for v in current_positions.values() if v != 0])
        available_slots = self.limits.max_positions - current_count

        if available_slots <= 0:
            logger.info("Max positions reached, no new entries allowed")
            # Only allow signals for existing positions (exits)
            existing_symbols = list(current_positions.keys())
            return signals.filter(pl.col("vt_symbol").is_in(existing_symbols))

        # Limit number of new signals
        filtered = signals.head(available_slots)

        logger.debug(f"Risk filter: {len(signals)} signals -> {len(filtered)} allowed")
        return filtered

    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        portfolio_value: float,
        volatility: float | None = None
    ) -> float:
        """
        Calculate appropriate position size for a trade.

        Args:
            symbol: Stock symbol
            price: Current price
            portfolio_value: Total portfolio value
            volatility: Optional volatility measure for adjustment

        Returns:
            Position size in monetary value
        """
        # Base position size
        base_size = portfolio_value * self.limits.position_size

        # Adjust for volatility if provided
        if volatility and volatility > 0:
            # Higher volatility -> smaller position
            vol_factor = min(1.0, 0.02 / volatility)
            base_size *= vol_factor

        # Ensure minimum viable position (at least 100 shares at current price)
        min_size = price * 100
        if base_size < min_size:
            base_size = min_size

        return base_size

    def calculate_volume(
        self,
        position_value: float,
        price: float,
        lot_size: int = 100
    ) -> int:
        """
        Calculate trading volume (number of shares).

        Args:
            position_value: Target position value
            price: Current price
            lot_size: Minimum lot size (usually 100 for A-shares)

        Returns:
            Number of shares to trade (rounded to lot size)
        """
        if price <= 0:
            return 0

        shares = position_value / price
        # Round down to nearest lot size
        volume = int(shares / lot_size) * lot_size

        return max(0, volume)

    def check_order(
        self,
        symbol: str,
        direction: str,
        volume: int,
        price: float,
        current_positions: dict[str, float],
        portfolio_value: float
    ) -> tuple[bool, str]:
        """
        Validate an order against risk limits.

        Args:
            symbol: Stock symbol
            direction: "buy" or "sell"
            volume: Order volume
            price: Order price
            current_positions: Current position dict
            portfolio_value: Total portfolio value

        Returns:
            Tuple of (is_allowed, rejection_reason)
        """
        order_value = volume * price

        # Check daily loss limit
        if self.daily_pnl < -self.limits.daily_loss_limit * portfolio_value:
            return False, "Daily loss limit exceeded"

        # Check drawdown limit
        if self.current_drawdown > self.limits.max_drawdown:
            return False, "Maximum drawdown exceeded"

        # Check position limit for buys
        if direction == "buy":
            current_count = len([v for v in current_positions.values() if v != 0])
            if symbol not in current_positions and current_count >= self.limits.max_positions:
                return False, "Maximum positions reached"

            # Check single position size
            if order_value > portfolio_value * self.limits.position_size * 1.5:
                return False, "Position size too large"

        return True, ""

    def _update_tracking(self, portfolio_value: float) -> None:
        """Update risk tracking metrics."""
        # Update peak value for drawdown calculation
        if portfolio_value > self.peak_portfolio_value:
            self.peak_portfolio_value = portfolio_value

        # Calculate current drawdown
        if self.peak_portfolio_value > 0:
            self.current_drawdown = (self.peak_portfolio_value - portfolio_value) / self.peak_portfolio_value
        else:
            self.current_drawdown = 0

    def _is_trading_allowed(self) -> bool:
        """Check if trading is allowed based on current risk state."""
        # Block trading if max drawdown exceeded
        if self.current_drawdown > self.limits.max_drawdown:
            logger.warning(f"Trading blocked: drawdown {self.current_drawdown:.2%} > limit {self.limits.max_drawdown:.2%}")
            return False

        return True

    def reset_daily(self, portfolio_value: float) -> None:
        """
        Reset daily tracking at start of trading day.

        Args:
            portfolio_value: Portfolio value at start of day
        """
        self.daily_start_value = portfolio_value
        self.daily_pnl = 0
        logger.info(f"Daily risk counters reset. Start value: {portfolio_value:,.2f}")

    def update_pnl(self, portfolio_value: float) -> None:
        """
        Update daily P&L tracking.

        Args:
            portfolio_value: Current portfolio value
        """
        if self.daily_start_value > 0:
            self.daily_pnl = portfolio_value - self.daily_start_value

    def get_risk_report(self) -> dict[str, Any]:
        """
        Generate a risk status report.

        Returns:
            Dict containing current risk metrics
        """
        return {
            "current_drawdown": f"{self.current_drawdown:.2%}",
            "max_drawdown_limit": f"{self.limits.max_drawdown:.2%}",
            "daily_pnl": self.daily_pnl,
            "peak_value": self.peak_portfolio_value,
            "max_positions": self.limits.max_positions,
            "position_size_limit": f"{self.limits.position_size:.2%}",
            "trading_allowed": self._is_trading_allowed()
        }
