import numpy as np
import pandas as pd


def compute_metrics(returns: pd.Series, risk_free_rate: float = 0.04) -> dict:
    """
    Compute performance metrics from a daily return series.

    Returns dict with: sharpe, max_drawdown, win_rate, profit_factor,
    total_return, cagr, calmar, volatility, num_trades.
    """
    if returns.empty or returns.isna().all():
        return _empty_metrics()

    # Clean returns
    returns = returns.fillna(0)

    # Annualized metrics
    daily_rf = risk_free_rate / 252
    excess = returns - daily_rf
    ann_vol = returns.std() * np.sqrt(252)

    if ann_vol == 0 or np.isnan(ann_vol):
        sharpe = 0.0
    else:
        sharpe = (excess.mean() * 252) / ann_vol

    # Total return
    total_return = (1 + returns).prod() - 1

    # CAGR
    n_years = len(returns) / 252
    if n_years > 0 and (1 + total_return) > 0:
        cagr = (1 + total_return) ** (1 / n_years) - 1
    else:
        cagr = 0.0

    # Max drawdown
    equity = (1 + returns).cumprod()
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_drawdown = drawdown.min()

    # Calmar ratio
    if max_drawdown != 0:
        calmar = cagr / abs(max_drawdown)
    else:
        calmar = 0.0

    # Win rate (on days we were in the market, i.e., non-zero returns)
    active_returns = returns[returns != 0]
    if len(active_returns) > 0:
        win_rate = (active_returns > 0).sum() / len(active_returns)
    else:
        win_rate = 0.0

    # Profit factor
    gains = active_returns[active_returns > 0].sum()
    losses = abs(active_returns[active_returns < 0].sum())
    if losses > 0:
        profit_factor = gains / losses
    else:
        profit_factor = float("inf") if gains > 0 else 0.0

    # Number of trades (position changes)
    num_trades = 0  # Will be set by comparison module if needed

    return {
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_drawdown, 4),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 3),
        "total_return": round(total_return, 4),
        "cagr": round(cagr, 4),
        "calmar": round(calmar, 3),
        "volatility": round(ann_vol, 4),
        "num_trades": num_trades,
    }


def _empty_metrics() -> dict:
    return {
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "total_return": 0.0,
        "cagr": 0.0,
        "calmar": 0.0,
        "volatility": 0.0,
        "num_trades": 0,
    }
