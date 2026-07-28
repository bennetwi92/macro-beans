# SIPP 23y build — data provenance

- Data path: **cached panel**
  (`returns_monthly_long.csv`, private to this mandate).
- History: **2008-04 to 2026-07** (220 months).
- Includes the 2008 global financial crisis: **yes**.
- Bootstrap: stationary block bootstrap, mean block 12 months,
  20,000 paths, seed 20260623.
- Bootstrap panel shifted so each column's mean equals its CMA expected return; higher moments left untouched.

This cache is separate from `outputs/returns_monthly.csv` on purpose: the ISA
build uses a 2009 start, and a longer window here must not silently change the
covariance behind an already-published allocation.

Regenerate with:

    python -m portfolio_optimiser.report.build_sipp_23y --refresh
