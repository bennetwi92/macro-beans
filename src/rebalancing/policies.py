"""Rebalancing policies.

Every policy is a small object with the same interface, and every one of them
runs through the identical engine in :mod:`src.rebalancing.engine`. That is
deliberate: the fastest way to manufacture a fake winner is to give one policy
its own code path.

Policies split into two kinds:

* **Scheduled** -- the trade dates are a function of the calendar or of the
  asset price path alone, so they can be precomputed into a boolean mask
  before the backtest starts. Calendar rebalancing and the drawdown trigger
  are both of this kind (a drawdown trigger depends on the equity path, not on
  what the portfolio did).
* **Band** -- the trade dates depend on the portfolio's own realised weights,
  so they have to be evaluated inside the loop.

The distinction is not cosmetic: it is what makes the block bootstrap
tractable, because scheduled masks vectorise across thousands of replicates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from numpy.typing import NDArray

Freq = Literal["daily", "monthly", "quarterly", "semiannual", "annual", "never"]


def period_start_mask(dates: pd.DatetimeIndex, freq: Freq) -> NDArray[np.bool_]:
    """First trading day of each period. ``daily`` is all days, ``never`` none."""
    if freq == "daily":
        return np.ones(len(dates), dtype=bool)
    if freq == "never":
        return np.zeros(len(dates), dtype=bool)

    series = pd.Series(np.arange(len(dates)), index=dates)
    if freq == "monthly":
        key = dates.to_period("M")
    elif freq == "quarterly":
        key = dates.to_period("Q")
    elif freq == "annual":
        key = dates.to_period("Y")
    elif freq == "semiannual":
        quarters = dates.to_period("Q")
        key = pd.PeriodIndex(
            [pd.Period(f"{p.year}Q{1 if p.quarter <= 2 else 3}", freq="Q") for p in quarters]
        )
    else:  # pragma: no cover - Freq is exhaustive
        raise ValueError(f"unknown frequency {freq!r}")

    firsts = series.groupby(key).min().to_numpy()
    mask = np.zeros(len(dates), dtype=bool)
    mask[firsts] = True
    mask[0] = False  # day 0 is already at target; no trade to make
    return mask


def drawdown_trigger_mask(
    equity_level: NDArray[np.float64],
    *,
    threshold: float,
    lookback: int = 252,
    lockout: int = 252,
) -> NDArray[np.bool_]:
    """Days on which equities are ``threshold`` below their trailing high.

    Fires on the *first* day the drawdown breaches the threshold and then
    disarms for ``lockout`` trading days, so a long bear market produces a
    handful of trades rather than one every day. Works on 1-D or 2-D
    (replicates x time) input.
    """
    single = equity_level.ndim == 1
    level = equity_level[None, :] if single else equity_level
    running_max = _rolling_max(level, lookback)
    breached = level < running_max * (1.0 - threshold)

    n_reps, n_days = breached.shape
    fires = np.zeros_like(breached)
    armed_at = np.full(n_reps, -(10**9), dtype=np.int64)
    for t in range(n_days):
        eligible = breached[:, t] & (t - armed_at >= lockout)
        fires[eligible, t] = True
        armed_at[eligible] = t
    return fires[0] if single else fires


def _rolling_max(values: NDArray[np.float64], window: int) -> NDArray[np.float64]:
    """Trailing (inclusive) rolling maximum along the last axis.

    Uses the van Herk / Gil-Werman two-pass algorithm: O(n) time and O(n)
    memory regardless of window length. The obvious ``sliding_window_view``
    approach would need ~9 GB for the bootstrap's dimensions.
    """
    n_reps, n_days = values.shape
    pad = (-n_days) % window
    padded = np.concatenate(
        [values, np.full((n_reps, pad), -np.inf)], axis=1
    ).reshape(n_reps, -1, window)

    prefix = np.maximum.accumulate(padded, axis=2).reshape(n_reps, -1)[:, :n_days]
    suffix = np.maximum.accumulate(padded[:, :, ::-1], axis=2)[:, :, ::-1].reshape(
        n_reps, -1
    )[:, :n_days]

    out = np.empty_like(values)
    # For the first `window-1` days the window is not yet full: expanding max.
    head = min(window - 1, n_days)
    out[:, :head] = np.maximum.accumulate(values[:, :head], axis=1)
    if n_days > head:
        idx = np.arange(head, n_days)
        out[:, head:] = np.maximum(suffix[:, idx - window + 1], prefix[:, idx])
    return out


# ---------------------------------------------------------------------------
# Policy objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Policy:
    """A rebalancing rule.

    ``schedule`` fixes the days on which the policy is *allowed* to act.
    ``abs_band`` / ``rel_band`` additionally require a weight breach on that
    day. A pure calendar policy has no bands; a pure threshold policy has a
    daily schedule; a hybrid has a monthly schedule *and* bands -- which is
    why all three fall out of one object rather than three classes.
    """

    name: str
    family: str
    schedule: Freq = "never"
    abs_band: float | None = None
    rel_band: float | None = None
    drawdown_trigger: float | None = None
    contributions_to_underweight: bool = False
    sells_allowed: bool = True
    description: str = ""

    @property
    def has_bands(self) -> bool:
        return self.abs_band is not None or self.rel_band is not None

    def schedule_mask(
        self, dates: pd.DatetimeIndex, equity_level: NDArray[np.float64] | None = None
    ) -> NDArray[np.bool_]:
        if self.drawdown_trigger is not None:
            if equity_level is None:
                raise ValueError(f"{self.name}: drawdown trigger needs an equity path")
            return drawdown_trigger_mask(equity_level, threshold=self.drawdown_trigger)
        return period_start_mask(dates, self.schedule)

    def breached(
        self, weights: NDArray[np.float64], target: NDArray[np.float64]
    ) -> NDArray[np.bool_]:
        """Whether the band is breached. Vectorised over leading axes."""
        if not self.has_bands:
            return np.ones(weights.shape[:-1], dtype=bool)
        deviation = np.abs(weights - target)
        active = target > 0
        trip = np.zeros(weights.shape, dtype=bool)
        if self.abs_band is not None:
            trip |= deviation >= self.abs_band
        if self.rel_band is not None:
            with np.errstate(divide="ignore", invalid="ignore"):
                relative = np.where(active, deviation / np.where(active, target, 1.0), 0.0)
            trip |= relative >= self.rel_band
        return (trip & active).any(axis=-1)


# The full policy space. The count matters for multiple-testing honesty: this
# is 15 variants, and any winner has to be read in that light.
POLICIES: tuple[Policy, ...] = (
    Policy("Never (drift)", "calendar", schedule="never",
           description="Buy and hold; weights drift wherever markets take them."),
    Policy("Monthly", "calendar", schedule="monthly",
           description="Rebalance to target on the first trading day of each month."),
    Policy("Quarterly", "calendar", schedule="quarterly",
           description="Rebalance to target on the first trading day of each quarter."),
    Policy("Semi-annual", "calendar", schedule="semiannual",
           description="Rebalance to target every six months."),
    Policy("Annual", "calendar", schedule="annual",
           description="Rebalance to target once a year."),
    Policy("Daily (constant mix)", "control", schedule="daily",
           description="Theoretical limit of rebalancing intensity; not investable."),
    Policy("Band 5pp (daily check)", "threshold", schedule="daily", abs_band=0.05,
           description="Check daily; trade when any weight is 5pp from target."),
    Policy("Band 25% rel (daily check)", "threshold", schedule="daily", rel_band=0.25,
           description="Check daily; trade when any weight is 25% of target away."),
    Policy("5/25 rule (daily check)", "threshold", schedule="daily",
           abs_band=0.05, rel_band=0.25,
           description="Swedroe 5/25: 5pp absolute or 25% relative, whichever trips."),
    Policy("Band 5pp (monthly check)", "hybrid", schedule="monthly", abs_band=0.05,
           description="Look once a month; trade only on a 5pp breach."),
    Policy("5/25 rule (monthly check)", "hybrid", schedule="monthly",
           abs_band=0.05, rel_band=0.25,
           description="Look once a month; trade only on a 5/25 breach."),
    Policy("5/25 rule (annual check)", "hybrid", schedule="annual",
           abs_band=0.05, rel_band=0.25,
           description="Look once a year; trade only on a 5/25 breach."),
    Policy("Drawdown trigger -15%", "opportunistic", drawdown_trigger=0.15,
           description="Rebalance when equities fall 15% from a 1-year high."),
    Policy("Drawdown trigger -20%", "opportunistic", drawdown_trigger=0.20,
           description="Rebalance when equities fall 20% from a 1-year high."),
    Policy("Cash-flow only", "cashflow", schedule="never",
           contributions_to_underweight=True, sells_allowed=False,
           description="Never sell; steer new contributions to the most underweight asset."),
)

POLICY_BY_NAME: dict[str, Policy] = {p.name: p for p in POLICIES}

__all__ = [
    "POLICIES",
    "POLICY_BY_NAME",
    "Policy",
    "drawdown_trigger_mask",
    "period_start_mask",
]
