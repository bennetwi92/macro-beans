# v3 signal sorts: the pre-backtest validation (§7.1–7.3)

This is the "basic calculation" gate from
[scanner_signals_v3](?r=guides-scanner_signals_v3) §7 — a cross-sectional
forward-return **sort**, not a backtest. There is no account, equity curve,
stop/target or P&L here; the only question is whether ranking the universe by
each proposed signal produces a **monotone forward-return gradient**. A clean
gradient = the signal has cross-sectional content on *this* universe; a
flat/noisy one = the §6 attenuation caveat (US single-stock results may not
survive on diversified LSE ETFs) is biting.

**Method.** Reproducible via
`scripts/scanner_strategy_v2/signal_sorts.py` on the v2 price cache.
Non-leveraged names only (91 usable), window **2021-07 → 2026-06**, **60**
monthly cross-sections of 84–91 names each. On the first trading day of each
month the signal is computed from data **up to that bar only**; forward return
uses the repo's next-open-entry convention (enter open *t+1*, exit close
*t+1+H*) at **H = 21d (1mo)** and **63d (3mo)**. The universe is split into
quintiles (Q1 = lowest signal, Q5 = highest); every (month, instrument) row is
aggregated by bucket across all 60 months. *Drift-removed* return = the
instrument's forward return minus that month's equal-weight universe forward
return, stripping beta the way §5 does.

**One sample, one mostly-rising regime.** Five years, one universe, a window
with no sustained bear. Treat the *direction* of these sorts as the signal and
the precise basis points as illustrative — same caveat as v1/v2/v3.

---

## Verdict at a glance

| Signal | 21d Q5−Q1 (raw / drift-rm) | 63d Q5−Q1 (raw / drift-rm) | Monotone? | Gate |
|---|---|---|---|---|
| **12-1 momentum (B1)** | +1.14% / +1.15% | +2.05% / +2.08% | ~yes (4/4 of the trend; one mid wobble) | **PASS** |
| **52wk-high proximity (B3)** | +0.62% / +0.60% | +0.37% / +0.46% | no (Q2 spikes) | **WEAK / marginal** |
| **Vol-norm drop z (A1)** | −0.36% / −0.36% | −0.77% / −0.74% | no — wrong direction | **FAIL (as a cross-sec dip-buy)** |

(`Q5−Q1` is top-bucket minus bottom-bucket mean forward return. For the drop-z
signal Q1 = the *most-negative* z = biggest dip, so the **negative** spread
means the dipped bucket does **not** lead.)

CSV outputs: `data/scanner_strategy_v2/sort_{52wk_high,mom_12_1,drop_z}.csv`,
`turnover_firecount.csv`, `volnorm_audit{,_summary}.csv`; chart
`signal_sorts.png`.

---

## 1. 12-1 absolute momentum (B1) — **passes**

| bucket | n | mean fwd21% | win21% | dr fwd21% | mean fwd63% | win63% | dr fwd63% |
|---|---|---|---|---|---|---|---|
| 1 (weakest) | 1081 | 0.14 | 50.6 | **−0.65** | 1.23 | 54.8 | **−0.86** |
| 2 | 1035 | 0.92 | 56.9 | +0.14 | 1.79 | 59.2 | −0.28 |
| 3 | 1040 | 0.73 | 57.0 | −0.07 | 2.16 | 61.2 | +0.07 |
| 4 | 1035 | 0.89 | 58.6 | +0.10 | 1.95 | 61.8 | −0.12 |
| 5 (strongest) | 1053 | **1.28** | 58.2 | **+0.50** | **3.28** | 61.8 | **+1.22** |

The gradient is real and, decisively, **grows with horizon** — the drift-removed
Q5−Q1 spread roughly doubles from +1.15% at 21d to +2.08% at 63d, the opposite
of a signal that decays. Most of the content sits in the **extremes**: the
weakest-momentum bucket is the clear laggard (drift-removed −0.65% / −0.86%, the
only bucket with a negative edge at *both* horizons) and the strongest is the
clear leader. The middle three are a noisy plateau, so this is more a
"avoid the laggards, lean on the leaders" tilt than a smooth five-step staircase
— but it is the cleanest of the three signals and the only one whose edge
*strengthens* at 63d. This is the workhorse §3 expected Engine B to be built on,
and it earns the slot.

## 2. 52-week-high proximity (B3) — **marginal**

| bucket | n | mean fwd21% | win21% | dr fwd21% | mean fwd63% | win63% | dr fwd63% |
|---|---|---|---|---|---|---|---|
| 1 (furthest below) | 1081 | 0.42 | 50.9 | −0.38 | 1.69 | 54.9 | −0.40 |
| 2 | 1035 | **1.06** | 57.1 | +0.27 | **2.94** | 63.6 | +0.86 |
| 3 | 937 | 0.71 | 55.6 | −0.06 | 2.02 | 58.7 | −0.16 |
| 4 | 1038 | 0.70 | 56.5 | −0.08 | 1.70 | 59.9 | −0.36 |
| 5 (nearest high) | 1154 | 1.03 | **60.7** | +0.22 | 2.06 | **61.5** | +0.06 |

The George–Hwang prediction (top bucket leads) shows up **only partially**. In
its favour: the bottom bucket (names furthest below their 1-year high — the
beaten-down) is the worst at both horizons with a negative drift-removed edge,
the top bucket has the best win rate (60.7% / 61.5%) and a positive drift-removed
tilt, and the overall Q5−Q1 stays positive after drift removal (+0.60% / +0.46%).
Against it: the gradient is **not monotone** — bucket 2 spikes well above the
rest, and the top bucket's edge has nearly washed out by 63d (+0.06% drift-rm).
Read: directionally consistent with the literature but **materially attenuated**,
exactly as §6 warned for diversified ETFs. It clears a low bar (right sign, top
bucket best win-rate, low turnover) but does not deliver the clean monotone sort
the note hoped for. Keep as a *gated/trend-confirmed* entry, not a standalone
cross-sectional ranker.

## 3. Vol-normalized multi-day drop z (A1, W=10) — **fails the predicted direction**

| bucket | n | mean fwd21% | win21% | dr fwd21% | mean fwd63% | win63% | dr fwd63% |
|---|---|---|---|---|---|---|---|
| 1 (biggest dip, z≪0) | 1098 | 0.79 | 55.7 | −0.00 | 1.72 | 59.0 | −0.29 |
| 2 | 1051 | 0.93 | 58.2 | +0.13 | **2.89** | 64.5 | +0.86 |
| 3 | 1049 | **1.05** | 58.2 | +0.26 | 2.40 | 59.2 | +0.38 |
| 4 | 1051 | 0.79 | 55.5 | −0.01 | 2.15 | 60.6 | +0.12 |
| 5 (biggest up-move, z≫0) | 1072 | 0.42 | 53.3 | −0.36 | 0.95 | 55.2 | **−1.03** |

The dip-alpha claim — "the most-negative bucket should have a positive forward
edge (reversion)" — **does not hold cross-sectionally on this universe.** The
biggest-dip bucket (Q1) has an essentially *zero* drift-removed edge at 21d
(−0.00%) that turns *negative* by 63d (−0.29%); it is not the leader. The shape
is a **hump that peaks in the middle and falls off at the top**: the clear,
monotone-from-the-top signal is that names which just had the biggest *up*-moves
(Q5) **give it back** — drift-removed −0.36% (21d) → **−1.03%** (63d). So the
only reversion present is "fade the recent sharp winners," not "buy the recent
sharp losers."

**Important nuance, not a rescue.** This sort buckets the *continuous* z over the
*whole* universe at month-start, with **no trend gate** and regardless of whether
a dip just fired. The A1 design is an **event** trigger (z ≤ −2) restricted to
**uptrend** names — a different lens. The horizon study
(`horizon_extended.csv`) does show the *event*-conditioned, trend-gated multiday
dip carrying positive edge. The honest reading: the dip edge, to the extent it
exists here, lives in the **event tail + the 200-day trend gate**, *not* in the
cross-sectional ranking of the raw signal. As a standalone cross-sectional dip
sorter, A1 does not pass.

---

## Supporting check 4 — turnover / fire-count (§7.2)

Fresh-trigger counts across the 91-name universe over the 5-year window
(`turnover_firecount.csv`):

| Detector | fires / instrument / yr | universe fires / yr |
|---|---|---|
| 52wk-high ≥ 0.95 | 5.1 | ~465 |
| 12-1 mom > 0 & > 200-day MA | 4.7 | ~425 |
| drop z (W=10) ≤ −2 | 3.0 | ~276 |

A given name newly tags each of these **3–5×/yr**, versus the live Scanner's
near-daily firing — the "low turnover by construction" claim in §5(c) holds.
These are state-entries, not one-bar twitches.

## Supporting check 5 — vol-normalization audit (§7.3)

Per-instrument fire counts, fixed-% threshold vs its z-score equivalent, with
the universe split at the median annualized vol (`volnorm_audit_summary.csv`):

| Trigger | low-vol mean fires | high-vol mean fires | high/low ratio | corr(vol, fires) |
|---|---|---|---|---|
| **fixed** bounce (−2%/1d) | 20.9 | 85.8 | **4.11×** | **+0.76** |
| z bounce (−2σ/1d) | 30.8 | 31.9 | 1.04× | −0.22 |
| **fixed** multiday (−8%/5d) | 2.2 | 13.2 | **5.93×** | **+0.88** |
| z multiday (−2σ/5d) | 19.0 | 19.3 | 1.01× | −0.29 |

Textbook confirmation of **design rule 2**. The fixed-% thresholds fire **4–6×
more often on the high-vol half** of the universe (and fire counts correlate
+0.76 / +0.88 with vol) — they are measuring volatility, not dislocation. The
z-score versions fire **equally** across the vol split (ratio ≈ 1.0, correlation
≈ 0): "a −2σ move" means the same thing on a gilt ETF and a 3× ETP. Re-expressing
every `%` constant as a z-score (overlay O1) is, as the note argued, the
cheapest high-leverage fix.

---

## Bottom line

- **12-1 momentum (B1): pass.** Roughly monotone, drift-survived, and — uniquely
  — *strengthening* at 63d. The strongest cross-sectional content of the three;
  the laggard bucket is the most reliable edge. Wire it into the v3 simulator.
- **52wk-high proximity (B3): marginal.** Right sign and best top-bucket win-rate,
  but non-monotone and washing out by 63d — attenuated as §6 predicted. Use it
  trend-gated, not as a standalone ranker.
- **Vol-normalized drop z (A1): fails as a cross-sectional dip-buy.** The
  most-dipped bucket carries no positive edge; the only reversion is recent
  *winners* fading. Any dip alpha lives in the event tail + trend gate, which
  this sort deliberately does not condition on — so this result narrows where to
  look, it does not kill A1 outright.
- **Both overlay checks pass cleanly:** turnover is low (3–5 fires/name/yr) and
  fixed-% thresholds demonstrably over-fire the volatile names (4–6×), motivating
  the z-score normalization.

A flat or wrong-signed sort is a *useful* result: it says the cross-sectional
content isn't there to mine, and points the next build at the event-and-trend
conditioning where the v3 horizon study already found the edge.
