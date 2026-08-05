# Portfolio rebalancing study — how to reproduce

Everything in [`report.md`](report.md) comes from one command.

```bash
python scripts/rebalancing/run_study.py
```

Roughly two minutes on a laptop. Deterministic: the only randomness is the
block bootstrap, seeded at 42 in `src/rebalancing/config.py`.

## Requirements

```bash
python -m pip install -r scripts/rebalancing/requirements.txt
```

Python 3.11. On this repo's machine use `/usr/local/bin/python3` directly —
see the root `CLAUDE.md`.

## What it writes

| Path | Contents |
|---|---|
| `data/rebalancing/results/summary.csv` | The full metrics table — every policy × portfolio × currency × cost model (197 rows) |
| `data/rebalancing/results/bootstrap.csv` | Bootstrap distribution summary vs monthly rebalancing |
| `data/rebalancing/results/rolling_{10,20}y.csv` | CAGR difference vs monthly over every overlapping window |
| `data/rebalancing/results/rolling_window_shares.csv` | Share of windows each policy beats monthly |
| `data/rebalancing/results/crash_windows.csv` | Per-event, per-policy performance in and after each drawdown |
| `data/rebalancing/results/crash_window_dates.csv` | Detected drawdown windows, GBP and USD |
| `data/rebalancing/results/correlation_regimes_{gbp,usd}.csv` | Unconditional and stress correlations by decade |
| `data/rebalancing/results/taxable_gia_appendix.csv` | Estimated CGT drag outside an ISA/SIPP |
| `data/rebalancing/results/splices.csv` | Every splice join with its overlap-window diagnostics |
| `data/rebalancing/results/data_sources.csv` | Provenance of each series |
| `data/rebalancing/charts/*.png` | The report's eleven figures |

## Flags

| Flag | Effect |
|---|---|
| `--quick` | 250 bootstrap replicates instead of 2,000. Chart shapes get noisy; rankings do not move. |
| `--refresh` | Re-download every raw series and rewrite the cache. Needs network. |

## Data and the cache

Raw downloads are cached as CSV in `data/rebalancing/cache/` and **committed**,
so a fresh clone reproduces the study byte-for-byte with no network access.
Delete the directory or pass `--refresh` to re-fetch.

Sources: **yfinance** (ETF/index-fund adjusted closes), **FRED** via
`pandas-datareader` (GBP/USD, SONIA, UK interbank), and the **LBMA** JSON
endpoint (daily gold PM fix in USD and GBP since 1968).

Two things worth knowing before you re-fetch:

- **yfinance needs a plain `curl_cffi` session here.** Its default Chrome TLS
  impersonation is reset by a TLS-terminating proxy and every download comes
  back as an empty frame with no error. `src/rebalancing/data.py` passes a
  non-impersonating session; do not remove it.
- **Stooq is not usable** as the fallback the original brief specified. It now
  serves a JavaScript proof-of-work challenge to non-browser clients and
  returns HTML instead of CSV. FRED and LBMA replace it.

## Validation

`python scripts/rebalancing/run_study.py` runs a validation gate before any
modelling and **raises** rather than proceeding on a hard failure. It checks
calendar gaps, missing observations, extreme daily returns (flagged for
inspection, never dropped), that the total-return adjustment actually
happened, unadjusted splits, the LBMA-vs-GLD cross-check, and the
daily-versus-weekly volatility gap. Splice joins print their overlap
correlation and warn below 0.97.

Two flags are expected on a clean run and are discussed in the report: the
gold timestamp offset (LBMA 15:00 London vs the 16:00 New York close) and the
resulting daily/weekly volatility gap.

## Layout

```
src/rebalancing/
  config.py     Typed settings: target weights, cost models, paths, seed
  data.py       Fetching, caching, splicing, GBP/USD panel construction
  validate.py   The pre-modelling validation gate
  policies.py   The fifteen rebalancing policies
  engine.py     Backtest engine — single path and vectorised batch
  metrics.py    Performance/risk metrics and the return decomposition
  stats.py      Block bootstrap, rolling windows, crash and correlation analysis
  charts.py     Figures
scripts/rebalancing/run_study.py   Entry point
```

## Tests

```bash
python -m pytest tests/rebalancing -q
```

The engine is cross-validated to machine precision against an analytic
constant-mix portfolio and against buy-and-hold, and the vectorised batch path
is checked to reproduce the single path exactly.

---

*Research, not financial advice.*
