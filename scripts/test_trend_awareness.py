"""Test trend awareness of model on COIN (downtrend) vs PFE (uptrend)"""

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


def analyze_symbol(symbol: str, model, data_loader, feature_engineer):
    """Analyze a single symbol and show trend features"""

    df = data_loader.load_symbol(symbol)

    if df.empty:
        print(f"No data for {symbol}")
        return None

    # Get features
    features = feature_engineer.create_features(df)

    # Get latest data
    latest_row = df.iloc[-1]
    latest_features = features.iloc[-1]

    # Get prediction
    X = features.iloc[[-1]].drop(['Symbol', 'Date'], axis=1, errors='ignore')
    confidence = model.predict_proba(X)[0]

    # Extract key metrics
    price = latest_row['Close']
    ma50 = latest_features['ma_50']
    ma200 = latest_features['ma_200']
    adx = latest_features['adx_14']
    plus_di = latest_features['plus_di_14']
    minus_di = latest_features['minus_di_14']
    di_diff = latest_features['di_diff']
    di_ratio = latest_features['di_ratio']
    price_above_ma50 = latest_features['price_above_ma50']
    price_above_ma200 = latest_features['price_above_ma200']
    ma50_above_ma200 = latest_features['ma50_above_ma200']
    ma50_slope = latest_features['ma50_slope']
    trend_alignment = latest_features['trend_alignment']

    return {
        'Symbol': symbol,
        'Confidence': confidence,
        'Price': price,
        'Price_vs_MA50': (price / ma50 - 1) * 100,
        'Price_vs_MA200': (price / ma200 - 1) * 100,
        'ADX': adx,
        '+DI': plus_di,
        '-DI': minus_di,
        'DI_Diff': di_diff,
        'DI_Ratio': di_ratio,
        'Price>MA50': int(price_above_ma50),
        'Price>MA200': int(price_above_ma200),
        'MA50>MA200': int(ma50_above_ma200),
        'MA50_Slope': ma50_slope,
        'Trend_Aligned': int(trend_alignment),
        'RSI_14': latest_features['rsi_14']
    }


def main():
    # Load model
    config = ModelConfig()
    model = MeanReversionModel(config)
    model.load_model("models/mean_reversion_model.pkl")

    data_loader = DataLoader()
    feature_engineer = FeatureEngineer(config)

    # Test symbols
    test_symbols = ['COIN', 'PFE']

    print("\n" + "="*100)
    print("TREND AWARENESS TEST: Downtrend (COIN) vs Uptrend (PFE)")
    print("="*100)

    results = []
    for symbol in test_symbols:
        result = analyze_symbol(symbol, model, data_loader, feature_engineer)
        if result:
            results.append(result)

    if results:
        df = pd.DataFrame(results)

        # Format for display
        pd.set_option('display.width', 200)
        pd.set_option('display.max_columns', None)

        print("\n")
        print(df.to_string(index=False))

        print("\n" + "="*100)
        print("INTERPRETATION:")
        print("="*100)

        for result in results:
            symbol = result['Symbol']
            conf = result['Confidence']

            print(f"\n{symbol}:")
            print(f"  Confidence: {conf:.1%}")
            print(f"  Price vs MA50: {result['Price_vs_MA50']:+.1f}%")
            print(f"  ADX (trend strength): {result['ADX']:.1f}")
            print(f"  +DI: {result['+DI']:.1f}  |  -DI: {result['-DI']:.1f}")
            print(f"  DI Diff: {result['DI_Diff']:+.1f} (positive=uptrend, negative=downtrend)")
            print(f"  Trend Aligned (Price>MA50>MA200): {result['Trend_Aligned']}")
            print(f"  RSI: {result['RSI_14']:.1f}")

        print("\n" + "="*100)
        print("EXPECTED:")
        print("  - COIN (downtrend): LOW confidence due to -DI > +DI, price < MA50")
        print("  - PFE (uptrend): HIGHER confidence due to +DI > -DI, price > MA50")
        print("="*100)


if __name__ == "__main__":
    main()
