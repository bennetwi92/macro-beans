#!/usr/bin/env python3
"""Full backtest comparison pipeline for BRNT.L oil ETF strategies."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
import pandas as pd
from loguru import logger

from src.data.provider import DataProvider
from src.data.features import FeatureEngine
from src.backtest.engine import BacktestEngine
from src.backtest.comparison import StrategyComparison
from src.backtest.metrics import compute_metrics
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


def load_config():
    with open("config/backtest.yml") as f:
        return yaml.safe_load(f)


def collect_all_strategies(include_ml=True):
    """Collect all strategy variants."""
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
    return strategies


def run_walk_forward(config, data, prices, strategies):
    """
    Walk-forward validation with proper data handling:
    - Strategies always receive FULL data for signal generation (so ML
      strategies train on proper history, seasonal strategies get warmup)
    - Metrics are computed only on the evaluation window
    - Train: first 60%, Validate: next 20%, Test: final 20%
    """
    n = len(prices)
    train_end = int(n * config["walk_forward"]["train_pct"])
    val_end = train_end + int(n * config["walk_forward"]["validation_pct"])

    train_date = str(data.index[0].date())
    train_end_date = str(data.index[train_end - 1].date())
    val_start_date = str(data.index[train_end].date())
    val_end_date = str(data.index[val_end - 1].date())
    test_start_date = str(data.index[val_end].date())
    test_end_date = str(data.index[-1].date())

    logger.info(f"Walk-forward split: train={train_end}, val={val_end-train_end}, test={n-val_end}")
    logger.info(f"Train: {train_date} to {train_end_date}")
    logger.info(f"Val:   {val_start_date} to {val_end_date}")
    logger.info(f"Test:  {test_start_date} to {test_end_date}")

    engine = BacktestEngine(
        initial_capital=config["initial_capital"],
        cost_bps=config["cost_bps"]
    )

    # Phase 1: Train period - rank all strategies
    # Strategies get train data only (no future leakage from features)
    train_data = data.iloc[:train_end]
    train_prices = prices.iloc[:train_end]
    comparison = StrategyComparison(engine, risk_free_rate=config["risk_free_rate"])

    logger.info(f"\n{'='*60}")
    logger.info(f"PHASE 1: Training period - {len(strategies)} strategies")
    logger.info(f"{'='*60}")
    train_results = comparison.run_all(strategies, train_data, train_prices)

    if train_results.empty:
        logger.error("No strategies produced results on training data")
        return None, None, None

    print(f"\n--- Top 15 strategies (TRAIN period) ---")
    print(train_results.head(15).to_string(index=False))

    # Phase 2: Validation - strategies get train+val data, evaluate on val window
    # This lets ML strategies train on the full train period while being evaluated on val
    val_data_full = data.iloc[:val_end]
    val_prices_full = prices.iloc[:val_end]

    logger.info(f"\n{'='*60}")
    logger.info(f"PHASE 2: Validation period")
    logger.info(f"{'='*60}")

    val_comparison = StrategyComparison(engine, risk_free_rate=config["risk_free_rate"])
    val_results = val_comparison.run_all(
        strategies, val_data_full, val_prices_full,
        eval_start=val_start_date
    )

    print(f"\n--- Top 15 strategies (VALIDATION period) ---")
    print(val_results.head(15).to_string(index=False))

    # Phase 3: Build ensemble from validation winners, test on held-out period
    logger.info(f"\n{'='*60}")
    logger.info(f"PHASE 3: Building ensemble from validation winners")
    logger.info(f"{'='*60}")

    ensemble = build_ensemble_from_results(
        val_comparison.results, strategies, top_n=7, method="sharpe_weighted"
    )

    # Test: strategies get ALL data, evaluate only on test window
    test_comparison = StrategyComparison(engine, risk_free_rate=config["risk_free_rate"])
    test_results = test_comparison.run_all(
        strategies + [ensemble], data, prices,
        eval_start=test_start_date
    )

    print(f"\n--- Top 15 strategies (TEST period - out of sample) ---")
    print(test_results.head(15).to_string(index=False))

    # Full period: individual strategies only (ensemble excluded to avoid selection bias)
    logger.info(f"\n{'='*60}")
    logger.info(f"FULL PERIOD RESULTS (individual strategies only)")
    logger.info(f"{'='*60}")
    full_comparison = StrategyComparison(engine, risk_free_rate=config["risk_free_rate"])
    full_results = full_comparison.run_all(strategies, data, prices)

    # Add ensemble test-period result as a separate row for reference
    ensemble_test = test_results[test_results["strategy"].str.startswith("Ensemble")]
    if not ensemble_test.empty:
        ensemble_row = ensemble_test.copy()
        ensemble_row["strategy"] = ensemble_row["strategy"] + " (test-only)"
        full_results = pd.concat([full_results, ensemble_row], ignore_index=True)

    print(f"\n--- ALL strategies (FULL period) + Ensemble (test-only) ---")
    print(full_results.to_string(index=False))

    return full_results, full_comparison, ensemble


def main():
    config = load_config()

    # Fetch data
    logger.info("Fetching market data...")
    provider = DataProvider()
    universe = provider.fetch_universe(
        start=config["start_date"], end=config["end_date"]
    )

    primary_name = "BRNT"
    if primary_name not in universe or universe[primary_name].empty:
        logger.error(f"No data for {primary_name}")
        return

    primary = universe[primary_name]
    related = {k: v for k, v in universe.items() if k != primary_name}

    logger.info(f"Primary data: {len(primary)} rows ({primary.index[0].date()} to {primary.index[-1].date()})")

    # Compute features
    logger.info("Computing features...")
    engine = FeatureEngine()
    data = engine.compute_all(primary, related)

    prices = data["close"]

    # Collect strategies (skip ML if --no-ml flag)
    include_ml = "--no-ml" not in sys.argv
    strategies = collect_all_strategies(include_ml=include_ml)
    logger.info(f"Collected {len(strategies)} strategy variants (ML={'yes' if include_ml else 'no'})")

    # Run walk-forward
    full_results, comparison, ensemble = run_walk_forward(config, data, prices, strategies)

    if full_results is not None:
        # Save results
        os.makedirs("output", exist_ok=True)
        full_results.to_csv("output/backtest_results.csv", index=False)
        logger.info(f"\nResults saved to output/backtest_results.csv")

        # Print summary
        best = full_results.iloc[0]
        print(f"\n{'='*60}")
        print(f"BEST STRATEGY: {best['strategy']}")
        print(f"  Sharpe:      {best['sharpe']:.3f}")
        print(f"  CAGR:        {best['cagr']:.2%}")
        print(f"  Max DD:      {best['max_drawdown']:.2%}")
        print(f"  Win Rate:    {best['win_rate']:.2%}")
        print(f"  Calmar:      {best['calmar']:.3f}")
        print(f"  Num Trades:  {best['num_trades']}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
