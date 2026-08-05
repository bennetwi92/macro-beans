# PLAN — Portfolio Rebalancing Policy Study

**Status:** awaiting review before implementation.
**Branch:** `claude/portfolio-rebalancing-research-h1dooi`
**Date:** 2026-08-05

---

## 0. Hypothesis under test

> "After a market crash with a flight to safety into gold, rebalancing more
> frequently is beneficial, because you systematically sell gold high and buy
> equities low."

Treated as a hypothesis. The study is designed so that it can come back
**false**, **true only in specific regimes**, or **indistinguishable from
noise** — and so that each of those three outcomes is reportable.

The pre-registered prior (stated now, before results, so it cannot be
retro-fitted): the *direction* of the effect will likely be positive in crash
windows, but the *magnitude* will be small relative to the sampling noise of a
four-event sample, and the risk-control benefit will dominate the return
benefit. The study is built to falsify that too.

---

## 1. Repository placement

`CLAUDE.md` mandates topic subdirectories, and takes precedence over the
brief's generic layout. Mapping from the brief's requested structure to this
repo's conventions:

| Brief asks for | Lands at |
|---|---|
| `report.md` | `docs/rebalancing/report.md` |
| `README.md` | `docs/rebalancing/README.md` (reproduction instructions) |
| `src/` | `src/rebalancing/` (typed library code) |
| — | `scripts/rebalancing/run_study.py` (one-command entry point) |
| `charts/` | `data/rebalancing/charts/*.png` |
| `results/summary.csv` | `data/rebalancing/results/summary.csv` |
| raw data cache | `data/rebalancing/cache/*.csv` (**committed**, so a re-run is byte-reproducible without network) |

This is Track 1 (research/studies) in `CLAUDE.md`. Nothing under `web/`,
`scripts/site/`, or `.github/workflows/` will be touched.

Deviation to flag: the repo's `MarketStore` / DuckDB layer is **not** used.
It caches OHLCV for a US research universe; this study needs FRED macro
series, LBMA fixings, and spliced total-return indices that the registry does
not model. A self-contained, committed CSV cache is the reproducible choice
here. `src.data.paths` **will** be used for repo/data locations.

---

## 2. Data — what is actually available (probed, not assumed)

Availability was tested against the live endpoints before writing this plan.

### 2.1 Access notes (environment-specific, will be documented in the code)

- **yfinance works**, but only when passed a `curl_cffi` session with
  impersonation **disabled**. The library's default Chrome TLS fingerprint is
  reset by this environment's egress proxy. One-line workaround, documented at
  the call site.
- **Stooq (the brief's stated fallback) is unavailable** — it now serves a
  JavaScript proof-of-work challenge to non-browser clients. `pandas-datareader`
  against Stooq returns HTML, not CSV. Fallback replaced by FRED + LBMA
  (below), which are in several respects *better* sources than Stooq.
- **FRED works** via `pandas-datareader`.
- **LBMA works** (public JSON endpoint).

### 2.2 Series and provenance

| Role | Source | Ticker/ID | History | Notes |
|---|---|---|---|---|
| Global equity TR (USD) | yfinance | `ACWI` | 2008-03-28→ | Adjusted close = total return |
| … splice segment 2 | yfinance | `VTSMX` + `VGTSX` | 1996-04-29→ | 55/45 daily-rebalanced blend ≈ ACWI's US weight in that era |
| … splice segment 3 | yfinance | `VFINX` | 1980-01-02→ | **US-only** — documented compromise for the earliest window |
| Intermediate govt bonds (USD) | yfinance | `IEF` | 2002-07-30→ | 7–10y Treasury ETF |
| … splice segment 2 | yfinance | `VFITX` | 1991-10-28→ | Vanguard Intermediate-Term Treasury, closest duration match |
| Gold (USD **and GBP**) | LBMA | `gold_pm.json` | 1968-04-01→ | Daily PM fix, both currencies natively — avoids a synthetic FX cross for gold |
| Gold cross-check | yfinance | `GLD` | 2004-11-18→ | Validation only, to confirm the LBMA series tracks the investable ETF |
| GBP/USD | FRED | `DEXUSUK` | 1971-01-04→ | USD per GBP, daily |
| USD cash | FRED | `DTB3` | 1954→ | 3M T-bill, accrued daily |
| GBP cash | FRED | `IUDSOIA` | 1997-01-02→ | SONIA, daily |
| … GBP cash pre-1997 | FRED | `IR3TIB01GBM156N` | 1970→ | UK 3M interbank, monthly, step-interpolated |
| UK-listed sanity checks | yfinance | `VWRL.L` `IGLT.L` `SGLN.L` `IWDA.L` | 2008–2012→ | Not used in the backtest (too short); used to validate that the USD→GBP construction tracks what a UK investor could actually have bought |

### 2.3 The sample-start problem, stated honestly

The brief asks for 1990–present. The binding constraint is the **bond** leg:
the earliest observed intermediate-Treasury total-return series is `VFITX` at
**1991-10-28**. Options considered:

- **Chosen:** headline sample runs **1991-11-01 → present** (~34.8 years).
  The 20-month shortfall against the brief is documented, not hidden.
- **Additionally:** an *optional, clearly-labelled* extension back to 1990
  using a **modelled** 10-year constant-maturity-yield total return
  (FRED `DGS10`, price return from duration + carry). This is a *model*, not
  an observed instrument, and will be reported only as a robustness check,
  never in the headline table.

No series will be fabricated or back-filled silently.

### 2.4 Splice policy

Splices are done by **chaining daily returns**, never by scaling price levels.
Every splice date is recorded in `data/rebalancing/results/splices.csv`, and
each splice gets a validation check: the correlation and return difference of
old vs new series over their **overlap** window is printed and charted. Any
splice with overlap correlation < 0.95 is a hard failure that stops the run.

The equity splice's weakest segment (1991-11 → 1996-04, US-only `VFINX`
standing in for global equity) is the single largest known compromise in the
study. Mitigation: **every headline conclusion is re-run on the
2008-03→present ACWI-only sub-sample**, where no equity splice exists. If a
conclusion survives only on the spliced sample, it is reported as a possible
splice artefact.

### 2.5 Currency

**Headline currency is GBP** — this is a UK investor. Construction:

- Gold: LBMA GBP fix directly (no synthetic cross).
- Equity/bonds: USD total-return index ÷ `DEXUSUK` (USD per GBP).
- Cash: SONIA (GBP), not T-bills, for the Sharpe risk-free rate.

A parallel **USD** run is produced for every table so the FX contribution is
isolable and reportable as its own line, per the brief.

### 2.6 Validation gate (runs before any modelling; prints diagnostics)

1. Calendar alignment — NYSE/LBMA/FRED calendars differ. Build a common
   business-day index; forward-fill **prices** at most 5 days; never
   forward-fill across a gap > 5 business days (hard error instead).
2. Missing-day census per series, printed as a table.
3. Suspicious returns: flag any |daily return| > 10% (equity/bond) or > 8%
   (gold) and print the dates for eyeball inspection against known events.
   Nothing is auto-dropped.
4. Dividend-adjustment check: `Close` vs `Adj Close` divergence must be
   monotone and positive-drifting for each ETF; a flat ratio would mean the
   TR adjustment silently failed.
5. Split check: any single-day price ratio outside [0.5, 2.0] that is *not*
   matched by an adjusted-close move is flagged as a suspected unadjusted
   split.
6. Cross-source check: LBMA gold vs `GLD` adjusted close, daily return
   correlation over 2004→ must exceed 0.95 (GLD bleeds ~0.4%/yr of expense —
   expected and reported, not corrected).

---

## 3. Backtest engine (`src/rebalancing/engine.py`)

Fully typed. Single code path — **every** policy runs through identical
machinery, so no policy gets an accidental advantage.

- State: unit holdings per asset, evolved daily by asset total returns.
- Policy interface (pluggable):
  ```python
  class Policy(Protocol):
      name: str
      def rebalance_targets(
          self, day: int, date: pd.Timestamp, weights: NDArray[np.float64],
          target: NDArray[np.float64], state: PolicyState,
      ) -> NDArray[np.float64] | None: ...   # None = no trade today
  ```
- Trades execute at the **same day's close** on information available at that
  close. That is a mild look-ahead in the strictest sense; it will be
  explicitly flagged, and a `--exec-lag 1` sensitivity (trade at next close)
  will confirm the conclusions are not lag-sensitive.
- Contributions: optional monthly cash inflow, applied before the policy runs.

### 3.1 Policies compared

| Family | Variants |
|---|---|
| Calendar | monthly, quarterly, semi-annual, annual, **never** (buy-and-hold/drift) |
| Threshold — absolute | ±5pp band on any asset |
| Threshold — relative | ±25% of target weight (the "5/25 rule") |
| Hybrid | check monthly / check daily, trade only on band breach (±5pp and ±25%) |
| Cash-flow only | direct contributions to the most-underweight asset, **never sell** |
| Opportunistic | rebalance whenever equity drawdown from rolling 1-year high exceeds 15% / 20% (and a 12-month re-arm lockout) |

Also run as controls: **constant-mix (daily rebalanced)** as the theoretical
upper bound on rebalancing intensity, and, for the decomposition, a
**constant-mix at each policy's own realised average weights**.

### 3.2 Portfolios

60/40 EQ/BOND · 60/20/20 EQ/BOND/GOLD · 40/30/30. Target weights are a
constructor parameter (`TargetWeights` dataclass), never hard-coded in
policy or engine code.

### 3.3 Costs

Modelled per unit of traded notional, not as an annual haircut:

- Half bid-ask spread: equity ETF 4bp, gilt ETF 3bp, gold ETC 6bp (LSE
  retail-size defaults; sourced and cited in the report).
- Platform commission: £5.95 flat per trade → converted to bps against a
  configurable portfolio size (default £100,000), so commission drag is
  correctly *smaller* for large portfolios and *dominant* for small ones. A
  £10k-portfolio sensitivity is run because that changes the ranking.
- **FX:** an important nuance the brief's framing invites getting wrong — a
  UK investor buying a **GBP-quoted LSE ETF** pays *no explicit FX
  conversion charge*; the currency exposure is unhedged inside the NAV but
  there is no per-trade FX spread. FX cost is therefore modelled as **0bp for
  the base case (LSE-listed)** and as **50bp** in a sensitivity representing a
  platform charging FX on US-listed lines. Both are reported.
- Every cost parameter lives in one `CostModel` dataclass, and the whole study
  re-runs at 0.5× and 2× cost.

---

## 4. Metrics (`src/rebalancing/metrics.py`)

Per policy × portfolio × currency: CAGR, annualised volatility, Sharpe
(excess over GBP cash), Sortino, max drawdown, Ulcer index, annual one-way
turnover, realised cost drag in bps/yr, terminal wealth, **mean absolute
deviation of realised weights from target**, mean/max realised equity weight,
number of trades, and years-to-recover from max drawdown.

### 4.1 Return/risk decomposition (the part that stops false winners)

For each policy, the excess CAGR over the monthly benchmark is split:

```
Δ CAGR = allocation effect + rebalancing effect + cost effect
```

- **allocation effect** = CAGR of a constant-mix portfolio at the policy's
  *realised time-average weights* − CAGR of constant-mix at *target weights*.
  This is the "you just held more equities" component.
- **cost effect** = measured directly from the executed trades.
- **rebalancing effect** = residual, i.e. the genuine volatility-harvesting /
  timing contribution.

A policy whose entire edge is the allocation effect will be explicitly named
as *not outperforming — taking more risk*. Return-per-unit-of-volatility and
per-unit-of-drawdown are reported alongside raw CAGR for exactly this reason.

---

## 5. Statistics

1. **Rolling windows.** All 10-year and 20-year overlapping windows; report
   the *fraction* of windows in which each policy beats monthly, plus the
   inter-quartile range of the difference — not a single full-sample number.
2. **Stationary block bootstrap** (Politis–Romano), geometric block length
   with mean 63 trading days (chosen a priori to span a quarter and preserve
   short-horizon autocorrelation), 2,000 replicates, **seed fixed at 42**.
   Resampling is done on the *joint* daily return matrix so cross-asset
   correlation is preserved. Implemented vectorised across replicates (all
   2,000 paths stepped simultaneously), which is why the full study runs in
   minutes not hours.
   Output: the distribution of CAGR difference between each policy and
   monthly; the share of replicates where the sign flips; a bootstrap p-value.
3. **Explicit noise verdict.** For every headline comparison, the report
   states one of: *distinguishable from noise*, *not distinguishable*, or
   *directionally consistent but within noise*. No comparison is reported
   without one of those three labels.
4. **Multiple-testing honesty.** The number of policy variants scanned is
   stated up front, and any policy selected *because* it topped the table is
   labelled as selected-in-sample, with its bootstrap distribution shown
   rather than its point estimate.

---

## 6. Crash-conditional analysis (the core question)

Peak/trough windows: 2000-03-24→2002-10-09, 2007-10-09→2009-03-09,
2020-02-19→2020-03-23, 2022-01-03→2022-10-12 (dated off the study's own
spliced equity series, not hard-coded from memory).

Measured per event: policy return within the drawdown window, and from the
**trough** over the following 1/3/5 years; plus the gold and bond behaviour
inside each window that drives it.

**Sample-size caveat is structural, not cosmetic.** With n=4 events, the
standard error of the mean event effect is enormous. The report will show the
per-event effects individually (never just their mean), state the n=4 limit in
the executive summary, and run a bootstrap over *events* to show the width of
the interval. If three of four events agree and the fourth disagrees, that is
reported as such, not averaged away.

---

## 7. Correlation instability

- Rolling 250-day gold/equity and bond/equity correlations, GBP and USD.
- A decade-by-decade correlation table, plus a conditional table
  (correlation in the worst 5% of equity days vs all days) — the safe-haven
  claim is a *conditional* claim and must be tested conditionally.
- **2022 gets its own treatment:** equities and bonds fell together, the case
  where the diversification premium mechanically collapses. The report will
  quantify what that regime did to each policy rather than treating it as an
  anecdote.

---

## 8. Charts (`data/rebalancing/charts/`)

1. `equity_curves.png` — log-scale wealth by policy (60/20/20, GBP)
2. `drawdowns.png` — drawdown comparison
3. `rolling_correlations.png` — gold/equity + bond/equity, 250d, with 2022 marked
4. `turnover_vs_return.png` — scatter, sized by cost drag
5. `bootstrap_distributions.png` — CAGR-difference distributions vs monthly
6. `weight_drift.png` — realised weights over time, drift vs monthly vs 5/25
7. `crash_windows.png` — per-event policy performance, 4 panels
8. `rolling_10y_difference.png` — rolling 10y CAGR difference vs monthly
9. `decomposition.png` — allocation vs rebalancing vs cost, stacked

House `dataviz` skill conventions will be followed for palette/typography.

---

## 9. Literature (cited separately from own results)

The report will keep a hard wall between **(a) published research, cited with
live links** and **(b) this study's own backtest**, in separate sections with
different headings. Intended citation set — every link will be verified live
before publication, and anything I cannot verify will be dropped rather than
cited from memory:

- Fernholz & Shannon (1982) on stochastic portfolio theory / excess growth
- Booth & Fama (1992), *Diversification Returns and Asset Contributions*
- Willenbrock (2011), *Diversification Return, Portfolio Rebalancing, and the
  Commodity Return Puzzle*, FAJ
- Erb & Harvey (2006) on commodity returns and rebalancing
- Vanguard, *Best practices for portfolio rebalancing* (Jaconetti, Kinniry,
  Zilbering)
- Dichtl, Drobetz & Wambach (2016) on rebalancing strategy performance
- Jegadeesh & Titman (1993) and Moskowitz, Ooi & Pedersen (2012) for momentum
  horizons; De Bondt & Thaler (1985) for long-horizon reversal
- Politis & Romano (1994) for the stationary bootstrap

---

## 10. Deliverables checklist

- [ ] `docs/rebalancing/report.md` — 2,000–3,000 words, BLUF executive
      summary, plain-English mechanism, evidence, recommendation, embedded
      charts, **strongest case against my own recommendation**, confidence
      levels per conclusion, bias/overfitting flags, taxable-GIA appendix,
      20-minute annual decision rule including contributions, and a standing
      "research, not financial advice" note.
- [ ] `docs/rebalancing/README.md` — one-command reproduction.
- [ ] `src/rebalancing/` — typed modules: `data.py`, `validate.py`,
      `engine.py`, `policies.py`, `metrics.py`, `stats.py`, `charts.py`,
      `config.py`.
- [ ] `scripts/rebalancing/run_study.py` — `python scripts/rebalancing/run_study.py --all`.
- [ ] `data/rebalancing/results/summary.csv` + supporting CSVs.
- [ ] `data/rebalancing/charts/*.png`.
- [ ] `requirements.txt` for the study (pinned).
- [ ] Incremental commits: data layer → engine → policies → stats → charts →
      report.

---

## 11. Known risks I am accepting, and how they are disclosed

| Risk | Disclosure |
|---|---|
| Equity splice is US-only 1991–1996 | Every conclusion re-run on ACWI-only 2008→ |
| n=4 crashes | Per-event reporting + event bootstrap + stated in exec summary |
| Same-close execution | `--exec-lag 1` sensitivity |
| Policy-parameter scanning (band widths, triggers) | Count of variants stated; winners labelled selected-in-sample |
| Survivorship in fund proxies (VFINX/VFITX survived) | Stated; effect on a broad index proxy is small but non-zero |
| Cost assumptions are the biggest single lever on ranking | 0.5×/2× cost sensitivity is a headline table, not an appendix |
| GLD/LBMA expense-ratio divergence | Measured and reported, not corrected |

---

## 12. Open questions for the reviewer

1. **Sample start.** Accept 1991-11 (observed instruments only), or extend to
   1990-01 using a modelled bond series flagged as modelled?
2. **Portfolio size for cost modelling.** Default £100,000 — is that the right
   base case, or should the headline be a smaller ISA-scale pot where flat
   commissions bite harder?
3. **Contributions.** Assume regular monthly contributions in the base case
   (realistic for an accumulating ISA/SIPP), or a lump-sum-only base case with
   contributions as a variant? This materially affects how good cash-flow
   rebalancing looks.

Sensible defaults are already chosen for all three (1991-11; £100k; monthly
contributions as a *variant* with lump-sum as base) so implementation can
proceed without answers if the reviewer prefers to see results first.

---

*This study is research, not financial advice.*
