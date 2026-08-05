#!/usr/bin/env python3
"""Run the whole portfolio-rebalancing study end to end.

    python scripts/rebalancing/run_study.py

Writes every table under ``data/rebalancing/results/`` and every figure under
``data/rebalancing/charts/``. Deterministic: the only randomness is the block
bootstrap, which is seeded.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.rebalancing import charts, engine, metrics, stats, validate  # noqa: E402
from src.rebalancing.config import (  # noqa: E402
    ASSETS,
    COST_BASE,
    COST_DOUBLE,
    COST_HALF,
    COST_SMALL_POT,
    COST_US_LISTED,
    COST_ZERO,
    HEADLINE_PORTFOLIO,
    PORTFOLIOS,
    RANDOM_SEED,
    RESULTS_DIR,
    UNSPLICED_START,
    CostModel,
    StudyConfig,
    TargetWeights,
)
from src.rebalancing.data import Panel, build_panel  # noqa: E402
from src.rebalancing.policies import POLICIES, POLICY_BY_NAME, Policy  # noqa: E402

BENCHMARK = POLICY_BY_NAME["Monthly"]
HIGHLIGHT = ["Never (drift)", "Monthly", "Drawdown trigger -20%"]


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def _write(frame: pd.DataFrame, name: str) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(RESULTS_DIR / name, index=False)
    _log(f"wrote results/{name}  ({len(frame)} rows)")


# ---------------------------------------------------------------------------
# Core sweep
# ---------------------------------------------------------------------------


def run_policies(
    panel: Panel,
    target: TargetWeights,
    cost: CostModel,
    *,
    portfolio_label: str,
    exec_lag: int = 0,
    monthly_contribution: float = 0.0,
    policies: tuple[Policy, ...] = POLICIES,
) -> tuple[list[metrics.PolicyMetrics], dict[str, engine.BacktestResult]]:
    """Every policy over one panel / target / cost combination."""
    weights = np.array(target.vector())
    returns = panel.returns

    common = dict(
        exec_lag=exec_lag,
        monthly_contribution=monthly_contribution,
        currency=panel.currency,
    )
    bench = engine.run(returns, BENCHMARK, weights, cost, **common)
    bench_gross = engine.run(returns, BENCHMARK, weights, COST_ZERO, **common)

    rows: list[metrics.PolicyMetrics] = []
    results: dict[str, engine.BacktestResult] = {}
    for policy in policies:
        # The cash-flow policy is only meaningful when there are cash flows.
        if policy.family == "cashflow" and monthly_contribution <= 0:
            continue
        net = engine.run(returns, policy, weights, cost, **common)
        gross = engine.run(returns, policy, weights, COST_ZERO, **common)
        results[policy.name] = net
        rows.append(
            metrics.summarise(
                net,
                portfolio=portfolio_label,
                family=policy.family,
                cash=panel.cash,
                returns=returns,
                benchmark=bench,
                result_gross=gross,
                benchmark_gross=bench_gross,
                cost_model=cost.name,
            )
        )
    return rows, results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="re-download raw data")
    parser.add_argument("--quick", action="store_true", help="fewer bootstrap replicates")
    args = parser.parse_args()

    config = StudyConfig()
    n_boot = 250 if args.quick else config.bootstrap_replicates

    # ---- data -------------------------------------------------------------
    _log("building panels")
    gbp_full = build_panel(currency="GBP", refresh=args.refresh)
    usd_full = build_panel(currency="USD", refresh=args.refresh)
    gbp = gbp_full.slice(config.start)
    usd = usd_full.slice(config.start)

    validate.run_all(gbp)

    _write(
        pd.DataFrame([s.__dict__ for s in gbp.splices]),
        "splices.csv",
    )
    _write(
        pd.DataFrame(
            [{"series": k, "source": v} for k, v in gbp.sources.items()]
        ),
        "data_sources.csv",
    )

    # ---- headline sweep: 3 portfolios x GBP/USD ---------------------------
    _log("running policy sweep")
    all_rows: list[metrics.PolicyMetrics] = []
    headline_results: dict[str, engine.BacktestResult] = {}

    for panel in (gbp, usd):
        for target in PORTFOLIOS:
            rows, results = run_policies(
                panel, target, COST_BASE, portfolio_label=target.name
            )
            all_rows += rows
            if target.name == HEADLINE_PORTFOLIO and panel.currency == "GBP":
                headline_results = results

    # ---- cost sensitivity -------------------------------------------------
    _log("cost sensitivity")
    headline_target = next(p for p in PORTFOLIOS if p.name == HEADLINE_PORTFOLIO)
    for cost in (COST_ZERO, COST_HALF, COST_DOUBLE, COST_US_LISTED, COST_SMALL_POT):
        rows, _ = run_policies(
            gbp, headline_target, cost, portfolio_label=HEADLINE_PORTFOLIO
        )
        all_rows += rows

    # ---- execution-lag sensitivity ---------------------------------------
    _log("execution-lag sensitivity")
    lag_rows, _ = run_policies(
        gbp, headline_target, COST_BASE, portfolio_label=HEADLINE_PORTFOLIO, exec_lag=1
    )
    for row in lag_rows:
        row.cost_model = "base+exec_lag1"
    all_rows += lag_rows

    # ---- unspliced sub-sample --------------------------------------------
    _log("unspliced (ACWI-only) sub-sample")
    acwi_panel = build_panel(currency="GBP", equity_source="acwi").slice(UNSPLICED_START)
    acwi_rows, _ = run_policies(
        acwi_panel, headline_target, COST_BASE, portfolio_label=HEADLINE_PORTFOLIO
    )
    for row in acwi_rows:
        row.cost_model = "base+acwi_only"
    all_rows += acwi_rows

    # ---- contributions variant -------------------------------------------
    _log("monthly-contribution variant")
    contrib_rows, _ = run_policies(
        gbp,
        headline_target,
        COST_BASE,
        portfolio_label=HEADLINE_PORTFOLIO,
        monthly_contribution=500.0,
    )
    for row in contrib_rows:
        row.cost_model = "base+contrib500"
    all_rows += contrib_rows

    summary = metrics.metrics_frame(all_rows)
    _write(summary, "summary.csv")

    # ---- bootstrap --------------------------------------------------------
    _log(f"stationary block bootstrap ({n_boot} replicates)")
    boot = stats.bootstrap_policies(
        gbp.returns,
        [p for p in POLICIES if p.family != "cashflow"],
        BENCHMARK,
        np.array(headline_target.vector()),
        COST_BASE,
        n_replicates=n_boot,
        mean_block=config.bootstrap_mean_block,
        seed=RANDOM_SEED,
    )
    _write(
        pd.DataFrame(
            [
                {k: v for k, v in b.__dict__.items() if k != "differences_bps"}
                for b in boot
            ]
        ),
        "bootstrap.csv",
    )

    # ---- rolling windows --------------------------------------------------
    _log("rolling windows")
    wealth = {name: res.wealth for name, res in headline_results.items()}
    for years in (10, 20):
        frame = stats.rolling_window_differences(wealth, BENCHMARK.name, years=years)
        _write(frame, f"rolling_{years}y.csv")
        if not frame.empty:
            charts.rolling_difference(frame, HIGHLIGHT, years)

    rolling_share = []
    for years in (10, 20):
        frame = stats.rolling_window_differences(wealth, BENCHMARK.name, years=years)
        if frame.empty:
            continue
        for policy in wealth:
            if policy == BENCHMARK.name:
                continue
            values = frame[policy]
            rolling_share.append(
                {
                    "window_years": years,
                    "policy": policy,
                    "n_windows": len(values),
                    "share_beating_monthly": float((values > 0).mean()),
                    "median_diff_bps": float(values.median()),
                    "p25_bps": float(values.quantile(0.25)),
                    "p75_bps": float(values.quantile(0.75)),
                }
            )
    _write(pd.DataFrame(rolling_share), "rolling_window_shares.csv")

    # ---- crash windows ----------------------------------------------------
    _log("crash-conditional analysis")
    equity_wealth = (1 + gbp.returns["equity"]).cumprod()
    windows = stats.find_crash_windows(equity_wealth)
    crash = stats.crash_analysis(wealth, windows)
    _write(crash, "crash_windows.csv")

    usd_windows = stats.find_crash_windows((1 + usd.returns["equity"]).cumprod())
    _write(
        pd.DataFrame(
            [
                {
                    "currency": cur,
                    "event": w.label,
                    "peak": w.peak.date(),
                    "trough": w.trough.date(),
                    "depth": round(w.depth, 4),
                }
                for cur, ws in (("GBP", windows), ("USD", usd_windows))
                for w in ws
            ]
        ),
        "crash_window_dates.csv",
    )

    # ---- taxable-account appendix ----------------------------------------
    # ISA/SIPP is the base case, so this is an appendix, not a headline. A
    # sell in a General Investment Account crystallises gains: the drag is
    # sell-side turnover x the embedded gain fraction x the CGT rate. Shown
    # across gain fractions because the embedded gain grows with holding
    # period and is the term nobody can pin down in advance.
    _log("taxable-GIA appendix")
    base_rows = summary[
        (summary.portfolio == HEADLINE_PORTFOLIO)
        & (summary.currency == "GBP")
        & (summary.cost_model == "base")
    ]
    cgt_rows = []
    for _, row in base_rows.iterrows():
        sell_side = row["turnover_per_year"] / 2.0
        for gain_fraction in (0.20, 0.40, 0.60):
            for rate, band in ((0.18, "basic"), (0.24, "higher")):
                cgt_rows.append(
                    {
                        "policy": row["policy"],
                        "sell_turnover_per_year": sell_side,
                        "embedded_gain_fraction": gain_fraction,
                        "cgt_rate": rate,
                        "band": band,
                        "annual_tax_drag_bps": sell_side * gain_fraction * rate * 1e4,
                    }
                )
    _write(pd.DataFrame(cgt_rows), "taxable_gia_appendix.csv")

    # ---- correlations -----------------------------------------------------
    _log("correlation regimes")
    _write(stats.correlation_regimes(gbp.returns), "correlation_regimes_gbp.csv")
    _write(stats.correlation_regimes(usd.returns), "correlation_regimes_usd.csv")

    # ---- charts -----------------------------------------------------------
    _log("charts")
    charts.equity_curves(wealth, HIGHLIGHT, "GBP")
    charts.drawdowns(wealth, HIGHLIGHT)
    charts.rolling_correlations(
        stats.rolling_correlation(gbp.returns, "equity", "bond"),
        stats.rolling_correlation(gbp.returns, "equity", "gold"),
        "GBP",
    )

    headline_frame = summary[
        (summary.portfolio == HEADLINE_PORTFOLIO)
        & (summary.currency == "GBP")
        & (summary.cost_model == "base")
    ]
    charts.turnover_vs_return(headline_frame)
    charts.decomposition(headline_frame)
    charts.bootstrap_distributions(boot, BENCHMARK.name)

    equity_idx = ASSETS.index("equity")
    charts.weight_drift(
        {
            name: pd.Series(
                headline_results[name].weights_predrift[:, equity_idx],
                index=headline_results[name].dates,
            )
            for name in HIGHLIGHT
        },
        target=headline_target.weights["equity"],
    )
    charts.crash_windows(crash, HIGHLIGHT)

    gbp_wealth = headline_results[BENCHMARK.name].wealth
    usd_rows, usd_results = run_policies(
        usd, headline_target, COST_BASE, portfolio_label=HEADLINE_PORTFOLIO
    )
    charts.fx_effect(gbp_wealth, usd_results[BENCHMARK.name].wealth)

    _log("done")


if __name__ == "__main__":
    main()
