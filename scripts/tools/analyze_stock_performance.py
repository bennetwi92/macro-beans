"""Analyze per-stock mean reversion performance"""

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


def analyze_stock_performance():
    """Analyze mean reversion success rates by stock"""

    config = ModelConfig()
    data_loader = DataLoader()
    feature_engineer = FeatureEngineer(config)

    # Training symbols to analyze
    training_symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'JPM', 'BAC', 'WMT', 'JNJ', 'PG', 'V', 'MA', 'UNH',
        'HD', 'DIS', 'NFLX', 'ADBE', 'CRM', 'PYPL', 'INTC', 'AMD',
        'CSCO', 'PEP', 'KO', 'NKE', 'MCD', 'COST', 'CVX', 'XOM'
    ]

    results = []

    for symbol in training_symbols:
        if symbol not in data_loader.available_symbols:
            continue

        print(f"Analyzing {symbol}...")
        df = data_loader.load_symbol(symbol, start_date="2015-01-01", end_date="2024-01-01")

        if df.empty or len(df) < config.lookback_days * 2:
            continue

        # Generate labels to see success rates
        labels = feature_engineer.generate_labels(df)

        # Calculate ATR for volatility context
        df['TR'] = pd.DataFrame({
            'hl': df['High'] - df['Low'],
            'hc': abs(df['High'] - df['Close'].shift()),
            'lc': abs(df['Low'] - df['Close'].shift())
        }).max(axis=1)

        atr_14 = df['TR'].rolling(window=14).mean()
        current_price = df['Close'].iloc[-1]
        current_atr = atr_14.iloc[-1]
        atr_pct = (current_atr / current_price) * 100

        # Calculate average daily volume
        avg_volume = df['Volume'].tail(20).mean()

        # Calculate success rate
        valid_labels = labels[labels['label'].notna()]
        success_rate = valid_labels['label'].mean() if len(valid_labels) > 0 else 0

        results.append({
            'Symbol': symbol,
            'Success_Rate': success_rate,
            'Total_Samples': len(valid_labels),
            'Successful_Trades': int(valid_labels['label'].sum()),
            'Current_Price': current_price,
            'ATR_14': current_atr,
            'ATR_Pct': atr_pct,
            'Avg_Volume_20d': avg_volume,
            'Avg_Holding_Days': valid_labels['holding_days'].mean()
        })

    # Create DataFrame and sort by success rate
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values('Success_Rate', ascending=False)

    print("\n" + "="*80)
    print("MEAN REVERSION SUCCESS RATES BY STOCK (2015-2024)")
    print("="*80)

    # Display all stocks
    print("\nAll Stocks Performance:")
    print(df_results[['Symbol', 'Success_Rate', 'Total_Samples', 'ATR_Pct', 'Avg_Holding_Days']].to_string(index=False))

    # Identify poor performers
    poor_threshold = 0.30
    poor_performers = df_results[df_results['Success_Rate'] < poor_threshold]

    print("\n" + "="*80)
    print(f"STOCKS WITH SUCCESS RATE < {poor_threshold:.0%} (RECOMMEND EXCLUSION):")
    print("="*80)
    print(poor_performers[['Symbol', 'Success_Rate', 'Total_Samples', 'ATR_Pct']].to_string(index=False))

    # Identify best performers
    good_performers = df_results[df_results['Success_Rate'] >= 0.40]
    print("\n" + "="*80)
    print("TOP PERFORMING STOCKS (SUCCESS RATE >= 40%):")
    print("="*80)
    print(good_performers[['Symbol', 'Success_Rate', 'Total_Samples', 'ATR_Pct']].to_string(index=False))

    # Volatility analysis
    print("\n" + "="*80)
    print("VOLATILITY ANALYSIS (ATR as % of Price):")
    print("="*80)

    low_vol = df_results[df_results['ATR_Pct'] < 2.0]
    high_vol = df_results[df_results['ATR_Pct'] > 4.0]

    print(f"\nLow Volatility Stocks (ATR < 2%):")
    print(f"  Average Success Rate: {low_vol['Success_Rate'].mean():.2%}")
    print(f"  Stocks: {', '.join(low_vol['Symbol'].tolist())}")

    print(f"\nHigh Volatility Stocks (ATR > 4%):")
    print(f"  Average Success Rate: {high_vol['Success_Rate'].mean():.2%}")
    print(f"  Stocks: {', '.join(high_vol['Symbol'].tolist())}")

    from pathlib import Path
    out_path = Path(__file__).resolve().parents[2] / 'data' / 'backtests' / 'stock_performance_analysis.csv'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_results.to_csv(out_path, index=False)
    print(f"\n[Saved detailed results to {out_path}]")

    return df_results, poor_performers['Symbol'].tolist()


if __name__ == "__main__":
    results, stocks_to_exclude = analyze_stock_performance()
    print(f"\n\nRECOMMENDED EXCLUSION LIST: {stocks_to_exclude}")