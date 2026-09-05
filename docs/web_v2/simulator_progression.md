# Simulator: persistence and progression

A product note on giving the swing-trading simulator a memory and a sense of
reward, without losing the thing that already works about it. Ideation only —
no code changes proposed for this step, and every recommendation here is meant
to be argued with.

## 1. Where it is today

The simulator (`web/v2/simulator.html`, `js/simulator.js`) is a four-state
machine — `decide` → `trade` → `recap`, or `decide` → `review` when you pass —
laid out in three bands that fill `100dvh` and never scroll. The trading model
is honest in the ways that matter: you commit on the close, you fill at the
next open, the stop is live intraday and a gap fills you at the open, and the
stop ratchets one way only. Results are quoted in percent and in R, with R
pinned to `initialStop` so trailing can never retroactively flatter a trade.

Two things are worth naming before changing anything, because they are the
product, not accidents of implementation:

**It is frictionless.** No sign-in, no setup, no configuration. Deal, decide,
next. The comment at the top of `simulator.js` says so out loud: *"The point is
repetition — hundreds of reps at reading a chart cold — not a strategy
backtest, so nothing is scored or stored."*

**It is compact.** `.sim-status` is capped at `max-height:52px` with
`overflow:hidden` — two rows of chips, and one row (30px) on a landscape phone.
In `trade` mode six chips are already competing for that space. There is no
spare room on this page. Anything new either replaces something, earns its
place in the recap where chips are fewer, or lives somewhere else entirely.

## 2. The tension to design around

Persistence and gamification both pull toward *more* — more UI, more state,
more steps between hands. The whole value of the current design is that there
is nothing between hands.

> **Design constraint:** nothing may be added between finishing one hand and
> starting the next. `NEXT OPPORTUNITY ▸` stays one tap away, always. Every
> feature below is either passive (it records without asking), ambient (it
> shows in space that already exists), or opt-in (it lives on its own page).

There is also a subtler trap. The moment a number is kept, the number becomes
the goal — and a simulator that rewards the wrong number teaches the wrong
habit. A textbook-correct 1R loss on a valid setup is a *good* trade. If the
only thing that fires an animation is a profit, we will have built a machine
that trains people to hate their own stops. That is worse than building
nothing.

## 3. Part A — persistence

### 3.1 The record is a *hand*, not a trade

Log every deal, including passes. A pass is a decision, and selectivity is
arguably the most valuable skill the simulator teaches — you cannot measure it
if the record only contains trades. Roughly:

| Field | Source | Why |
|---|---|---|
| `played_at` | wall clock | streaks, "today" scoping |
| `ticker`, `sector` | `S.ticker`, `S.sector` | coverage milestones, sector bias |
| `decision_date` | `S.bars[S.dIdx].d` | so a hand can be re-dealt via `?t=&d=` |
| `outcome` | `traded` \| `passed` | selectivity |
| `side` | `long` \| `short` | the long/short split is usually damning |
| `entry`, `initial_stop`, `risk_pct` | `S.trade` | risk sanity, not just result |
| `r`, `pct` | `tradeStats()` | the result |
| `days_held` | `curIdx − entryIndex` | patience |
| `exit_reason` | `stop` \| `manual` \| `time` \| `gapped` | *how* it ended |
| `trailed`, `used_be` | stop ≠ `initialStop` | stop discipline |
| `revealed` | `S.revealed` | did you peek before deciding? |
| `fwd_20d` | review-mode stats | what a pass avoided or missed |

That is ~15 fields, call it 150 bytes of compact JSON per hand. A thousand
hands is 150 KB.

The `?t=<ticker>&d=<date>` debug params already deal a fixed hand. Storing the
ticker and date means any logged hand is replayable from its record — which is
worth more for learning than any statistic. "Show me the three worst hands I
ever played" is a genuinely great feature and it comes almost free.

### 3.2 Where it lives — local first, Neon later

The cockpit already has a sanctioned backend: Neon Postgres with Auth and
Row-Level Security, used by Trades, Positions, Portfolio and Requests via
`js/neon.js`. It works and it syncs across devices.

**It is still the wrong choice for phase one.** Every page that uses Neon is
gated behind `requireAuth()`, and the simulator is the one v2 page that is
deliberately open. A sign-in wall in front of "deal me a chart" would cost more
than the sync is worth.

**Recommendation: `localStorage`, and only `localStorage`, for the MVP.**

- Zero friction, works on the first visit, survives a refresh.
- Already the storage layer the site trusts — the Neon auth session lives there.
- The failure mode is honest and small: clear your browser, lose your record.
  Say so once, in the UI, and offer an export.
- Cap the log (2,000 hands, FIFO) and keep a rolling aggregate alongside the
  raw rows, so the stats page never has to parse everything to draw a header.

**Phase two, if and only if the habit sticks:** a `sim_hands` table in Neon,
RLS-scoped like every other private table, with the local log as the write-
ahead buffer that syncs when a session exists. The upgrade path should be
"sign in and your local record uploads" — never "sign in to start recording."
Design the local schema now so that migration is a straight column mapping.

An export/import button (download the log as JSON) covers the device-move case
in the meantime, and costs an afternoon rather than a schema.

### 3.3 What to measure — and what to refuse to

The metrics chosen here *are* the product. Proposed headline set:

- **Expectancy (avg R per trade)** — the one number. Everything else explains it.
- **Win rate** paired with **avg win R / avg loss R**. Neither means anything
  alone; shown together they tell you which kind of trader you are.
- **Worst loss in R.** The simulator models gap-through-stop fills, so losses
  larger than 1R genuinely happen. This number is where you find out whether
  your stops are surviving contact with reality.
- **Selectivity** — hands traded ÷ hands dealt.
- **Long vs short expectancy, split.** Most people are quietly terrible at one
  side and have never seen it written down.
- **Exit mix** — stopped / manual / time exit. A high time-exit count means
  trades are being held without a thesis until the 60-day runway ends them.
- **Stop discipline** — share of trades where the stop was trailed, and share
  that reached break-even.

Deliberately **not** included:

- **A currency balance or equity curve in pounds.** The simulator has no
  position sizing, so any monetary figure is invented. Inventing one teaches
  the user to think in a number the game does not actually model.
- **Total percent return.** Same problem, one step removed — it silently
  implies a fixed size across trades of wildly different risk.
- **Any ranking, league table, or comparison to other users.** Not the point,
  and the site is single-player by design.

**R is the currency of this game.** A cumulative-R curve *is* honest — it is
just the sum of the numbers the simulator actually produces — and it is the one
chart worth drawing. Draw that, and nothing denominated in money.

### 3.4 Say how much the numbers are worth

At twelve hands, an expectancy of +0.4R is noise wearing a suit. A simulator
that displays it flatly is teaching overconfidence — the exact vice the thing
exists to cure.

Recommendation: metrics below a sample threshold render dimmed
(`color:var(--dim)`) and carry a provisional marker, with a plain line like
`PROVISIONAL · 12 of ~30 hands`. Above the threshold they render in `--ink`.
This is one CSS class and a comparison, it costs nothing, and it is completely
on-brand for a repository whose other pages are research notes.

### 3.5 Where the record surfaces

Three candidate homes, and I think two of them should both happen:

**(a) An ambient strip on the simulator page — yes, but only in `recap` and
`review`.** Those modes use four or five chips against `trade` mode's six, so
there is room for one more. Something like `TODAY 6 · +2.3R · W3`. It appears
at exactly the moment the user is receptive (they have just finished a hand)
and is absent while they are deciding, when it would be a distraction and,
worse, an anchor — knowing you are on a three-win streak is precisely the
information that should not be in your head while you size up the next chart.

**(b) A dedicated page — yes.** `sim-record.html`, added to `PAGES` in
`nav.js`, holding the full stats, the cumulative-R curve, the hand log, the
replay links, and export/import. This is where the analysis lives, it is
scrollable, it has no layout budget problem, and it follows the established
cockpit page pattern exactly.

**(c) A fifth mode inside the simulator — no.** It crowds the state machine
that is currently easy to reason about, and it buys nothing over (b).

## 4. Part B — progression and reward

### 4.1 Three principles

1. **Reward the process, not just the outcome.** A profitable close gets a
   celebration. A clean stop-out on a valid setup gets a *different*,
   quieter acknowledgment — call it `STOP HELD` — rather than silence.
   Silence after a loss is itself a message, and it is the wrong one.
2. **Streaks must track things the user controls.** See below.
3. **Nothing blocks the next hand.** No modal, no dismiss button, no
   "continue". Animations play in place, over the chart and the chips, while
   `NEXT OPPORTUNITY ▸` stays live underneath the whole time.

### 4.2 Celebrations

Fire on entering `recap`, tiered by result so the big ones stay big:

| Result | Treatment |
|---|---|
| ≥ +3R | Full sequence + milestone toast if it is a personal best |
| ≥ +1R | Result chip counts up, green sweep across the price panel |
| > 0 | Result chip flashes green, brief |
| Stop held (≈ −1R, no gap) | `STOP HELD` mark on the stop line, neutral-cyan, quiet |
| Gapped through stop | No animation. A note, plainly. This is the lesson |

On vocabulary: the cockpit is a terminal, not an arcade — the skill is explicit
that v2 dropped the v1 pixel look. So no confetti, no emoji, no sparkles. The
native celebration language here is **the tape**: digits ticking up like a
price feed, a scanline sweep across the price panel, the result chip pulsing
its border, a brief bloom on the exit marker. Fast — 600–900ms end to end.

All of it belongs in `cockpit.css` as `@keyframes` against existing variables
(`--win`, `--cyan`, `--loss`), triggered by a class the page module toggles.
No library, no canvas, no new dependency. And wrap the lot in
`@media (prefers-reduced-motion: reduce)` with a static end-state fallback.

### 4.3 Streaks — which are honest, which are traps

**Session streak (consecutive days played) — recommend.** Pure habit
formation, zero perverse incentive. It rewards showing up, which is exactly
what "hundreds of reps" requires. This is the highest-value streak in the whole
design and the least dangerous.

**Green streak (consecutive profitable closes) — recommend, carefully.** You
asked for it and it is genuinely fun. The risk is real though: a user three
wins deep who does not want to break the run is a user who will not take a
stop. Mitigations: show it as a transient badge in the recap, never as a
headline metric on the record page; never write copy that implies a streak is
at stake before a decision; and keep it out of the `decide`-mode status strip
entirely.

**Discipline streak — recommend, and make it the one with status.**
Consecutive hands where the stop was set within a sane risk band and the trade
ended by stop or by decision rather than by running out of runway. This is a
streak you keep by trading well and *cannot* keep by trading scared, which is
the exact opposite incentive to the green streak. If only one streak gets
prominence on the record page, it should be this one.

**Explicitly not:** win-rate streaks, "don't lose your streak" nudges, anything
with a countdown, anything that punishes passing.

### 4.4 Milestones

Collection-style, unlocked once, listed on the record page and announced with a
one-line toast in the recap band:

- **Volume** — 10 / 50 / 100 / 250 / 500 / 1,000 hands. Directly rewards the
  repetition the simulator is for.
- **Coverage** — 25 / 100 distinct tickers, all 11 GICS sectors traded. Fights
  the natural tendency to only recognise the setups you have already seen.
- **Craft** — first +3R trade, first profitable short, first trade trailed to
  break-even and then stopped out in profit, first 10-hand discipline streak.
- **Habit** — 3-day, 7-day, 30-day session streaks.

Milestones are safe to be generous with because none of them reward being
*right*. They reward showing up, seeing variety, and doing the mechanics well.

## 5. Proposed scope

**MVP — the whole of "simple".**

1. Log every hand to `localStorage` (schema §3.1), including passes.
2. Ambient `TODAY n · ±xR · Wn` chip in `recap` and `review` only.
3. Tiered CSS celebration on `recap`, plus the `STOP HELD` acknowledgment,
   with `prefers-reduced-motion` handled.
4. Session streak and green streak, computed from the log.
5. `sim-record.html`: headline stats with provisional-sample dimming, the
   cumulative-R curve, the hand log with replay links, export/import JSON.

That is one new page, one storage module, and a CSS block. No backend, no
library, no change to `sim-engine.js` or the trading model — everything above
reads state the engine already produces.

**Phase two, if the habit sticks.** Discipline streak and milestones; the
long/short and exit-mix breakdowns; "worst three hands, replayed"; and the Neon
sync with local-first writes.

**Parked, on purpose.** Position sizing and a currency balance. Any social,
sharing, or leaderboard feature. Difficulty modes. Notifications or reminders.
Scoring passes as if they were trades.

## 6. Risks

- **Metric capture.** Whatever goes on the record page becomes the target.
  This is the reason for §3.3's exclusions and for giving the discipline streak
  more prominence than the green streak.
- **The 52px band.** Verify at 375px wide *and* in landscape before committing
  to the ambient chip — the `max-height:30px` media query leaves one row.
- **Local-only loss.** Users will lose records. Set the expectation in the UI
  from day one rather than apologising later; ship export in the MVP.
- **Animation fatigue.** What delights at hand 5 irritates at hand 200. Keeping
  the sub-1R tier genuinely brief is what makes the ≥3R tier still land.
- **Selection bias in the record.** Decision dates are drawn at random from the
  last five years, which were mostly a bull market. A flattering long
  expectancy may be the sample, not the skill. Worth a line of copy on the
  record page.

## 7. Open questions

1. **The green streak** — headline it, or keep it a transient recap badge? I
   lean transient, for the reasons in §4.3, but it is your simulator and your
   fun that is the point of the exercise.
2. **Should passes be scored at all?** Counting them (selectivity) is clearly
   right. Scoring them — "that pass avoided a −2R" — is tempting and might
   teach hindsight bias instead of judgement. Recommend counting only in MVP.
3. **Provisional threshold** — 30 hands is a defensible round number, but the
   right answer depends on how many hands a sitting actually produces. Worth
   measuring once the log exists rather than guessing now.
4. **Does the record page belong in the main nav** (an eleventh entry in the
   already-crowded app bar), or reached only from the simulator's recap?
5. **Session streak timezone** — local midnight, or something more forgiving
   like a rolling 30-hour window, so a late-night session does not break a run?
