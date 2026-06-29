# v3 signals: redesigning the Scanner's detectors for longer horizons

[v3](?r=guides-scanner_trade_strategy_v3) settled the *horizon* question: the
Scanner plateaued because it traded at the one hold where a cost-bound account
cannot win, and the fix is to hold for weeks, not days. It proposed two engines
(an alpha dip-reversion sleeve at ~1 month, a beta momentum-rotation sleeve) but
left the **signals themselves** — the six detectors that decide *what fires* —
largely as-is. That is the gap this note closes.

The six detectors were all built for a few-day hold. You can lengthen the hold
all you like, but if the *trigger* still describes a single-bar twitch, you are
holding a multi-week position on a thesis that expired on day two. **A long
horizon needs long-horizon signals.** This note reviews the six against the
longer horizon, states the three design rules a long-hold signal must obey, and
proposes a redesigned + expanded signal menu — each one grounded in the
literature and in your own horizon data.

Same caveat as v3, kept deliberately: this is a **research-and-design note**.
Per the brief, it is built on published evidence and basic arithmetic from data
you already have — **not** a new backtest. The numbers I quote are from the
v3 horizon study (`data/scanner_strategy_v2/horizon_extended.csv`) and the cost
arithmetic; the per-signal account curves are the build that follows (§7).

---

## 1. Why the current six are short-horizon by construction

Strip each detector to what it actually measures and the problem is structural,
not a tuning issue:

| Detector | Trigger | What it measures | Lookback | Why it's short-horizon |
|---|---|---|---|---|
| Buy the Bounce | 1-day close ≤ −2% | a single down *bar* | 1 day | one bar is mostly bid-ask bounce / noise; nothing about it persists for a month |
| Red Streak | 3 consecutive down closes | a 3-day *event* | 3 days | 3 down days has ~no predictive content past a few days; v2's worst loser |
| Multi-Day Drop | 5-day move ≤ −8% | a real *dislocation* | 5 days | the best of the dips — but the −8% is fixed, not vol-scaled |
| Breakout High | close > prior 20-day high | a 1-month *event high* | 20 days | a 1-month breakout; its long-hold gain is pure drift (see §5) |
| MA Cross Up | close crosses 200-day MA | a one-shot *regime flip* | 200 days | right idea (trend), wrong form: rare, whippy, a single bar |
| Tight Range | 10-day spread ≤ 6%, first day | a brief *squeeze* | 10 days | a 10-day base is too short to precede a multi-week move |

Three failures recur, and they define what a fix has to do:

1. **They fire on *events*, not *states*.** "Price fell 2% today" or "price
   crossed the MA today" is a one-bar fact. A position you intend to hold for a
   month needs a *condition that is still true next week* — "this name is in a
   confirmed uptrend and just pulled back," not "this name had one red bar."
2. **Their thresholds are fixed percentages, not volatility-scaled.** A −2% day
   in a gilt ETF is a five-sigma event; in a 3× leveraged ETP it is a Tuesday.
   The same `−2%` / `−8%` / `6%` constant means wildly different things across a
   124-instrument universe, so the detector fires far too often on the volatile
   names and almost never on the calm ones. The Scanner *already computes* the
   z-score machinery to fix this (`_move_z` in `scanner_lib.py`) — it just uses
   it for display, not for the trigger.
3. **Only two carry any trend context (cross, and breakout implicitly).** The
   dip detectors fire on *any* drop, including knives falling out of downtrends.
   v2 bolted on a 200-day uptrend *gate* to patch this; a long-horizon signal
   should bake the trend in, not gate it after the fact.

---

## 2. Three rules for a long-horizon signal

Everything below follows from three rules, each backed by the evidence v3
already assembled plus the papers in §6:

1. **State, not event.** The trigger must describe a condition that persists
   across the hold (in an uptrend, near its highs, oversold-but-recovering),
   so the thesis is still alive on day 20. Robust effects live at 1–12 month
   horizons ([Moskowitz–Ooi–Pedersen][tsmom]); single-bar effects are mostly
   microstructure noise that dies in days.
2. **Normalize by volatility.** Replace fixed-% thresholds with z-scores or
   ATR-multiples so a trigger means the same thing on every instrument and in
   every regime. This is also the single cheapest improvement — the code
   already has the vol and z-score functions.
3. **Separate alpha from beta, and trend-gate both.** Your own data (§5) splits
   the book cleanly: the *dip* setups carry real, growing alpha; the *momentum*
   setups carry only beta you were churning away. Design the two engines to
   each do its one job, and keep the 200-day trend filter on both — it is the
   standard mitigation for the momentum crash tail
   ([Daniel–Moskowitz][crashes]).

---

## 3. The redesigned signal menu

Organized by the two v3 engines. For each I give the **trigger** (the basic
calculation), the **hold**, the **research basis**, and how it maps to code that
already exists.

### Engine A — alpha: reversion *inside* an uptrend

The dip setups are where the genuine edge lives, and §5 shows it *grows* with
horizon. The job here is to keep the real signal (a dislocation) and drop the
noise (single bars, falling knives, fixed thresholds).

**A1 — Multi-Day Drop, volatility-normalized** *(improved `multiday`)*
- **Trigger:** the trailing 5–10-day return ≤ **−2σ** of that name's own
  trailing ~1-year distribution of same-window moves — i.e. `_move_z(close, t,
  W) ≤ −2`, instead of the fixed `−8%`. Optionally require 200-day uptrend.
- **Hold:** ~21 trading days (time-exit), wide disaster stop.
- **Basis:** the well-documented reversal effect is a *monthly* phenomenon, not
  a daily one — [Jegadeesh (1990)][jeg] showed prior-**month** losers outperform
  over the next month. Measuring the dislocation over ~a month and holding ~a
  month aligns the signal with the horizon at which reversion actually pays.
  Vol-normalizing makes "a −2σ drop" comparable across the whole universe.
- **Code:** `multiday` already has the cleanest long-horizon profile in §5;
  swap its fixed threshold in `_trigger_arrays` for the existing `_move_z` test
  and lengthen `HOLD["multiday"]`.

**A2 — Pullback-in-uptrend** *(new — the disciplined replacement for bounce &
streak)*
- **Trigger:** 200-day trend up **AND** price has pulled back to/below its
  50-day MA (or `RSI(14) < ~35`), **AND** a first up-close / re-cross back above
  a short MA confirms the bounce has started.
- **Hold:** ~21 days, wide stop, time-exit.
- **Basis:** this is the short-term-reversal side of time-series momentum,
  harvested *deliberately and only in uptrends*. Momentum studies routinely
  **skip the most recent month** because short-term reversal contaminates it
  ([Moskowitz et al.][tsmom]) — A2 turns that contamination into the entry:
  buy the dip, but only in names that are structurally going up. It replaces
  Buy-the-Bounce (one noisy bar, no context) and Red Streak (falling knives,
  v2's worst loser) with a single trend-aware reversion signal.

### Engine B — beta: low-turnover trend / momentum

§5 is blunt: at long horizons the current momentum detectors (breakout, cross)
have **no bankable alpha** — their long-hold gains are market drift. So Engine B
should stop trying to extract alpha from short-term breakouts and instead
capture beta cheaply with the proven low-turnover momentum frame — and use the
*one* momentum signal the literature says actually predicts at horizon.

**B1 — 12-1 absolute (time-series) momentum** *(new)*
- **Trigger:** 12-month total return, **skipping the most recent month**, > 0
  and price > 200-day MA. Equal-weight; rebalance monthly.
- **Hold:** ~1 month, rolled.
- **Basis:** time-series momentum is positive in nearly every asset class at a
  12-month lookback / 1-month hold, with the skip-month standard
  ([Moskowitz–Ooi–Pedersen][tsmom]). This is the workhorse v3's Engine B is
  built on.

**B2 — Cross-sectional relative strength** *(new)*
- **Trigger:** each month, rank the non-leveraged universe by a blended 3/6/12-
  month total return; hold the **top 3–5** that are *also* above their 200-day
  MA. Equal-weight, monthly rebalance.
- **Hold:** monthly, rolled.
- **Basis:** Faber's rotation beat buy-and-hold ~70% of the time over 80+ years
  ([StockCharts][faber]); Antonacci's dual momentum trades 2–3×/yr and halved
  drawdowns ([QuantifiedStrategies][dual]) — treat as a robust low-turnover
  frame, not a magic lookback ([fragility note][fragility]).

**B3 — 52-week-high proximity** *(new — the *correct* long-horizon breakout)*
- **Trigger:** `close / (252-day high) ≥ ~0.95` (within 5% of the 1-year high),
  in a 200-day uptrend.
- **Hold:** weeks-to-months, time-exit / held while condition true.
- **Basis:** this is the key upgrade. [George & Hwang (2004)][gh] found nearness
  to the 52-week high predicts returns over 6–12 months *better* than past-return
  momentum — **0.65%/mo vs 0.38%** — and, decisively, those returns **do not
  reverse in the long run**. Contrast your own data: the 20-day Breakout's
  drift-removed edge goes *negative* by 42–63 days (§5). The 20-day breakout is
  a noise high with no lasting alpha; the 52-week high is the breakout that
  actually carries predictability at horizon. Replace `breakout` with B3.

**B4 — Moving-average trend *state*** *(improved `cross`)*
- **Trigger:** hold while price is above a **rising** 200-day MA (or use a
  50/200 golden-cross *regime*); use distance-above-MA as a strength score.
  This is a persistent **state**, not the one-bar cross event.
- **Hold:** held while true (this is also Engine B's gate).
- **Basis:** MA timing is a documented cross-sectional anomaly, strongest on
  higher-vol names and surviving costs ([Han–Yang–Zhou (2013)][hyz]); Faber's
  10-month-MA rule is the canonical retail form ([StockCharts][faber]). The raw
  `cross` event has *negative* drift-removed edge at every horizon in §5 —
  because a single whippy cross is mostly noise; the *state* of being in an
  uptrend is the thing with value. Demote `cross` from a trade trigger to the
  trend filter it should always have been.

**B5 — Volatility-contraction base breakout** *(improved `range`)*
- **Trigger:** realized volatility (or the trailing range) at a multi-**month**
  low — e.g. a 6-month low in 20-day realized vol — followed by an up-breakout
  from the base, in an uptrend. Widen the window from 10 days to a real base.
- **Hold:** weeks, time-exit.
- **Basis:** longer consolidations precede larger moves (the classic base-
  breakout idea). `range`'s drift-removed edge is small but *positive and
  growing* in §5 (+0.45% at 21d → +0.65% at 63d), so it is worth keeping — but a
  10-day "base" is too short to mean much; lengthen it. Lower priority than
  A1/A2/B3.

### Cross-cutting overlays (apply to all signals)

These are not new detectors — they are improvements that lift every signal:

- **O1 — Vol-normalized thresholds everywhere.** Re-express every `%` constant
  as a z-score or ATR-multiple (rule 2). Cheapest, highest-leverage change.
- **O2 — Volatility-targeted sizing.** Scale each position inversely to its
  recent realized vol. [Moreira–Muir (2017)][volman] show scaling exposure down
  when variance is high materially raises Sharpe and tames the crash tail —
  exactly momentum's weakness. `realised_vol()` already exists; reuse it for
  sizing, not just display.
- **O3 — Residual / idiosyncratic momentum** *(higher-effort refinement of
  B1/B2).* Rank on **beta-adjusted** returns rather than raw returns.
  [Blitz–Huij–Martens (2011)][resmom] find residual momentum earns ~2× the
  risk-adjusted profit of total-return momentum with less crash risk. Needs a
  market-proxy regression per name — flag as a v3.1 enhancement, not v3.0.
- **O4 — Absolute-momentum escape hatch.** When a name (or the universe's
  breadth) falls below its 200-day MA, rotate that slice to a short-gilt/cash
  ETF — the dual-momentum defence ([Antonacci][dual]). Already in v3 Engine B;
  reaffirmed here as a signal-level rule.

---

## 4. Old → new: the verdict

| Existing detector | Verdict | Successor |
|---|---|---|
| Buy the Bounce | **Transform** | absorbed into **A2** (pullback-in-uptrend) — keep the dip, add trend context |
| Red Streak | **Retire** | none — pure noise, v2's worst loser; its long-hold "gains" are just beta (§5) |
| Multi-Day Drop | **Keep + improve** | **A1** — vol-normalize the threshold, lengthen the hold |
| Breakout High | **Retire short form** | **B3** (52-week-high) — the breakout that actually predicts at horizon |
| MA Cross Up | **Demote** | **B4** — keep as the trend *state*/filter, not a trade trigger |
| Tight Range | **Transform / deprioritize** | **B5** — lengthen the base to multi-month |

Net: of the six, **one is retired outright (streak), two are demoted/transformed
into states or filters (cross, range), one is improved in place (multiday), and
two genuinely new alpha/beta signals are added (A2, B1/B2/B3).**

---

## 5. The basic calculation: why these pay where the old ones didn't

No new backtest — just the v3 horizon table and cost arithmetic. Two numbers
from your own data carry the whole argument.

**(a) Cost is fixed per trade, so the signal must clear ~0.30% — which only a
long hold's move can do.** A round-trip on a liquid LSE ETF costs ~0.25–0.30%.
Over 3 days an average ETF moves ~0.7% gross, so even a *good* edge inside that
is a fraction of the cost. Over a month it moves several percent and the same
0.30% barely registers. In the horizon table every setup crosses net-zero
around **~10 trading days** and is solidly positive by a month — the break-even
hold is ~2 weeks, and everything below that is feeding the spread.

**(b) The *drift-removed edge* column sorts the signals into alpha vs beta — and
tells you exactly which to keep.** Reading `edge%` (gross move with market drift
removed) at the 63-day hold:

| Setup | Style | Drift-removed edge: 21d → 63d | Read |
|---|---|---|---|
| Multi-Day Drop | dip | +0.69% → **+2.94%** | real alpha, **growing** → improve as **A1** |
| Buy the Bounce | dip | +0.71% → **+1.58%** | real alpha, growing → fold into **A2** |
| Tight Range | range | +0.45% → +0.65% | small alpha, growing → **B5** |
| Red Streak | dip | +0.15% → +0.35% | ~zero alpha; net gains are beta → **retire** |
| Breakout High | momo | +0.02% → **−0.26%** | alpha *gone* at horizon → replace with **B3** |
| MA Cross Up | momo | −0.37% → **−1.12%** | negative alpha → demote to a **filter (B4)** |

This is the empirical spine of the whole redesign:

- The **dip** setups have positive, horizon-growing drift-removed edge → they
  carry alpha, so Engine A keeps and sharpens them (A1, A2).
- The **momentum** setups (breakout, cross) have ~zero or *negative*
  drift-removed edge at long holds → they have no alpha to bank, only beta. So
  Engine B stops mining them for signal and instead (i) captures the beta
  cheaply via low-turnover rotation (B1/B2) and (ii) uses the *one* momentum
  signal the literature says doesn't decay — the 52-week high (B3).

**(c) Turnover.** B1/B2/B3 on a monthly rebalance make ~12 decisions/yr vs the
Scanner's ~125; A1/A2 at a 21-day hold cut Engine A's turnover ~3–4×. Selectivity
was the only reliable lever in v2 — these signals pull it by construction.

---

## 6. What I won't oversell

- **Hypotheses, not yet measured on your book.** Every signal here is grounded
  in published evidence and your horizon table, but none has been run through
  the v2 account simulator on your universe. That is the next build (§7), per
  the brief. I expect improvement; I have not yet *measured* it.
- **Most cited results are US single-stock studies; you trade LSE ETFs.** ETFs
  are already diversified, so cross-sectional dispersion is smaller and B2's
  relative-strength has less to sort. Residual momentum (O3) needs per-name
  betas. Expect the effects to attenuate vs the headline paper numbers.
- **Momentum still crashes in rebound bears.** B1/B2/B3 inherit the tail; the
  200-day filter (B4) and vol-targeting (O2) mitigate, they do not eliminate
  ([Daniel–Moskowitz][crashes]).
- **One sample, one mostly-rising regime** — same caveat as v1/v2/v3. The
  *direction* of the §5 split (dip = alpha, momo = beta) is robust; the precise
  numbers are illustrative.

---

## 7. The next experiments (concretely, pre-backtest)

These are "basic calculation" sanity checks — *sorts, not account curves* — to
run before committing to the full v3 simulator:

1. **Forward-return sort by signal.** Each month, bucket the universe by (i)
   52-week-high proximity, (ii) 12-1 momentum, (iii) the vol-normalized 5–10d
   drop z-score; read the mean next-21d and next-63d forward return by bucket.
   If the buckets sort monotonically, the signal has cross-sectional content —
   this is a one-script check on the existing price cache, not a backtest.
2. **Fire-count / turnover per detector.** Count fires-per-year for each new
   trigger on the universe to confirm the turnover claim in §5(c).
3. **Vol-normalization audit.** Compare fire counts of fixed-% vs z-score
   thresholds per instrument to confirm the fixed thresholds over-fire the
   volatile names (the rule-2 motivation).

Then wire the surviving signals into `scanner_lib.py` with a configurable hold
(v3 §7.1) and run them through the v2 simulator with honest accounting — that is
where these proposals turn into numbers.

---

## Sources

- Moskowitz, Ooi & Pedersen, *Time Series Momentum* (2012) — [JFE][tsmom] · [PDF](https://elmwealth.com/wp-content/uploads/2017/06/timeseriesmomentum.pdf)
- George & Hwang, [*The 52-Week High and Momentum Investing*][gh], Journal of Finance (2004) — [PDF](https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf)
- Jegadeesh, [*Evidence of Predictable Behavior of Security Returns*][jeg] (1990) — short-term (monthly) reversal
- Blitz, Huij & Martens, [*Residual Momentum*][resmom], Journal of Empirical Finance (2011) — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2319861)
- Moreira & Muir, [*Volatility-Managed Portfolios*][volman], Journal of Finance (2017)
- Han, Yang & Zhou, [*A New Anomaly: The Cross-Sectional Profitability of Technical Analysis*][hyz], JFQA (2013) — [PDF](https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Han_Yang_Zhou.pdf)
- Daniel & Moskowitz, [*Momentum Crashes*][crashes], JFE (2016)
- Faber, [*Sector Rotation*][faber] (StockChartsschool); Antonacci, [*Dual Momentum*][dual] (QuantifiedStrategies); ThinkNewfound, [*Fragility Case Study: GEM*][fragility]

[tsmom]: https://www.sciencedirect.com/science/article/pii/S0304405X11002613
[gh]: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2004.00695.x
[jeg]: https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1990.tb05110.x
[resmom]: https://ideas.repec.org/a/eee/empfin/v18y2011i3p506-521.html
[volman]: https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12513
[hyz]: https://profiles.wustl.edu/en/publications/a-new-anomaly-the-cross-sectional-profitability-of-technical-anal/
[crashes]: https://www.sciencedirect.com/science/article/pii/S0304405X16301490
[faber]: https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/fabers-sector-rotation-trading-strategy
[dual]: https://www.quantifiedstrategies.com/dual-momentum-trading-strategy/
[fragility]: https://blog.thinknewfound.com/2019/01/fragility-case-study-dual-momentum-gem/
</content>
</invoke>
