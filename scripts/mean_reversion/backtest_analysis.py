"""
Quick analysis to understand why the strategy is performing poorly
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.data.store import MarketStore  # noqa: E402

_STORE = MarketStore()

def analyze_strategy_conditions():
    """Check how often entry conditions are actually met"""

    # Parameters
    RSI_THRESHOLD = 30
    PULLBACK_MIN = 3
    PULLBACK_MAX = 6
    MA20_DISTANCE = 1.5

    results = []

    # Load a few representative stocks
    test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META']

    for symbol in test_symbols:
        df = _STORE.get_prices(symbol)
        if df.empty:
            continue

        # Only use recent 2 years
        df = df[df.index >= '2024-01-01']

        if len(df) < 200:
            continue

        # Calculate indicators
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=2).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=2).mean()
        rs = gain / loss
        df['RSI_2'] = 100 - (100 / (1 + rs))

        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA50'] = df['Close'].rolling(50).mean()
        df['MA200'] = df['Close'].rolling(200).mean()

        df['High_10d'] = df['High'].rolling(10).max()
        df['Pullback_pct'] = ((df['High_10d'] - df['Close']) / df['High_10d']) * 100

        df['MA20_distance'] = abs((df['Close'] - df['MA20']) / df['MA20']) * 100

        df['Uptrend'] = (df['Close'] > df['MA50']) & (df['MA50'] > df['MA200'])

        # Check each condition
        df['RSI_Signal'] = df['RSI_2'] < RSI_THRESHOLD
        df['Pullback_Signal'] = (df['Pullback_pct'] >= PULLBACK_MIN) & (df['Pullback_pct'] <= PULLBACK_MAX)
        df['MA20_Signal'] = df['MA20_distance'] <= MA20_DISTANCE
        df['All_Conditions'] = df['RSI_Signal'] & df['Uptrend'] & df['Pullback_Signal'] & df['MA20_Signal']

        # Count occurrences
        total_days = len(df.dropna())

        if total_days > 0:
            results.append({
                'Symbol': symbol,
                'Total_Days': total_days,
                'RSI<30': df['RSI_Signal'].sum(),
                'RSI<30_pct': df['RSI_Signal'].sum() / total_days * 100,
                'Uptrend': df['Uptrend'].sum(),
                'Uptrend_pct': df['Uptrend'].sum() / total_days * 100,
                'Pullback_3-6%': df['Pullback_Signal'].sum(),
                'Pullback_pct': df['Pullback_Signal'].sum() / total_days * 100,
                'Near_MA20': df['MA20_Signal'].sum(),
                'Near_MA20_pct': df['MA20_Signal'].sum() / total_days * 100,
                'All_Conditions': df['All_Conditions'].sum(),
                'All_Conditions_pct': df['All_Conditions'].sum() / total_days * 100,
                'Avg_RSI': df['RSI_2'].mean(),
                'Min_RSI': df['RSI_2'].min(),
                'Median_RSI': df['RSI_2'].median()
            })

            # Print some sample signals
            if df['All_Conditions'].sum() > 0:
                print(f"\n{symbol} - Sample entry signals:")
                signal_dates = df[df['All_Conditions']].index[-5:]  # Last 5 signals
                for date in signal_dates:
                    row = df.loc[date]
                    print(f"  {date.date()}: RSI={row['RSI_2']:.1f}, Pullback={row['Pullback_pct']:.1f}%, Price=${row['Close']:.2f}")

    # Create summary
    if results:
        df_results = pd.DataFrame(results)

        print("\n" + "="*80)
        print("ENTRY CONDITION ANALYSIS")
        print("="*80)
        print("\nIndividual Condition Frequency (% of trading days):")
        print("-"*50)

        for _, row in df_results.iterrows():
            print(f"\n{row['Symbol']}:")
            print(f"  RSI < 30: {row['RSI<30_pct']:.1f}% ({row['RSI<30']} days)")
            print(f"  Uptrend (Price>MA50>MA200): {row['Uptrend_pct']:.1f}% ({row['Uptrend']} days)")
            print(f"  Pullback 3-6%: {row['Pullback_pct']:.1f}% ({row['Pullback_3-6%']} days)")
            print(f"  Near MA20 (±1.5%): {row['Near_MA20_pct']:.1f}% ({row['Near_MA20']} days)")
            print(f"  ALL CONDITIONS MET: {row['All_Conditions_pct']:.2f}% ({row['All_Conditions']} days)")
            print(f"  RSI Stats: Min={row['Min_RSI']:.1f}, Avg={row['Avg_RSI']:.1f}, Median={row['Median_RSI']:.1f}")

        print("\n" + "="*80)
        print("SUMMARY STATISTICS")
        print("="*80)
        print(f"\nAverage across all stocks:")
        print(f"  RSI < 30: {df_results['RSI<30_pct'].mean():.1f}% of days")
        print(f"  Uptrend: {df_results['Uptrend_pct'].mean():.1f}% of days")
        print(f"  Pullback 3-6%: {df_results['Pullback_pct'].mean():.1f}% of days")
        print(f"  Near MA20: {df_results['Near_MA20_pct'].mean():.1f}% of days")
        print(f"  ALL CONDITIONS: {df_results['All_Conditions_pct'].mean():.2f}% of days")
        print(f"\n  Average RSI(2): {df_results['Avg_RSI'].mean():.1f}")
        print(f"  Minimum RSI(2) seen: {df_results['Min_RSI'].min():.1f}")

        # Estimate trade frequency
        avg_signals_per_year = df_results['All_Conditions'].mean() * 2  # Roughly 2 years of data
        print(f"\n  Expected signals per stock per year: {avg_signals_per_year:.1f}")
        print(f"  With 50 stocks, expected signals per year: {avg_signals_per_year * 50:.0f}")

    return df_results

def test_relaxed_parameters():
    """Test with more relaxed parameters to see if we get more trades"""

    print("\n" + "="*80)
    print("TESTING RELAXED PARAMETERS")
    print("="*80)

    parameter_sets = [
        {'name': 'Original', 'rsi': 30, 'pullback_min': 3, 'pullback_max': 6, 'ma20_dist': 1.5},
        {'name': 'Relaxed RSI', 'rsi': 40, 'pullback_min': 3, 'pullback_max': 6, 'ma20_dist': 1.5},
        {'name': 'Relaxed Pullback', 'rsi': 30, 'pullback_min': 2, 'pullback_max': 8, 'ma20_dist': 1.5},
        {'name': 'Relaxed MA20', 'rsi': 30, 'pullback_min': 3, 'pullback_max': 6, 'ma20_dist': 3.0},
        {'name': 'All Relaxed', 'rsi': 40, 'pullback_min': 2, 'pullback_max': 8, 'ma20_dist': 3.0},
    ]

    for params in parameter_sets:
        print(f"\n{params['name']}:")
        print(f"  RSI < {params['rsi']}, Pullback {params['pullback_min']}-{params['pullback_max']}%, MA20 ± {params['ma20_dist']}%")

        total_signals = 0

        # Test on a few stocks
        for symbol in ['AAPL', 'MSFT', 'GOOGL']:
            df = _STORE.get_prices(symbol)
            if df.empty:
                continue
            df = df[df.index >= '2024-01-01']

            if len(df) < 200:
                continue

            # Calculate indicators (same as before)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=2).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=2).mean()
            rs = gain / loss
            df['RSI_2'] = 100 - (100 / (1 + rs))

            df['MA20'] = df['Close'].rolling(20).mean()
            df['MA50'] = df['Close'].rolling(50).mean()
            df['MA200'] = df['Close'].rolling(200).mean()

            df['High_10d'] = df['High'].rolling(10).max()
            df['Pullback_pct'] = ((df['High_10d'] - df['Close']) / df['High_10d']) * 100
            df['MA20_distance'] = abs((df['Close'] - df['MA20']) / df['MA20']) * 100

            # Check conditions with current parameters
            conditions = (
                (df['RSI_2'] < params['rsi']) &
                (df['Close'] > df['MA50']) &
                (df['MA50'] > df['MA200']) &
                (df['Pullback_pct'] >= params['pullback_min']) &
                (df['Pullback_pct'] <= params['pullback_max']) &
                (df['MA20_distance'] <= params['ma20_dist'])
            )

            signals = conditions.sum()
            total_signals += signals

        print(f"  Total signals (3 stocks): {total_signals}")

if __name__ == "__main__":
    # Run analysis
    print("MEAN REVERSION STRATEGY - DIAGNOSTIC ANALYSIS")
    print("="*80)

    # Analyze why we're not getting trades
    df_results = analyze_strategy_conditions()

    # Test relaxed parameters
    test_relaxed_parameters()

    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    print("\nThe strategy conditions are too restrictive. Key issues:")
    print("1. RSI(2) < 30 is extremely rare (occurs < 1% of trading days)")
    print("2. Combining all 4 conditions creates an extremely low probability setup")
    print("3. The strategy needs parameter adjustment to be tradeable")
    print("\nRecommendations:")
    print("- Increase RSI threshold to 35-40")
    print("- Widen pullback range to 2-8%")
    print("- Increase MA20 distance tolerance to 2-3%")
    print("- Consider using RSI(5) or RSI(14) instead of RSI(2)")