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
    Walk-forward validation:
    - Train: first 60% - run all strategies, compute Sharpe
    - Validate: next 20% - evaluate train winners, pick top N
    - Test: final 20% - evaluate ensemble on unseen data
    """
    n = len(prices)
    train_end = int(n * config["walk_forward"]["train_pct"])
    val_end = train_end + int(n * config["walk_forward"]["validation_pct"])

    train_data = data.iloc[:train_end]
    train_prices = prices.iloc[:train_end]
    val_data = data.iloc[train_end:val_end]
    val_prices = prices.iloc[train_end:val_end]
    test_data = data.iloc[val_end:]
    test_prices = prices.iloc[val_end:]

    logger.info(f"Walk-forward split: train={train_end}, val={val_end-train_end}, test={n-val_end}")
    logger.info(f"Train: {train_data.index[0].date()} to {train_data.index[-1].date()}")
    logger.info(f"Val:   {val_data.index[0].date()} to {val_data.index[-1].date()}")
    logger.info(f"Test:  {test_data.index[0].date()} to {test_data.index[-1].date()}")

    # Phase 1: Train period - rank all strategies
    engine = BacktestEngine(
        initial_capital=config["initial_capital"],
        cost_bps=config["cost_bps"]
    )
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

    # Phase 2: Validation - evaluate top strategies
    logger.info(f"\n{'='*60}")
    logger.info(f"PHASE 2: Validation period")
    logger.info(f"{'='*60}")

    val_comparison = StrategyComparison(engine, risk_free_rate=config["risk_free_rate"])
    val_results = val_comparison.run_all(strategies, val_data, val_prices)

    print(f"\n--- Top 15 strategies (VALIDATION period) ---")
    print(val_results.head(15).to_string(index=False))

    # Phase 3: Build ensemble from validation winners
    logger.info(f"\n{'='*60}")
    logger.info(f"PHASE 3: Building ensemble from validation winners")
    logger.info(f"{'='*60}")

    ensemble = build_ensemble_from_results(
        val_comparison.results, strategies, top_n=7, method="sharpe_weighted"
    )

    # Test the ensemble on the test period
    test_comparison = StrategyComparison(engine, risk_free_rate=config["risk_free_rate"])
    test_results = test_comparison.run_all(
        strategies + [ensemble], test_data, test_prices
    )

    print(f"\n--- Top 15 strategies (TEST period - out of sample) ---")
    print(test_results.head(15).to_string(index=False))

    # Full period results
    logger.info(f"\n{'='*60}")
    logger.info(f"FULL PERIOD RESULTS")
    logger.info(f"{'='*60}")
    full_comparison = StrategyComparison(engine, risk_free_rate=config["risk_free_rate"])
    full_results = full_comparison.run_all(strategies + [ensemble], data, prices)

    print(f"\n--- ALL strategies (FULL period) ---")
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
