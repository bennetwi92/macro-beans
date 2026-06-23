# Portfolio allocation optimiser — ISA (A) + SIPP (B)

A small, config-driven tool that builds **quantitatively optimised target
allocations** for two UK Trading-212 portfolios and drives **monthly
contribution rebalancing**. Re-run it once a year to refresh the targets; use the
rebalancer each month.

> **Not financial advice.** This is a modelling tool. Every assumption lives in
> `config/` and is editable. It produces optimised *candidates* and the trade-offs
> behind them; the investor decides.

---

## What it does

| Portfolio | Mandate | Objective |
|---|---|---|
| **B — SIPP** | Untouchable ~25y; maximise terminal wealth | Maximise expected **geometric growth** g(w)=μ'w−½w'Σw, long-only, per-holding ≤30%, sleeve caps/floors |
| **A — ISA** | Tolerate a ~1y withdrawal yet compound ~25y; AI-crash-averse | Maximise geometric growth **subject to** a hard ballast **liquidity floor** and a **95% CVaR / drawdown cap** |

Inputs are built carefully (the brief's warning — naive mean-variance gives
unstable corner solutions — is taken seriously):

- **Expected returns** are forward-looking **CMAs** (building-block premia: cash,
  ERP, value/size/profitability/quality, term), *not* raw historical means. See
  `config/cma.toml`.
- **Covariance** is a **shrinkage** estimate (correlation shrunk toward a
  constant-correlation target, per-asset variances preserved) on month-end GBP
  total returns, with **young funds spliced onto longer-history proxies** and
  **MAD-winsorised** to kill data-error ticks. See `optimiser/covariance.py` and
  the `[proxy.*]` map in `config/universe.toml`.
- Arithmetic returns are converted to **geometric** (g = μ − ½σ²).
- The headline weights are the **resampled (Michaud)** solution (robust to
  estimation error), cross-checked against **Black-Litterman** and **HRP**.

It then **validates** (Monte Carlo terminal wealth for B; 1-year drawdown/CVaR
for A), **stress-tests** the weights against ±1ppt CMA shifts, and ships a
**rebalancer**.

---

## Install

```bash
/usr/local/bin/python3 -m pip install -r portfolio_optimiser/requirements.txt
```
(Conda users: the deps are standard — numpy, pandas, scipy, scikit-learn, cvxpy,
yfinance, matplotlib, tabulate.)

## Run the full pipeline

From the **repo root**:

```bash
# uses the cached returns if present:
python -m portfolio_optimiser.report.build_report
# re-fetch market data (do this on the annual review):
python -m portfolio_optimiser.report.build_report --refresh
```

Outputs land in `portfolio_optimiser/outputs/`:

| File | What |
|---|---|
| `REPORT.md` | The human-readable summary — **start here** |
| `targets_isa.csv`, `targets_sipp.csv` | Target weights + Trading 212 Pie % |
| `method_comparison_*.csv` | Recommended vs convex / resampled / BL / HRP |
| `sensitivity_*.csv` | What each weight hinges on (CMA shifts) |
| `montecarlo_sipp.csv/.png` | 25y terminal-wealth distribution |
| `drawdown_isa.csv/.png` | 1y drawdown distribution vs the tail cap |
| `expected_returns.csv`, `correlation.csv` | The model inputs |
| `returns_monthly.csv` | Cached total-return history (regenerable) |

## Monthly rebalancing

```bash
# first contribution into an empty SIPP Pie:
python -m portfolio_optimiser.rebalancer.run_rebalance --portfolio sipp --contribution 1500

# monthly top-up with current holdings (CSV columns: ticker,value):
python -m portfolio_optimiser.rebalancer.run_rebalance --portfolio isa --contribution 500 --holdings my_isa.csv
```

It allocates new money to the most-underweight holdings first (buy-only by
default — no CGT churn, and harmless in a wrapper), prints resulting weights and
the **Pie target %**, and raises a **drift flag** when a holding is so overweight
that contributions alone can't fix it (default thresholds: 5 abs pts or 25%
relative). Add `--allow-sells` for a full rebalance.

The `pie_target_%` column maps 1:1 onto a Trading 212 Pie: create one slice per
ticker at that percentage and let Pie auto-invest do the monthly buys.

---

## The three investor parameters (in `config/constraints.toml`)

These are **yours to set** — the model does not assume them:

| Parameter | Key | Current |
|---|---|---|
| ISA 1-year withdrawal need (ballast floor) | `[isa].liquidity_floor_gbp` | £10,000 |
| ISA tail limit (max drawdown / 95% CVaR) | `[isa].cvar_limit` | 0.20 |
| SIPP funding for the tax year | `[sipp].value_gbp` | £20,000 |

> The £10k floor on a £20k ISA forces **~50% ballast** — a heavy drag on the 25y
> mandate. It's an *absolute* £ amount, so its share shrinks as contributions grow
> the pot. If your external ~£30k cash buffer covers the 1-year need, **lower
> `liquidity_floor_gbp`** to free that sleeve for growth. (T212 SIPP has no operator
> fee now, so `fixed_fee_gbp = 0`.)

## Annual review checklist

1. **Refresh data & re-optimise:** `python -m portfolio_optimiser.report.build_report --refresh`.
2. **Re-confirm the three parameters** above (income, withdrawal need, risk limits change).
3. **Revisit the CMAs** in `config/cma.toml` — these drive everything. Update the
   building-block premia if your forward view has changed. The `sensitivity_*.csv`
   tables show which assumptions the weights are most exposed to.
4. **Re-verify the universe** (`report/UNIVERSE_VERIFICATION.md`): tickers, TERs,
   and especially **Trading 212 SIPP eligibility of SGLN (ETC) and JMFP** — confirm
   with T212 before funding; same-role fallbacks are documented there. Swap an
   instrument by editing its block in `config/universe.toml`.
5. **Read `outputs/REPORT.md`**, sanity-check against the method-comparison and
   Monte-Carlo tables, then update your Pie targets.

## Tuning levers (all in `config/`)

- `[isa]`/`[sipp].sleeve_floors` — guarantee a minimum crash-diversifier / real-asset
  sleeve (the barbell). Set to 0 to let the optimiser decide purely on growth.
- `[isa]`/`[sipp].sleeve_caps`, `weight_max` — diversification bands.
- `[optimiser].min_holding` — dust threshold for a tidy Pie (default 3%).
- `[optimiser].resample_draws`, `random_seed` — robustness vs runtime; reproducibility.

---

## Project layout

```
portfolio_optimiser/
  config/
    universe.toml      instruments + proxy series (single source of truth)
    cma.toml           capital-market assumptions (building blocks + formulas)
    constraints.toml   per-portfolio constraints, investor params, validation
  optimiser/
    config.py          typed loaders for the TOML configs
    data.py            total-return fetch, proxy splice, GBP conversion, cache
    cma.py             expected returns from blocks; arith<->geo conversion
    covariance.py      MAD-winsorise + correlation-shrinkage covariance
    objectives.py      cvxpy building blocks (geometric obj, CVaR, scenarios)
    optimize.py        optimise_sipp / optimise_isa + cleanup/summaries
    robust.py          resampled (Michaud), Black-Litterman, HRP
    sensitivity.py     CMA sensitivity sweep
  rebalancer/
    rebalance.py       the rebalance() function
    run_rebalance.py   CLI
  report/
    validate.py        Monte Carlo (terminal wealth, drawdown/CVaR)
    build_report.py    end-to-end pipeline -> outputs/
    UNIVERSE_VERIFICATION.md   sourced ticker/TER/SIPP-eligibility findings
  outputs/             generated artefacts (committed as deliverables)
  tests/               pytest (offline, deterministic)
  requirements.txt
```

Run the tests with `python -m pytest portfolio_optimiser/tests/ -q`.

## Known limitations

- CMAs are a transparent prior, **not a forecast** — the most important and most
  uncertain input. Treat the sensitivity tables as the honest health-warning.
- Covariance proxies are imperfect (esp. European-defence → US-defence beta, and
  the GBP-hedged managed-futures proxy). Documented inline in `config/universe.toml`.
- Monte Carlo assumes multivariate-normal monthly returns (thin tails). The CVaR
  cap and the gold/managed-futures diversifiers are the deliberate hedge against
  the fat-tailed AI-crash the normal model understates.
