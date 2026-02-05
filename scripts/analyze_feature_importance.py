"""Analyze feature importance and trend feature impact"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from src.models.config import ModelConfig
from src.models.model import MeanReversionModel


def main():
    # Load model
    config = ModelConfig()
    model = MeanReversionModel(config)
    model.load_model("models/mean_reversion_model.pkl")

    # Get feature importance
    fi_df = model.feature_importance.sort_values('importance', ascending=False)

    print("\n" + "="*80)
    print("FEATURE IMPORTANCE ANALYSIS")
    print("="*80)

    # Identify trend-related features
    trend_features = [
        'adx_14', 'plus_di_14', 'minus_di_14', 'di_diff', 'di_ratio',
        'price_above_ma50', 'price_above_ma200', 'ma50_above_ma200',
        'ma50_slope', 'trend_alignment'
    ]

    # Split into categories
    trend_df = fi_df[fi_df['feature'].apply(lambda x: any(tf in x for tf in trend_features))]
    other_df = fi_df[~fi_df['feature'].apply(lambda x: any(tf in x for tf in trend_features))]

    print("\n--- TREND & DIRECTIONAL FEATURES (new) ---")
    for _, row in trend_df.iterrows():
        print(f"  {row['feature']:30s} : {row['importance']:8.1f}")

    print(f"\n  TOTAL TREND IMPORTANCE: {trend_df['importance'].sum():.1f}")

    print("\n--- OTHER FEATURES (top 20) ---")
    for _, row in other_df.head(20).iterrows():
        print(f"  {row['feature']:30s} : {row['importance']:8.1f}")

    # Check for oversold features
    oversold_features = ['rsi_', 'bb_percent_b', 'dist_from_low', 'oversold']
    oversold_df = fi_df[fi_df['feature'].apply(lambda x: any(of in x for of in oversold_features))]

    print("\n--- OVERSOLD FEATURES ---")
    for _, row in oversold_df.head(10).iterrows():
        print(f"  {row['feature']:30s} : {row['importance']:8.1f}")

    print(f"\n  TOTAL OVERSOLD IMPORTANCE: {oversold_df['importance'].sum():.1f}")

    print("\n" + "="*80)
    print("INTERPRETATION:")
    print("="*80)
    print(f"Trend features contribute {trend_df['importance'].sum():.1f} importance")
    print(f"Oversold features contribute {oversold_df['importance'].sum():.1f} importance")
    print("")
    print("If oversold >> trend, the model will prioritize extreme oversold over trend direction")
    print("="*80)


if __name__ == "__main__":
    main()
