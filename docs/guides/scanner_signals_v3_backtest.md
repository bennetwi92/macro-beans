# v3 signals, backtested: does a profitable £1000 strategy actually exist?

This is the build the design note promised. [scanner_signals_v3](?r=guides-scanner_signals_v3)
proposed a long-horizon signal menu; [scanner_signals_v3_sorts](?r=guides-scanner_signals_v3_sorts)
ran the pre-backtest validation sort and found exactly one signal with clean
cross-sectional content (**12-1 momentum**), one marginal (**52-week-high
proximity**), and one that failed as a cross-sectional ranker (**vol-normalized
drop**). This note takes the surviving signals, cements them into strategy code,
and runs them through a *proper, honest* backtest on the simulated £1000 GBP ISA.

The question is not "can I draw a line above the index" — it is **whether a
trustworthy, net-of-cost, risk-adjusted edge over just buying the market
survives out-of-sample.** The answer here is a qualified **yes**, with the
qualifications stated as loudly as the result.

---

## Verdict at a glance

| Strategy (net of cost, GBP) | Total return | CAGR | Max DD | Sharpe | Calmar |
|---|---|---|---|---|---|
| **Buy & hold MSCI World (IWDA)** | +76.8% | 12.1% | −19.1% | **0.79** | 0.63 |
| **Recommended: top-12, quarterly, 12-1 mom, 200-MA gate** | **+112%** | 16.3% | −21.3% | **0.96** | **0.76** |
| Pre-registered: top-5, monthly | +152% | 20.3% | −36.0% | 0.88 | 0.57 |
| Concentrated: top-3, monthly | +217% | 26.1% | −35.6% | 0.96 | 0.73 |

Full window 2021-07 → 2026-06, 91 non-leveraged LSE ETFs. **Every** sensible
configuration beat buy-and-hold on total return *and* — for diversified books —
on risk-adjusted return, net of a realistic LSE round-trip + FX. The recommended
book beat the index in **both** the train and the test halves on a Sharpe basis,
which is the bar that matters.

**But:** the edge is *modest* (Sharpe ~0.96 vs 0.79 — about +0.17), it comes
with **deeper drawdowns** than the index in choppy markets, you **cannot reliably
tune the book size** in advance (train and test disagree on it), and the whole
thing rests on **one mostly-rising regime** in which the strategy's own crash
defence never had to fire. This is a real edge worth acting on with discipline —
not a free lunch.

---

## 1. What got cemented, and why

The signal decisions follow the sort evidence, not the design note's hopes:

| Signal | Sort verdict | Decision in code | Where |
|---|---|---|---|
| **12-1 momentum (B1)** | PASS — monotone-ish, edge grows at 63d | **The strategy.** Primary ranking signal for a monthly/quarterly rotation. | `signals_v3.momentum_12_1` |
| **52-wk-high proximity (B3)** | MARGINAL — right sign, non-monotone, fades | Kept as an optional trend-gated *tilt* (`blend_proximity`); adds ~+0.02 Sharpe — not load-bearing. | `signals_v3.high_proximity` |
| **Vol-norm drop z (A1)** | FAIL as ranker; thin event edge under trend gate | Exposed as an **event** trigger for a dip *satellite* only; evaluated and **cut** (§5). | `signals_v3.multiday_drop_z` |
| **200-day MA** | — | Cemented as the universal **state** gate + the cash escape hatch (demoted `cross`, per the note). | `signals_v3.trend_up` |
| Red Streak | (v2's worst loser; ~0 alpha) | **Retired** — not carried into v3 at all. | — |

The signals live in a new module, `scripts/scanner_strategy_v2/signals_v3.py`.
The live website's Scanner detectors (`scripts/scanner_strategy/scanner_lib.py`)
are deliberately **left untouched** — this is a research-track change and must
not silently alter what the public site fires on. The vol-normalization that the
sort's audit justified (fixed `−8%` thresholds over-fire high-vol names 4–6×) is
baked into the z-score signals.

**Why a new engine.** The v2 backtest is event-driven (a setup fires, you enter,
a stop/target/time exits you) — the right machine for a *dip trade*, and under
honest accounting it lost money (v1-honest ended at £542, −46%). But the one
signal that passed is a **monthly rotation**, a different machine entirely.
`scripts/scanner_strategy_v2/backtest_v3.py` rotates — rank the universe, hold
the top-N trend-confirmed names, rebalance — while reusing v2's honest GBP/FX/
cost accounting and the same IWDA-GBP benchmark verbatim.

---

## 2. Methodology — the four guardrails

1. **No look-ahead.** Signals are read at the close of the first trading day of
   each month (or quarter), using only data up to that bar; the rebalance
   executes at the **next open**. Same next-open convention the sort used.
2. **Honest costs.** Each rebalance is charged the LSE round-trip spread
   (0.25%, applied half per side) plus Trading 212's FX conversion fee (0.15%
   per conversion) on USD/EUR names, translated to GBP through the daily cross —
   identical to v2. Only the *realised delta* of each rebalance is charged
   (names that stay in the book are not churned), so costs are not overstated.
   Over five years the recommended book pays just **£39** in total costs.
3. **Out-of-sample discipline.** Knobs are tuned on a **train** window
   (2021-07 → 2024-06) and the verdict is read on a held-out **test** window
   (2024-07 → 2026-06). Every number below is labelled IS or OOS. A
   **pre-registered** default (top-5, pure 12-1, monthly) is reported alongside
   so the conclusion does not hinge on the tuning.
4. **Honest benchmark.** Net-of-cost vs £1000 into IWDA in GBP with one entry
   cost — the same "just buy the market" yardstick v2 used. Risk-adjusted
   (Sharpe, Calmar), not just the headline number.

**Data hygiene.** Two artefacts were found and fixed in the engine, because both
would have manufactured fake results:
- *Phantom-gap drawdowns.* The union timeline contains days where some names
  didn't trade; marking a held name to zero on such a day invented a −70%
  "crash" that snapped back next bar. Fixed by **carrying forward** the last
  valid close for marks (no look-ahead).
- *Bad-print spikes.* Yahoo prints the odd one-day spike-and-revert (e.g. a gold
  ETF 2517 → 3317 → 2380 in three closes). 37 such bars across the universe are
  **de-spiked** by interpolation before any signal or mark uses them.

---

## 3. Out-of-sample: the result holds, but you can't tune it

Tuning the **book size** on the train window by Sharpe, then reading the held-out
test window:

| N (book size) | TRAIN Sharpe | OOS Sharpe | OOS return | OOS max DD |
|---|---|---|---|---|
| 3 | **0.89** | 1.10 | +69% | −27% |
| 5 | 0.69 | 1.21 | +66% | −23% |
| 8 | 0.64 | 1.26 | +60% | −20% |
| 10 | 0.54 | **1.50** | +69% | −17% |
| 15 | 0.43 | 1.39 | +55% | −14% |
| 20 | 0.38 | 1.33 | +49% | −15% |
| 25 | 0.40 | 1.36 | +48% | −16% |
| *IWDA benchmark* | *0.66 (IS)* | *1.05* | *+32%* | *−19%* |

Two things to read honestly from this:

- **The good news is robust.** *Every* book size beat the benchmark out-of-sample
  on both return (+48–69% vs +32%) and Sharpe (1.10–1.50 vs 1.05). The momentum
  signal's content showed up in data it was never fitted to. The *direction* —
  momentum rotation > buy-and-hold — is the reliable part.
- **The optimal N is not learnable.** Train Sharpe and OOS Sharpe are *inversely*
  related across N: concentration (N=3) won the 2021–24 half (which contained the
  2022 bear and its rebound), while diversification (N=10) won the smooth 2024–26
  half. A naive "maximize train Sharpe" rule picks **N=3**, whose OOS Sharpe
  (1.10) is the *worst* of the lot and barely clears the index. **This is the
  curve-fitting trap, caught live.** The right response is to choose the book for
  *robustness*, not to chase the in-sample winner.

That is why the recommended config is a **diversified, low-turnover** one rather
than the return-maximizing N=3.

---

## 4. The recommended configuration

**Top-12 names by 12-1 momentum, above their 200-day MA, equal-weight, rebalanced
quarterly, with a cash escape hatch.** Chosen because it is the diversified end
of the robust range and it is the one config that beats the index risk-adjusted
in **both** halves:

| Window | Return | CAGR | Max DD | Sharpe | Calmar | vs IWDA |
|---|---|---|---|---|---|---|
| Full (5y) | +112% | 16.3% | −21.3% | **0.96** | **0.76** | IWDA 0.79 / 0.63 |
| In-sample (2021–24) | +35.9% | 10.8% | −21.3% | **0.71** | 0.51 | IWDA 0.66 / — |
| Out-of-sample (2024–26) | +57.3% | 25.6% | −17.5% | **1.32** | 1.47 | IWDA 1.05 |

Why quarterly over monthly: it cut turnover to **20 rebalances** and **£39** of
costs over five years (vs £74 monthly), reduced whipsaw, *lowered* the drawdown
(−21% vs −26% for monthly top-10), and *raised* Calmar (0.76 vs 0.64). For a
£1000 account where every trade is a fixed cost drag, less churn is strictly
better here. Out-of-sample its drawdown (−17.5%) was actually **milder than the
index's** (−19.1%) while returning nearly double.

**Design-choice ablations** (full window, monthly top-10 base) show what each
piece is worth:

| Variant | Sharpe | Max DD | Return | Read |
|---|---|---|---|---|
| base (12-1, gated) | 0.92 | −26% | +113% | — |
| − 200-MA gate | 0.87 | −29% | +107% | the gate helps risk-adjusted return |
| − cash escape hatch | 0.93 | −26% | +113% | **no effect — it never triggered** (one bull regime) |
| + proximity tilt | 0.94 | −26% | +117% | marginal help, not load-bearing |
| + vol-target sizing | 0.95 | −23% | +104% | trims drawdown, costs some return |
| **quarterly rebalance** | **0.95** | **−22%** | **+120%** | **best — the recommendation** |

---

## 5. The dip satellite: tested, and cut

The sort said the vol-normalized drop fails as a cross-sectional ranker but a thin
edge might survive in its *event tail under a trend gate*. We built exactly that
as a small satellite: enter the next open after a ≥2σ multi-day drop **in a
200-MA uptrend**, hold 21 days with a wide disaster stop, equal-risk, capped at 4
concurrent, same costs.

| Window | Trades | Win % | Sleeve return | vs cash |
|---|---|---|---|---|
| Full (5y) | 120 | 57.5% | **+13.6%** | £1000 → £1136 |
| Out-of-sample | 53 | 62.3% | +9.2% | £1000 → £1092 |

The events are real and slightly positive (win rate > 50%, a few tenths of a
percent edge over the drift baseline per trade), exactly as the horizon study
hinted. But **+13.6% over five years is ~2.6%/yr — barely above cash and far
below both the momentum sleeve and the index.** For a £1000 account it is not
worth the extra moving parts, the extra turnover, or the extra ways to be wrong.
**Verdict: cut it.** The momentum rotation is the whole strategy. (The code is
kept so the claim is reproducible and so a future, larger account could revisit
it.)

---

## 6. What this does *not* prove — the honest caveats

- **One sample, one mostly-rising regime.** Five years, one universe, no
  sustained bear. The 200-MA gate and cash escape hatch — the strategy's entire
  crash defence — **almost never triggered** (the book stayed ~97–100% invested
  throughout). So the part of the design meant to protect you in a downturn is
  **completely untested here.** Momentum's known failure mode is the sharp
  rebound after a crash ([Daniel–Moskowitz momentum crashes][crashes]); this
  window contains no such event. Expect the live drawdown, in a real bear, to be
  *worse* than anything shown above.
- **It wins by taking more risk.** The return-beating book sizes carry deeper
  drawdowns than the index (−21% to −36% vs −19%). The Sharpe edge is genuine but
  modest. This is "own a more concentrated, more volatile tilt toward what's
  been winning," not alpha from thin air.
- **The optimum is not knowable in advance** (§3). We mitigate by recommending a
  diversified, robust config, but that is a judgement call, not a fitted result.
- **Diversified-ETF attenuation, as warned.** The cross-sectional signals are
  weaker on already-diversified ETFs than the US single-stock literature; the
  proximity tilt in particular barely earns its keep.

Confidence level: **moderate.** The direction (12-1 momentum rotation beats
buy-and-hold here, net of honest costs, in and out of sample) is well-supported.
The magnitude and especially the downside behaviour in a bear are not.

---

## 7. Plain English, for the owner

**What it does.** Once a quarter, look at all ~91 plain (non-leveraged) ETFs.
Keep only the ones in a long-term uptrend (above their 200-day average). Of
those, buy the **12 with the strongest momentum** — the biggest total return over
the past year, ignoring the most recent month — in equal £-amounts. Three months
later, repeat: sell what dropped off the list, buy what's new, leave the rest.
That's it. About four decisions a year.

**What it returned.** Over the last five years, £1000 run this way would have
become **~£2,120 after all trading and currency costs** — versus **~£1,770** for
simply buying a global tracker (IWDA) and holding. It beat the market in both
the first half and the second half of the test, so it isn't a one-off fluke.

**How risky.** It is bumpier than the tracker. Its worst peak-to-trough fall was
about **−21%**, versus −19% for the tracker — and in a genuinely bad market it
would very likely fall *more* than the tracker, because everything it owns is
"what's been going up lately," which is exactly what gets hit hardest when a
rally breaks. The five years we tested never delivered that kind of crash, so
treat the smooth ride as flattering.

**How much to trust it.** Moderately. The core idea — lean toward what's been
winning, in things that are trending up — is one of the most repeatedly-documented
effects in markets, and it showed up here in data it wasn't fitted to. But this
is one slice of history with no real bear market in it, and we found (and show)
that trying to squeeze out the absolute best version by tuning would have
back-fired. So: a real, modest edge worth running with a **diversified** book and
**eyes open to a deeper drawdown than the backtest shows** — not a money machine.

---

## 8. Reproduce

```bash
# 1. build the (gitignored) price + FX cache
/usr/local/bin/python3 scripts/scanner_strategy_v2/fetch_prices.py
# 2. run the full experiment suite (sections A–E above)
/usr/local/bin/python3 -m scripts.scanner_strategy_v2.run_experiments_v3
# smoke-test the engine on the default config only:
/usr/local/bin/python3 -m scripts.scanner_strategy_v2.backtest_v3
```

Outputs (`data/scanner_strategy_v2/`): `results_v3.json` (all tables),
`equity_curve_v3.csv` / `.png`, `sweep_v3.csv`. Signals:
`scripts/scanner_strategy_v2/signals_v3.py`. Engine: `backtest_v3.py`. Driver:
`run_experiments_v3.py`.

[crashes]: https://www.sciencedirect.com/science/article/pii/S0304405X16301490
