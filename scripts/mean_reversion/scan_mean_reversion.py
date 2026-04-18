"""Production scanner using trained mean reversion model"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import warnings
import argparse
warnings.filterwarnings('ignore')

from src.models.config import ModelConfig
from src.models.data_loader import DataLoader
from src.models.features import FeatureEngineer
from src.models.model import MeanReversionModel


def calculate_trend_quality(features_row):
    """Calculate trend quality score (0-100, higher = better uptrend)"""

    score = 0

    # Price position (30 points)
    if features_row.get('price_above_ma50', 0) == 1:
        score += 15
    if features_row.get('price_above_ma200', 0) == 1:
        score += 15

    # Directional movement (40 points)
    di_diff = features_row.get('di_diff', 0)
    if di_diff > 10:  # Strong uptrend
        score += 40
    elif di_diff > 0:  # Weak uptrend
        score += 20
    elif di_diff > -10:  # Weak downtrend
        score += 10

    # Trend alignment (30 points)
    if features_row.get('trend_alignment', 0) == 1:
        score += 20
    if features_row.get('ma50_slope', 0) > 0:
        score += 10

    return score


def calculate_position_sizing(price, stop_pct, balance, max_positions=5, risk_pct=0.015):
    """
    Calculate position sizing based on risk management

    Args:
        price: Current stock price
        stop_pct: Stop loss percentage (e.g., 0.03 for -3%)
        balance: Total account balance
        max_positions: Maximum concurrent positions (default: 5)
        risk_pct: Risk per trade as % of balance (default: 1.5%)

    Returns:
        dict with shares, position_value, dollar_risk, pct_of_portfolio
    """
    # Method 1: Equal allocation (simple)
    equal_position_value = balance / max_positions
    equal_shares = int(equal_position_value / price)

    # Method 2: Risk-based sizing (risk X% of capital per trade)
    risk_dollars = balance * risk_pct
    position_value_risk = risk_dollars / stop_pct
    risk_shares = int(position_value_risk / price)

    # Use the more conservative approach
    shares = min(equal_shares, risk_shares)
    position_value = shares * price
    dollar_risk = shares * price * stop_pct
    pct_of_portfolio = (position_value / balance) * 100

    return {
        'shares': shares,
        'position_value': position_value,
        'dollar_risk': dollar_risk,
        'pct_of_portfolio': pct_of_portfolio
    }


def scan_for_opportunities(balance=None, max_positions=5, risk_pct=0.015):
    """
    Scan all symbols for mean reversion opportunities

    Args:
        balance: Account balance for position sizing (optional)
        max_positions: Maximum concurrent positions (default: 5)
        risk_pct: Risk per trade as % of balance (default: 1.5%)
    """

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
            # Calculate trend quality score
            trend_score = calculate_trend_quality(latest_features.iloc[0])

            # FILTER: Only Tier 2-3 (TQ 60-80) based on backtest results
            # Tier 1 (100): Negative expectancy in strong uptrends
            # Tier 4 (<60): Too risky in downtrends
            if trend_score < 60 or trend_score >= 90:
                continue

            current_price = df.iloc[-1]['Close']
            target_price = current_price * (1 + config.target_return)
            stop_price = current_price * (1 + config.stop_loss)

            opp = {
                'Symbol': symbol,
                'Confidence': confidence,
                'Trend_Quality': trend_score,
                'Entry': current_price,
                'Target': target_price,
                'Stop': stop_price,
                'Volume': df.iloc[-1]['Volume'],
                'RSI_14': latest_features.iloc[0].get('rsi_14', np.nan),
                'DI_Diff': latest_features.iloc[0].get('di_diff', np.nan),
            }

            # Add position sizing if balance provided
            if balance is not None:
                sizing = calculate_position_sizing(
                    current_price,
                    abs(config.stop_loss),
                    balance,
                    max_positions,
                    risk_pct
                )
                opp['Shares'] = sizing['shares']
                opp['Position_Value'] = sizing['position_value']
                opp['Risk_$'] = sizing['dollar_risk']
                opp['% Portfolio'] = sizing['pct_of_portfolio']

            opportunities.append(opp)

    # Sort by trend quality first, then confidence
    opportunities = sorted(opportunities, key=lambda x: (x['Trend_Quality'], x['Confidence']), reverse=True)

    # Display results
    print("\n" + "="*80)
    print("MEAN REVERSION OPPORTUNITIES - TIER 2-3 ONLY (Optimal Performance)")
    print("="*80)
    print(f"\nFound {len(opportunities)} opportunities (filtered to TQ 60-90)")
    print(f"Confidence threshold: {config.confidence_threshold:.0%}")
    print("\nBacktest-validated filters:")
    print("  ✓ Trend Quality 60-90 (Tier 2-3): 75-85% win rate, +0.90% avg return")
    print("  ✗ Excluded TQ 100 (too strong): 57% win rate, -0.03% avg return")
    print("  ✗ Excluded TQ <60 (downtrends): 64% win rate, -0.30% avg return\n")

    if opportunities:
        df_opps = pd.DataFrame(opportunities)

        # Format for display
        for col in ['Entry', 'Target', 'Stop']:
            if col in df_opps.columns:
                df_opps[col] = df_opps[col].apply(lambda x: f"${x:.2f}")
        if 'Position_Value' in df_opps.columns:
            df_opps['Position_Value'] = df_opps['Position_Value'].apply(lambda x: f"${x:,.0f}")
        if 'Risk_$' in df_opps.columns:
            df_opps['Risk_$'] = df_opps['Risk_$'].apply(lambda x: f"${x:.0f}")
        if '% Portfolio' in df_opps.columns:
            df_opps['% Portfolio'] = df_opps['% Portfolio'].apply(lambda x: f"{x:.1f}%")
        df_opps['Confidence'] = df_opps['Confidence'].apply(lambda x: f"{x:.1%}")
        df_opps['RSI_14'] = df_opps['RSI_14'].apply(lambda x: f"{x:.1f}" if not pd.isna(x) else "N/A")
        df_opps['DI_Diff'] = df_opps['DI_Diff'].apply(lambda x: f"{x:+.1f}" if not pd.isna(x) else "N/A")

        print(df_opps.to_string(index=False))

        if balance is not None:
            total_capital_used = sum([opp['Position_Value'] for opp in opportunities])
            total_risk = sum([opp['Risk_$'] for opp in opportunities])
            print("\n" + "-"*80)
            print(f"PORTFOLIO SUMMARY (Balance: ${balance:,.0f})")
            print(f"  Total positions: {len(opportunities)} (max: {max_positions})")
            print(f"  Capital allocated: ${total_capital_used:,.0f} ({(total_capital_used/balance)*100:.1f}%)")
            print(f"  Total risk: ${total_risk:,.0f} ({(total_risk/balance)*100:.2f}%)")
            print(f"  Risk per trade: {risk_pct*100:.1f}% of balance")
            print("-"*80)

        print("\n" + "-"*80)
        print(f"Trade Setup: Entry at close → Target +2% → Stop -3% → Max hold 10 days")
        print(f"Expected: 75-85% win rate, +0.90% avg return per trade")
        print("-"*80)

    return opportunities


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Mean Reversion Scanner with Position Sizing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic scan without position sizing
  python scan_mean_reversion.py

  # Scan with $10,000 account balance
  python scan_mean_reversion.py --balance 10000

  # Custom risk settings: $25k balance, max 3 positions, risk 2% per trade
  python scan_mean_reversion.py --balance 25000 --max-positions 3 --risk-pct 2.0
        """
    )
    parser.add_argument(
        '--balance', '-b',
        type=float,
        default=None,
        help='Account balance for position sizing (e.g., 10000)'
    )
    parser.add_argument(
        '--max-positions', '-m',
        type=int,
        default=5,
        help='Maximum concurrent positions (default: 5)'
    )
    parser.add_argument(
        '--risk-pct', '-r',
        type=float,
        default=1.5,
        help='Risk per trade as %% of balance (default: 1.5)'
    )

    args = parser.parse_args()

    # Convert risk percentage to decimal
    risk_pct = args.risk_pct / 100

    opportunities = scan_for_opportunities(
        balance=args.balance,
        max_positions=args.max_positions,
        risk_pct=risk_pct
    )
