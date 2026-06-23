"""Quantitative allocation optimiser for a UK ISA (A) and SIPP (B).

A small, config-driven project that:
  * builds forward-looking expected returns (CMAs) and a shrinkage covariance,
  * optimises two portfolios with distinct objectives (max geometric growth for
    the SIPP; risk-adjusted growth under a liquidity floor + CVaR cap for the ISA),
  * cross-checks with resampled (Michaud), Black-Litterman and HRP methods,
  * validates via Monte Carlo, and
  * ships a monthly contribution-driven rebalancer.

Not financial advice. Every assumption lives in ``config/`` and is editable.
"""

__version__ = "0.1.0"
