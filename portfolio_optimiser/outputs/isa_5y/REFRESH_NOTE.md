# Refresh note — silver → water swap (July 2026)

After the three-analyst review, the account holder replaced the **silver**
(`ISLN.L`) slice of the rotating sleeve with **water** (`IH2O.L`, iShares Global
Water). The spec now reflects this: `report/build_isa_5y.py` `THEMES` uses
`WATER`, and `config/universe.toml` + `config/cma.toml` define it.

## What is and isn't refreshed here

`WATER` (`IH2O.L`) is a new line with **no column in the committed return cache**
(`outputs/returns_monthly.csv`), and market data was **not reachable** in the
environment where this swap was made. So:

- **`targets_recommended.csv` — updated (authoritative).** The rotating sleeve is
  an equal-weight overlay applied *outside* the optimiser, and the optimised core
  is solved over the core universe only, so no core weight changes. The silver row
  was swapped for a water row at the same 5% — a deterministic edit, exact.
- **`results.json` and `wealth_5y.png` — NOT refreshed.** Their risk/return
  figures (expected return, volatility, CVaR, 5-year drawdown, terminal wealth,
  P(beat tracker)) come from a 20,000-path Monte-Carlo that needs water's return
  history. They still reflect the **prior silver-in build**.

## Direction of the change (so the stale figures aren't misread)

Water is a strict improvement on the metric that mattered in the review:

| | Silver (`ISLN.L`, removed) | Water (`IH2O.L`, added) |
|---|---:|---:|
| Modelled arithmetic return (net) | ~4.8% | ~7.35% |
| Modelled compounded return | **~0.8%** | **~6%** |
| Volatility | ~28% | ~15% |

So swapping silver → water **raises** the portfolio's expected return and
**lowers** its volatility. The committed silver-in headline figures are therefore
a mild *understatement* of the water version — the true refreshed numbers are
modestly better, not worse.

## To refresh the numbers

Run online so the water history is fetched, spliced onto its proxy (`CGW`), and
the full Monte-Carlo re-runs:

    python -m portfolio_optimiser.report.build_isa_5y --refresh

That regenerates `results.json`, `targets_recommended.csv` and `wealth_5y.png`
consistently, and this note can then be deleted.
