"""
Model Calibration Analysis
===========================

Check if the model's predicted probabilities match actual outcomes.
A well-calibrated model with 75% confidence should have ~75% actual win rate.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')
import pickle

from src.models.config import ModelConfig
from src.models.data_loader import DataLoader
from src.models.features import FeatureEngineer
from src.models.model import MeanReversionModel


def analyze_calibration():
    """Analyze model calibration"""
    print("\n" + "="*80)
    print("MODEL CALIBRATION ANALYSIS")
    print("="*80)
    print("\nQuestion: Does 75% predicted probability = 75% actual win rate?")
    print("(If not, the model is miscalibrated)\n")

    # Check if model exists
    if not os.path.exists("models/mean_reversion_model.pkl"):
        print("ERROR: Model not found at models/mean_reversion_model.pkl")
        print("Please train the model first using: python scripts/train_mean_reversion_model.py")
        return

    # Load configuration and model
    config = ModelConfig()
    model = MeanReversionModel(config)
    model.load_model("models/mean_reversion_model.pkl")

    # Initialize components
    data_loader = DataLoader()
    feature_engineer = FeatureEngineer(config)

    # Test on holdout period
    test_symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'JPM', 'BAC', 'V', 'MA', 'HD', 'WMT', 'PG', 'DIS'
    ]

    available_symbols = [s for s in test_symbols if s in data_loader.available_symbols]

    all_predictions = []
    all_actuals = []

    print("Generating predictions and outcomes on test data (2024)...\n")

    for symbol in available_symbols:
        df = data_loader.load_symbol(symbol, start_date="2024-01-01", end_date="2024-12-31")

        if df.empty or len(df) < 100:
            continue

        # Create features
        features = feature_engineer.create_features(df)

        # Generate labels
        labels = feature_engineer.generate_labels(df, use_atr=config.use_atr_targets)

        # Remove rows with insufficient history
        valid_idx = ~features.iloc[:, :20].isnull().any(axis=1)
        features = features[valid_idx]
        labels = labels[valid_idx]

        if len(features) == 0:
            continue

        # Get predictions
        X = features.copy()

        # Drop metadata columns if they exist
        for col in ['Symbol', 'Date']:
            if col in X.columns:
                X = X.drop(col, axis=1)

        try:
            predictions = model.predict_proba(X)

            # Store predictions and actual outcomes
            all_predictions.extend(predictions)
            all_actuals.extend(labels['label'].values)

        except Exception as e:
            print(f"Warning: Could not process {symbol}: {e}")
            continue

    if len(all_predictions) == 0:
        print("No predictions generated. Cannot perform calibration analysis.")
        return

    # Convert to arrays
    predictions = np.array(all_predictions)
    actuals = np.array(all_actuals)

    print(f"Total predictions: {len(predictions)}")
    print(f"Base success rate: {actuals.mean():.2%}\n")

    # Calibration analysis by confidence bins
    print("="*80)
    print("CALIBRATION BY CONFIDENCE BIN")
    print("="*80)

    bins = [(0, 0.5), (0.5, 0.55), (0.55, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 0.75), (0.75, 0.8), (0.8, 1.0)]

    calibration_results = []

    for low, high in bins:
        mask = (predictions >= low) & (predictions < high)
        if mask.sum() == 0:
            continue

        actual_win_rate = actuals[mask].mean()
        predicted_prob = predictions[mask].mean()
        count = mask.sum()

        calibration_results.append({
            'confidence_range': f"{low:.0%}-{high:.0%}",
            'avg_predicted_prob': predicted_prob,
            'actual_win_rate': actual_win_rate,
            'count': count,
            'calibration_error': abs(predicted_prob - actual_win_rate)
        })

        print(f"\nConfidence {low:.0%}-{high:.0%}:")
        print(f"  Count: {count}")
        print(f"  Avg Predicted: {predicted_prob:.2%}")
        print(f"  Actual Win Rate: {actual_win_rate:.2%}")
        print(f"  Calibration Error: {abs(predicted_prob - actual_win_rate):.2%}")

    # Summary statistics
    print("\n" + "="*80)
    print("CALIBRATION SUMMARY")
    print("="*80)

    if calibration_results:
        results_df = pd.DataFrame(calibration_results)

        avg_error = results_df['calibration_error'].mean()
        max_error = results_df['calibration_error'].max()

        print(f"\nAverage Calibration Error: {avg_error:.2%}")
        print(f"Max Calibration Error: {max_error:.2%}")

        if avg_error < 0.05:
            print("\nVERDICT: Model is WELL CALIBRATED")
        elif avg_error < 0.10:
            print("\nVERDICT: Model has MODERATE calibration issues")
        else:
            print("\nVERDICT: Model is POORLY CALIBRATED")

        # Check specific threshold (60%)
        mask_60 = predictions >= 0.60
        if mask_60.sum() > 0:
            actual_60 = actuals[mask_60].mean()
            print(f"\nAt 60% confidence threshold:")
            print(f"  Trades: {mask_60.sum()}")
            print(f"  Actual win rate: {actual_60:.2%}")
            print(f"  Expected: 60%+")
            print(f"  Gap: {abs(actual_60 - 0.60):.2%}")

    # Plot calibration curve (text-based)
    print("\n" + "="*80)
    print("CALIBRATION CURVE (Predicted vs Actual)")
    print("="*80)

    if calibration_results:
        print("\n  Actual |")
        print("  Win    |")
        print("  Rate   |")
        print("         |")

        for i in range(10, -1, -1):
            y_val = i * 0.1
            line = f"  {y_val:.0%}   |"

            for result in calibration_results:
                pred = result['avg_predicted_prob']
                actual = result['actual_win_rate']

                # Plot point if close to this y value
                if abs(actual - y_val) < 0.05:
                    x_pos = int(pred * 60)  # Scale to 60 char width
                    line += " " * max(0, x_pos - len(line) + 9) + "*"

            print(line)

        print("         |" + "-"*60)
        print("         0%        20%        40%        60%        80%       100%")
        print("                        Predicted Probability")

    print("\n" + "="*80)
    print("INTERPRETATION")
    print("="*80)
    print("\nA well-calibrated model should have points along the diagonal.")
    print("If points are BELOW diagonal: Model is overconfident (predicts higher than actual)")
    print("If points are ABOVE diagonal: Model is underconfident (predicts lower than actual)")


def main():
    analyze_calibration()


if __name__ == "__main__":
    main()
