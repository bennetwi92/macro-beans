"""Contribution-driven rebalancing toward target weights.

Operating model: annual target weights, monthly rebalancing via *new money* only
(no selling, to avoid CGT churn -- though inside an ISA/SIPP that is moot, the
default stays buy-only so the same logic works for taxable accounts too).

``rebalance`` takes current holdings (GBP per holding) and this month's
contribution, and returns the buy split that moves each holding as close to target
as the contribution allows -- a water-filling allocation that funds the most
underweight holdings first.

It raises a drift flag when a holding is so far from target that contributions
alone cannot fix it (i.e. it is *over*weight and would need a sale), using the
configured absolute (5 ppt) and relative (25%) thresholds. The output maps
directly onto a Trading 212 Pie (target % per holding).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class RebalancePlan:
    buys: pd.Series              # GBP to buy per holding (>= 0), sums to contribution
    post_value: float            # portfolio value after the contribution
    post_weights: pd.Series      # resulting weights
    target_weights: pd.Series
    drift_before: pd.Series      # actual - target, before contribution
    drift_after: pd.Series       # actual - target, after contribution
    flags: list[str] = field(default_factory=list)
    pie_targets: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


def rebalance(
    current: dict[str, float] | pd.Series,
    contribution: float,
    target_weights: dict[str, float] | pd.Series,
    drift_abs_pts: float = 0.05,
    drift_rel: float = 0.25,
    allow_sells: bool = False,
) -> RebalancePlan:
    """Compute the buy split for a monthly contribution.

    Parameters
    ----------
    current : GBP value currently held per holding (missing holdings = 0).
    contribution : new money to deploy this month (GBP, >= 0).
    target_weights : desired weights (will be normalised to sum 1).
    drift_abs_pts, drift_rel : thresholds for the "can't fix with contributions" flag.
    allow_sells : if True, also returns sells to fully rebalance (Pie auto-invest off).
    """
    target = pd.Series(target_weights, dtype=float)
    target = target / target.sum()
    holdings = target.index

    cur = pd.Series(current, dtype=float).reindex(holdings).fillna(0.0)
    cur_value = float(cur.sum())
    if contribution < 0:
        raise ValueError("contribution must be >= 0 (use allow_sells for rebalancing).")

    post_value = cur_value + contribution
    desired = target * post_value                      # GBP target after contribution
    gap = desired - cur                                # +ve = underweight (needs buying)

    drift_before = (cur / cur_value - target) if cur_value > 0 else target * 0 - target

    if allow_sells:
        buys = gap.clip(lower=None)                    # may be negative (sell)
    else:
        # Water-filling: distribute the contribution across underweight holdings in
        # proportion to their shortfall, capped so no holding overshoots its target.
        need = gap.clip(lower=0.0)
        if need.sum() <= 1e-9 or contribution <= 0:
            buys = pd.Series(0.0, index=holdings)
        elif contribution >= need.sum():
            # Enough to fill every gap; remainder goes to target proportions.
            extra = contribution - need.sum()
            buys = need + target * extra
        else:
            buys = need * (contribution / need.sum())

    post = cur + buys
    post_weights = post / post.sum()
    drift_after = post_weights - target

    flags: list[str] = []
    for h in holdings:
        d = drift_after[h]
        rel = abs(d) / target[h] if target[h] > 0 else 0.0
        # Only an *overweight* (positive drift) cannot be fixed by buying more.
        if d > 0 and (d > drift_abs_pts or rel > drift_rel) and not allow_sells:
            flags.append(
                f"{h}: {post_weights[h]:.1%} vs target {target[h]:.1%} "
                f"(+{d*100:.1f}pp / +{rel*100:.0f}% rel) -- overweight, "
                "contributions can't fix; consider a sell or pausing its Pie slice."
            )

    return RebalancePlan(
        buys=buys.round(2),
        post_value=post_value,
        post_weights=post_weights,
        target_weights=target,
        drift_before=drift_before,
        drift_after=drift_after,
        flags=flags,
        pie_targets=(target * 100).round(1),
    )
