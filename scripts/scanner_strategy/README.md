# scanner_strategy

A rules-based trade-picking playbook on top of the v2 Scanner, plus the backtest
that stress-tests it. Companion to `docs/guides/scanner_trade_strategy.md` (which
is published on the v2 Reports page).

## Pipeline

```bash
# 1. Fetch ~10y split/dividend-adjusted open/close for the whole Scanner
#    universe -> data/scanner_strategy/prices.parquet  (gitignored, regenerable)
/usr/local/bin/python3 scripts/scanner_strategy/fetch_prices.py

# 2. Replay the Scanner day by day and simulate the £1000 ISA under the
#    playbook. Writes equity curve, trade log, per-year / per-setup / cost
#    sensitivity tables, summary.json and a chart into data/scanner_strategy/.
/usr/local/bin/python3 scripts/scanner_strategy/backtest.py
```

`scanner_lib.py` is a faithful Python port of `web/v2/js/scanner.js` +
`web/js/strategy-engine.js` (same detectors, EDGE, MAE, ranking) so the backtest
sees exactly what the live Scanner would have shown each morning, with no
look-ahead. `backtest.py`'s `Config` dataclass holds every tunable rule; edit it
and re-run to test a variant.

## Notes

- Why a custom fetcher and not yfinance / MarketStore: in the agent environment
  yfinance's curl backend fails behind the egress proxy, so `fetch_prices.py`
  hits Yahoo's chart endpoint directly with `requests` and applies the same
  `auto_adjust=True` total-return adjustment the live data layer uses.
- Leveraged ⚡ ETPs are excluded from the backtest: Yahoo's LSE leveraged-ETP
  history contains un-flagged reverse splits that fake ±100%+ moves. A
  split-repair pass in `scanner_lib.build_instruments` cleans the rest of the
  universe (a >4× single-day move is impossible even for a 3× ETF, so it is a
  data error, not a return).
- The committed CSV/PNG/JSON under `data/scanner_strategy/` are analysis outputs;
  the `*.parquet` price caches are gitignored.
