"""
90-Day Walk-Forward Backtest for Mean Reversion Scanner
Replays scanner daily and tracks actual outcomes with proper look-ahead bias prevention
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = 'data/stock_history'


@dataclass
class Signal:
    """Represents a trading signal"""
    symbol: str
    signal_date: str
    entry_price: float
    target_price: float
    stop_price: float
    rsi: float
    pullback_pct: float
    distance_to_ma20: float
    ma20: float
    ma50: float
    ma200: float
    in_uptrend: bool
    trend_quality: int
    confidence: float

    # Outcomes (filled later)
    outcome: Optional[str] = None
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    days_to_exit: Optional[int] = None
    pnl_pct: Optional[float] = None
    hit_target: Optional[bool] = None
    hit_stop: Optional[bool] = None


class WalkForwardBacktest:
    """
    Walk-forward backtester that replays scanner daily
    Tracks outcomes with no look-ahead bias
    """

    def __init__(self, lookback_days: int = 90, hold_period: int = 10,
                 require_uptrend: bool = True):
        self.lookback_days = lookback_days
        self.hold_period = hold_period
        self.target_pct = 0.02  # +2% target
        self.stop_pct = -0.03   # -3% stop
        self.commission_pct = 0.001  # 0.1% round-trip
        self.require_uptrend = require_uptrend

    def load_stock_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Load cached stock data"""
        filepath = os.path.join(DATA_DIR, f"{symbol}.csv")
        if not os.path.exists(filepath):
            return None

        data = pd.read_csv(filepath, index_col=0, parse_dates=True)
        data.index = pd.to_datetime(data.index, utc=True).tz_localize(None)
        return data

    def calculate_rsi(self, prices: pd.Series, period: int = 2) -> pd.Series:
        """Calculate RSI using Wilder's smoothing"""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_adx(self, data: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series]:
        """Calculate ADX and Directional Index difference"""
        high = data['High']
        low = data['Low']
        close = data['Close']

        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Directional Movement
        up_move = high - high.shift()
        down_move = low.shift() - low

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

        plus_dm = pd.Series(plus_dm, index=data.index)
        minus_dm = pd.Series(minus_dm, index=data.index)

        # Smoothed indicators
        atr = tr.ewm(alpha=1/period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1e-10)
        adx = dx.ewm(alpha=1/period, adjust=False).mean()

        di_diff = plus_di - minus_di

        return adx, di_diff

    def calculate_trend_quality(self, data_slice: pd.DataFrame) -> int:
        """
        Calculate trend quality score
        100 = strong uptrend (DI+ > DI- and ADX > 25)
        80 = moderate uptrend (DI+ > DI- and ADX 20-25)
        50-70 = weak uptrend (DI+ > DI- and ADX < 20)
        <50 = downtrend (DI- > DI+)
        """
        try:
            adx, di_diff = self.calculate_adx(data_slice)
            current_adx = adx.iloc[-1]
            current_di_diff = di_diff.iloc[-1]

            if current_di_diff > 0:  # Uptrend (DI+ > DI-)
                if current_adx > 25:
                    return 100
                elif current_adx > 20:
                    return 80
                elif current_adx > 15:
                    return 70
                else:
                    return 60
            else:  # Downtrend (DI- > DI+)
                if current_adx > 25:
                    return 20
                elif current_adx > 20:
                    return 30
                else:
                    return 40
        except:
            return 50

    def calculate_confidence(self, rsi: float, pullback: float,
                           distance_to_ma: float, trend_quality: int) -> float:
        """
        Calculate signal confidence (0-100)
        Higher confidence = better setup
        """
        score = 0

        # RSI component (0-30 points)
        if rsi < 15:
            score += 30
        elif rsi < 20:
            score += 25
        elif rsi < 25:
            score += 20
        elif rsi < 30:
            score += 15

        # Pullback component (0-25 points)
        if 3.5 <= pullback <= 4.5:
            score += 25
        elif 3.0 <= pullback <= 5.0:
            score += 20
        elif 2.5 <= pullback <= 5.5:
            score += 15
        elif 2.0 <= pullback <= 6.0:
            score += 10

        # Distance to MA20 component (0-20 points)
        if distance_to_ma <= 0.5:
            score += 20
        elif distance_to_ma <= 1.0:
            score += 15
        elif distance_to_ma <= 1.5:
            score += 10
        elif distance_to_ma <= 2.0:
            score += 5

        # Trend quality component (0-25 points)
        if trend_quality >= 100:
            score += 25
        elif trend_quality >= 80:
            score += 20
        elif trend_quality >= 70:
            score += 15
        elif trend_quality >= 60:
            score += 10
        elif trend_quality >= 50:
            score += 5

        return score

    def scan_on_date(self, symbol: str, scan_date: pd.Timestamp,
                     data: pd.DataFrame) -> Optional[Signal]:
        """
        Run scanner as if it were scan_date
        Only use data available up to and including scan_date
        """
        # Get data up to scan_date only (no look-ahead)
        data_slice = data[data.index <= scan_date].copy()

        if len(data_slice) < 200:
            return None

        # Calculate indicators
        data_slice['RSI_2'] = self.calculate_rsi(data_slice['Close'], period=2)
        data_slice['MA20'] = data_slice['Close'].rolling(20).mean()
        data_slice['MA50'] = data_slice['Close'].rolling(50).mean()
        data_slice['MA200'] = data_slice['Close'].rolling(200).mean()

        # Current values
        current_price = data_slice['Close'].iloc[-1]
        current_rsi = data_slice['RSI_2'].iloc[-1]
        ma20 = data_slice['MA20'].iloc[-1]
        ma50 = data_slice['MA50'].iloc[-1]
        ma200 = data_slice['MA200'].iloc[-1]

        # Check for NaN values
        if pd.isna([current_price, current_rsi, ma20, ma50, ma200]).any():
            return None

        # 1. Check uptrend
        in_uptrend = (current_price > ma50) and (ma50 > ma200)

        # Skip if uptrend required but not present
        if self.require_uptrend and not in_uptrend:
            return None

        # 2. Check pullback (3-6% from 10-day high)
        high_10d = data_slice['High'].tail(10).max()
        pullback_pct = ((high_10d - current_price) / high_10d) * 100
        valid_pullback = 3 <= pullback_pct <= 6

        # 3. Check distance to MA20
        distance_pct = abs((current_price - ma20) / ma20) * 100

        # 4. Check RSI oversold
        if current_rsi > 30:
            return None

        # Must have valid pullback to generate signal
        if not valid_pullback:
            return None

        # Calculate trend quality
        trend_quality = self.calculate_trend_quality(data_slice)

        # Calculate confidence
        confidence = self.calculate_confidence(
            current_rsi, pullback_pct, distance_pct, trend_quality
        )

        # Define trade parameters
        entry_price = current_price
        target_price = entry_price * (1 + self.target_pct)
        stop_price = entry_price * (1 + self.stop_pct)

        return Signal(
            symbol=symbol,
            signal_date=scan_date.strftime('%Y-%m-%d'),
            entry_price=round(entry_price, 2),
            target_price=round(target_price, 2),
            stop_price=round(stop_price, 2),
            rsi=round(current_rsi, 1),
            pullback_pct=round(pullback_pct, 1),
            distance_to_ma20=round(distance_pct, 2),
            ma20=round(ma20, 2),
            ma50=round(ma50, 2),
            ma200=round(ma200, 2),
            in_uptrend=in_uptrend,
            trend_quality=trend_quality,
            confidence=round(confidence, 1)
        )

    def track_outcome(self, signal: Signal, data: pd.DataFrame) -> Signal:
        """
        Track what happened after the signal
        Check next N days to see if target/stop hit
        """
        signal_date = pd.to_datetime(signal.signal_date)

        # Get future data (next hold_period days after signal)
        future_data = data[data.index > signal_date].head(self.hold_period)

        if len(future_data) == 0:
            signal.outcome = "NO_DATA"
            return signal

        entry_price = signal.entry_price
        target_price = signal.target_price
        stop_price = signal.stop_price

        # Check each day for target/stop hit
        for i, (date, row) in enumerate(future_data.iterrows()):
            high = row['High']
            low = row['Low']
            close = row['Close']

            # Check if target hit (intraday)
            if high >= target_price:
                signal.outcome = "WIN"
                signal.exit_price = target_price
                signal.exit_date = date.strftime('%Y-%m-%d')
                signal.days_to_exit = i + 1
                signal.pnl_pct = self.target_pct * 100 - self.commission_pct * 100
                signal.hit_target = True
                signal.hit_stop = False
                return signal

            # Check if stop hit (intraday)
            if low <= stop_price:
                signal.outcome = "LOSS"
                signal.exit_price = stop_price
                signal.exit_date = date.strftime('%Y-%m-%d')
                signal.days_to_exit = i + 1
                signal.pnl_pct = self.stop_pct * 100 - self.commission_pct * 100
                signal.hit_target = False
                signal.hit_stop = True
                return signal

        # Neither target nor stop hit - exit at close of last day
        final_close = future_data['Close'].iloc[-1]
        pnl_pct = ((final_close - entry_price) / entry_price) * 100 - self.commission_pct * 100

        signal.outcome = "EXPIRE"
        signal.exit_price = round(final_close, 2)
        signal.exit_date = future_data.index[-1].strftime('%Y-%m-%d')
        signal.days_to_exit = len(future_data)
        signal.pnl_pct = round(pnl_pct, 2)
        signal.hit_target = False
        signal.hit_stop = False

        return signal

    def run_backtest(self, symbols: List[str]) -> List[Signal]:
        """
        Run walk-forward backtest across all symbols
        For each trading day, scan all symbols and track outcomes
        """
        print(f"Starting 90-day walk-forward backtest...")
        print(f"Target: +{self.target_pct*100}% | Stop: {self.stop_pct*100}%")
        print(f"Hold period: {self.hold_period} days")
        print(f"Commission: {self.commission_pct*100}% round-trip\n")

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.lookback_days + self.hold_period + 90)

        all_signals = []
        symbols_processed = 0
        days_scanned = 0

        for symbol in symbols:
            data = self.load_stock_data(symbol)
            if data is None:
                continue

            # Filter to our date range
            data = data[(data.index >= start_date) & (data.index <= end_date)]

            if len(data) < 200:
                continue

            symbols_processed += 1

            # Get trading days in last 90 days
            scan_end = end_date - timedelta(days=self.hold_period)
            scan_start = scan_end - timedelta(days=self.lookback_days)

            trading_days = data[(data.index >= scan_start) & (data.index <= scan_end)].index
            days_scanned = max(days_scanned, len(trading_days))

            # Scan each day
            for scan_date in trading_days:
                signal = self.scan_on_date(symbol, scan_date, data)

                if signal is not None:
                    # Track outcome
                    signal = self.track_outcome(signal, data)
                    all_signals.append(signal)

        print(f"Symbols processed: {symbols_processed}")
        print(f"Trading days scanned: {days_scanned}")
        print(f"Total signals generated: {len(all_signals)}\n")
        return all_signals

    def analyze_results(self, signals: List[Signal]) -> pd.DataFrame:
        """Comprehensive performance analysis"""
        if not signals:
            print("No signals to analyze")
            return pd.DataFrame()

        df = pd.DataFrame([vars(s) for s in signals])

        # Overall performance
        print("="*80)
        print("OVERALL PERFORMANCE")
        print("="*80)

        total_signals = len(df)
        wins = len(df[df['outcome'] == 'WIN'])
        losses = len(df[df['outcome'] == 'LOSS'])
        expires = len(df[df['outcome'] == 'EXPIRE'])

        win_rate = (wins / total_signals) * 100 if total_signals > 0 else 0

        avg_win = df[df['outcome'] == 'WIN']['pnl_pct'].mean() if wins > 0 else 0
        avg_loss = df[df['outcome'] == 'LOSS']['pnl_pct'].mean() if losses > 0 else 0
        avg_expire = df[df['outcome'] == 'EXPIRE']['pnl_pct'].mean() if expires > 0 else 0

        avg_return = df['pnl_pct'].mean()
        total_return = df['pnl_pct'].sum()

        # Expectancy
        win_prob = wins / total_signals if total_signals > 0 else 0
        loss_prob = losses / total_signals if total_signals > 0 else 0
        expire_prob = expires / total_signals if total_signals > 0 else 0

        expectancy = (win_prob * avg_win) + (loss_prob * avg_loss) + (expire_prob * avg_expire)

        print(f"Total Signals: {total_signals}")
        print(f"Wins: {wins} ({win_rate:.1f}%)")
        print(f"Losses: {losses} ({losses/total_signals*100:.1f}%)")
        print(f"Expires: {expires} ({expires/total_signals*100:.1f}%)")
        print(f"\nAverage Win: +{avg_win:.2f}%")
        print(f"Average Loss: {avg_loss:.2f}%")
        print(f"Average Expire: {avg_expire:.2f}%")
        print(f"\nAverage Return Per Trade: {avg_return:.2f}%")
        print(f"Cumulative Return: {total_return:.2f}%")
        print(f"Expectancy: {expectancy:.2f}%")

        # Best/worst
        best_trade = df.loc[df['pnl_pct'].idxmax()]
        worst_trade = df.loc[df['pnl_pct'].idxmin()]

        print(f"\nBest Trade: {best_trade['symbol']} on {best_trade['signal_date']} (+{best_trade['pnl_pct']:.2f}%)")
        print(f"Worst Trade: {worst_trade['symbol']} on {worst_trade['signal_date']} ({worst_trade['pnl_pct']:.2f}%)")

        # Sharpe ratio (annualized, assuming ~250 trading days)
        if len(df) > 1:
            sharpe = (df['pnl_pct'].mean() / df['pnl_pct'].std()) * np.sqrt(250 / self.hold_period)
            print(f"Sharpe Ratio: {sharpe:.2f}")

        # Max consecutive losses
        df['is_loss'] = df['pnl_pct'] < 0
        df['loss_streak'] = (df['is_loss'] != df['is_loss'].shift()).cumsum()
        max_consecutive = df[df['is_loss']].groupby('loss_streak').size().max() if df['is_loss'].any() else 0
        print(f"Max Consecutive Losses: {max_consecutive}")

        # Performance by Trend Quality
        print("\n" + "="*80)
        print("PERFORMANCE BY TREND QUALITY")
        print("="*80)

        tier_mapping = {
            100: "Tier 1 (TQ 100 - Strong Uptrend)",
            80: "Tier 2 (TQ 80 - Moderate Uptrend)",
            70: "Tier 3 (TQ 70 - Weak Uptrend)",
            60: "Tier 3 (TQ 60 - Weak Uptrend)",
            40: "Tier 4 (TQ 40 - Downtrend)",
            30: "Tier 4 (TQ 30 - Downtrend)",
            20: "Tier 4 (TQ 20 - Downtrend)"
        }

        df['tier'] = df['trend_quality'].map(tier_mapping).fillna("Other")

        for tier in sorted(df['tier'].unique()):
            tier_df = df[df['tier'] == tier]
            tier_count = len(tier_df)
            tier_wins = len(tier_df[tier_df['outcome'] == 'WIN'])
            tier_win_rate = (tier_wins / tier_count) * 100 if tier_count > 0 else 0
            tier_avg_return = tier_df['pnl_pct'].mean()
            tier_total_return = tier_df['pnl_pct'].sum()

            print(f"\n{tier}:")
            print(f"  Signals: {tier_count}")
            print(f"  Win Rate: {tier_win_rate:.1f}%")
            print(f"  Avg Return: {tier_avg_return:.2f}%")
            print(f"  Total Return: {tier_total_return:.2f}%")

        # Performance by Confidence Threshold
        print("\n" + "="*80)
        print("PERFORMANCE BY CONFIDENCE THRESHOLD")
        print("="*80)

        for threshold in [50, 55, 60, 65, 70, 75]:
            conf_df = df[df['confidence'] >= threshold]
            conf_count = len(conf_df)

            if conf_count == 0:
                continue

            conf_wins = len(conf_df[conf_df['outcome'] == 'WIN'])
            conf_win_rate = (conf_wins / conf_count) * 100
            conf_avg_return = conf_df['pnl_pct'].mean()
            conf_total_return = conf_df['pnl_pct'].sum()

            print(f"\nConfidence >= {threshold}%:")
            print(f"  Signals: {conf_count}")
            print(f"  Win Rate: {conf_win_rate:.1f}%")
            print(f"  Avg Return: {conf_avg_return:.2f}%")
            print(f"  Total Return: {conf_total_return:.2f}%")

        # Additional analysis: Average days to exit
        print("\n" + "="*80)
        print("HOLDING PERIOD ANALYSIS")
        print("="*80)

        avg_days_win = df[df['outcome'] == 'WIN']['days_to_exit'].mean()
        avg_days_loss = df[df['outcome'] == 'LOSS']['days_to_exit'].mean()
        avg_days_expire = df[df['outcome'] == 'EXPIRE']['days_to_exit'].mean()

        print(f"Average Days to Exit (Wins): {avg_days_win:.1f}")
        print(f"Average Days to Exit (Losses): {avg_days_loss:.1f}")
        print(f"Average Days to Exit (Expires): {avg_days_expire:.1f}")

        return df

    def save_results(self, df: pd.DataFrame, output_path: str):
        """Save detailed results to CSV"""
        df.to_csv(output_path, index=False)
        print(f"\n{'='*80}")
        print(f"Results saved to: {output_path}")
        print("="*80)


def main():
    """Run the backtest"""

    # Define universe
    symbols = [
        'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'TSLA', 'NVDA',
        'JPM', 'V', 'MA', 'BAC', 'WMT', 'PG', 'HD', 'DIS',
        'ADBE', 'CRM', 'NFLX', 'PYPL', 'INTC', 'CSCO', 'PFE',
        'AMD', 'ORCL', 'QCOM', 'TXN', 'AVGO', 'COST', 'NKE',
        'PLTR', 'HOOD', 'COIN', 'SHOP', 'UBER', 'ABNB', 'SNOW',
        'SOFI', 'RBLX', 'NET', 'DDOG', 'CRWD', 'ZS',
        'MU', 'MRVL', 'KLAC', 'AMAT', 'LRCX',
        'CVX', 'XOM', 'COP', 'SLB', 'MPC'
    ]

    # Try different lookback periods to find data with uptrends
    print("="*80)
    print("TESTING MULTIPLE TIME PERIODS")
    print("="*80)
    print("\nNote: Recent market has been in downtrend, expanding search period...\n")

    best_results_df = None
    best_signals = []
    best_period = None

    for lookback in [90, 180, 270]:
        print(f"\n{'='*80}")
        print(f"SCENARIO: {lookback}-DAY LOOKBACK")
        print(f"{'='*80}\n")

        backtester = WalkForwardBacktest(lookback_days=lookback, hold_period=10,
                                        require_uptrend=True)
        signals = backtester.run_backtest(symbols)

        if len(signals) > 0:
            results_df = backtester.analyze_results(signals)

            if best_results_df is None or len(results_df) > len(best_results_df):
                best_results_df = results_df.copy()
                best_signals = signals
                best_period = lookback

            # Save to CSV
            output_path = f'/Users/williambennett/Github/macro-beans/data/backtest_results_{lookback}day.csv'
            backtester.save_results(results_df, output_path)

    # If no signals with uptrend requirement, try without it
    if best_results_df is None or len(best_results_df) < 20:
        print(f"\n{'='*80}")
        print("SCENARIO: 180-DAY WITHOUT UPTREND REQUIREMENT")
        print("Testing strategy in downtrends/mixed conditions")
        print(f"{'='*80}\n")

        backtester = WalkForwardBacktest(lookback_days=180, hold_period=10,
                                        require_uptrend=False)
        signals = backtester.run_backtest(symbols)

        if len(signals) > 0:
            results_df = backtester.analyze_results(signals)
            best_results_df = results_df
            best_signals = signals
            best_period = "180_no_uptrend"

            output_path = '/Users/williambennett/Github/macro-beans/data/backtest_results_180day_no_uptrend.csv'
            backtester.save_results(results_df, output_path)

    # Print final recommendations
    print("\n" + "="*80)
    print("FINAL RECOMMENDATIONS")
    print("="*80)

    if best_results_df is not None and len(best_results_df) > 0:
        results_df = best_results_df

        overall_win_rate = len(results_df[results_df['outcome'] == 'WIN']) / len(results_df) * 100

        # Find optimal confidence threshold
        best_conf = None
        best_expectancy = -999

        for threshold in [50, 55, 60, 65, 70, 75]:
            conf_df = results_df[results_df['confidence'] >= threshold]
            if len(conf_df) > 10:  # Need sufficient sample
                expectancy = conf_df['pnl_pct'].mean()
                if expectancy > best_expectancy:
                    best_expectancy = expectancy
                    best_conf = threshold

        print(f"\nBest dataset: {best_period}-day lookback ({len(results_df)} signals)")
        print(f"\n1. Overall Win Rate: {overall_win_rate:.1f}%")
        if overall_win_rate >= 60:
            print("   STATUS: VALIDATED - Exceeds 60% target")
        else:
            print("   STATUS: UNDERPERFORMED - Below 60% target")

        if best_conf:
            print(f"\n2. Optimal Confidence Threshold: {best_conf}%")
            print(f"   Expected return per trade: {best_expectancy:.2f}%")

        # Trend quality analysis
        tier1 = results_df[results_df['tier'].str.contains('Tier 1')]
        if len(tier1) > 0:
            tier1_wr = len(tier1[tier1['outcome'] == 'WIN']) / len(tier1) * 100
            print(f"\n3. Tier 1 (TQ 100) Win Rate: {tier1_wr:.1f}%")
            if tier1_wr > overall_win_rate:
                print("   STATUS: Tier 1 OUTPERFORMS - Focus on strong uptrends")
            else:
                print("   STATUS: Tier 1 does NOT significantly outperform")

        print("\n4. Strategy Viability:")
        avg_return = results_df['pnl_pct'].mean()
        if avg_return > 0.5 and overall_win_rate > 55:
            print("   VERDICT: TRADEABLE - Positive expectancy with acceptable win rate")
        elif avg_return > 0:
            print("   VERDICT: MARGINAL - Positive but low expectancy")
        else:
            print("   VERDICT: NOT TRADEABLE - Negative expectancy")
    else:
        print("\nINSUFFICIENT DATA: No qualifying signals found in any period.")
        print("This indicates the strategy criteria are too strict or market conditions")
        print("have not been favorable for mean reversion setups.")


if __name__ == "__main__":
    main()
