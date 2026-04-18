# Mean Reversion Strategy — Complete Guide

Production-ready mean-reversion scanner for swing trading mega-cap tech stocks. Walk-forward backtested with proper look-ahead-bias prevention.

**Latest validated performance (270-day walk-forward, 2025-11 → 2026-01):**

| Metric | Value |
|---|---|
| Win rate | 68.0% |
| Expectancy per trade | +0.45% |
| Sharpe ratio | 1.02 |
| Cumulative return | +34.1% |
| Signals | 75 |

Full breakdown in [`mean_reversion_walkforward_backtest_270day.md`](mean_reversion_walkforward_backtest_270day.md). Trend-aware upgrade (which generated the above numbers) documented in [`trend_aware_model_upgrade.md`](trend_aware_model_upgrade.md).

---

## Strategy rules

### Entry conditions (all must be met)

1. **RSI(2) < 30** — extreme oversold
2. **Pullback within an established uptrend** — price > MA50 > MA200
3. **Pullback magnitude:** 2–8% from recent 10-day high
4. **Near support:** price within 2% of MA20
5. **Trend quality (TQ) score 60–80** — moderate-to-weak uptrends only (counterintuitive: TQ 100 strong-trend setups underperform; see backtest doc)
6. **Confidence ≥ 60%** — model-derived score

### Exit conditions (first to trigger)

1. **Profit target:** +2% from entry
2. **Stop loss:** -3% from entry
3. **Max hold:** 10 days

### Position sizing

Risk **1.5%** of account balance per trade:

```
Position Size = (Account Balance × 0.015) / (Entry Price × stop_pct)
```

Example: $10,000 account, entry $200, stop -3% → risk $150 → 25 shares ($5,000 position).

Cap at **5 concurrent positions**.

---

## Critical insight: trend quality paradox

Strong uptrends (TQ 100, ADX > 25, DI+ ≫ DI-) **underperform** in this strategy. When price pulls back in a strong trend, it often signals trend reversal, not a buyable dip.

| Trend tier | Win rate | Avg return |
|---|---|---|
| TQ 60–70 | 100% | +1.90% |
| TQ 80 | 84.6% | +1.25% |
| TQ 100 (strong) | 57.1% | -0.03% |

**Trade implication:** the scanner explicitly filters to TQ 60–80. Don't override this manually.

---

## Cost assumptions (IBKR Lite)

- Stock commission: $0.00 (IBKR Lite)
- Slippage: ~$0.05/share on mega-caps
- Backtest models 0.1% round-trip cost (conservative)

---

## Universe (mega-cap liquid tech)

AAPL · MSFT · GOOGL · AMZN · META · NVDA · TSLA

(Plus the broader cached universe in `data/stock_history/` if you want to widen scans.)

---

## Usage

### Daily scan

```bash
python scripts/mean_reversion/scan_mean_reversion.py
```

`scan_mean_reversion.py` accepts CLI args (see `--help`) for account balance, max positions, and risk per trade. Output: list of valid setups with entry, stop, target, position size.

### Walk-forward backtest

```bash
python scripts/mean_reversion/backtest_mean_reversion_walkforward.py
```

Replays the scanner day-by-day with no look-ahead. Writes results to `data/backtests/backtest_results_<lookback>day.csv`. Generate the human-readable summary with:

```bash
python scripts/mean_reversion/backtest_summary_report.py
```

### Streamlit dashboard

```bash
streamlit run scripts/mean_reversion/dashboard.py
```

### Train / refresh model

```bash
python scripts/mean_reversion/train_mean_reversion_model.py
```

Outputs to `models/mean_reversion_model.pkl`.

### Other utilities

- `scripts/mean_reversion/analyze_feature_importance.py` — inspect model features
- `scripts/mean_reversion/test_trend_awareness.py` — trend-quality logic tests
- `scripts/mean_reversion/debug_scanner.py` — step-through debug for scanner output

---

## Live trading workflow

**Daily (market close or next morning):**

1. Run `scan_mean_reversion.py`.
2. Review valid setups.
3. For each setup:
   - Verify TQ tier (60–80) and confidence (≥60%).
   - Calculate position size from current balance.
   - Place limit order at or slightly below scanner entry.
   - Set hard stop loss immediately (don't move it).
   - Set profit-target order or manage manually.

**During trade:**

- Monitor daily for exits.
- Close at +2% target, -3% stop, or after 10 days.
- Do **not** widen the stop.

---

## Files

### Scripts (`scripts/mean_reversion/`)

| File | Purpose |
|---|---|
| `scan_mean_reversion.py` | Daily scanner — produce valid entry signals |
| `backtest_mean_reversion_walkforward.py` | Walk-forward backtester (production) |
| `backtest_summary_report.py` | Human-readable backtest summary |
| `backtest_analysis.py` | Per-trade analytics |
| `train_mean_reversion_model.py` | Train confidence-scoring model |
| `analyze_feature_importance.py` | Feature importance inspection |
| `test_trend_awareness.py` | Trend-quality logic tests |
| `debug_scanner.py` | Scanner debug helper |
| `dashboard.py` | Streamlit dashboard |

### Reusable package (`src/models/`)

`config.py`, `data_loader.py`, `features.py`, `model.py`, `backtest.py` — imported by the scripts above.

### Data (`data/backtests/`)

| File | Contents |
|---|---|
| `backtest_results_270day.csv` | Latest walk-forward output |
| `backtest_results_90day.csv` | Earlier walk-forward run |
| `stock_performance_analysis.csv` | Per-symbol stats from `tools/analyze_stock_performance.py` |

Cached OHLCV data lives in `data/stock_history/`.

### Docs (`docs/mean_reversion/`)

- `mean_reversion_strategy_guide.md` — this file
- `mean_reversion_walkforward_backtest_270day.md` — latest backtest writeup
- `trend_aware_model_upgrade.md` — trend-quality upgrade rationale

---

## Risk warnings

- Walk-forward sample is short (~270 days). Strategy is **not** validated through a prolonged bear market.
- Backtest assumes IBKR Lite ($0 commission); other brokers will degrade returns materially.
- Slippage assumption (~0.1% round-trip) holds only for mega-cap names with tight spreads.
- Max 5 concurrent positions × 1.5% risk = 7.5% account-at-risk if everything stops simultaneously.
- Real fills, especially at the open, may diverge from backtest entry prices.

---

## Next steps

- Paper trade for 1–2 months and reconcile real fills against backtest assumptions.
- Test on extended universe (SPY, QQQ, broader liquid mega-caps).
- Add VIX filter (skip new entries when VIX > 25) — not yet validated.
- Add earnings-calendar filter (avoid holding through earnings).

Not financial advice. Personal-use only.
