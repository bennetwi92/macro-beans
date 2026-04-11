"""Daily signal generation CLI module."""

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml
from loguru import logger

from src.data.provider import DataProvider
from src.data.features import FeatureEngine
from src.backtest.engine import BacktestEngine
from src.backtest.metrics import compute_metrics
from src.strategy.ensemble import EqualWeightEnsemble, SharpeWeightedEnsemble


def load_ensemble_config(results_path: str = "output/backtest_results.csv"):
    """Load backtest results to determine top strategies."""
    if not os.path.exists(results_path):
        return None
    return pd.read_csv(results_path)


def generate_daily_signal(ensemble, data: pd.DataFrame, prices: pd.Series):
    """Generate today's signal and supporting info."""
    signal_series = ensemble.generate_signals(data)
    today_signal = signal_series.iloc[-1]

    # Get sub-strategy signals
    sub_signals = {}
    if hasattr(ensemble, "get_sub_signals"):
        sub_signals = ensemble.get_sub_signals(data)
        sub_signals = {k: v.iloc[-1] for k, v in sub_signals.items()}

    # Confidence = fraction of sub-strategies that agree
    if sub_signals:
        n_long = sum(1 for v in sub_signals.values() if v == 1.0)
        confidence = n_long / len(sub_signals)
    else:
        confidence = 1.0 if today_signal == 1.0 else 0.0

    # Key indicators
    indicators = {}
    for col in ["close", "rsi_14", "sma_50", "sma_200", "vix", "vol_20", "atr"]:
        if col in data.columns:
            val = data[col].iloc[-1]
            if pd.notna(val):
                indicators[col] = round(float(val), 2)

    # Rolling performance (252-day)
    engine = BacktestEngine(initial_capital=100_000, cost_bps=10)
    lookback = min(252, len(signal_series))
    recent_prices = prices.iloc[-lookback:]
    recent_signals = signal_series.iloc[-lookback:]
    result = engine.run(recent_prices, recent_signals)
    rolling_metrics = compute_metrics(result.returns)

    # YTD performance
    year_start = data.index[-1].replace(month=1, day=1)
    ytd_mask = data.index >= year_start
    if ytd_mask.sum() > 1:
        ytd_prices = prices[ytd_mask]
        ytd_signals = signal_series[ytd_mask]
        ytd_result = engine.run(ytd_prices, ytd_signals)
        ytd_return = (1 + ytd_result.returns).prod() - 1
    else:
        ytd_return = 0.0

    return {
        "date": data.index[-1].strftime("%Y-%m-%d"),
        "signal": "LONG" if today_signal == 1.0 else "FLAT",
        "signal_numeric": today_signal,
        "confidence": confidence,
        "sub_signals": sub_signals,
        "indicators": indicators,
        "rolling_sharpe": rolling_metrics["sharpe"],
        "rolling_max_dd": rolling_metrics["max_drawdown"],
        "ytd_return": ytd_return,
    }


def format_signal_output(info: dict, sub_sharpes: dict = None) -> str:
    """Format signal info for CLI output."""
    if sub_sharpes is None:
        sub_sharpes = {}

    signal_color = "LONG" if info["signal"] == "LONG" else "FLAT"
    n_long = sum(1 for v in info["sub_signals"].values() if v == 1.0)
    n_total = len(info["sub_signals"])

    lines = []
    lines.append(f"\n{'='*55}")
    lines.append(f"  BRNT.L Daily Signal - {info['date']}")
    lines.append(f"{'='*55}")
    lines.append(f"  Signal: {signal_color}  |  Confidence: {info['confidence']:.0%} ({n_long}/{n_total} sub-strategies)")
    lines.append("")

    if info["sub_signals"]:
        lines.append("  Sub-strategy signals:")
        for name, sig in sorted(info["sub_signals"].items()):
            sig_str = "LONG" if sig == 1.0 else "FLAT"
            sharpe_str = f"(Sharpe: {sub_sharpes[name]:.2f})" if name in sub_sharpes else ""
            lines.append(f"    {name:25s} {sig_str:6s} {sharpe_str}")
        lines.append("")

    if info["indicators"]:
        lines.append("  Key Indicators:")
        indicator_parts = [f"{k}: {v}" for k, v in info["indicators"].items()]
        lines.append(f"    {' | '.join(indicator_parts)}")
        lines.append("")

    lines.append("  Rolling Performance (252d):")
    lines.append(f"    Sharpe: {info['rolling_sharpe']:.2f}  |  MaxDD: {info['rolling_max_dd']:.1%}  |  YTD: {info['ytd_return']:.1%}")
    lines.append(f"{'='*55}\n")

    return "\n".join(lines)


def append_to_csv(info: dict, csv_path: str = "output/daily_signals.csv"):
    """Append today's signal to the daily CSV log."""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    row = {
        "date": info["date"],
        "signal": info["signal"],
        "confidence": round(info["confidence"], 3),
        "rolling_sharpe": info["rolling_sharpe"],
        "rolling_max_dd": round(info["rolling_max_dd"], 4),
        "ytd_return": round(info["ytd_return"], 4),
    }

    # Add indicators
    for k, v in info["indicators"].items():
        row[k] = v

    # Add sub-strategy signals
    for k, v in info["sub_signals"].items():
        row[f"sig_{k}"] = int(v)

    df = pd.DataFrame([row])

    if os.path.exists(csv_path):
        existing = pd.read_csv(csv_path)
        # Don't duplicate today's entry
        if info["date"] not in existing["date"].values:
            df = pd.concat([existing, df], ignore_index=True)
        else:
            existing.loc[existing["date"] == info["date"]] = df.iloc[0].values
            df = existing

    df.to_csv(csv_path, index=False)
