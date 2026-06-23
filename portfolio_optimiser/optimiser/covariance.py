"""Robust annualised covariance: winsorise bad ticks, then shrink correlations.

Two pitfalls this module deliberately avoids:

1. **Bad ticks.** yfinance LSE/proxy series occasionally carry data errors (e.g. a
   spurious -99% month in the managed-futures proxy, -39% in the gold series after
   FX conversion). Left in, they wreck the variance estimate. We winsorise each
   column at its 0.5/99.5 percentiles.

2. **Variance homogenisation.** Plain Ledoit-Wolf shrinks the *covariance* toward
   sigma_bar^2 * I. With assets as different as near-cash (ERNS, ~0.8% vol) and
   uranium miners (~50% vol), that pulls every diagonal toward the cross-asset
   average -- so cash comes out at 16% vol, which is nonsense. Instead we keep each
   asset's own sample variance and shrink only the **correlation** matrix toward a
   constant-correlation target (Ledoit-Wolf 2004). The shrinkage *intensity* is
   taken from sklearn's estimator on standardised returns, so it is data-driven.

cov = D . R_shrunk . D, with D = diag(annualised sample std).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

from .config import Settings


def _winsorise(returns: pd.DataFrame, k: float = 8.0) -> pd.DataFrame:
    """Clip each column to median +/- k * (robust sigma) using the MAD.

    MAD-based clipping is insensitive to a single huge bad tick (unlike a 0.5%
    percentile, which a -99% spike can drag into the data), yet it adapts to each
    asset's own scale, so a genuine -35% uranium-miner month survives while an
    impossible -99% managed-futures tick is clipped.
    """
    med = returns.median()
    mad = (returns - med).abs().median() * 1.4826
    mad = mad.where(mad > 0, returns.std(ddof=1))  # guard near-constant series
    lo = med - k * mad
    hi = med + k * mad
    return returns.clip(lower=lo, upper=hi, axis=1)


def estimate_covariance(returns: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Annualised shrinkage covariance (DataFrame, keys x keys)."""
    clean = returns.dropna(how="any")
    if clean.shape[0] < 24:
        clean = returns.dropna(how="all")
        clean = clean.fillna(clean.mean())
    clean = _winsorise(clean)

    std = clean.std(ddof=1)
    corr = clean.corr().values
    cols = clean.columns

    if settings.shrinkage == "ledoit_wolf":
        corr_shrunk = _shrink_correlation(clean.values, corr)
    else:
        corr_shrunk = corr

    d = std.values * np.sqrt(settings.trading_periods)
    cov_annual = np.outer(d, d) * corr_shrunk
    return pd.DataFrame(cov_annual, index=cols, columns=cols)


def _shrink_correlation(returns: np.ndarray, sample_corr: np.ndarray) -> np.ndarray:
    """Shrink the sample correlation toward a constant-correlation target.

    Intensity comes from sklearn's Ledoit-Wolf fit on standardised returns
    (so it reflects estimation noise), applied to the average-correlation target
    rather than to the identity -- which preserves the cross-asset diversification
    structure instead of flattening it.
    """
    p = sample_corr.shape[0]
    z = (returns - returns.mean(0)) / returns.std(0, ddof=1)
    delta = float(np.clip(LedoitWolf().fit(z).shrinkage_, 0.0, 1.0))

    off = sample_corr[~np.eye(p, dtype=bool)]
    r_bar = float(off.mean()) if off.size else 0.0
    target = np.full_like(sample_corr, r_bar)
    np.fill_diagonal(target, 1.0)

    shrunk = delta * target + (1 - delta) * sample_corr
    np.fill_diagonal(shrunk, 1.0)
    return shrunk


def correlation(cov: pd.DataFrame) -> pd.DataFrame:
    d = np.sqrt(np.diag(cov.values))
    corr = cov.values / np.outer(d, d)
    return pd.DataFrame(corr, index=cov.index, columns=cov.columns)


def annual_vol(cov: pd.DataFrame) -> pd.Series:
    return pd.Series(np.sqrt(np.diag(cov.values)), index=cov.index, name="vol")
