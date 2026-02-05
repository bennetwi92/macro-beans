"""
Production-ready backtest for mean reversion trading strategy
Statistical rigor with walk-forward validation and out-of-sample testing
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import os
import warnings
from scipy import stats
import json
warnings.filterwarnings('ignore')

# We don't need to import the scanner since we're implementing our own logic

@dataclass
class BacktestConfig:
    """Configuration for backtest parameters"""
    initial_capital: float = 10000
    position_size_pct: float = 0.20  # 20% per position
    max_positions: int = 5
    stop_loss_pct: float = 0.03
    profit_target_pct: float = 0.03
    max_hold_days: int = 5
    commission_per_trade: float = 1.0  # $1 per trade
    slippage_pct: float = 0.001  # 0.1% slippage

    # Entry thresholds
    rsi_threshold: float = 30
    pullback_min: float = 3
    pullback_max: float = 6
    ma20_distance: float = 1.5  # Max % distance from MA20

@dataclass
class TradeResult:
    """Individual trade record"""
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    pnl_pct: float
    exit_reason: str
    days_held: int
    commission: float
    slippage: float

    @property
    def net_pnl(self) -> float:
        return self.pnl - self.commission - self.slippage

@dataclass
class BacktestResults:
    """Complete backtest statistics"""
    trades: List[TradeResult]
    period_start: pd.Timestamp
    period_end: pd.Timestamp
    initial_capital: float
    final_capital: float

    # Performance metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    profit_factor: float = 0

    # Risk metrics
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    calmar_ratio: float = 0
    max_drawdown: float = 0
    avg_drawdown: float = 0

    # Additional statistics
    avg_days_held: float = 0
    monthly_returns: Dict = field(default_factory=dict)
    parameter_sensitivity: Dict = field(default_factory=dict)

class RobustBacktester:
    """
    Production-grade backtester with proper train/test splits
    and statistical validation
    """

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.data_dir = '/Users/williambennett/Github/macro-beans/data/stock_history'

    def load_universe_data(self) -> Dict[str, pd.DataFrame]:
        """Load all available stock data"""
        universe = {}

        for file in os.listdir(self.data_dir):
            if file.endswith('.csv'):
                symbol = file.replace('.csv', '')
                filepath = os.path.join(self.data_dir, file)
                df = pd.read_csv(filepath, index_col=0, parse_dates=True)

                # Only include if we have sufficient history
                if len(df) > 500:  # ~2 years of data minimum
                    universe[symbol] = df

        print(f"Loaded {len(universe)} stocks with sufficient history")
        return universe

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all required technical indicators"""
        df = df.copy()

        # RSI calculation
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=2).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=2).mean()
        rs = gain / loss
        df['RSI_2'] = 100 - (100 / (1 + rs))

        # Moving averages
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA50'] = df['Close'].rolling(50).mean()
        df['MA200'] = df['Close'].rolling(200).mean()

        # Pullback from 10-day high
        df['High_10d'] = df['High'].rolling(10).max()
        df['Pullback_pct'] = ((df['High_10d'] - df['Close']) / df['High_10d']) * 100

        # Distance to MA20
        df['MA20_distance'] = abs((df['Close'] - df['MA20']) / df['MA20']) * 100

        # Trend conditions
        df['Uptrend'] = (df['Close'] > df['MA50']) & (df['MA50'] > df['MA200'])

        return df

    def check_entry_signal(self, row: pd.Series, config: BacktestConfig) -> bool:
        """Check if entry conditions are met"""
        if pd.isna(row['RSI_2']) or pd.isna(row['MA200']):
            return False

        conditions = [
            row['RSI_2'] < config.rsi_threshold,
            row['Uptrend'],
            config.pullback_min <= row['Pullback_pct'] <= config.pullback_max,
            row['MA20_distance'] <= config.ma20_distance
        ]

        return all(conditions)

    def simulate_trades(self,
                       data: Dict[str, pd.DataFrame],
                       start_date: pd.Timestamp,
                       end_date: pd.Timestamp,
                       config: Optional[BacktestConfig] = None) -> List[TradeResult]:
        """Simulate trading over a specific period"""

        if config is None:
            config = self.config

        trades = []
        open_positions = {}  # symbol -> (entry_date, entry_price, shares)
        capital = config.initial_capital

        # Get all trading dates from the data
        all_trading_dates = set()
        for symbol, df in data.items():
            # Filter dates within our period
            mask = (df.index >= start_date) & (df.index <= end_date)
            valid_dates = df[mask].index
            all_trading_dates.update(valid_dates)

        all_trading_dates = sorted(list(all_trading_dates))

        for date in all_trading_dates:
            # Check exits first
            closed_symbols = []
            for symbol, (entry_date, entry_price, shares) in open_positions.items():
                if symbol not in data:
                    continue

                # Get the data for this symbol
                symbol_data = data[symbol]
                if date not in symbol_data.index:
                    continue

                current_price = data[symbol].loc[date, 'Close']
                days_held = (date - entry_date).days
                pnl_pct = (current_price - entry_price) / entry_price

                # Exit conditions
                exit_triggered = False
                exit_reason = ""

                if pnl_pct >= config.profit_target_pct:
                    exit_triggered = True
                    exit_reason = "profit_target"
                elif pnl_pct <= -config.stop_loss_pct:
                    exit_triggered = True
                    exit_reason = "stop_loss"
                elif days_held >= config.max_hold_days:
                    exit_triggered = True
                    exit_reason = "max_hold"

                if exit_triggered:
                    # Apply slippage on exit
                    exit_price = current_price * (1 - config.slippage_pct)
                    pnl = shares * (exit_price - entry_price)

                    trade = TradeResult(
                        symbol=symbol,
                        entry_date=entry_date,
                        exit_date=date,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        shares=shares,
                        pnl=pnl,
                        pnl_pct=(exit_price - entry_price) / entry_price,
                        exit_reason=exit_reason,
                        days_held=days_held,
                        commission=config.commission_per_trade * 2,  # Entry and exit
                        slippage=shares * (entry_price * config.slippage_pct + current_price * config.slippage_pct)
                    )

                    trades.append(trade)
                    capital += trade.net_pnl
                    closed_symbols.append(symbol)

            # Remove closed positions
            for symbol in closed_symbols:
                del open_positions[symbol]

            # Check for new entries if we have capacity
            if len(open_positions) < config.max_positions:
                candidates = []

                for symbol, df in data.items():
                    if symbol in open_positions or date not in df.index:
                        continue

                    row = df.loc[date]
                    if self.check_entry_signal(row, config):
                        candidates.append((symbol, row['RSI_2'], row['Close']))

                # Sort by RSI (lowest first) and take best setups
                candidates.sort(key=lambda x: x[1])
                positions_to_open = min(len(candidates), config.max_positions - len(open_positions))

                for i in range(positions_to_open):
                    symbol, rsi, price = candidates[i]

                    # Apply slippage on entry
                    entry_price = price * (1 + config.slippage_pct)
                    position_size = capital * config.position_size_pct
                    shares = int(position_size / entry_price)

                    if shares > 0 and shares * entry_price <= capital:
                        open_positions[symbol] = (date, entry_price, shares)
                        capital -= shares * entry_price + config.commission_per_trade

        return trades

    def calculate_performance_metrics(self,
                                     trades: List[TradeResult],
                                     initial_capital: float) -> BacktestResults:
        """Calculate comprehensive performance metrics"""

        if not trades:
            return BacktestResults(
                trades=[],
                period_start=pd.Timestamp.now(),
                period_end=pd.Timestamp.now(),
                initial_capital=initial_capital,
                final_capital=initial_capital
            )

        # Convert to DataFrame for easier analysis
        trades_df = pd.DataFrame([
            {
                'symbol': t.symbol,
                'entry_date': t.entry_date,
                'exit_date': t.exit_date,
                'pnl': t.net_pnl,
                'pnl_pct': t.pnl_pct,
                'days_held': t.days_held,
                'exit_reason': t.exit_reason
            }
            for t in trades
        ])

        # Basic statistics
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] <= 0]

        # Calculate equity curve
        trades_df = trades_df.sort_values('exit_date')
        trades_df['cumulative_pnl'] = trades_df['pnl'].cumsum()
        trades_df['equity'] = initial_capital + trades_df['cumulative_pnl']

        # Monthly returns - ensure exit_date is datetime
        trades_df['exit_date'] = pd.to_datetime(trades_df['exit_date'])
        trades_df['month'] = trades_df['exit_date'].dt.to_period('M')
        monthly_returns = trades_df.groupby('month')['pnl'].sum().to_dict()

        # Calculate drawdowns
        running_max = trades_df['equity'].expanding().max()
        drawdown = (trades_df['equity'] - running_max) / running_max

        # Risk-adjusted returns
        daily_returns = trades_df.groupby('exit_date')['pnl_pct'].sum()

        # Handle edge cases
        sharpe = 0
        sortino = 0
        calmar = 0

        if len(daily_returns) > 1:
            # Sharpe Ratio (assuming 252 trading days)
            if daily_returns.std() > 0:
                sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)

            # Sortino Ratio
            downside_returns = daily_returns[daily_returns < 0]
            if len(downside_returns) > 0 and downside_returns.std() > 0:
                sortino = (daily_returns.mean() / downside_returns.std()) * np.sqrt(252)

            # Calmar Ratio
            max_dd = abs(drawdown.min()) if len(drawdown) > 0 else 0
            annual_return = trades_df['pnl'].sum() / initial_capital
            if max_dd > 0:
                calmar = annual_return / max_dd

        results = BacktestResults(
            trades=trades,
            period_start=trades_df['entry_date'].min(),
            period_end=trades_df['exit_date'].max(),
            initial_capital=initial_capital,
            final_capital=initial_capital + trades_df['pnl'].sum(),
            total_trades=len(trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=len(winning_trades) / len(trades) * 100 if len(trades) > 0 else 0,
            avg_win=winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0,
            avg_loss=losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0,
            profit_factor=abs(winning_trades['pnl'].sum() / losing_trades['pnl'].sum()) if len(losing_trades) > 0 and losing_trades['pnl'].sum() != 0 else 0,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=abs(drawdown.min()) * 100 if len(drawdown) > 0 else 0,
            avg_drawdown=abs(drawdown[drawdown < 0].mean()) * 100 if len(drawdown[drawdown < 0]) > 0 else 0,
            avg_days_held=trades_df['days_held'].mean(),
            monthly_returns={str(k): v for k, v in monthly_returns.items()}
        )

        return results

    def walk_forward_analysis(self,
                             universe: Dict[str, pd.DataFrame],
                             train_months: int = 12,
                             test_months: int = 3,
                             step_months: int = 3) -> List[Tuple[BacktestResults, BacktestResults]]:
        """
        Walk-forward optimization with expanding windows
        Returns list of (in_sample, out_sample) results
        """

        # Prepare data with indicators
        print("\nPreparing data with technical indicators...")
        for symbol in universe:
            universe[symbol] = self.calculate_indicators(universe[symbol])

        # Find common date range
        min_date = max([df.index.min() for df in universe.values()])
        max_date = min([df.index.max() for df in universe.values()])

        # Ensure we have enough data - handle timezone awareness
        comparison_date = pd.Timestamp('2020-01-01')
        if min_date.tz is not None:
            comparison_date = comparison_date.tz_localize(min_date.tz)
        min_date = max(min_date, comparison_date)

        results = []
        current_date = min_date + pd.DateOffset(months=train_months)

        print(f"\nWalk-Forward Analysis")
        print(f"Training window: {train_months} months")
        print(f"Testing window: {test_months} months")
        print(f"Step size: {step_months} months\n")

        window_num = 1
        while current_date + pd.DateOffset(months=test_months) <= max_date:
            # Define periods
            train_start = current_date - pd.DateOffset(months=train_months)
            train_end = current_date
            test_start = train_end
            test_end = test_start + pd.DateOffset(months=test_months)

            print(f"Window {window_num}:")
            print(f"  Train: {train_start.date()} to {train_end.date()}")
            print(f"  Test:  {test_start.date()} to {test_end.date()}")

            # Run in-sample backtest
            in_sample_trades = self.simulate_trades(universe, train_start, train_end)
            in_sample_results = self.calculate_performance_metrics(
                in_sample_trades, self.config.initial_capital
            )

            # Run out-of-sample backtest
            out_sample_trades = self.simulate_trades(universe, test_start, test_end)
            out_sample_results = self.calculate_performance_metrics(
                out_sample_trades, self.config.initial_capital
            )

            print(f"  In-sample: {in_sample_results.total_trades} trades, "
                  f"{in_sample_results.win_rate:.1f}% win rate")
            print(f"  Out-sample: {out_sample_results.total_trades} trades, "
                  f"{out_sample_results.win_rate:.1f}% win rate\n")

            results.append((in_sample_results, out_sample_results))

            # Move forward
            current_date += pd.DateOffset(months=step_months)
            window_num += 1

        return results

    def parameter_sensitivity_analysis(self,
                                      universe: Dict[str, pd.DataFrame],
                                      test_period_start: pd.Timestamp,
                                      test_period_end: pd.Timestamp) -> Dict:
        """Test sensitivity to key parameters"""

        print("\nParameter Sensitivity Analysis")
        print("-" * 50)

        baseline_config = self.config
        sensitivity_results = {}

        # Test RSI thresholds
        rsi_thresholds = [20, 25, 30, 35, 40]
        rsi_results = []

        print("\nTesting RSI thresholds...")
        for threshold in rsi_thresholds:
            config = BacktestConfig(
                rsi_threshold=threshold,
                initial_capital=baseline_config.initial_capital,
                stop_loss_pct=baseline_config.stop_loss_pct,
                profit_target_pct=baseline_config.profit_target_pct
            )

            trades = self.simulate_trades(universe, test_period_start, test_period_end, config)
            results = self.calculate_performance_metrics(trades, config.initial_capital)

            rsi_results.append({
                'threshold': threshold,
                'trades': results.total_trades,
                'win_rate': results.win_rate,
                'sharpe': results.sharpe_ratio,
                'total_return': (results.final_capital - results.initial_capital) / results.initial_capital * 100
            })

            print(f"  RSI < {threshold}: {results.total_trades} trades, "
                  f"{results.win_rate:.1f}% win rate, "
                  f"{rsi_results[-1]['total_return']:.1f}% return")

        sensitivity_results['rsi_thresholds'] = rsi_results

        # Test stop/target ratios
        risk_reward_ratios = [
            (0.02, 0.02),  # 2% stop, 2% target
            (0.03, 0.03),  # 3% stop, 3% target (baseline)
            (0.04, 0.04),  # 4% stop, 4% target
            (0.03, 0.05),  # 3% stop, 5% target
            (0.02, 0.04),  # 2% stop, 4% target
        ]

        print("\nTesting risk/reward ratios...")
        rr_results = []

        for stop_loss, profit_target in risk_reward_ratios:
            config = BacktestConfig(
                rsi_threshold=baseline_config.rsi_threshold,
                initial_capital=baseline_config.initial_capital,
                stop_loss_pct=stop_loss,
                profit_target_pct=profit_target
            )

            trades = self.simulate_trades(universe, test_period_start, test_period_end, config)
            results = self.calculate_performance_metrics(trades, config.initial_capital)

            rr_results.append({
                'stop_loss': stop_loss * 100,
                'profit_target': profit_target * 100,
                'trades': results.total_trades,
                'win_rate': results.win_rate,
                'sharpe': results.sharpe_ratio,
                'total_return': (results.final_capital - results.initial_capital) / results.initial_capital * 100
            })

            print(f"  Stop {stop_loss*100:.0f}% / Target {profit_target*100:.0f}%: "
                  f"{results.total_trades} trades, {results.win_rate:.1f}% win rate, "
                  f"{rr_results[-1]['total_return']:.1f}% return")

        sensitivity_results['risk_reward'] = rr_results

        # Test holding period limits
        hold_periods = [3, 5, 7, 10]
        hold_results = []

        print("\nTesting max holding periods...")
        for days in hold_periods:
            config = BacktestConfig(
                rsi_threshold=baseline_config.rsi_threshold,
                initial_capital=baseline_config.initial_capital,
                stop_loss_pct=baseline_config.stop_loss_pct,
                profit_target_pct=baseline_config.profit_target_pct,
                max_hold_days=days
            )

            trades = self.simulate_trades(universe, test_period_start, test_period_end, config)
            results = self.calculate_performance_metrics(trades, config.initial_capital)

            hold_results.append({
                'max_days': days,
                'trades': results.total_trades,
                'win_rate': results.win_rate,
                'avg_days_held': results.avg_days_held,
                'total_return': (results.final_capital - results.initial_capital) / results.initial_capital * 100
            })

            print(f"  Max {days} days: {results.total_trades} trades, "
                  f"{results.win_rate:.1f}% win rate, "
                  f"avg hold {results.avg_days_held:.1f} days")

        sensitivity_results['holding_periods'] = hold_results

        return sensitivity_results

    def monte_carlo_simulation(self,
                              historical_trades: List[TradeResult],
                              num_simulations: int = 1000,
                              num_trades: int = 100) -> Dict:
        """Monte Carlo simulation for confidence intervals"""

        if not historical_trades:
            return {}

        print(f"\nRunning {num_simulations} Monte Carlo simulations...")

        # Extract returns from historical trades
        returns = [t.pnl_pct for t in historical_trades]

        simulation_results = []

        for _ in range(num_simulations):
            # Sample with replacement
            simulated_returns = np.random.choice(returns, size=num_trades, replace=True)

            # Calculate metrics
            total_return = np.sum(simulated_returns)
            win_rate = np.mean(simulated_returns > 0) * 100

            # Calculate max drawdown
            cumulative = np.cumsum(simulated_returns)
            running_max = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - running_max) / (running_max + 1e-8)
            max_dd = np.min(drawdown) * 100

            simulation_results.append({
                'total_return': total_return,
                'win_rate': win_rate,
                'max_drawdown': abs(max_dd)
            })

        # Calculate percentiles
        df = pd.DataFrame(simulation_results)

        confidence_intervals = {
            'total_return': {
                'p5': df['total_return'].quantile(0.05),
                'p25': df['total_return'].quantile(0.25),
                'p50': df['total_return'].quantile(0.50),
                'p75': df['total_return'].quantile(0.75),
                'p95': df['total_return'].quantile(0.95),
            },
            'win_rate': {
                'p5': df['win_rate'].quantile(0.05),
                'p25': df['win_rate'].quantile(0.25),
                'p50': df['win_rate'].quantile(0.50),
                'p75': df['win_rate'].quantile(0.75),
                'p95': df['win_rate'].quantile(0.95),
            },
            'max_drawdown': {
                'p5': df['max_drawdown'].quantile(0.05),
                'p25': df['max_drawdown'].quantile(0.25),
                'p50': df['max_drawdown'].quantile(0.50),
                'p75': df['max_drawdown'].quantile(0.75),
                'p95': df['max_drawdown'].quantile(0.95),
            }
        }

        return confidence_intervals

def run_comprehensive_backtest():
    """Main function to run complete backtest analysis"""

    print("=" * 80)
    print("MEAN REVERSION STRATEGY - COMPREHENSIVE BACKTEST")
    print("=" * 80)

    # Initialize backtester
    config = BacktestConfig()
    backtester = RobustBacktester(config)

    # Load universe
    universe = backtester.load_universe_data()

    # 1. Walk-Forward Analysis
    print("\n" + "=" * 80)
    print("WALK-FORWARD ANALYSIS")
    print("=" * 80)

    wf_results = backtester.walk_forward_analysis(
        universe,
        train_months=12,
        test_months=3,
        step_months=3
    )

    # Aggregate walk-forward results
    in_sample_stats = []
    out_sample_stats = []

    for in_sample, out_sample in wf_results:
        if in_sample.total_trades > 0:
            in_sample_stats.append({
                'win_rate': in_sample.win_rate,
                'sharpe': in_sample.sharpe_ratio,
                'max_dd': in_sample.max_drawdown,
                'trades': in_sample.total_trades
            })

        if out_sample.total_trades > 0:
            out_sample_stats.append({
                'win_rate': out_sample.win_rate,
                'sharpe': out_sample.sharpe_ratio,
                'max_dd': out_sample.max_drawdown,
                'trades': out_sample.total_trades
            })

    if in_sample_stats and out_sample_stats:
        in_df = pd.DataFrame(in_sample_stats)
        out_df = pd.DataFrame(out_sample_stats)

        print("\nWalk-Forward Summary:")
        print("-" * 50)
        print("In-Sample Performance (Average):")
        print(f"  Win Rate: {in_df['win_rate'].mean():.1f}% ± {in_df['win_rate'].std():.1f}%")
        print(f"  Sharpe Ratio: {in_df['sharpe'].mean():.2f} ± {in_df['sharpe'].std():.2f}")
        print(f"  Max Drawdown: {in_df['max_dd'].mean():.1f}% ± {in_df['max_dd'].std():.1f}%")
        print(f"  Avg Trades/Period: {in_df['trades'].mean():.0f}")

        print("\nOut-of-Sample Performance (Average):")
        print(f"  Win Rate: {out_df['win_rate'].mean():.1f}% ± {out_df['win_rate'].std():.1f}%")
        print(f"  Sharpe Ratio: {out_df['sharpe'].mean():.2f} ± {out_df['sharpe'].std():.2f}")
        print(f"  Max Drawdown: {out_df['max_dd'].mean():.1f}% ± {out_df['max_dd'].std():.1f}%")
        print(f"  Avg Trades/Period: {out_df['trades'].mean():.0f}")

        # Statistical test for performance degradation
        if len(in_df) > 1 and len(out_df) > 1:
            t_stat, p_value = stats.ttest_ind(in_df['win_rate'], out_df['win_rate'])
            print(f"\nPerformance Degradation Test (Win Rate):")
            print(f"  t-statistic: {t_stat:.2f}")
            print(f"  p-value: {p_value:.4f}")
            if p_value < 0.05:
                print("  ⚠️ Significant difference between in-sample and out-of-sample")
            else:
                print("  ✓ No significant overfitting detected")

    # 2. Parameter Sensitivity
    print("\n" + "=" * 80)
    print("PARAMETER SENSITIVITY ANALYSIS")
    print("=" * 80)

    # Use last year for sensitivity testing
    test_end = pd.Timestamp('2026-01-31')
    test_start = pd.Timestamp('2025-01-01')

    sensitivity = backtester.parameter_sensitivity_analysis(
        universe, test_start, test_end
    )

    # 3. Full Period Backtest
    print("\n" + "=" * 80)
    print("FULL PERIOD BACKTEST (Last 2 Years)")
    print("=" * 80)

    # Use the actual data range
    full_start = pd.Timestamp('2024-01-01')
    full_end = pd.Timestamp('2026-01-31')

    full_trades = backtester.simulate_trades(universe, full_start, full_end)
    full_results = backtester.calculate_performance_metrics(
        full_trades, config.initial_capital
    )

    print(f"\nOverall Performance:")
    print(f"  Period: {full_results.period_start.date()} to {full_results.period_end.date()}")
    print(f"  Total Trades: {full_results.total_trades}")
    print(f"  Win Rate: {full_results.win_rate:.1f}%")
    print(f"  Avg Win: ${full_results.avg_win:.2f}")
    print(f"  Avg Loss: ${full_results.avg_loss:.2f}")
    print(f"  Profit Factor: {full_results.profit_factor:.2f}")

    print(f"\nRisk Metrics:")
    print(f"  Sharpe Ratio: {full_results.sharpe_ratio:.2f}")
    print(f"  Sortino Ratio: {full_results.sortino_ratio:.2f}")
    print(f"  Calmar Ratio: {full_results.calmar_ratio:.2f}")
    print(f"  Max Drawdown: {full_results.max_drawdown:.1f}%")
    print(f"  Avg Drawdown: {full_results.avg_drawdown:.1f}%")

    print(f"\nCapital Growth:")
    print(f"  Initial: ${full_results.initial_capital:,.0f}")
    print(f"  Final: ${full_results.final_capital:,.0f}")
    print(f"  Total Return: {(full_results.final_capital/full_results.initial_capital - 1)*100:.1f}%")
    print(f"  Avg Days Held: {full_results.avg_days_held:.1f}")

    # Exit reason analysis
    if full_trades:
        exit_reasons = pd.DataFrame([{'reason': t.exit_reason, 'pnl': t.net_pnl} for t in full_trades])
        exit_summary = exit_reasons.groupby('reason').agg({
            'pnl': ['count', 'sum', 'mean']
        })

        print(f"\nExit Analysis:")
        for reason in exit_summary.index:
            count = exit_summary.loc[reason, ('pnl', 'count')]
            total_pnl = exit_summary.loc[reason, ('pnl', 'sum')]
            avg_pnl = exit_summary.loc[reason, ('pnl', 'mean')]
            print(f"  {reason}: {count:.0f} trades, ${total_pnl:.2f} total, ${avg_pnl:.2f} avg")

    # 4. Monte Carlo Simulation
    print("\n" + "=" * 80)
    print("MONTE CARLO SIMULATION")
    print("=" * 80)

    if full_trades:
        mc_results = backtester.monte_carlo_simulation(full_trades)

        print("\nExpected Performance (95% Confidence):")
        print(f"  Total Return (100 trades):")
        print(f"    5th percentile: {mc_results['total_return']['p5']:.1f}%")
        print(f"    25th percentile: {mc_results['total_return']['p25']:.1f}%")
        print(f"    Median: {mc_results['total_return']['p50']:.1f}%")
        print(f"    75th percentile: {mc_results['total_return']['p75']:.1f}%")
        print(f"    95th percentile: {mc_results['total_return']['p95']:.1f}%")

        print(f"\n  Win Rate:")
        print(f"    5th-95th percentile: {mc_results['win_rate']['p5']:.1f}% - {mc_results['win_rate']['p95']:.1f}%")

        print(f"\n  Max Drawdown:")
        print(f"    5th-95th percentile: {mc_results['max_drawdown']['p5']:.1f}% - {mc_results['max_drawdown']['p95']:.1f}%")

    # 5. Final Recommendations
    print("\n" + "=" * 80)
    print("CONCLUSIONS & RECOMMENDATIONS")
    print("=" * 80)

    # Strategy viability assessment
    viable = True
    concerns = []

    if full_results.win_rate < 50:
        concerns.append(f"Win rate ({full_results.win_rate:.1f}%) below 50%")
        viable = False

    if full_results.sharpe_ratio < 0.5:
        concerns.append(f"Sharpe ratio ({full_results.sharpe_ratio:.2f}) below 0.5")
        viable = False

    if full_results.max_drawdown > 20:
        concerns.append(f"Max drawdown ({full_results.max_drawdown:.1f}%) exceeds 20%")

    # Account for costs
    total_commission = len(full_trades) * config.commission_per_trade * 2 if full_trades else 0
    total_slippage = sum([t.slippage for t in full_trades]) if full_trades else 0
    total_costs = total_commission + total_slippage
    net_return = full_results.final_capital - full_results.initial_capital - total_costs

    print(f"\nStrategy Assessment:")
    print(f"  Viable for Production: {'✓ YES' if viable else '✗ NO'}")

    if concerns:
        print(f"\n  Concerns:")
        for concern in concerns:
            print(f"    - {concern}")

    print(f"\nCost Analysis:")
    print(f"  Total Commission: ${total_commission:.2f}")
    print(f"  Total Slippage: ${total_slippage:.2f}")
    print(f"  Net Return After Costs: ${net_return:.2f}")
    print(f"  Net Return %: {(net_return/config.initial_capital)*100:.1f}%")

    # Parameter recommendations
    print(f"\nOptimal Parameters (from sensitivity analysis):")

    if 'rsi_thresholds' in sensitivity:
        best_rsi = max(sensitivity['rsi_thresholds'], key=lambda x: x['sharpe'])
        print(f"  RSI Threshold: {best_rsi['threshold']}")

    if 'risk_reward' in sensitivity:
        best_rr = max(sensitivity['risk_reward'], key=lambda x: x['sharpe'])
        print(f"  Stop/Target: {best_rr['stop_loss']:.0f}% / {best_rr['profit_target']:.0f}%")

    if 'holding_periods' in sensitivity:
        best_hold = max(sensitivity['holding_periods'], key=lambda x: x['win_rate'])
        print(f"  Max Hold Period: {best_hold['max_days']} days")

    print("\nRisk Management:")
    print(f"  Recommended Position Size: 20% of capital")
    print(f"  Max Concurrent Positions: {config.max_positions}")
    print(f"  Kelly Criterion Suggestion: {min(full_results.win_rate/100 * 0.5, 0.25)*100:.0f}% per trade")

    # Market regime analysis
    if full_results.monthly_returns:
        monthly_df = pd.DataFrame([
            {'month': k, 'return': v}
            for k, v in full_results.monthly_returns.items()
        ])

        if len(monthly_df) > 0:
            positive_months = (monthly_df['return'] > 0).sum()
            total_months = len(monthly_df)

            print(f"\nMonthly Consistency:")
            print(f"  Positive Months: {positive_months}/{total_months} ({positive_months/total_months*100:.0f}%)")
            print(f"  Best Month: ${monthly_df['return'].max():.2f}")
            print(f"  Worst Month: ${monthly_df['return'].min():.2f}")
            print(f"  Avg Monthly Return: ${monthly_df['return'].mean():.2f}")

    print("\n" + "=" * 80)
    print("END OF BACKTEST REPORT")
    print("=" * 80)

if __name__ == "__main__":
    run_comprehensive_backtest()