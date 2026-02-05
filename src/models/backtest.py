"""Backtesting engine for mean reversion model"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Represents a single trade"""
    symbol: str
    entry_date: datetime
    entry_price: float
    position_size: int
    confidence: float
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    return_pct: Optional[float] = None
    exit_reason: Optional[str] = None


@dataclass
class BacktestResults:
    """Backtesting results"""
    trades: List[Trade] = field(default_factory=list)
    portfolio_value: List[float] = field(default_factory=list)
    dates: List[datetime] = field(default_factory=list)
    cash: List[float] = field(default_factory=list)
    positions_value: List[float] = field(default_factory=list)

    def calculate_metrics(self, initial_capital: float = 100000) -> Dict:
        """Calculate performance metrics"""
        if not self.trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'avg_return': 0,
                'total_return': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'calmar_ratio': 0
            }

        # Trade statistics
        closed_trades = [t for t in self.trades if t.exit_date is not None]
        winning_trades = [t for t in closed_trades if t.pnl > 0]
        losing_trades = [t for t in closed_trades if t.pnl <= 0]

        # Returns
        returns = [t.return_pct for t in closed_trades if t.return_pct is not None]
        portfolio_returns = pd.Series(self.portfolio_value).pct_change().dropna()

        # Calculate metrics
        metrics = {
            'total_trades': len(closed_trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': len(winning_trades) / len(closed_trades) if closed_trades else 0,
            'avg_return': np.mean(returns) if returns else 0,
            'median_return': np.median(returns) if returns else 0,
            'total_return': (self.portfolio_value[-1] - initial_capital) / initial_capital if self.portfolio_value else 0,
            'final_value': self.portfolio_value[-1] if self.portfolio_value else initial_capital,
        }

        # Risk metrics
        if len(portfolio_returns) > 0:
            metrics['volatility'] = portfolio_returns.std() * np.sqrt(252)
            metrics['sharpe_ratio'] = (portfolio_returns.mean() * 252) / (portfolio_returns.std() * np.sqrt(252)) if portfolio_returns.std() > 0 else 0
            metrics['max_drawdown'] = self.calculate_max_drawdown()
            metrics['calmar_ratio'] = metrics['total_return'] / abs(metrics['max_drawdown']) if metrics['max_drawdown'] != 0 else 0
        else:
            metrics['volatility'] = 0
            metrics['sharpe_ratio'] = 0
            metrics['max_drawdown'] = 0
            metrics['calmar_ratio'] = 0

        # Additional trade statistics
        if winning_trades:
            metrics['avg_winner'] = np.mean([t.return_pct for t in winning_trades])
            metrics['max_winner'] = max([t.return_pct for t in winning_trades])

        if losing_trades:
            metrics['avg_loser'] = np.mean([t.return_pct for t in losing_trades])
            metrics['max_loser'] = min([t.return_pct for t in losing_trades])

        metrics['profit_factor'] = (
            sum([t.pnl for t in winning_trades]) / abs(sum([t.pnl for t in losing_trades]))
            if losing_trades and sum([t.pnl for t in losing_trades]) != 0 else 0
        )

        return metrics

    def calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown"""
        if not self.portfolio_value:
            return 0

        portfolio_series = pd.Series(self.portfolio_value)
        cummax = portfolio_series.cummax()
        drawdown = (portfolio_series - cummax) / cummax
        return drawdown.min()


class Backtester:
    """Backtesting engine for mean reversion strategy"""

    def __init__(self, config):
        """Initialize backtester with configuration"""
        self.config = config
        self.results = BacktestResults()
        self.current_positions = {}

    def run_backtest(self, predictions: pd.DataFrame, market_data: Dict[str, pd.DataFrame],
                     start_date: str = None, end_date: str = None) -> BacktestResults:
        """
        Run backtest on predictions

        Args:
            predictions: DataFrame with columns [date, symbol, confidence, features...]
            market_data: Dict of symbol -> price data DataFrame
            start_date: Backtest start date
            end_date: Backtest end date
        """
        logger.info(f"Starting backtest from {start_date} to {end_date}")

        # Initialize portfolio
        cash = self.config.initial_capital
        self.current_positions = {}

        # Filter predictions by date
        if start_date:
            predictions = predictions[predictions['date'] >= start_date]
        if end_date:
            predictions = predictions[predictions['date'] <= end_date]

        # Sort predictions by date
        predictions = predictions.sort_values('date')

        # Group predictions by date
        for date in predictions['date'].unique():
            daily_signals = predictions[predictions['date'] == date]

            # Check existing positions for exit conditions
            self.check_exits(date, market_data, cash)

            # Filter signals by confidence threshold
            high_conf_signals = daily_signals[
                daily_signals['confidence'] >= self.config.confidence_threshold
            ].nlargest(self.config.max_positions - len(self.current_positions), 'confidence')

            # Enter new positions
            for _, signal in high_conf_signals.iterrows():
                if len(self.current_positions) >= self.config.max_positions:
                    break

                symbol = signal['symbol']
                if symbol in self.current_positions:
                    continue

                # Check if we have market data
                if symbol not in market_data:
                    continue

                # Get entry price (next day's open)
                symbol_data = market_data[symbol]
                date_idx = symbol_data[symbol_data['Date'] == date].index
                if len(date_idx) == 0 or date_idx[0] >= len(symbol_data) - 1:
                    continue

                entry_price = symbol_data.iloc[date_idx[0] + 1]['Open']

                # Calculate position size
                position_value = cash * self.config.position_size
                position_size = int(position_value / entry_price)

                if position_size > 0 and position_value <= cash:
                    # Enter trade
                    trade = Trade(
                        symbol=symbol,
                        entry_date=date,
                        entry_price=entry_price,
                        position_size=position_size,
                        confidence=signal['confidence']
                    )

                    self.current_positions[symbol] = trade
                    cash -= position_value * (1 + self.config.transaction_cost)

                    logger.debug(f"Entered {symbol} on {date} at {entry_price:.2f}")

            # Record portfolio value
            positions_value = sum([
                self.get_position_value(symbol, date, market_data)
                for symbol in self.current_positions
            ])

            self.results.portfolio_value.append(cash + positions_value)
            self.results.dates.append(date)
            self.results.cash.append(cash)
            self.results.positions_value.append(positions_value)

        # Close any remaining positions
        if self.current_positions and self.results.dates:
            last_date = self.results.dates[-1]
            for symbol in list(self.current_positions.keys()):
                self.close_position(symbol, last_date, market_data, "End of backtest")

        logger.info(f"Backtest complete - {len(self.results.trades)} trades executed")

        return self.results

    def check_exits(self, current_date: datetime, market_data: Dict[str, pd.DataFrame], cash: float):
        """Check existing positions for exit conditions"""
        for symbol in list(self.current_positions.keys()):
            trade = self.current_positions[symbol]

            if symbol not in market_data:
                continue

            symbol_data = market_data[symbol]
            date_mask = symbol_data['Date'] == current_date
            if not date_mask.any():
                continue

            current_bar = symbol_data[date_mask].iloc[0]

            # Calculate returns
            current_return = (current_bar['Close'] - trade.entry_price) / trade.entry_price

            # Check exit conditions
            exit_trade = False
            exit_reason = ""

            # Target hit
            if current_bar['High'] >= trade.entry_price * (1 + self.config.target_return):
                exit_trade = True
                exit_reason = "Target"
                exit_price = trade.entry_price * (1 + self.config.target_return)

            # Stop loss hit
            elif current_bar['Low'] <= trade.entry_price * (1 + self.config.stop_loss):
                exit_trade = True
                exit_reason = "Stop Loss"
                exit_price = trade.entry_price * (1 + self.config.stop_loss)

            # Time exit
            elif (current_date - trade.entry_date).days >= self.config.max_holding_days:
                exit_trade = True
                exit_reason = "Time Exit"
                exit_price = current_bar['Close']

            if exit_trade:
                self.close_position(symbol, current_date, market_data, exit_reason, exit_price)

    def close_position(self, symbol: str, exit_date: datetime, market_data: Dict[str, pd.DataFrame],
                       exit_reason: str, exit_price: float = None):
        """Close a position"""
        if symbol not in self.current_positions:
            return

        trade = self.current_positions[symbol]

        # Get exit price if not provided
        if exit_price is None:
            symbol_data = market_data[symbol]
            date_mask = symbol_data['Date'] == exit_date
            if date_mask.any():
                exit_price = symbol_data[date_mask].iloc[0]['Close']
            else:
                return

        # Update trade
        trade.exit_date = exit_date
        trade.exit_price = exit_price
        trade.exit_reason = exit_reason
        trade.return_pct = (exit_price - trade.entry_price) / trade.entry_price
        trade.pnl = trade.position_size * (exit_price - trade.entry_price) * (1 - self.config.transaction_cost)

        # Add to results
        self.results.trades.append(trade)

        # Remove from current positions
        del self.current_positions[symbol]

        logger.debug(f"Closed {symbol} on {exit_date} at {exit_price:.2f} - {exit_reason} - Return: {trade.return_pct:.2%}")

    def get_position_value(self, symbol: str, date: datetime, market_data: Dict[str, pd.DataFrame]) -> float:
        """Get current value of a position"""
        if symbol not in self.current_positions or symbol not in market_data:
            return 0

        trade = self.current_positions[symbol]
        symbol_data = market_data[symbol]
        date_mask = symbol_data['Date'] == date

        if date_mask.any():
            current_price = symbol_data[date_mask].iloc[0]['Close']
            return trade.position_size * current_price

        return 0