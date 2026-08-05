"""Configuration objects for the rebalancing study.

Every tunable lives here as a typed dataclass so that sensitivity analysis is
a matter of constructing a variant, never of editing engine code. Target
weights in particular are a parameter, never a hard-coded constant.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from src.data.paths import DATA_DIR

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

STUDY_DIR: Path = DATA_DIR / "rebalancing"
CACHE_DIR: Path = STUDY_DIR / "cache"
RESULTS_DIR: Path = STUDY_DIR / "results"
CHARTS_DIR: Path = STUDY_DIR / "charts"

# Fixed everywhere a random number is drawn.
RANDOM_SEED: int = 42

# Asset order is fixed across the whole study; every weight vector uses it.
ASSETS: tuple[str, ...] = ("equity", "bond", "gold")

TRADING_DAYS_PER_YEAR: int = 252


# ---------------------------------------------------------------------------
# Target weights
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TargetWeights:
    """A target allocation over :data:`ASSETS`.

    Weights are stored as a mapping so a two-asset portfolio simply omits
    gold; :meth:`vector` always returns a full-length vector in ``ASSETS``
    order, which is what the engine consumes.
    """

    name: str
    weights: dict[str, float]

    def __post_init__(self) -> None:
        unknown = set(self.weights) - set(ASSETS)
        if unknown:
            raise ValueError(f"unknown assets in target weights: {sorted(unknown)}")
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"target weights for {self.name!r} sum to {total}, not 1")

    def vector(self) -> list[float]:
        return [float(self.weights.get(a, 0.0)) for a in ASSETS]

    @property
    def active_assets(self) -> tuple[str, ...]:
        return tuple(a for a in ASSETS if self.weights.get(a, 0.0) > 0.0)


PORTFOLIOS: tuple[TargetWeights, ...] = (
    TargetWeights("60/40", {"equity": 0.60, "bond": 0.40}),
    TargetWeights("60/20/20", {"equity": 0.60, "bond": 0.20, "gold": 0.20}),
    TargetWeights("40/30/30", {"equity": 0.40, "bond": 0.30, "gold": 0.30}),
)

HEADLINE_PORTFOLIO: str = "60/20/20"


# ---------------------------------------------------------------------------
# Costs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostModel:
    """Round-trip friction, modelled per unit of traded notional.

    ``half_spread_bps`` is charged on every pound traded in either direction.
    ``commission_flat`` is charged once per asset per rebalance date, which is
    how UK retail platforms actually bill: it makes commission drag large for
    a small pot and negligible for a large one, so the portfolio size is part
    of the cost model rather than an afterthought.

    ``fx_bps`` covers platforms that charge an explicit FX conversion on
    US-listed lines. It is zero in the base case because a UK investor buying
    a **GBP-quoted LSE ETF** pays no per-trade FX charge -- the currency
    exposure is unhedged inside the NAV, which is a market risk, not a fee.
    """

    name: str = "base"
    half_spread_bps: dict[str, float] = field(
        default_factory=lambda: {"equity": 4.0, "bond": 3.0, "gold": 6.0}
    )
    commission_flat: float = 5.95
    fx_bps: float = 0.0
    initial_value: float = 100_000.0

    def scaled(self, factor: float, name: str | None = None) -> CostModel:
        """Return a copy with every variable cost multiplied by ``factor``."""
        return replace(
            self,
            name=name or f"{self.name}x{factor:g}",
            half_spread_bps={k: v * factor for k, v in self.half_spread_bps.items()},
            commission_flat=self.commission_flat * factor,
            fx_bps=self.fx_bps * factor,
        )

    def spread_vector(self) -> list[float]:
        return [self.half_spread_bps.get(a, 0.0) + self.fx_bps for a in ASSETS]


COST_BASE = CostModel(name="base")
COST_ZERO = CostModel(
    name="zero",
    half_spread_bps={a: 0.0 for a in ASSETS},
    commission_flat=0.0,
    fx_bps=0.0,
)
COST_HALF = COST_BASE.scaled(0.5, "half")
COST_DOUBLE = COST_BASE.scaled(2.0, "double")
COST_US_LISTED = replace(COST_BASE, name="us_listed_fx", fx_bps=50.0)
COST_SMALL_POT = replace(COST_BASE, name="small_pot", initial_value=10_000.0)


# ---------------------------------------------------------------------------
# Study-level settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StudyConfig:
    """Top-level knobs for a single run of the study."""

    start: str = "1991-11-01"
    end: str | None = None
    currency: str = "GBP"
    exec_lag: int = 0
    monthly_contribution: float = 0.0
    bootstrap_replicates: int = 2000
    bootstrap_mean_block: int = 63
    seed: int = RANDOM_SEED


# Sub-sample with no equity splice at all: ACWI is the sole equity source from
# its inception. Every headline conclusion is re-checked here.
UNSPLICED_START: str = "2008-03-31"

__all__ = [
    "ASSETS",
    "CACHE_DIR",
    "CHARTS_DIR",
    "COST_BASE",
    "COST_DOUBLE",
    "COST_HALF",
    "COST_SMALL_POT",
    "COST_US_LISTED",
    "COST_ZERO",
    "CostModel",
    "HEADLINE_PORTFOLIO",
    "PORTFOLIOS",
    "RANDOM_SEED",
    "RESULTS_DIR",
    "STUDY_DIR",
    "StudyConfig",
    "TRADING_DAYS_PER_YEAR",
    "TargetWeights",
    "UNSPLICED_START",
]
