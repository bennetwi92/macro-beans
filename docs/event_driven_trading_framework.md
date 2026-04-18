# Event-Driven Trading Framework

A reusable process for turning a geopolitical / macro event + a directional view into a sized trade executable from a UK retail IBKR account.

## How to use this document

Provide Claude with:
1. **The event** (what happened, when, where)
2. **Your view** (which direction, which asset, why)
3. **Current account size** and max % willing to risk

Claude will follow the steps below to produce a concrete trade with instruments, sizing, entry rules, and exits.

## Operating notes

**Asset class scope**: this framework is cross-asset. Examples and historical analogs are oil-heavy because that was the first deployment case, but the process applies to equities, FX, rates, commodities, and crypto equally. Do not force-fit the oil analogs when the event is in a different asset class — use Step 3 as a *template* for structuring regime classification, and research fresh analogs for the relevant asset.

**Desktop vs. mobile use**: scripts in `scripts/` are for desktop re-analysis and backtest extension. When Claude is invoked from mobile (no code execution), work from the inline tables in this document — the regime classification (Step 3), sizing comparison (Step 5), and scenario envelope (Step 7) contain the data needed to produce a trade proposal without running any scripts.

---

## Step 1 — Event validation

Before doing anything else, verify the event is real and understand what is already priced in.

**Research tasks (delegate to web search):**
- Confirm the event happened, when, and in what sequence. Flag any rhetoric flips in the preceding weeks
- Pull closing prices of the primary asset (e.g., Brent, WTI) on the last trading day before the event, and the trajectory over the preceding 2–4 weeks
- Find sell-side analyst price targets / scenario ranges for the most relevant desks (Goldman, JPM, MS, RBC, Citi for oil; similar for other asset classes)
- Quantify what's already priced vs. what a "full escalation" scenario would price in

**Red-flag questions to answer honestly:**
- Is this the *first* shock of this type, or the nth in an ongoing cycle? (nth gets faded)
- Has the market already taken out most of the move on prior news? (If yes, the trade thesis weakens)
- Was the event telegraphed in advance? (If yes, positioning is already set → fade risk)
- Did Friday's close already react to the event? (If yes, Monday's gap is not clean)

**Decision rule**: if the event is the nth re-flip in an active cycle, or if >70% of the scenario pricing is already in, **reduce position size or skip**.

---

## Step 2 — Instrument universe

### Hard constraints for UK retail at IBKR

**PRIIPs/MiFID II blocks US-domiciled ETFs.** You cannot open positions in:
- UCO, SCO, USO, BNO, GUSH, OIH (oil)
- SDS, SPXU, SSO, SPXL (S&P)
- SQQQ, TQQQ, QLD (Nasdaq)
- Any ProShares/Direxion US LETF

**Options on US ETFs ARE allowed** (PRIIPs exemption) — but commission drag and IV crush make them unsuitable for budgets under ~£2000.

### LSE-listed LETF universe (UCITS/ETC, UK retail accessible)

**Oil:**
| Ticker | Exposure | Currency line |
|---|---|---|
| 3OIL.L | +3x WTI | USD |
| 3BRL.L | +3x Brent | USD |
| 3OIS.L | -3x WTI | USD |
| 3SOI.L | -3x WTI | GBp |
| 3BRS.L | -3x Brent | USD |
| 3BSR.L | -3x Brent | GBp |
| PCRD.L | +1x WTI GBP-hedged | GBP |
| SOIL.L | -1x WTI | USD |

**Equity indices:**
| Ticker | Exposure |
|---|---|
| 3USS.L / 3ULS.L | -3x S&P 500 (USD / GBP-hedged) |
| QQQS.L / LQQS.L | -3x Nasdaq 100 (USD / GBP-hedged) |
| 3UKS.L | -3x FTSE 100 — **avoid for oil-up pairs** (FTSE has 13% energy weight, rises with oil) |
| SPY3.L | +3x S&P 500 |
| 3LUS.L | +3x S&P 500 (alt) |

**Gold / safe-haven:**
| Ticker | Exposure |
|---|---|
| SGLN.L | +1x gold (iShares Physical Gold) |
| PHAU.L | +1x gold (WisdomTree Physical Gold) |
| 3GOL.L | +3x gold |

Note: "GBp-traded lines" (3SOI, 3BSR, 3BRL, etc.) are priced in pence but FX-unhedged. True currency hedging requires explicit "GBP Daily Hedged" in the name.

### Options (only if budget ≥£2k)

Options on US ETFs (USO, SPY, QQQ, GLD) bypass PRIIPs and are tradeable. But: commission ~5% round-trip on small premium; IV crush typically eats 10–30% on event entries; theta drain on weeklies. **Not recommended below £2000 budget.**

---

## Step 3 — Historical event study

**Asset class check first.** The regime table and analogs below are oil-specific — built from Saturday oil shocks since USO inception. **If the current event is in a different asset class** (equities earnings/CPI/FOMC, FX central bank action, crypto exchange failure, rates surprise, etc.), **do not force-fit these analogs**. Instead, use the structure of the regime table as a *template* and research fresh analogs via web for the relevant asset. The five regime archetypes below (genuine shock / policy shock / risk-premium / whipsaw-already-priced / telegraphed / escalation-in-priced-markets) generalise across asset classes even though the specific events don't.

Run `scripts/oil_weekend_event_study.py` (desktop only) to pull historical precedent for oil events. For other assets, adapt the script or work from web-researched analogs inline.

**Oil events to benchmark against** (weekend oil shocks, n=7, since USO inception):
- 2011-03-19 Libya intervention
- 2019-09-14 Abqaiq drone attack (supply shock)
- 2023-04-02 OPEC+ surprise cut (Sunday)
- 2023-10-07 Hamas attack on Israel
- 2023-12-23 Houthi Red Sea escalation
- 2024-04-13 Iran→Israel (telegraphed, contaminated)
- 2025-06-21 US B-2 strikes on Iran (escalation-in-priced-markets)

**Regime classification** — identify which prior event is the closest analog:

| Regime | Analog | Typical Monday | T+3 | Setup tells |
|---|---|---|---|---|
| Genuine supply shock | Abqaiq | USO +9–12% | +5–7% | Physical supply removed, market surprised |
| Supply policy shock | OPEC+ 2023-04-02 | USO +5–6% | +5–6% | Producer cartel action, sustainable |
| Risk-premium add | Hamas 2023-10-07 | USO +3–4% | +2% | New conflict risk, no immediate supply hit |
| Whipsaw / already-priced | Houthi 2023-12-23 | USO +2–3% | -2 to -3% | Reopens prior cycle, market fatigue |
| Telegraphed escalation | Iran 2024-04-13 | USO flat/-1% | -3% | Attack pre-announced, intercept expected |
| **Escalation-in-priced-markets** | **B-2 strikes 2025** | **USO -8%** | **-11%** | **War already priced, escalation signals end-game** |

The last regime is the main **downside landmine** — escalations in already-priced markets can CRASH oil on the "sell-the-news" dynamic.

**For Friday-crash setups specifically**, run `scripts/oil_friday_crash_study.py`. Large down-Fridays in USO (>-5%) historically show **continuation**, not mean reversion — Monday typically continues the fade. Only precedent for -10%+ Fridays (Omicron, 2021-11-26) gave a Monday bounce that fully reversed by Wednesday.

---

## Step 4 — Pair construction

If the user wants a pair (relative value) trade rather than single-leg:

**Standard pair templates:**
- **Oil-up thesis with risk-off follow-through**: Long oil LETF + Short Nasdaq (QQQS.L) — Nasdaq has near-zero energy weight, maximum oil-up/stocks-down beta
- **Oil-up thesis with classic hedge**: Long oil + Short S&P (3USS.L) — S&P has 4% energy, slightly dampens pair beta
- **Escalation-amplification**: Long oil + Long gold (3GOL.L or SGLN.L) — both benefit from safe-haven bid, less correlated than stocks-short
- **Avoid**: Long oil + Short FTSE (3UKS.L) — FTSE has 13% energy weight, rises with oil, wrong direction

**Commission reality check**: at IBKR UK, each leg costs ~£3 min per side = £6 round-trip. For a 3-leg portfolio at £100 budget, commissions = 18% drag. **Maximum 2 legs below £500 budget.**

---

## Step 5 — Sizing methodology

Run `scripts/oil_nasdaq_pair_event_study.py` (or adapt) to compare three sizing approaches.

### The three approaches

| Approach | Formula | Use when |
|---|---|---|
| **Vol parity** | w_i ∝ 1/vol_i, sum to 1 | No strong directional view; want balanced risk |
| **Equal notional** | w_i = 0.5 each | Mid-conviction, simpler |
| **Conviction tilt** | e.g. 70/30 or 80/20 to favoured leg | Strong directional view on specific leg |

### Vol parity math (two-leg case)

```
w_leg1 = vol_leg2 / (vol_leg1 + vol_leg2)
w_leg2 = vol_leg1 / (vol_leg1 + vol_leg2)
```

Where `vol_i` = 20-day rolling stdev of daily simple returns on the underlying index (not the LETF).

**Key observation**: when pairing a high-vol asset (oil) with a low-vol asset (equities), vol parity skews heavily toward the low-vol leg. E.g., USO vol 2.2% + QQQ vol 0.9% → w_oil = 29%, w_qqq = 71%. The "oil trade" becomes mostly a stocks trade.

### How to pick

- If your view is "both legs will work directionally" → **equal notional**
- If your view is "I'm confident on leg A, leg B is a hedge" → **conviction tilt toward A (60/40 or 70/30)**
- If your view is "exposure to the theme, no preference on which leg drives" → **vol parity**
- If your view is "leg A will absolutely dominate" → **single leg** (skip the pair)

### Risk-return comparison (historical, oil+nasdaq-short pair)

| Sizing | Mean T+0 | Max gain | Max loss |
|---|---:|---:|---:|
| Vol parity | +2.2% | +£15 | -£9 |
| Equal notional | +3.3% | +£19 | -£14 |
| Conviction 70/30 oil | +5.3% | +£26 | -£18 |

Conviction sizing roughly 2x the upside AND 2x the downside vs. vol parity.

---

## Step 6 — Execution plan

### Go / no-go decision (Sunday evening → Monday 07:30 UK)

- **CME crude electronic open (Sun 23:00 UK)**: watch for gap size and direction
- **Monday 07:30 UK GO criteria**: underlying asset is up ≥+3% from Friday close AND within 1% of overnight highs
- **NO-GO criteria**: <+2% gap OR underlying has faded >2% from overnight high OR any de-escalation headline overnight
- If NO-GO: stand down, trade is off

### Entry timing

- **Do NOT** trade in the LSE opening auction (08:00 UK)
- **Wait 15–20 minutes** for spreads to tighten from auction-level 100–200 bps to continuous-trading 30–70 bps
- **Enter 08:15–08:20 UK**: LIMIT order, marketable (ask + 0.1–0.2%), destination = LSE (not SMART), TIF = DAY

### Order type

- **Plain LIMIT** is sufficient for <£500 position size
- IBKR Adaptive Algo (Urgent priority) adds ~10–20 bps of improvement if desired
- **Avoid**: Market, MOO, TWAP, VWAP, Pegged-to-Midpoint — either overkill at small size or actively harmful on gap days
- **Snap-to-Midpoint** is a reasonable alternative to plain LIMIT (static limit at snapshot-mid + offset)

### Position sizing discipline

- Whole shares only — compute `floor(budget / price)` per leg
- Leave £10–20 buffer in account for commissions and price drift
- Note fill prices; calculate stop and profit levels immediately after fill

---

## Step 7 — Risk management

### Stop losses

- **Hard portfolio stop**: cut all legs if combined P&L reaches **-12% of deployed capital** (2/3 of historical worst-case intraday drawdown)
- **Headline stop**: any de-escalation/negotiation news → cut all legs immediately, regardless of P&L
- **Time stop**: all positions flat by **14:00 UK** (before NYSE opens at 14:30 UK) — NYSE session can reprice violently and undo the European gap

### Take profits

- Trim 50% at **+10%** portfolio P&L
- Trail remaining 50% with stop at breakeven
- Full exit by time stop at 14:00 UK regardless

### Scenario envelope (historical basis)

Calibrate expectations to the regime you're in:

| Regime | P&L at T+0 envelope (per £100) |
|---|---:|
| Genuine supply shock | +£15 to +£26 |
| Moderate bullish | +£5 to +£13 |
| Whipsaw / fade | -£5 to +£5 |
| De-escalation shock | -£10 to -£18 |

Your realistic EV is the weighted average of these — for most "nth-in-cycle" events, EV is roughly flat to slightly negative once you include commissions.

---

## Step 8 — Post-trade review

After closing positions, document:
1. Actual fills (entry, exit, slippage vs model)
2. Realized P&L vs expected envelope
3. Which regime actually played out
4. What the best-informed observer knew at 07:30 UK that Claude didn't
5. Calibration: was my view/conviction justified by the outcome?

Save under `docs/trades/YYYY-MM-DD_<event>_review.md` for future calibration.

---

## Scripts and data references

- `scripts/oil_weekend_event_study.py` — USO reaction to Saturday oil shocks (n=7)
- `scripts/oil_friday_crash_study.py` — Conditional Monday return given Friday magnitude (n=472 down-Fridays)
- `scripts/oil_nasdaq_pair_event_study.py` — Long oil + short Nasdaq pair with vol-parity, equal-notional, and conviction-tilted sizing
- `data/oil_weekend_event_study.csv` — Per-event table
- `data/oil_nasdaq_pair_study.csv` — Pair P&L by sizing method

Adapt these scripts for non-oil events by swapping the event list, underlying tickers, and horizons.

---

## Appendix — PRIIPs workarounds if budget grows

Above £2000 budget, options on US ETFs become viable and give access to the full US LETF universe via synthetics. At that point, consider:
- Options on USO for oil directional exposure (deltas > cash ETF equivalents)
- Options on SPY/QQQ for equity hedges
- Calendar spreads to capture IV crush rather than fight it

Below £2000, stay in LSE-listed ETCs / UCITS LETFs.
