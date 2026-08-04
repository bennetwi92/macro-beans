# SIPP — simplified 4-fund build

*Generated 2026-08 by `portfolio_optimiser.report.build_sipp_simple`. Not
financial advice. Every input lives in `portfolio_optimiser/config/`.*

Replaces the 8-holding SIPP target with four funds, chosen by searching **all 70
four-fund combinations** of the existing SIPP universe under the same
maximise-geometric-growth objective and the same Michaud resampling the main
report uses — not by hand-picking.

## The allocation

Trading 212 SIPP Pie, auto-rebalance on, £20,000 for 2026/27.

| # | Holding | Ticker | Pie % | Job |
|---|---------|--------|------:|-----|
| 1 | Avantis Global Equity (value/profitability) | `AVCG.L` | **35.7** | Global core, tilted to cheap + profitable |
| 2 | Avantis Global Small Cap Value | `AVSG.L` | **29.3** | The highest expected factor premium in the universe |
| 3 | iShares Core MSCI EM IMI | `EMIM.L` | **24.8** | Emerging markets — the diversifier from US/tech |
| 4 | iShares Physical Gold ETC | `SGLN.L` | **10.2** | Crash / inflation-regime hedge |

**Total 100%.** Blended ongoing charge **0.25%/yr** (~£50 on £20,000).
All four are sterling LSE lines, so no FX fee.

**Expected:** geometric **7.78%/yr**, arithmetic 8.59%, volatility 12.69%.
Monte Carlo over 25 years on a £20,000 seed, no further contributions:

| Metric | Value |
|---|---|
| Median terminal | **×7.00** (≈ £140,000) |
| 5th percentile | ×2.43 |
| 95th percentile | ×19.75 |
| P(beat the global tracker) | **97%** |

## Why these four

Every candidate was scored on its own price history rather than the
full-universe matrix — see the estimation-window note below. Among the builds
that keep a genuine hedge **and** rest on the full 211-month history, this is
the best risk-adjusted one:

| Build | geo | vol | Verdict |
|---|---:|---:|---|
| AVWC/AVSG/EMIM/**SGLN** | 7.78% | **12.69%** | **Recommended** |
| AVWC/AVSG/EMIM/**GLIN** | 7.89% | 13.46% | +0.11pp growth for +0.77pp vol, and infrastructure correlates ~0.64 with equity — it is a real asset, not a crash hedge |
| AVWC/AVSG/EMIM/**IWQU** | 8.19% | 12.18% | Highest growth, but 100% equity — no hedge at all, and priced on 157 months not 211 |

**Gold earns the hedge slot** because it is the only holding in the universe
that is genuinely uncorrelated with the book (≈0.04 vs the equity core, against
0.64 for infrastructure). The main report's own caveat applies here: Monte Carlo
assumes normally-distributed returns, so it *understates* the value of a
fat-tail hedge. The modelled numbers therefore flatter the all-equity build.

**JMFP (managed futures) was dropped deliberately**, despite scoring well
(7.98% geo). Two reasons, both about trust rather than modelled return: its
Trading 212 SIPP eligibility is still unconfirmed, and Yahoo's `JMFP.L` price
feed **ends 2020-11**, so any number attached to it rests on 119 months of data
that stop before the 2022 regime the fund exists to handle. Simplifying is the
right moment to drop the holding with the least verifiable data.

## What you give up vs the 8-fund target

Almost nothing on the modelled numbers — but read that carefully.

The 4-fund build shows *higher* modelled growth than the 8-fund target (7.78%
vs 7.41%). That is **not** evidence that simplifying earns you money. Two
things drive the gap:

1. Concentrating into the four highest-CMA holdings mechanically raises modelled
   growth. Given the CMAs, that is real; the CMAs are a transparent prior, not a
   forecast.
2. The 8-fund figure is estimated on a **shorter, older window** (see below), so
   the two are not measured on the same data.

What you genuinely give up is the second-order diversification of XDEW
(equal-weight US), IWQU (quality) and GLIN (infrastructure). The correction in
the 2026-08 currency audit showed IWQU correlates **0.94** with the AVWC core —
so dropping it costs far less than it looks. XDEW at 0.90 is much the same story.

What you gain, beyond four lines instead of eight: **stability**. The 8-fund
target swung EMIM by up to 19 percentage points for a ±1pp shift in the EM
premium, because it held several near-interchangeable global-equity funds that
traded places whenever the assumptions moved. This build's largest response to
any ±1pp CMA shift is **3.6pp**:

| CMA block | −1pp | base | +1pp |
|---|---:|---:|---:|
| EM premium → EMIM | 20.6% | 24.8% | 28.4% |
| Size/value premium → AVSG | 25.6% | 29.3% | 33.2% |
| Profitability → AVWC | 31.0% | 35.7% | 38.6% |

## Read this before funding

- **Two of four are Avantis** (65% combined). Same issuer, same house
  methodology, both tilted to value + profitability. That is a deliberate factor
  bet and a single-manager concentration; if you would rather not, swap `AVSG.L`
  for a broader small-cap line and accept ~0.3pp less modelled growth.
- **EM at 24.8% is roughly 2.5× global market weight.** It is the single biggest
  active call in the book and it comes straight from the `em_premium` CMA. If you
  do not believe that premium, the −1pp row above shows where it lands.
- **No bonds, by design.** 25-year untouchable money; the gold sleeve is the
  only ballast. Do not copy this shape into the ISA, which has a liquidity floor
  and a CVaR cap.
- **Confirm SGLN is available inside the T212 SIPP wrapper** before funding — it
  is an ETC, not a UCITS fund, and eligibility is inferred rather than
  documented. See `report/UNIVERSE_VERIFICATION.md`. Fallback is a gold-miners
  equity ETF, which is not the same thing (equity beta, not spot gold).
- The per-holding cap is **0.40**, not the 0.30 in `[sipp]`. At four holdings a
  0.30 cap is arithmetically infeasible against the 15% sleeve caps. That is a
  consequence of holding fewer funds, not a change of risk appetite.

## Estimation-window caveat (applies to the main report too)

`estimate_covariance` is complete-case (`dropna(how="any")`). Priced across all
19 instruments, the dead JMFP feed collapses the usable window to **79 months,
Nov 2013 – Dec 2020** — excluding the 2021 inflation shock, the 2022 drawdown
and everything since, from every correlation in the main `REPORT.md`.

`build_sipp_simple` sidesteps this by pricing each candidate on its own keys,
which is why the recommended build rests on the full **211 months** while the
8-fund baseline is stuck at 119. **The main report has not been re-run against
this** — fixing it properly means either restoring a live JMFP series or
extending `_splice` to fall back to the proxy *after* a fund's data ends, not
just before. Tracked in `report/UNIVERSE_VERIFICATION.md`.

## Reproduce

```bash
python -m portfolio_optimiser.report.build_sipp_simple --k 4     # or --k 5
```

Writes `outputs/sipp_simple/candidates_k4.csv` (all 70, scored) and
`shortlist_k4.csv`.
