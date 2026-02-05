"""
CRITICAL ANALYSIS: Mean Reversion Model Performance Investigation
==================================================================

This script investigates why the mean reversion model has poor performance:
- Base success rate: 31.27%
- Cross-validation AUC: 0.5649 (barely above random)

Key Questions:
1. Are 1.5x ATR targets too aggressive?
2. Is the model calibrated? (predicted prob vs actual win rate)
3. Should we do the OPPOSITE? (momentum instead of mean reversion)
4. What's the distribution of returns?
5. Is this approach viable?
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')
from typing import Dict, List, Tuple

from src.models.config import ModelConfig
from src.models.data_loader import DataLoader
from src.models.features import FeatureEngineer


class MeanReversionAnalysis:
    """Comprehensive analysis of mean reversion strategy viability"""

    def __init__(self):
        self.config = ModelConfig()
        self.data_loader = DataLoader()
        self.feature_engineer = FeatureEngineer(self.config)

    def test_atr_multipliers(self, symbols: List[str], atr_multipliers: List[float]) -> pd.DataFrame:
        """Test different ATR multipliers to find optimal target size"""
        print("\n" + "="*80)
        print("ANALYSIS 1: ATR MULTIPLIER SENSITIVITY")
        print("="*80)
        print("\nTesting different ATR multipliers for profit targets...")
        print("Question: Are 1.5x ATR targets too aggressive?\n")

        results = []

        for atr_mult in atr_multipliers:
            print(f"\nTesting ATR multiplier: {atr_mult}x")

            success_rates = []
            hit_target_pcts = []
            hit_stop_pcts = []
            expired_pcts = []
            avg_returns = []

            for symbol in symbols:
                df = self.data_loader.load_symbol(symbol, start_date="2020-01-01", end_date="2024-01-01")
                if df.empty or len(df) < 100:
                    continue

                # Calculate ATR
                atr = self.feature_engineer.calculate_atr(df, period=14)

                # Test trades
                trade_outcomes = self._test_trades_with_atr(df, atr, atr_mult)

                if len(trade_outcomes) > 0:
                    success_rates.append(trade_outcomes['success_rate'])
                    hit_target_pcts.append(trade_outcomes['hit_target_pct'])
                    hit_stop_pcts.append(trade_outcomes['hit_stop_pct'])
                    expired_pcts.append(trade_outcomes['expired_pct'])
                    avg_returns.append(trade_outcomes['avg_return'])

            if len(success_rates) > 0:
                results.append({
                    'atr_multiplier': atr_mult,
                    'avg_success_rate': np.mean(success_rates),
                    'avg_hit_target_pct': np.mean(hit_target_pcts),
                    'avg_hit_stop_pct': np.mean(hit_stop_pcts),
                    'avg_expired_pct': np.mean(expired_pcts),
                    'avg_return': np.mean(avg_returns),
                    'expectancy': np.mean(avg_returns)  # Expected return per trade
                })

                print(f"  Success Rate: {np.mean(success_rates):.1%}")
                print(f"  Hit Target: {np.mean(hit_target_pcts):.1%}")
                print(f"  Hit Stop: {np.mean(hit_stop_pcts):.1%}")
                print(f"  Expired: {np.mean(expired_pcts):.1%}")
                print(f"  Avg Return: {np.mean(avg_returns):.2%}")

        results_df = pd.DataFrame(results)

        print("\n" + "-"*80)
        print("SUMMARY: ATR Multiplier Analysis")
        print("-"*80)
        print(results_df.to_string(index=False))

        best_mult = results_df.loc[results_df['avg_success_rate'].idxmax(), 'atr_multiplier']
        print(f"\nBest ATR multiplier: {best_mult}x (highest success rate)")

        best_expectancy = results_df.loc[results_df['expectancy'].idxmax()]
        print(f"Best expectancy: {best_expectancy['atr_multiplier']}x ATR "
              f"({best_expectancy['expectancy']:.2%} per trade)")

        return results_df

    def _test_trades_with_atr(self, df: pd.DataFrame, atr: pd.Series,
                              atr_multiplier: float) -> Dict:
        """Test trades using specific ATR multiplier"""
        max_holding = self.config.max_holding_days

        hit_target = 0
        hit_stop = 0
        expired = 0
        returns = []

        for i in range(len(df) - max_holding):
            if pd.isna(atr.iloc[i]) or atr.iloc[i] <= 0:
                continue

            entry_price = df['Close'].iloc[i]
            current_atr = atr.iloc[i]

            target_price = entry_price + (current_atr * atr_multiplier)
            stop_price = entry_price - (current_atr * 1.0)  # Keep stop at 1x ATR

            # Check outcome
            for j in range(1, max_holding + 1):
                if i + j >= len(df):
                    break

                future_high = df['High'].iloc[i + j]
                future_low = df['Low'].iloc[i + j]
                future_close = df['Close'].iloc[i + j]

                # Check if target hit
                if future_high >= target_price:
                    hit_target += 1
                    returns.append((target_price - entry_price) / entry_price)
                    break

                # Check if stop hit
                if future_low <= stop_price:
                    hit_stop += 1
                    returns.append((stop_price - entry_price) / entry_price)
                    break

                # If last day, expired
                if j == max_holding:
                    expired += 1
                    returns.append((future_close - entry_price) / entry_price)

        total_trades = hit_target + hit_stop + expired

        if total_trades == 0:
            return {}

        return {
            'success_rate': hit_target / total_trades,
            'hit_target_pct': hit_target / total_trades,
            'hit_stop_pct': hit_stop / total_trades,
            'expired_pct': expired / total_trades,
            'avg_return': np.mean(returns) if returns else 0
        }

    def test_momentum_vs_mean_reversion(self, symbols: List[str]) -> pd.DataFrame:
        """Compare mean reversion (buy dips) vs momentum (buy breakouts)"""
        print("\n" + "="*80)
        print("ANALYSIS 2: MOMENTUM vs MEAN REVERSION")
        print("="*80)
        print("\nShould we do the OPPOSITE?")
        print("Testing: Mean reversion (RSI < 30) vs Momentum (RSI > 70)\n")

        results = []

        for symbol in symbols:
            df = self.data_loader.load_symbol(symbol, start_date="2020-01-01", end_date="2024-01-01")
            if df.empty or len(df) < 100:
                continue

            # Calculate indicators
            rsi = self.feature_engineer.calculate_rsi(df['Close'], 14)
            atr = self.feature_engineer.calculate_atr(df, 14)
            ma_50 = df['Close'].rolling(50).mean()

            # Mean reversion signals (oversold)
            mean_rev_trades = self._backtest_strategy(
                df, rsi, atr, ma_50,
                condition=lambda r, p, m: r < 30 and p > m,
                name="Mean Reversion"
            )

            # Momentum signals (overbought + breakout)
            momentum_trades = self._backtest_strategy(
                df, rsi, atr, ma_50,
                condition=lambda r, p, m: r > 70 and p > m,
                name="Momentum"
            )

            if mean_rev_trades and momentum_trades:
                results.append({
                    'symbol': symbol,
                    'mean_rev_win_rate': mean_rev_trades['win_rate'],
                    'mean_rev_trades': mean_rev_trades['total_trades'],
                    'mean_rev_avg_return': mean_rev_trades['avg_return'],
                    'momentum_win_rate': momentum_trades['win_rate'],
                    'momentum_trades': momentum_trades['total_trades'],
                    'momentum_avg_return': momentum_trades['avg_return']
                })

        results_df = pd.DataFrame(results)

        if not results_df.empty:
            print("\nPer-Symbol Results:")
            print(results_df.to_string(index=False))

            print("\n" + "-"*80)
            print("AGGREGATE COMPARISON")
            print("-"*80)

            print(f"\nMean Reversion Strategy:")
            print(f"  Avg Win Rate: {results_df['mean_rev_win_rate'].mean():.1%}")
            print(f"  Avg Trades per Symbol: {results_df['mean_rev_trades'].mean():.0f}")
            print(f"  Avg Return per Trade: {results_df['mean_rev_avg_return'].mean():.2%}")

            print(f"\nMomentum Strategy:")
            print(f"  Avg Win Rate: {results_df['momentum_win_rate'].mean():.1%}")
            print(f"  Avg Trades per Symbol: {results_df['momentum_trades'].mean():.0f}")
            print(f"  Avg Return per Trade: {results_df['momentum_avg_return'].mean():.2%}")

            # Verdict
            mean_rev_better = results_df['mean_rev_win_rate'].mean() > results_df['momentum_win_rate'].mean()

            print("\n" + "="*80)
            print("VERDICT:")
            print("="*80)
            if mean_rev_better:
                diff = results_df['mean_rev_win_rate'].mean() - results_df['momentum_win_rate'].mean()
                print(f"Mean reversion performs BETTER by {diff:.1%}")
            else:
                diff = results_df['momentum_win_rate'].mean() - results_df['mean_rev_win_rate'].mean()
                print(f"Momentum performs BETTER by {diff:.1%}")
                print("\nYES - YOU SHOULD BE DOING THE OPPOSITE!")

        return results_df

    def _backtest_strategy(self, df: pd.DataFrame, rsi: pd.Series, atr: pd.Series,
                          ma_50: pd.Series, condition, name: str) -> Dict:
        """Backtest a trading strategy"""
        max_holding = self.config.max_holding_days

        wins = 0
        losses = 0
        returns = []

        for i in range(50, len(df) - max_holding):  # Start after MA50 is valid
            if pd.isna(rsi.iloc[i]) or pd.isna(atr.iloc[i]):
                continue

            current_rsi = rsi.iloc[i]
            current_price = df['Close'].iloc[i]
            current_ma = ma_50.iloc[i]

            # Check entry condition
            if not condition(current_rsi, current_price, current_ma):
                continue

            entry_price = current_price
            current_atr = atr.iloc[i]

            # Use 1.5x ATR target
            target_price = entry_price + (current_atr * 1.5)
            stop_price = entry_price - (current_atr * 1.0)

            # Check outcome
            for j in range(1, max_holding + 1):
                if i + j >= len(df):
                    break

                future_high = df['High'].iloc[i + j]
                future_low = df['Low'].iloc[i + j]
                future_close = df['Close'].iloc[i + j]

                if future_high >= target_price:
                    wins += 1
                    returns.append((target_price - entry_price) / entry_price)
                    break
                elif future_low <= stop_price:
                    losses += 1
                    returns.append((stop_price - entry_price) / entry_price)
                    break
                elif j == max_holding:
                    if future_close > entry_price:
                        wins += 1
                    else:
                        losses += 1
                    returns.append((future_close - entry_price) / entry_price)

        total = wins + losses

        if total == 0:
            return None

        return {
            'win_rate': wins / total,
            'total_trades': total,
            'avg_return': np.mean(returns) if returns else 0
        }

    def analyze_return_distribution(self, symbols: List[str]) -> None:
        """Analyze distribution of returns for mean reversion trades"""
        print("\n" + "="*80)
        print("ANALYSIS 3: RETURN DISTRIBUTION")
        print("="*80)
        print("\nWhat's the distribution of returns?")
        print("Are we experiencing fat tails (big losses)?\n")

        all_returns = []

        for symbol in symbols:
            df = self.data_loader.load_symbol(symbol, start_date="2020-01-01", end_date="2024-01-01")
            if df.empty or len(df) < 100:
                continue

            rsi = self.feature_engineer.calculate_rsi(df['Close'], 14)
            atr = self.feature_engineer.calculate_atr(df, 14)
            ma_50 = df['Close'].rolling(50).mean()

            max_holding = self.config.max_holding_days

            for i in range(50, len(df) - max_holding):
                if pd.isna(rsi.iloc[i]) or pd.isna(atr.iloc[i]):
                    continue

                # Mean reversion entry signal
                if rsi.iloc[i] >= 30 or df['Close'].iloc[i] <= ma_50.iloc[i]:
                    continue

                entry_price = df['Close'].iloc[i]
                current_atr = atr.iloc[i]

                target_price = entry_price + (current_atr * 1.5)
                stop_price = entry_price - (current_atr * 1.0)

                # Track outcome
                for j in range(1, max_holding + 1):
                    if i + j >= len(df):
                        break

                    future_high = df['High'].iloc[i + j]
                    future_low = df['Low'].iloc[i + j]
                    future_close = df['Close'].iloc[i + j]

                    if future_high >= target_price:
                        all_returns.append((target_price - entry_price) / entry_price)
                        break
                    elif future_low <= stop_price:
                        all_returns.append((stop_price - entry_price) / entry_price)
                        break
                    elif j == max_holding:
                        all_returns.append((future_close - entry_price) / entry_price)

        if len(all_returns) > 0:
            returns_pct = np.array(all_returns) * 100

            print(f"Total trades analyzed: {len(returns_pct)}")
            print(f"\nReturn Statistics:")
            print(f"  Mean: {returns_pct.mean():.2f}%")
            print(f"  Median: {np.median(returns_pct):.2f}%")
            print(f"  Std Dev: {returns_pct.std():.2f}%")
            print(f"  Min: {returns_pct.min():.2f}%")
            print(f"  Max: {returns_pct.max():.2f}%")

            print(f"\nPercentiles:")
            for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
                print(f"  {p}th: {np.percentile(returns_pct, p):.2f}%")

            print(f"\nDistribution Breakdown:")
            print(f"  Big wins (>5%): {(returns_pct > 5).sum()} ({(returns_pct > 5).sum()/len(returns_pct):.1%})")
            print(f"  Small wins (0-5%): {((returns_pct > 0) & (returns_pct <= 5)).sum()} "
                  f"({((returns_pct > 0) & (returns_pct <= 5)).sum()/len(returns_pct):.1%})")
            print(f"  Small losses (0 to -5%): {((returns_pct < 0) & (returns_pct >= -5)).sum()} "
                  f"({((returns_pct < 0) & (returns_pct >= -5)).sum()/len(returns_pct):.1%})")
            print(f"  Big losses (<-5%): {(returns_pct < -5).sum()} ({(returns_pct < -5).sum()/len(returns_pct):.1%})")

            # Check for fat tails
            print(f"\nFat Tail Analysis:")
            print(f"  Trades with losses > 2 std devs: {(returns_pct < (returns_pct.mean() - 2*returns_pct.std())).sum()}")
            print(f"  Worst 10 losses: {sorted(returns_pct)[:10]}")

    def test_alternative_definitions(self, symbols: List[str]) -> pd.DataFrame:
        """Test alternative success definitions"""
        print("\n" + "="*80)
        print("ANALYSIS 4: ALTERNATIVE SUCCESS DEFINITIONS")
        print("="*80)
        print("\nWhat if we define success differently?\n")

        results = []

        for symbol in symbols[:10]:  # Test on subset
            df = self.data_loader.load_symbol(symbol, start_date="2020-01-01", end_date="2024-01-01")
            if df.empty or len(df) < 100:
                continue

            rsi = self.feature_engineer.calculate_rsi(df['Close'], 14)
            atr = self.feature_engineer.calculate_atr(df, 14)
            ma_50 = df['Close'].rolling(50).mean()

            # Test different definitions
            atr_1_5x = self._test_alternative_target(df, rsi, atr, ma_50, target_mult=1.5, name="1.5x ATR")
            atr_1_0x = self._test_alternative_target(df, rsi, atr, ma_50, target_mult=1.0, name="1.0x ATR")
            fixed_2pct = self._test_fixed_target(df, rsi, ma_50, target_pct=0.02, name="Fixed 2%")
            fixed_5pct = self._test_fixed_target(df, rsi, ma_50, target_pct=0.05, name="Fixed 5%")
            any_profit = self._test_any_profit(df, rsi, ma_50, name="Any Profit")

            if all([atr_1_5x, atr_1_0x, fixed_2pct, fixed_5pct, any_profit]):
                results.append({
                    'symbol': symbol,
                    'atr_1_5x_win_rate': atr_1_5x['win_rate'],
                    'atr_1_0x_win_rate': atr_1_0x['win_rate'],
                    'fixed_2pct_win_rate': fixed_2pct['win_rate'],
                    'fixed_5pct_win_rate': fixed_5pct['win_rate'],
                    'any_profit_win_rate': any_profit['win_rate']
                })

        results_df = pd.DataFrame(results)

        if not results_df.empty:
            print(results_df.to_string(index=False))

            print("\n" + "-"*80)
            print("AVERAGE WIN RATES BY DEFINITION:")
            print("-"*80)
            print(f"  1.5x ATR target: {results_df['atr_1_5x_win_rate'].mean():.1%}")
            print(f"  1.0x ATR target: {results_df['atr_1_0x_win_rate'].mean():.1%}")
            print(f"  Fixed 2% target: {results_df['fixed_2pct_win_rate'].mean():.1%}")
            print(f"  Fixed 5% target: {results_df['fixed_5pct_win_rate'].mean():.1%}")
            print(f"  Any profit: {results_df['any_profit_win_rate'].mean():.1%}")

        return results_df

    def _test_alternative_target(self, df, rsi, atr, ma_50, target_mult, name):
        """Test with alternative ATR multiplier"""
        max_holding = self.config.max_holding_days
        wins = 0
        total = 0

        for i in range(50, len(df) - max_holding):
            if pd.isna(rsi.iloc[i]) or pd.isna(atr.iloc[i]):
                continue

            if rsi.iloc[i] >= 30 or df['Close'].iloc[i] <= ma_50.iloc[i]:
                continue

            entry_price = df['Close'].iloc[i]
            target_price = entry_price + (atr.iloc[i] * target_mult)
            stop_price = entry_price - (atr.iloc[i] * 1.0)

            for j in range(1, max_holding + 1):
                if i + j >= len(df):
                    break

                if df['High'].iloc[i + j] >= target_price:
                    wins += 1
                    total += 1
                    break
                elif df['Low'].iloc[i + j] <= stop_price:
                    total += 1
                    break
                elif j == max_holding:
                    total += 1

        return {'win_rate': wins / total if total > 0 else 0}

    def _test_fixed_target(self, df, rsi, ma_50, target_pct, name):
        """Test with fixed percentage target"""
        max_holding = self.config.max_holding_days
        wins = 0
        total = 0

        for i in range(50, len(df) - max_holding):
            if pd.isna(rsi.iloc[i]):
                continue

            if rsi.iloc[i] >= 30 or df['Close'].iloc[i] <= ma_50.iloc[i]:
                continue

            entry_price = df['Close'].iloc[i]
            target_price = entry_price * (1 + target_pct)
            stop_price = entry_price * 0.97  # 3% stop

            for j in range(1, max_holding + 1):
                if i + j >= len(df):
                    break

                if df['High'].iloc[i + j] >= target_price:
                    wins += 1
                    total += 1
                    break
                elif df['Low'].iloc[i + j] <= stop_price:
                    total += 1
                    break
                elif j == max_holding:
                    total += 1

        return {'win_rate': wins / total if total > 0 else 0}

    def _test_any_profit(self, df, rsi, ma_50, name):
        """Test if trade closes positive at any point"""
        max_holding = self.config.max_holding_days
        wins = 0
        total = 0

        for i in range(50, len(df) - max_holding):
            if pd.isna(rsi.iloc[i]):
                continue

            if rsi.iloc[i] >= 30 or df['Close'].iloc[i] <= ma_50.iloc[i]:
                continue

            entry_price = df['Close'].iloc[i]

            # Check if any day closes profitable
            profitable = False
            for j in range(1, max_holding + 1):
                if i + j >= len(df):
                    break

                if df['Close'].iloc[i + j] > entry_price:
                    profitable = True
                    break

            if profitable:
                wins += 1
            total += 1

        return {'win_rate': wins / total if total > 0 else 0}


def main():
    """Run comprehensive analysis"""
    print("\n" + "="*80)
    print("MEAN REVERSION MODEL: CRITICAL ANALYSIS")
    print("="*80)
    print("\nInvestigating poor performance (31% win rate, 0.56 AUC)")
    print("Key question: Should we be doing the OPPOSITE?\n")

    analyzer = MeanReversionAnalysis()

    # Select liquid stocks for analysis
    test_symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'JPM', 'BAC', 'V', 'MA', 'HD', 'WMT', 'PG', 'DIS'
    ]

    # Filter to available symbols
    available_symbols = [s for s in test_symbols if s in analyzer.data_loader.available_symbols]
    print(f"Testing on {len(available_symbols)} symbols: {', '.join(available_symbols)}\n")

    # Run analyses

    # 1. ATR multiplier sensitivity
    atr_results = analyzer.test_atr_multipliers(
        available_symbols,
        atr_multipliers=[0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
    )

    # 2. Momentum vs Mean Reversion
    comparison_results = analyzer.test_momentum_vs_mean_reversion(available_symbols)

    # 3. Return distribution
    analyzer.analyze_return_distribution(available_symbols)

    # 4. Alternative definitions
    alt_results = analyzer.test_alternative_definitions(available_symbols)

    # Final recommendations
    print("\n" + "="*80)
    print("FINAL RECOMMENDATIONS")
    print("="*80)

    print("\n1. ATR TARGET SIZING:")
    if not atr_results.empty:
        best_atr = atr_results.loc[atr_results['avg_success_rate'].idxmax()]
        print(f"   - Current: 1.5x ATR ({atr_results[atr_results['atr_multiplier']==1.5]['avg_success_rate'].values[0]:.1%} win rate)")
        print(f"   - Optimal: {best_atr['atr_multiplier']}x ATR ({best_atr['avg_success_rate']:.1%} win rate)")
        print(f"   - Recommendation: {'CHANGE TO ' + str(best_atr['atr_multiplier']) + 'x' if best_atr['atr_multiplier'] != 1.5 else 'KEEP CURRENT'}")

    print("\n2. STRATEGY DIRECTION:")
    if not comparison_results.empty:
        mean_rev_wr = comparison_results['mean_rev_win_rate'].mean()
        momentum_wr = comparison_results['momentum_win_rate'].mean()

        if momentum_wr > mean_rev_wr:
            print(f"   - Mean reversion: {mean_rev_wr:.1%} win rate")
            print(f"   - Momentum: {momentum_wr:.1%} win rate")
            print(f"   - Recommendation: SWITCH TO MOMENTUM STRATEGY")
        else:
            print(f"   - Mean reversion is superior ({mean_rev_wr:.1%} vs {momentum_wr:.1%})")
            print(f"   - Recommendation: STICK WITH MEAN REVERSION")

    print("\n3. MODEL VIABILITY:")
    if not atr_results.empty:
        best_expectancy = atr_results['expectancy'].max()
        if best_expectancy > 0.005:  # > 0.5% per trade
            print(f"   - Best expectancy: {best_expectancy:.2%} per trade")
            print(f"   - Recommendation: VIABLE (positive edge exists)")
        else:
            print(f"   - Best expectancy: {best_expectancy:.2%} per trade")
            print(f"   - Recommendation: NOT VIABLE (edge too small or negative)")

    print("\n4. NEXT STEPS:")
    print("   - If viable: Retrain model with optimal ATR multiplier")
    print("   - If not viable: Consider alternative strategies (momentum, breakout, etc.)")
    print("   - Focus on model calibration (predicted prob should match actual win rate)")
    print("   - Consider ensemble approach (combine mean reversion + momentum signals)")


if __name__ == "__main__":
    main()
