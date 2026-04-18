"""Configuration for the storage model"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class StorageConfig:
    """Storage facility configuration — maps gas storage parameters to ETF trading.

    Gas Storage Term        ETF Analogy             Parameter
    ──────────────────────  ──────────────────────  ─────────────────────
    Working gas capacity    Max shares held          max_inventory
    Cushion gas             Minimum reserve          min_inventory
    Injection rate          Max daily buy            max_inject_per_day
    Withdrawal rate         Max daily sell           max_withdraw_per_day
    Injection season        Buy window months        inject_months
    Withdrawal season       Sell window months       withdraw_months
    Ratchets                Rate varies with level   use_ratchets
    """

    # Asset
    ticker: str = "GLD"
    asset_name: str = "Gold (GLD ETF)"
    start_date: str = "2010-01-01"
    end_date: Optional[str] = None  # None = today

    # Storage facility parameters (units = shares of ETF)
    max_inventory: int = 1000
    min_inventory: int = 100        # cushion gas
    initial_inventory: int = 100    # start at cushion
    max_inject_per_day: int = 50
    max_withdraw_per_day: int = 50

    # Ratchets: injection/withdrawal rates change with inventory level
    # When enabled, injection rate decreases as storage fills (harder to push
    # gas in at high pressure) and withdrawal rate decreases as storage empties
    # (less pressure to push gas out).
    use_ratchets: bool = True

    # Capital
    initial_capital: float = 100_000.0

    # Seasonal windows
    inject_months: List[int] = field(default_factory=lambda: [5, 6, 7, 8, 9])
    withdraw_months: List[int] = field(default_factory=lambda: [10, 11, 12, 1, 2, 3, 4])

    # Seasonal discipline: penalize or block off-season trades
    # "hard" = block off-season trades entirely
    # "soft" = apply penalty multiplier to composite signal for off-season trades
    # "none" = no seasonal gate (original behavior)
    seasonal_gate: str = "soft"
    seasonal_penalty: float = 0.5  # multiplier applied to off-season signal (soft mode)

    # Signal parameters
    zscore_window: int = 63             # ~1 quarter lookback
    momentum_window: int = 5
    seasonal_weight: float = 0.4
    zscore_weight: float = 0.4
    momentum_weight: float = 0.2

    # Composite signal thresholds — bang-bang: when crossed, trade at full rate
    inject_signal_threshold: float = 0.3
    withdraw_signal_threshold: float = -0.3

    # Transaction costs
    transaction_cost_pct: float = 0.001  # 0.1%

    # Preset name (for display)
    preset: str = "balanced"

    def __post_init__(self):
        all_months = set(self.inject_months) | set(self.withdraw_months)
        if all_months != set(range(1, 13)):
            raise ValueError("inject_months and withdraw_months must cover all 12 months")
        if self.min_inventory >= self.max_inventory:
            raise ValueError("min_inventory must be less than max_inventory")
        if self.initial_inventory < self.min_inventory:
            raise ValueError("initial_inventory cannot be below min_inventory (cushion)")
        if self.initial_inventory > self.max_inventory:
            raise ValueError("initial_inventory cannot exceed max_inventory")
        weights = self.seasonal_weight + self.zscore_weight + self.momentum_weight
        if abs(weights - 1.0) > 0.01:
            raise ValueError(f"Signal weights must sum to 1.0, got {weights}")
        if self.seasonal_gate not in ("hard", "soft", "none"):
            raise ValueError(f"seasonal_gate must be 'hard', 'soft', or 'none', got '{self.seasonal_gate}'")

    def effective_inject_rate(self, inventory: int) -> int:
        """Injection rate adjusted for ratchets.
        As storage fills, injection rate decreases (higher pressure = harder to inject).
        """
        if not self.use_ratchets:
            return self.max_inject_per_day
        working_capacity = self.max_inventory - self.min_inventory
        fill_pct = (inventory - self.min_inventory) / working_capacity
        # Linear ratchet: full rate at empty, 20% rate when full
        ratchet_factor = max(0.2, 1.0 - 0.8 * fill_pct)
        return max(1, int(self.max_inject_per_day * ratchet_factor))

    def effective_withdraw_rate(self, inventory: int) -> int:
        """Withdrawal rate adjusted for ratchets.
        As storage empties, withdrawal rate decreases (lower pressure = harder to extract).
        """
        if not self.use_ratchets:
            return self.max_withdraw_per_day
        working_capacity = self.max_inventory - self.min_inventory
        fill_pct = (inventory - self.min_inventory) / working_capacity
        # Linear ratchet: 20% rate when empty, full rate when full
        ratchet_factor = max(0.2, 0.2 + 0.8 * fill_pct)
        return max(1, int(self.max_withdraw_per_day * ratchet_factor))


# ── Asset Presets ──
# GLD inject months: May-Sep (empirically weak months for gold)
# GLD withdraw months: Oct-Apr (includes Jan +3.3%, Aug moved to borderline)
# Based on World Gold Council data and In Gold We Trust 2024 Halloween Effect analysis

GLD_PRESET = StorageConfig(
    ticker="GLD",
    asset_name="Gold (GLD ETF)",
    inject_months=[5, 6, 7, 8, 9],
    withdraw_months=[10, 11, 12, 1, 2, 3, 4],
    preset="balanced",
)

# CORN: Physical corn peaks Jun-Jul (planting uncertainty), bottoms at harvest (Oct-Nov).
# But the CORN ETF has roll drag and doesn't track spot cleanly. Empirical ETF data
# shows May-Sep as weak months and Oct-Apr as stronger months.
# Note: seasonal effect has compressed significantly post-2010 (Li et al. 2024).
CORN_PRESET = StorageConfig(
    ticker="CORN",
    asset_name="Corn (CORN ETF)",
    start_date="2011-01-01",
    inject_months=[5, 6, 7, 8, 9],
    withdraw_months=[10, 11, 12, 1, 2, 3, 4],
    preset="balanced",
)


# ── Risk Presets (applied on top of asset preset) ──

CONSERVATIVE_OVERRIDES = dict(
    max_inventory=500,
    min_inventory=100,
    max_inject_per_day=25,
    max_withdraw_per_day=25,
    inject_signal_threshold=0.5,
    withdraw_signal_threshold=-0.5,
    preset="conservative",
)

AGGRESSIVE_OVERRIDES = dict(
    max_inventory=2000,
    min_inventory=50,
    max_inject_per_day=100,
    max_withdraw_per_day=100,
    inject_signal_threshold=0.15,
    withdraw_signal_threshold=-0.15,
    preset="aggressive",
)
