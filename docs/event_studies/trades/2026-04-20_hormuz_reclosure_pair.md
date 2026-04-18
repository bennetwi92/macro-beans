# Trade Record: 2026-04-20 Hormuz Re-closure Pair

## Event

**Date news broke**: Saturday 2026-04-18

**Summary**: Iran's parliament speaker Ghalibaf reversed the foreign minister's Friday announcement that the Strait of Hormuz was "completely open." Iran subsequently fired on tankers transiting Hormuz. This is a *re-closure* within an active 6-week-old Iran-US crisis, not a first-time shock.

**Preceding sequence:**
- Feb 28 – Apr 8, 2026: Hormuz largely blocked following US/Israel air war and Khamenei assassination
- Apr 8: Ceasefire reached
- Apr 13: US naval blockade of Iranian ports begins
- Apr 17 AM: Iran FM Araghchi announces Hormuz "completely open"
- Apr 17 PM: **Brent closes -12.63% at $86.84, WTI closes -15.75% at $79.78** — the Monday price trigger
- Apr 17 evening / Apr 18: Ghalibaf reverses, tanker attacks reported

**Sources** (validated by independent research agent):
- [Axios — Iran closes Strait of Hormuz once again, fires on tankers](https://www.axios.com/2026/04/18/iran-closes-strait-of-hormuz-once-again-fires-on-tankers)
- [NPR — Iran Middle East updates](https://www.npr.org/2026/04/18/nx-s1-5789780/iran-middle-east-updates)
- [Al Jazeera — Iran closes Hormuz again over US blockade](https://www.aljazeera.com/news/2026/4/18/iran-closes-strait-of-hormuz-again-over-us-blockade-of-its-ports)

## Thesis (user view)

Friday's -15.7% WTI crash priced in a bullish-for-equities / bearish-for-oil outcome (Hormuz open + ceasefire). That outcome has now been reversed by Iran's Saturday action. Expect:
1. Oil gap UP at Monday open as the market un-does Friday's reopen pricing
2. Equities gap DOWN on renewed Middle East risk premium + higher oil
3. Europe session (LSE 08:00–14:00 UK) carries the move before NYSE reprices

## Account

- Broker: IBKR (UK retail)
- Cash available: £189
- PRIIPs restrictions apply — no US-domiciled LETFs (UCO, SDS, etc.)

## Analysis performed

### 1. Weekend event study (n=7 Saturday/Sunday oil shocks since 2006)

Ran `scripts/event_studies/oil_weekend_event_study.py`. Key findings:
- Mean USO Monday gap: +3.2% (clean events), range -0.65% to +9.2%
- Dominant historical regimes: supply shock (Abqaiq-like, extends and holds) vs de-escalation shock (B-2 strikes 2025-like, crashes)
- **2025-06-21 US B-2 strikes on Iran** is the closest political analog; USO crashed -8.07% Monday, -12% by T+5 on "sell the news" dynamic

### 2. Friday-crash study (n=472 down-Fridays, USO 2006–2026)

Ran `scripts/event_studies/oil_friday_crash_study.py`. Key findings:
- Friday -15.7% is **off the historical distribution** — only 1 precedent for -10%+ Fridays in USO (Omicron 2021-11-26)
- Omicron precedent: Monday gap +4.7%, close +1.1%, **faded to -5.2% by T+2**
- Base rate for Friday ≤-5%: 50% positive Monday gap, but only 35.7% positive Monday close (mean -3.17%) — momentum continuation, not mean reversion

### 3. Pair event study under three sizings

Ran `scripts/event_studies/oil_nasdaq_pair_event_study.py` on long-oil + short-Nasdaq pair. Key findings:

Clean events (n=6), T+0 close from Friday close:

| Sizing | Mean | Median | Max gain | Max loss |
|---|---:|---:|---:|---:|
| Vol parity (~£25/£75) | +2.2% | +2.1% | +£15 | -£9 |
| Equal notional (£50/£50) | +3.3% | +3.8% | +£19 | -£14 |
| **Oil-tilted 70/30 (£70/£30)** | **+5.3%** | **+6.0%** | **+£26** | **-£18** |

Win rate at T+0 unchanged at 5/7 (71%) across sizings — conviction tilt buys *asymmetry*, not hit rate.

## Instruments

Both tradeable for UK retail at IBKR (LSE-listed ETC, UCITS-exempt but PRIIPs-accessible).

| Leg | Ticker | Exposure | Allocation |
|---|---|---|---:|
| Long oil | **3BRL.L** | +3x daily Brent crude | **£70** |
| Short equity | **QQQS.L** | -3x daily Nasdaq 100 | **£30** |

**Sizing rationale**: Vol parity would allocate ~£25 oil / ~£75 Nasdaq-short given elevated USO realized vol entering Monday. User has explicit directional conviction on oil (Hormuz sensitivity + Friday overshoot reversal) — overrides vol parity to 70/30 oil-tilted. Captures more upside in Abqaiq-regime, accepts deeper drawdown in B-2-regime. Nasdaq short retained as hedge for "Iran escalates further" scenario where stocks also fall.

**Why these specific tickers**:
- **3BRL.L over 3OIL.L**: Brent is the seaborne global benchmark; Hormuz directly threatens Brent-priced flows. WTI (3OIL) is more US-shale-sensitive
- **QQQS.L over 3USS.L**: Nasdaq has ~0% energy weight vs S&P's 4% — maximum oil-up/stocks-down beta, no internal hedge dampening the pair

## Entry plan

### Timeline (UK time)

| Time | Action |
|---|---|
| Sun 18:00 | Headline scan — any Iran de-escalation signal → trade off |
| Sun 23:00 | CME electronic crude opens; note WTI gap magnitude/direction |
| Mon 07:00 | Re-check CME range + overnight headlines |
| **Mon 07:30** | **Go/no-go decision**. GO: WTI ≥+3% AND within 1% of overnight high. NO-GO: WTI <+2% OR >2% off high OR de-escalation headline |
| Mon 08:00 | LSE opens — **do not trade** during opening auction |
| **Mon 08:15–08:20** | **Entry window**. LIMIT orders, marketable (ask +0.1–0.2%), Destination = LSE, TIF = DAY |

### Order specs

- **3BRL.L**: LIMIT buy, ~5 shares (whole shares under £70), destination LSE
- **QQQS.L**: LIMIT buy, ~2 shares (whole shares under £30), destination LSE
- Order type: plain LIMIT (no algos, no Market, no MOO, no Pegged)
- Verify destination is `LSE` not `SMART`

## Exit plan

### Hard rules

| Trigger | Action |
|---|---|
| Portfolio -£12 (approx -12%) | Cut both legs, walk away |
| Any Iran de-escalation headline | Cut both legs immediately, regardless of P&L |
| Portfolio +£10 | Trim 50%, trail remainder with breakeven stop |
| **Mon 14:00 UK** (time stop, before NYSE opens) | Exit all remaining positions |

### Rationale

- NYSE opens at 14:30 UK; historical data shows NYSE session can undo European-session moves on Middle East events
- Historical T+2/T+3 pair returns fade mid-week (win rate drops from 71% to 43%); holding beyond Monday adds variance without expected return
- 2025-06-21 B-2 strikes scenario produces -£18 loss at Monday close extending to -£28 by Friday under 70/30 sizing; time stop limits exposure to the primary catastrophic scenario

## Expected outcome envelope

Rough subjective probabilities conditional on event proceeding as described:

| Scenario | Probability | Monday close P&L | Notes |
|---|---:|---:|---|
| Abqaiq-analog supply shock | 15% | +£15 to +£26 | Requires genuine sustained supply removal |
| Moderate bullish | 25% | +£6 to +£13 | Hamas/OPEC-like risk premium add |
| Whipsaw/fade | 30% | -£5 to +£5 | Houthi-like, market fatigue |
| De-escalation shock | 30% | -£10 to -£18 | B-2 2025 analog, war-premium-already-paid regime |

**Expected value at T+0: roughly flat** (~+£2 on £100). Commission drag (£6 round-trip for 2 legs) makes net EV mildly negative. Trade is taken on conviction, not on statistical edge.

## Known risks and caveats

1. **Event is "nth in cycle", not first-time shock** — market fatigue discounts further rhetoric flips
2. **Friday's -15.7% has no historical precedent** — only Omicron (-11.2%) is close; Omicron bounced Monday then faded
3. **70/30 tilt doubles downside vs vol parity** — -£18 max historical loss vs -£9 under VP
4. **Commission drag ~6% of budget** — £6 round-trip on £100 is material
5. **Currency exposure** — 3BRL.L and QQQS.L are USD-settled GBp-traded lines; FX unhedged. Minor at 1-day horizon
6. **Spread risk at LSE open** — auction-level spreads 100–200 bps; mitigated by waiting 15 min

## Pre-flight checklist (complete Sunday evening)

- [ ] 3BRL.L visible in IBKR with LSE as routable destination
- [ ] QQQS.L visible in IBKR with LSE as routable destination
- [ ] £189 cash available
- [ ] Commission tier noted (IBKR Fixed: £3 min per leg)
- [ ] Alarm set for 07:30 UK Monday for go/no-go
- [ ] Framework document re-read
- [ ] Hard stops written down (Portfolio -£12, time stop 14:00 UK)

## Post-trade review (complete after close Monday)

*To be filled in after trade execution.*

- Actual entry prices: 3BRL.L ____, QQQS.L ____
- Actual fill times: 3BRL.L ____, QQQS.L ____
- Actual exit prices: 3BRL.L ____, QQQS.L ____
- Realized P&L (£): ____
- Realized P&L (%): ____
- Which regime played out: ____
- Primary P&L driver (oil leg vs Nasdaq leg): ____
- Commission total: ____
- Slippage vs expected: ____
- Calibration note — was the 70/30 conviction justified: ____
- Lessons for framework update: ____
