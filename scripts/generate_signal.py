#!/usr/bin/env python3
"""Generate today's trading signal for BRNT.L and append to CSV."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import yaml
from loguru import logger

from src.data.provider import DataProvider
from src.data.features import FeatureEngine
from src.backtest.engine import BacktestEngine
from src.backtest.comparison import StrategyComparison
from src.backtest.metrics import compute_metrics
from src.dashboard.cli import (
    generate_daily_signal, format_signal_output, append_to_csv
)
from src.strategy.trend import create_variants as trend_variants
from src.strategy.mean_reversion import create_variants as mr_variants
from src.strategy.carry import create_variants as carry_variants
from src.strategy.macro import create_variants as macro_variants
from src.strategy.volatility import create_variants as vol_variants
from src.strategy.seasonal import create_variants as seasonal_variants
from src.strategy.cross_asset import create_variants as cross_variants
from src.strategy.technical_composite import create_variants as tc_variants
from src.strategy.ml_strategy import create_variants as ml_variants
from src.strategy.ensemble import build_ensemble_from_results


def main():
    with open("config/backtest.yml") as f:
        config = yaml.safe_load(f)

    # Fetch recent data (last 3 years for feature warmup + ML training)
    logger.info("Fetching latest market data...")
    provider = DataProvider()
    universe = provider.fetch_universe(start="2023-01-01")

    primary = universe.get("BRNT")
    if primary is None or primary.empty:
        logger.error("Could not fetch BRNT.L data")
        return

    related = {k: v for k, v in universe.items() if k != "BRNT"}

    # Compute features
    logger.info("Computing features...")
    feature_engine = FeatureEngine()
    data = feature_engine.compute_all(primary, related)
    prices = data["close"]

    logger.info(f"Data range: {data.index[0].date()} to {data.index[-1].date()} ({len(data)} rows)")

    # Collect all strategies
    include_ml = "--no-ml" not in sys.argv
    strategies = []
    strategies.extend(trend_variants())
    strategies.extend(mr_variants())
    strategies.extend(carry_variants())
    strategies.extend(macro_variants())
    strategies.extend(vol_variants())
    strategies.extend(seasonal_variants())
    strategies.extend(cross_variants())
    strategies.extend(tc_variants())
    if include_ml:
        strategies.extend(ml_variants())

    # Run backtest on available data to rank strategies
    logger.info(f"Running backtest on {len(strategies)} strategies...")
    engine = BacktestEngine(
        initial_capital=config["initial_capital"],
        cost_bps=config["cost_bps"]
    )
    comparison = StrategyComparison(engine, risk_free_rate=config["risk_free_rate"])
    results_df = comparison.run_all(strategies, data, prices)

    # Build ensemble from top strategies
    ensemble = build_ensemble_from_results(
        comparison.results, strategies, top_n=7, method="sharpe_weighted"
    )

    # Collect Sharpe per sub-strategy
    sub_sharpes = {}
    if hasattr(ensemble, "sub_strategies"):
        for strat in ensemble.sub_strategies:
            match = results_df[results_df["strategy"] == strat.name]
            if not match.empty:
                sub_sharpes[strat.name] = match.iloc[0]["sharpe"]

    # Generate today's signal
    info = generate_daily_signal(ensemble, data, prices)

    # Format and print
    output = format_signal_output(info, sub_sharpes)
    print(output)

    # Append to CSV
    append_to_csv(info)
    logger.info(f"Signal appended to output/daily_signals.csv")

    # Also save strategy ranking
    if not results_df.empty:
        os.makedirs("output", exist_ok=True)
        results_df.to_csv("output/backtest_results.csv", index=False)


if __name__ == "__main__":
    main()
