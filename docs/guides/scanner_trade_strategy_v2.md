# Turning Scanner Signals into Trades, v2: an honest rebuild

[Strategy v1](?r=guides-scanner_trade_strategy) gave a rules-based way to trade
Scanner rows with £1000 and an honest backtest that admitted it lost to a global
tracker. You read it, pushed back hard on the methodology, and asked for a v2
that fixes the accounting and the exit model — and that proves its gains with
numbers, not adjectives. This is that rebuild.

The short version is uncomfortable and worth saying first: **most of your
feedback was right, and following it made the strategy look *worse*, not
better — because v1's headline was flattered by an unrealistic assumption.**
Once the exits are modelled the way a real resting stop actually fills, v1's own
rules turn £1000 into **£542**, not the £1,348 it advertised. The useful work in
v2 was then clawing that back to a positive-expectancy, low-drawdown system —
and the lever that did it was the one you told me to drop.

This note states, for each point you raised, what I did, what the data showed,
and whether I kept or rejected it.

---

## How to read the comparison

Everything below runs on **one freshly-pulled dataset** (124 LSE instruments,
10y of daily *open/high/low/close*, plus GBPUSD/GBPEUR), so every column is
strictly comparable. Two consequences:

1. **v1 re-run on today's data makes £1,214, not its published £1,348.** Nothing
   changed in v1's rules — Yahoo continuously re-adjusts dividend/split history,
   so a refetch a few months later shifts which signals clear the thresholds.
   The benchmark barely moves (£1,697 vs £1,699 published), which is the tell
   that the port is faithful and the drift is in the data, not the code.
2. The **fair** comparison is therefore not "v2 vs v1's old number." It is
   **v1's rules and v2's rules, both costed honestly, on the same prices.**

### Headline (all figures GBP, £1000 start, Jul 2021 → Jun 2026)

| Metric | v1 rules, v1 accounting | v1 rules, **honest** accounting | **v2 (core)** | v2 (selective) | Buy & hold MSCI World |
|---|---|---|---|---|---|
| Final value | £1,214 | £542 | **£1,095** | **£1,224** | £1,767 |
| Total return | +21.4% | −45.8% | +9.6% | +22.4% | +76.7% |
| Annualised (compounded) | +4.0% | −11.6% | +1.8% | +4.1% | +12.1% |
| Worst drawdown | −26.3% | −52.8% | **−16.8%** | **−8.1%** | −19.1% |
| Trades | 675 | 793 | 322 | 146 | 1 |
| Win rate | 49.9% | 46.4% | 53.4% | 56.2% | — |
| Avg trade | +0.13% | −0.25% | +0.16% | +0.70% | — |

**The honest, like-for-like result: v2 roughly doubles v1 (£542 → £1,095, and
£1,224 in its selective form), turns a −45.8% loss into a positive return, and
cuts the worst drawdown from −52.8% to −16.8% / −8.1%.** That is the marked,
quantified gain you asked for.

**The two things I won't bury:**

- **v2 does not beat v1's *published* £1,348 (or the £1,214 refetch) in raw
  pounds.** It can't, honestly — that number leaned on a close-only stop that a
  real resting order would not have given you. v2 wins decisively only when v1 is
  costed by the same honest rules.
- **v2 still loses to just buying a world tracker** (£1,767), exactly as v1 did.
  It loses by *less pain* — its worst drawdown is now shallower than the
  market's — but if the goal is the highest pound figure in five years, the
  tracker is still ahead. The defensive-satellite verdict from v1 survives.

---

## Your feedback, point by point

### 1. Use daily highs and lows; model stops *and* targets honestly — **KEPT (and it's the whole story)**

**What I did.** Refetched the full daily bar (high/low, not just close) and
rewrote the exit engine to check the stop against each day's **low** and the
target against each day's **high**, *intraday*, filling at the level the moment
it's touched (gap-through-the-open fills at the open). On the rare day a bar
spans both the stop and the target, I assume the **stop** filled first — the
conservative read, since we can't see intraday order.

**What the data showed.** This single change is the most important number in the
whole exercise. v1 only ever checked the stop on the *closing* price, so an
intraday dip that recovered by the close never stopped you out. A real resting
stop order does not work that way — it fills when price trades through it. Model
that honestly and v1's rules collapse:

| | v1 close-only stop | honest intraday stop |
|---|---|---|
| Final value | £1,214 | **£542** |
| Worst drawdown | −26.3% | −52.8% |
| Avg trade | +0.13% | −0.25% |

You were right to demand this, and it *does* cut both ways as you said — targets
also fill more easily — but **not symmetrically.** This is a mean-reversion book:
"Buy the Bounce" works precisely because price dips and then recovers. An
intraday stop sells you at the bottom of exactly the dip you were paid to sit
through. The downside trigger fires far more often than the upside one, so
honest intraday accounting is a large net negative. **Kept — it is reality, not
a dial.** Everything after this is about surviving it.

### 2. Intraday exit on alert (don't wait for the close) — **KEPT**

Folded into the same engine: a fired target alert exits *that day* at the target
level, not at the next open. On its own this is a small positive (you bank
spikes you'd otherwise give back overnight); it can't rescue the stop problem
above. Kept because it matches how you actually trade.

### 3. Redefine success as "max price reached," size the target off a **low**
percentile of that distribution — **PARTLY KEPT, and your dial is backwards**

**Pushback first.** "Max price achieved during the period" is the right thing to
*study* but the wrong thing to *bank*. You can't capture the max; you can only
pre-commit a target and capture it *if* it prints before the stop or the clock.
Crediting the max would silently inflate every result. So v2 uses the historical
**max-favourable-excursion (MFE)** distribution only to *place* the target, and
credits trades at their **realised** exit.

**What I did.** For each signal I compute the MFE of comparable past events
(same setup, same trend regime, trailing 5y) and set the take-profit at a chosen
percentile of that distribution. Then I swept the percentile — on the proper v2
base (honest exits + the confluence gate + wide stops from §6/§2):

| Target percentile | Target-hit rate | Win rate | Avg trade | Final value |
|---|---|---|---|---|
| p30 (your "low, high-probability") | 64% | 66.5% | +0.01% | £926 |
| p50 | 46% | 58.8% | +0.07% | £961 |
| p70 | 29% | 52.9% | +0.04% | £1,023 |
| **p75** | **27%** | **53.4%** | **+0.16%** | **£1,095** |
| p80 | 21% | 52.8% | +0.08% | £1,046 |
| fixed 3R (v1's wide alert) | — | 51.6% | −0.01% | £991 |
| no target (clock only) | — | 51.4% | −0.14% | £919 |

**What the data showed — and where your instinct inverts.** A *low* percentile
does exactly what you predicted: a high probability of being reached (p30 hits
64% of the time, 66% win rate). But that high hit-rate is a trap. It caps your
winners at a tiny gain while the honest intraday stop leaves your losers
**full-size** — so expectancy collapses to zero. Expectancy *rises* as you lift
the target, peaking around the **75th percentile**, then fading as the target
gets too rare to fill. So I **kept the mechanism** (set the target from the MFE
distribution — it beats both v1's fixed 3R alert and a clock-only exit) but
**rejected the low percentile** in favour of a high one. Net of the whole change,
the MFE target is a modest positive; the bigger lesson is that "reached with
high probability" and "worth trading" point in opposite directions here.

### 4. Add a volatility regime — **TESTED; kept only as an optional risk filter, not an edge source**

**What I did.** Added 20-day realised vol and a high/low regime flag (vs each
name's own trailing-median vol), conditioned the EDGE on (trend × vol), and
tested both gating entries by regime and requiring the vol-conditioned edge to
be positive.

**What the data showed — two different answers.**

- *Does vol predict edge?* Barely. Average forward EDGE is **+0.141%** in
  high-vol regimes and **+0.134%** in low-vol — statistically a coin-flip. The
  signal's edge is **not** regime-dependent, and conditioning on it just
  fragments already-thin samples. As an *edge* source, rejected.
- *Does avoiding high vol help the realised book?* Yes, a lot — because of §1.
  High-vol days are where wide intraday ranges tag stops on noise and dip-buys
  fail. Trading **only low-vol regimes** lifts v2 from £1,095 to **£1,224** and
  *halves* the drawdown (−16.8% → −8.1%).

So vol is a **risk filter, not an alpha filter.** I ship it as the **"selective"
v2** variant, but flag it as the lever I trust least: the sample drops to 146
trades and it is the most in-sample-optimised choice here. The honest core v2
does not depend on it.

### 5. More horizons — **TESTED, REJECTED (overfitting)**

I measured per-day edge for every setup across holds of 2–20 days. The momentum
setups do decay fast — breakout's per-day edge peaks at a 2-day hold, not its
current 10; MA-cross at 2, not 20 — while range prefers longer and bounce/streak
are flat across the grid. But **picking each setup's best-in-sample hold off a
7-point grid is textbook curve-fitting**, and v2 is already strong on the
original holds. I kept the existing horizons and noted the one robust takeaway
(momentum signals fade quickly, so don't lengthen their holds). Adding horizons
did not earn its place.

### 6. Confluence shouldn't rescue weak strategies — **YOUR HYPOTHESIS WAS WRONG; confluence is v2's biggest edge**

This is the one to read twice. You argued that if the individual setups are
unprofitable, requiring several to agree shouldn't help, and told me to drop
confluence if it didn't. I tested it as a hard **gate** (require ≥2 setups firing
on the same name the same day):

| | conf ≥1 (gate off) | **conf ≥2** | conf ≥3 |
|---|---|---|---|
| Final value | £789 | **£1,095** | £1,007 |
| Worst drawdown | −45.4% | **−16.8%** | −2.4% (only 5 trades) |
| Trades | 913 | 322 | 5 |

Requiring two setups to agree is **the single most powerful filter in the whole
study** — it lifts the honest book from £789 to £1,095 and cuts the drawdown
from −45% to −17%. **Kept, prominently.**

**But you were half-right, and it's worth being precise about *why* it works.**
It is **not** that confluence rescues weak setups. Isolate the individually-weak
non-bounce setups and require confluence, and they stay weak — actually a touch
worse (avg −0.49% with confluence vs −0.17% without, on a small sample). What the
gate really does is **selectivity**: it concentrates the book from ~910 trades
into ~320 calmer, higher-conviction days, and turnover is the enemy of a thin
edge (v1 taught us that). So your underlying instinct — "a pile of bad signals
doesn't become good" — is correct at the per-setup level. You were wrong only
that this makes confluence useless; as a *turnover gate* it's the best lever we
have. Kept as a gate; not relied on to fix bad setups.

### 7. FX costs on USD/EUR names — **KEPT; you were right, it was a quiet drag**

**What I did.** 45 of the 124 instruments (and IWDA itself) are quoted in
USD/EUR. v2 translates every fill to GBP through the daily cross *and* charges
Trading 212's 0.15%-per-conversion FX fee on those names (0.30% round-trip, on
top of spread).

**What the data showed.** FX alone knocks v1 from £1,214 to **£1,049** — about
**−14% of final equity, ~3 points of CAGR** — quietly eaten, exactly as you
suspected. It also raises the *benchmark* to £1,767 (sterling weakened over the
window, so a USD world tracker is worth *more* in GBP — v1 ignored this and
understated the bar it had to clear). Both effects are real and now modelled.
Kept.

### 8. Compounding — **CONFIRMED; your worry was unfounded**

I checked: **v1 already compounds.** Position size is `risk% × live equity`, and
equity is marked to market every day, so profits are reinvested — there are no
flat stakes anywhere in v1 or v2. The annualised figures in every table above
*are* the compounded outcome (CAGR). Your premise — that reliably capturing ~1%
over a 3–5 day window should compound to something meaningful over a year — is
sound arithmetic; the problem was never that v1 failed to compound, it's that
the per-trade edge, once costed honestly, isn't reliably ~1%. It's closer to
+0.16% gross of the lagging market. Nothing to change; worth confirming out loud.

---

## What v2 actually is

Stripped to the playbook, v2 keeps v1's shape (morning check, risk-sized entries,
one position per name) and changes five things:

1. **Honest intraday exits.** Stops and target alerts fill the moment price
   trades through them, against the day's range — not on the close.
2. **A confluence gate.** Only take a name when **≥2 Scanner setups fire on it
   the same day.** This is the core filter; it roughly thirds your turnover.
3. **Wide disaster stops, lean on the clock.** Size the stop off the *intraday*
   MAE with a wide floor/cap (5%–20%) so normal noise can't tag it; let the
   time-exit do most of the selling (190 of 322 exits are the clock, 86 the
   target, only 46 the stop).
4. **A high-percentile MFE target** (~75th) instead of v1's fixed 3R alert.
5. **FX modelled explicitly** on USD/EUR names.

Optionally (the **selective** variant), also **skip high-volatility regimes** —
better risk-adjusted numbers, fewer trades, but the least robust of the levers.

### Where v2 makes and loses its money

| Setup | Trades | Win rate | Avg trade | Total P&L |
|---|---|---|---|---|
| MA Cross Up | 77 | 55.8% | +0.73% | **+£100** |
| Buy the Bounce | 105 | 54.3% | +0.39% | **+£93** |
| Tight Range | 25 | 60.0% | +0.70% | +£35 |
| Breakout High | 73 | 49.3% | −0.29% | +£6 |
| Multi-Day Drop | 3 | 66.7% | +0.44% | +£3 |
| Red Streak | 39 | 48.7% | −1.07% | **−£105** |

Bounce still pulls its weight, as in v1. The honest surprise is **MA-Cross**
(slow, 20-day momentum) becoming the top contributor once confluence concentrates
it into high-conviction trends — and **Red Streak** becoming the clear loser
(buying into falling knives that the intraday stop then guts). A v3 would
probably retire Red Streak; I've left it in so the comparison stays clean.

### Year by year (v2 core vs the market, GBP)

| Year | v2 | MSCI World |
|---|---|---|
| 2021 (H2) | +7.8% | +9.7% |
| 2022 | −3.3% | −8.8% |
| 2023 | +7.2% | +18.1% |
| 2024 | −3.8% | +22.0% |
| 2025 | +5.4% | +12.9% |
| 2026 (H1) | −4.2% | +10.2% |

The defensive shape v1 had is now *sharper*: v2 never has a bad year (worst is
−4.2%) and protected you in 2022, but it badly lags every bull year. It is a
capital-preservation sleeve with a positive but small edge, not a growth engine.

---

## What this means for the Scanner itself

You asked that fixing the strategy feed back into a better scanner. Three changes
earn it:

1. **Surface confluence as a first-class rank, not a tie-breaker.** It is the
   strongest single filter we found. The Scanner already computes a `×2/×3`
   badge — it should be promotable to a hard filter ("≥2 only") in the daily
   view, because that's where the positive expectancy lives.
2. **Show an intraday-MAE-based stop suggestion, and a high-percentile MFE
   target**, not a fixed multiple. The row already has the data; v2 shows the
   close-only MAE understates the dip you'll actually endure.
3. **Flag the FX names.** A small "FX" tag on USD/EUR-quoted rows would remind
   you that those carry a ~0.3% round-trip conversion drag the GBp names don't.

A volatility column is worth showing for context, but the data says **don't**
gate the *signal* on it — gate the *risk* on it, if at all.

---

## Honest limitations (unchanged from v1, plus new ones)

- **One sample, one regime.** Five mostly-rising years. The confluence gate and
  the p75 target are chosen partly in-sample; treat the exact numbers as
  illustrative. The *direction* (honest stops hurt, confluence helps, low-
  percentile targets are a trap) is robust across every configuration I ran.
- **Still daily data.** Intraday H/L is a big step up from close-only, but a
  real stop can fill *between* the day's high and low at a price I can't see; I
  fill at the level, which is mildly optimistic on gappy names.
- **FX translation is modelled; FX *timing* is not.** I convert at daily closes,
  not at the second you trade.
- **Survivorship.** Today's instrument list; dead ETFs aren't here.
- **v2 selective leans on 146 trades.** Small. Trust the core v2 first.

---

## The scripts

Everything is reproducible under `scripts/scanner_strategy_v2/` (the v1 scripts
are untouched at `scripts/scanner_strategy/`):

| Script | What it does |
|---|---|
| `fetch_prices.py` | Pulls 10y of split/dividend-adjusted daily **OHLC** for the universe **plus GBPUSD/GBPEUR** into a local cache. |
| `scanner_lib.py` | Reuses v1's tested detectors and adds intraday MAE, the MFE percentile distribution, and the volatility regime. |
| `backtest.py` | The GBP, compounding account with switchable exit/target/stop/FX modes, so any change can be ablated. |
| `run_experiments.py` | Runs every table in this note — the accounting attribution, the MFE sweep, the confluence/vol/horizon tests, and the final v1-vs-v2 comparison. |

Run them in order with `/usr/local/bin/python3`. The one knob that moves the
result most is no longer spread — it's **how honestly you model the stop**, then
**turnover** (the confluence gate), then **FX**.
