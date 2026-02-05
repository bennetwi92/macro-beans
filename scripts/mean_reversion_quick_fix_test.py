"""
Quick Test: What happens if we use better targets?
===================================================

This script simulates what the model would look like with different target sizes
WITHOUT retraining. This gives us a preview of whether fixing ATR targets will help.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from src.models.config import ModelConfig
from src.models.data_loader import DataLoader
from src.models.features import FeatureEngineer
from src.models.model import MeanReversionModel


def test_target_scenarios():
    """Test different target scenarios with current model"""
    print("\n" + "="*80)
    print("QUICK FIX TEST: What if we change targets?")
    print("="*80)
    print("\nThis shows what happens if we use the CURRENT MODEL")
    print("but evaluate it against DIFFERENT profit targets.\n")

    # Check if model exists
    if not os.path.exists("models/mean_reversion_model.pkl"):
        print("ERROR: Model not found. Please train first:")
        print("  python scripts/train_mean_reversion_model.py")
        return

    # Load model
    config = ModelConfig()
    model = MeanReversionModel(config)
    model.load_model("models/mean_reversion_model.pkl")

    data_loader = DataLoader()
    feature_engineer = FeatureEngineer(config)

    test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
                   'JPM', 'BAC', 'V', 'MA', 'HD', 'WMT', 'PG', 'DIS']

    available = [s for s in test_symbols if s in data_loader.available_symbols]

    # Test scenarios
    scenarios = [
        {'name': '1.5x ATR (Current)', 'atr_mult': 1.5, 'threshold': 0.60},
        {'name': '1.0x ATR (Recommended)', 'atr_mult': 1.0, 'threshold': 0.60},
        {'name': 'Fixed 2% Target', 'atr_mult': None, 'fixed_pct': 0.02, 'threshold': 0.60},
        {'name': '0.75x ATR (Highest WR)', 'atr_mult': 0.75, 'threshold': 0.60},
    ]

    results = []

    for scenario in scenarios:
        print(f"\n{'='*80}")
        print(f"Testing: {scenario['name']}")
        print('='*80)

        total_signals = 0
        wins = 0
        losses = 0
        total_return = 0

        for symbol in available:
            df = data_loader.load_symbol(symbol, start_date="2024-01-01", end_date="2024-12-31")

            if df.empty or len(df) < 100:
                continue

            # Create features
            features = feature_engineer.create_features(df)

            # Calculate ATR for this test
            atr = feature_engineer.calculate_atr(df, 14)

            # Get predictions
            X = features.copy()
            for col in ['Symbol', 'Date']:
                if col in X.columns:
                    X = X.drop(col, axis=1)

            try:
                predictions = model.predict_proba(X)
            except:
                continue

            # Find signals above threshold
            max_holding = config.max_holding_days

            for i in range(len(predictions) - max_holding):
                if predictions[i] < scenario['threshold']:
                    continue

                total_signals += 1

                entry_price = df['Close'].iloc[i]

                # Set target based on scenario
                if scenario['atr_mult'] is not None:
                    if pd.isna(atr.iloc[i]) or atr.iloc[i] <= 0:
                        continue
                    target_price = entry_price + (atr.iloc[i] * scenario['atr_mult'])
                    stop_price = entry_price - (atr.iloc[i] * 1.0)
                else:
                    target_price = entry_price * (1 + scenario['fixed_pct'])
                    stop_price = entry_price * 0.97  # 3% stop

                # Check outcome
                hit_target = False
                for j in range(1, max_holding + 1):
                    if i + j >= len(df):
                        break

                    future_high = df['High'].iloc[i + j]
                    future_low = df['Low'].iloc[i + j]

                    if future_high >= target_price:
                        wins += 1
                        total_return += (target_price - entry_price) / entry_price
                        hit_target = True
                        break
                    elif future_low <= stop_price:
                        losses += 1
                        total_return += (stop_price - entry_price) / entry_price
                        hit_target = True
                        break

                if not hit_target:
                    # Expired
                    exit_price = df['Close'].iloc[min(i + max_holding, len(df) - 1)]
                    if exit_price > entry_price:
                        wins += 1
                    else:
                        losses += 1
                    total_return += (exit_price - entry_price) / entry_price

        # Calculate metrics
        total_trades = wins + losses
        win_rate = wins / total_trades if total_trades > 0 else 0
        avg_return = total_return / total_trades if total_trades > 0 else 0

        print(f"\nResults at {scenario['threshold']:.0%} confidence threshold:")
        print(f"  Total signals: {total_signals}")
        print(f"  Total trades: {total_trades}")
        print(f"  Win rate: {win_rate:.2%}")
        print(f"  Avg return: {avg_return:.2%}")
        print(f"  Total return: {total_return:.2%}")

        results.append({
            'scenario': scenario['name'],
            'threshold': scenario['threshold'],
            'signals': total_signals,
            'trades': total_trades,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'total_return': total_return
        })

    # Summary comparison
    print("\n" + "="*80)
    print("SUMMARY COMPARISON")
    print("="*80)

    results_df = pd.DataFrame(results)
    print("\n" + results_df.to_string(index=False))

    print("\n" + "="*80)
    print("INTERPRETATION")
    print("="*80)

    best = results_df.loc[results_df['win_rate'].idxmax()]

    print(f"\nBest win rate: {best['scenario']} ({best['win_rate']:.1%})")
    print(f"Current approach: {results_df.iloc[0]['scenario']} ({results_df.iloc[0]['win_rate']:.1%})")

    improvement = best['win_rate'] - results_df.iloc[0]['win_rate']
    print(f"\nPotential improvement: {improvement:.1%} higher win rate")

    if improvement > 0.10:  # More than 10% improvement
        print("\nVERDICT: Changing targets would SIGNIFICANTLY improve performance")
        print(f"Recommendation: Retrain model with {best['scenario']}")
    elif improvement > 0.05:
        print("\nVERDICT: Changing targets would MODERATELY improve performance")
        print(f"Recommendation: Consider retraining with {best['scenario']}")
    else:
        print("\nVERDICT: Changing targets won't help much")
        print("Recommendation: The model itself needs improvement, not just target sizing")

    # Check if any scenario is viable
    max_win_rate = results_df['win_rate'].max()
    if max_win_rate > 0.55:
        print(f"\nGOOD NEWS: {best['scenario']} achieves {best['win_rate']:.1%} win rate")
        print("This suggests the model IS picking up valid signals")
        print("\nNEXT STEPS:")
        print("1. Retrain model using the better target definition")
        print("2. Re-run calibration analysis")
        print("3. If still calibrated, proceed to paper trading")
    else:
        print(f"\nBAD NEWS: Best achievable win rate is only {max_win_rate:.1%}")
        print("Even with optimal targets, performance is marginal")
        print("\nNEXT STEPS:")
        print("1. Add more features (volatility regime, market breadth, etc)")
        print("2. Filter trades by market conditions")
        print("3. Or consider alternative strategies entirely")


def main():
    test_target_scenarios()


if __name__ == "__main__":
    main()
