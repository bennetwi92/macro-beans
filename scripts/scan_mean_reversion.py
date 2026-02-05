"""Production scanner using trained mean reversion model"""

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


def scan_for_opportunities():
    """Scan all symbols for mean reversion opportunities"""

    # Load configuration and model
    config = ModelConfig()
    model = MeanReversionModel(config)
    model.load_model("models/mean_reversion_model.pkl")

    # Initialize components
    data_loader = DataLoader()
    feature_engineer = FeatureEngineer(config)

    # Scan all available symbols
    opportunities = []

    for symbol in data_loader.available_symbols:
        df = data_loader.load_symbol(symbol)

        if df.empty or len(df) < config.lookback_days * 2:
            continue

        # Get latest features
        features = feature_engineer.create_features(df)

        if features.empty:
            continue

        # Get prediction for latest day
        latest_features = features.iloc[[-1]]
        latest_features = latest_features.drop(['Symbol', 'Date'], axis=1, errors='ignore')

        confidence = model.predict_proba(latest_features)[0]

        if confidence >= config.confidence_threshold:
            opportunities.append({
                'Symbol': symbol,
                'Confidence': confidence,
                'Price': df.iloc[-1]['Close'],
                'Volume': df.iloc[-1]['Volume'],
                'RSI_14': latest_features.iloc[0].get('rsi_14', np.nan),
                'Distance_from_20d_low': latest_features.iloc[0].get('dist_from_low_20d', np.nan)
            })

    # Sort by confidence
    opportunities = sorted(opportunities, key=lambda x: x['Confidence'], reverse=True)

    # Display results
    print("\n" + "="*80)
    print("MEAN REVERSION OPPORTUNITIES")
    print("="*80)
    print(f"\nFound {len(opportunities)} opportunities above {config.confidence_threshold:.0%} confidence\n")

    if opportunities:
        df_opps = pd.DataFrame(opportunities)
        print(df_opps.to_string(index=False))

    return opportunities


if __name__ == "__main__":
    opportunities = scan_for_opportunities()
