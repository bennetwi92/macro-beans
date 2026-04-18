"""Plotly visualizations for the storage model dashboard"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.storage_model.config import StorageConfig


def create_price_signal_chart(daily_df: pd.DataFrame, trades_df: pd.DataFrame) -> go.Figure:
    """Price chart with SMA + Bollinger Bands and inject/withdraw markers.
    Two-panel subplot: top = price, bottom = composite signal.
    """
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=["Price & Trade Signals", "Composite Signal"],
    )

    # Price line
    fig.add_trace(go.Scatter(
        x=daily_df.index, y=daily_df["price"],
        name="Price", line=dict(color="#2196F3", width=1.5),
    ), row=1, col=1)

    # SMA overlay (63-day, matching z-score window)
    sma = daily_df["price"].rolling(63).mean()
    fig.add_trace(go.Scatter(
        x=daily_df.index, y=sma,
        name="63d SMA", line=dict(color="#FF9800", width=1, dash="dash"),
    ), row=1, col=1)

    # Bollinger Bands
    std = daily_df["price"].rolling(63).std()
    fig.add_trace(go.Scatter(
        x=daily_df.index, y=sma + 2 * std,
        name="Upper BB", line=dict(color="rgba(150,150,150,0.3)", width=0.5),
        showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=daily_df.index, y=sma - 2 * std,
        name="Lower BB", line=dict(color="rgba(150,150,150,0.3)", width=0.5),
        fill="tonexty", fillcolor="rgba(150,150,150,0.08)",
        showlegend=False,
    ), row=1, col=1)

    # Injection markers
    if not trades_df.empty:
        injects = trades_df[trades_df["action"] == "inject"]
        if not injects.empty:
            fig.add_trace(go.Scatter(
                x=injects.index, y=injects["price"],
                mode="markers", name="Inject (Buy)",
                marker=dict(color="#4CAF50", size=6, symbol="triangle-up"),
            ), row=1, col=1)

        withdrawals = trades_df[trades_df["action"] == "withdraw"]
        if not withdrawals.empty:
            fig.add_trace(go.Scatter(
                x=withdrawals.index, y=withdrawals["price"],
                mode="markers", name="Withdraw (Sell)",
                marker=dict(color="#F44336", size=6, symbol="triangle-down"),
            ), row=1, col=1)

    # Composite signal
    fig.add_trace(go.Scatter(
        x=daily_df.index, y=daily_df["composite_signal"],
        name="Composite", line=dict(color="#9C27B0", width=1),
    ), row=2, col=1)

    # Threshold bands
    fig.add_hline(y=0.3, line_dash="dot", line_color="green", opacity=0.5, row=2, col=1)
    fig.add_hline(y=-0.3, line_dash="dot", line_color="red", opacity=0.5, row=2, col=1)
    fig.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.3, row=2, col=1)

    fig.update_layout(
        height=600, template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=60, r=20, t=40, b=40),
    )
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    fig.update_yaxes(title_text="Signal", row=2, col=1)
    return fig


def create_inventory_profile_chart(daily_df: pd.DataFrame, config: StorageConfig) -> go.Figure:
    """Classic gas storage inventory profile: stacked area of cushion / working / empty."""
    cushion = config.min_inventory
    inventory = daily_df["inventory"]
    working = (inventory - cushion).clip(lower=0)
    empty = (config.max_inventory - inventory).clip(lower=0)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=daily_df.index, y=[cushion] * len(daily_df),
        name="Cushion (Min Reserve)", fill="tozeroy",
        fillcolor="rgba(244,67,54,0.2)",
        line=dict(color="rgba(244,67,54,0.5)", width=0),
    ))
    fig.add_trace(go.Scatter(
        x=daily_df.index, y=cushion + working,
        name="Working Inventory", fill="tonexty",
        fillcolor="rgba(33,150,243,0.3)",
        line=dict(color="rgba(33,150,243,0.7)", width=1),
    ))
    fig.add_trace(go.Scatter(
        x=daily_df.index, y=[config.max_inventory] * len(daily_df),
        name="Max Capacity", fill="tonexty",
        fillcolor="rgba(200,200,200,0.15)",
        line=dict(color="rgba(150,150,150,0.5)", width=0.5, dash="dot"),
    ))

    fig.update_layout(
        title="Storage Inventory Profile",
        yaxis_title="Units (Shares)",
        height=400, template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=60, r=20, t=60, b=40),
    )
    return fig


def create_inventory_gauge(current_inventory: int, config: StorageConfig) -> go.Figure:
    """Plotly gauge chart for current inventory level."""
    pct = (current_inventory / config.max_inventory) * 100
    cushion_pct = (config.min_inventory / config.max_inventory) * 100

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=current_inventory,
        title={"text": "Current Inventory"},
        delta={"reference": config.min_inventory, "relative": False, "prefix": "vs cushion: "},
        gauge={
            "axis": {"range": [0, config.max_inventory]},
            "bar": {"color": "#2196F3"},
            "steps": [
                {"range": [0, config.min_inventory], "color": "rgba(244,67,54,0.2)"},
                {"range": [config.min_inventory, config.max_inventory * 0.7], "color": "rgba(76,175,80,0.15)"},
                {"range": [config.max_inventory * 0.7, config.max_inventory], "color": "rgba(255,152,0,0.15)"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 2},
                "thickness": 0.75,
                "value": config.min_inventory,
            },
        },
    ))
    fig.update_layout(height=300, margin=dict(l=30, r=30, t=60, b=30))
    return fig


def create_portfolio_vs_benchmark_chart(daily_df: pd.DataFrame) -> go.Figure:
    """Portfolio value vs buy-and-hold benchmark."""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=daily_df.index, y=daily_df["portfolio_value"],
        name="Storage Strategy",
        line=dict(color="#2196F3", width=2),
    ))

    # Buy-and-hold: invest all initial capital at first price
    first_price = daily_df["price"].iloc[0]
    initial_value = daily_df["portfolio_value"].iloc[0]
    buy_hold = initial_value * (daily_df["price"] / first_price)
    fig.add_trace(go.Scatter(
        x=daily_df.index, y=buy_hold,
        name="Buy & Hold",
        line=dict(color="#FF9800", width=1.5, dash="dash"),
    ))

    fig.update_layout(
        title="Portfolio Value: Storage Strategy vs Buy & Hold",
        yaxis_title="Portfolio Value ($)",
        height=400, template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=60, r=20, t=60, b=40),
    )
    return fig


def create_storage_value_chart(daily_df: pd.DataFrame) -> go.Figure:
    """Intrinsic + optionality value stacked area over time."""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=daily_df.index, y=daily_df["intrinsic_value"],
        name="Intrinsic Value", fill="tozeroy",
        fillcolor="rgba(33,150,243,0.3)",
        line=dict(color="#2196F3", width=1),
    ))
    fig.add_trace(go.Scatter(
        x=daily_df.index,
        y=daily_df["intrinsic_value"] + daily_df["optionality_value"],
        name="+ Optionality Value", fill="tonexty",
        fillcolor="rgba(156,39,176,0.2)",
        line=dict(color="#9C27B0", width=1),
    ))

    fig.update_layout(
        title="Storage Value Decomposition",
        yaxis_title="Value ($)",
        height=400, template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=60, r=20, t=60, b=40),
    )
    return fig


def create_signal_decomposition_chart(daily_df: pd.DataFrame) -> go.Figure:
    """Three-panel chart showing each signal component."""
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=["Seasonal Score", "Z-Score (Mean Reversion)", "Momentum Filter"],
    )

    fig.add_trace(go.Scatter(
        x=daily_df.index, y=daily_df["seasonal_score"],
        name="Seasonal", line=dict(color="#4CAF50", width=1),
    ), row=1, col=1)
    fig.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.3, row=1, col=1)

    fig.add_trace(go.Scatter(
        x=daily_df.index, y=daily_df["zscore"],
        name="Z-Score", line=dict(color="#2196F3", width=1),
    ), row=2, col=1)
    fig.add_hline(y=-1, line_dash="dot", line_color="green", opacity=0.5, row=2, col=1)
    fig.add_hline(y=1, line_dash="dot", line_color="red", opacity=0.5, row=2, col=1)
    fig.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.3, row=2, col=1)

    fig.add_trace(go.Scatter(
        x=daily_df.index, y=daily_df["momentum"],
        name="Momentum", line=dict(color="#FF9800", width=1),
    ), row=3, col=1)
    fig.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.3, row=3, col=1)

    fig.update_layout(
        height=600, template="plotly_white",
        showlegend=False,
        margin=dict(l=60, r=20, t=40, b=40),
    )
    return fig


def create_seasonal_heatmap(monthly_stats: pd.DataFrame) -> go.Figure:
    """Monthly average returns heatmap."""
    returns = monthly_stats["mean_return"].values * 100  # to percent

    fig = go.Figure(go.Heatmap(
        z=[returns],
        x=monthly_stats["month_name"].values,
        y=["Avg Return %"],
        colorscale="RdYlGn",
        text=[[f"{r:.2f}%" for r in returns]],
        texttemplate="%{text}",
        showscale=True,
        colorbar=dict(title="Return %"),
    ))

    fig.update_layout(
        title="Average Monthly Returns (Historical)",
        height=200, template="plotly_white",
        margin=dict(l=80, r=20, t=60, b=40),
        yaxis=dict(showticklabels=False),
    )
    return fig


def create_annual_pnl_chart(daily_df: pd.DataFrame) -> go.Figure:
    """Annual P&L bar chart."""
    daily_df = daily_df.copy()
    daily_df["year"] = daily_df.index.year
    yearly = daily_df.groupby("year").agg(
        start_value=("portfolio_value", "first"),
        end_value=("portfolio_value", "last"),
    )
    yearly["pnl"] = yearly["end_value"] - yearly["start_value"]
    yearly["return_pct"] = ((yearly["end_value"] / yearly["start_value"]) - 1) * 100

    colors = ["#4CAF50" if v >= 0 else "#F44336" for v in yearly["pnl"]]

    fig = go.Figure(go.Bar(
        x=yearly.index.astype(str),
        y=yearly["return_pct"],
        marker_color=colors,
        text=[f"{r:.1f}%" for r in yearly["return_pct"]],
        textposition="outside",
    ))

    fig.update_layout(
        title="Annual Returns (%)",
        yaxis_title="Return %",
        height=350, template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=40),
    )
    return fig
