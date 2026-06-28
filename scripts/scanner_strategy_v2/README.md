# scanner_strategy_v2

The honest rebuild of the Scanner trade-picking playbook. Companion to
`docs/guides/scanner_trade_strategy_v2.md` (published on the v2 Reports page).
The v1 scripts under `scripts/scanner_strategy/` are untouched; this directory
reuses v1's tested detectors and changes only the methodology the owner's
feedback asked for.

## What changed from v1

| Axis | v1 | v2 |
|---|---|---|
| Stops / targets | checked on the **close**, filled next open | checked **intraday** against the day's high/low, filled at the level |
| Take-profit | fixed 3× the stop | a **high percentile (~75th) of the historical MFE** distribution |
| Stop sizing | close-based MAE | **intraday (low) MAE**, wide floor/cap, lean on the time-exit |
| Selection | confluence a tie-breaker | **confluence ≥2 as a hard gate** (the biggest edge found) |
| Currency | ignored | **GBP throughout** — USD/EUR fills translated + charged T212 FX fee |
| Vol regime | none | optional **low-vol-only** risk filter (the "selective" variant) |

## Pipeline

```bash
# 1. Fetch ~10y split/dividend-adjusted daily OHLC for the universe PLUS
#    GBPUSD/GBPEUR -> data/scanner_strategy_v2/{prices_ohlc,fx}.parquet (gitignored)
/usr/local/bin/python3 scripts/scanner_strategy_v2/fetch_prices.py

# 2. Run every experiment in the report — accounting attribution, MFE percentile
#    sweep, confluence / vol / horizon tests, and the final v1-vs-v2 comparison.
#    Writes results.json + equity curve / by-year / by-setup CSVs + a chart.
/usr/local/bin/python3 -m scripts.scanner_strategy_v2.run_experiments
```

`backtest.py`'s `Config` dataclass holds every switch (`exit_mode`,
`target_mode`, `stop_basis`, `fx`, `confluence_min`, `vol_gate`, …), so any one
change can be ablated. `scanner_lib.py` imports v1's `_trigger_arrays` etc.
verbatim, so the two backtests can never disagree on what fires when.

```bash
# 3. (v3 research) Extend the horizon study to ~3 months and report net-of-cost
#    expectancy per setup -> data/scanner_strategy_v2/horizon_extended.{csv,png}.
#    Underpins docs/guides/scanner_trade_strategy_v3.md.
/usr/local/bin/python3 scripts/scanner_strategy_v2/horizon_extended.py
```

`horizon_extended.py` reuses the v2 price cache and v1 detectors to measure, per
setup across holds of 3–63 trading days, the **net return per trade after a
0.30% round-trip cost** (and its annualised, drift-removed-edge companions). The
finding: short holds are net-negative, expectancy rises *monotonically* with
horizon, and the dip setups' true edge grows with the hold — the evidence behind
the v3 longer-horizon proposal.

## The headline finding

v1's published return leaned on a close-only stop a real resting order would not
have given you. Costed honestly (intraday fills + FX), v1's own rules make
**£542**, not £1,348. v2's job was clawing that back: the confluence gate, wide
disaster stops, a high-percentile MFE target and explicit FX get it to **£1,095**
(core) / **£1,224** (selective) with a far shallower drawdown. It still lags a
plain world tracker — v2 is a defensive sleeve, not a growth engine.

## Notes

- Same custom Yahoo fetcher rationale as v1 (yfinance's TLS backend fails behind
  the egress proxy). OHLC is `auto_adjust`-equivalent; a split-repair pass
  cleans the leveraged-ETP reverse-split discontinuities, scaling high/low by the
  same factor as the close.
- Committed CSV/PNG/JSON under `data/scanner_strategy_v2/` are analysis outputs;
  the `*.parquet` caches are gitignored and regenerable via `fetch_prices.py`.
