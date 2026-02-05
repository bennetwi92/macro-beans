"""
Seasonality Visualizations
===========================
Charts for seasonal patterns in VIX.
"""

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np


def create_monthly_heatmap(vix_data):
    """
    Create heatmap showing average VIX by month and year.

    Args:
        vix_data: DataFrame with VIX historical data

    Returns:
        plotly Figure
    """
    df = vix_data.copy()
    df['Year'] = df.index.year
    df['Month'] = df.index.month

    # Pivot to get Year x Month matrix
    pivot = df.pivot_table(values='VIX', index='Year', columns='Month', aggfunc='mean')

    # Only show recent years (last 10)
    pivot = pivot.tail(10)

    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=month_names,
        y=pivot.index,
        colorscale='RdYlGn_r',  # Red for high VIX, green for low
        text=pivot.values.round(1),
        texttemplate='%{text}',
        textfont={"size": 10},
        colorbar=dict(title="Avg VIX")
    ))

    fig.update_layout(
        title="Average VIX by Month and Year (Last 10 Years)",
        xaxis_title="Month",
        yaxis_title="Year",
        height=500
    )

    return fig


def create_monthly_box_plot(monthly_stats):
    """
    Create box plot showing VIX distribution by month.

    Args:
        monthly_stats: DataFrame with monthly statistics

    Returns:
        plotly Figure
    """
    fig = go.Figure()

    months = monthly_stats['Month_Name'].values
    means = monthly_stats['Mean'].values
    medians = monthly_stats['Median'].values

    # Bar chart of mean VIX
    fig.add_trace(go.Bar(
        x=months,
        y=means,
        name='Mean VIX',
        marker_color='steelblue',
        text=means.round(1),
        textposition='outside'
    ))

    # Add median as line
    fig.add_trace(go.Scatter(
        x=months,
        y=medians,
        name='Median VIX',
        mode='lines+markers',
        line=dict(color='red', width=2, dash='dash'),
        marker=dict(size=8)
    ))

    fig.update_layout(
        title="Average VIX by Month",
        xaxis_title="Month",
        yaxis_title="VIX Level",
        hovermode='x unified',
        height=400
    )

    return fig


def create_day_of_week_chart(dow_stats):
    """
    Create chart showing VIX behavior by day of week.

    Args:
        dow_stats: DataFrame with day of week statistics

    Returns:
        plotly Figure
    """
    fig = go.Figure()

    days = dow_stats['Day'].values
    avg_change = dow_stats['Avg Change %'].values
    colors = ['green' if x < 0 else 'red' for x in avg_change]

    fig.add_trace(go.Bar(
        x=days,
        y=avg_change,
        marker_color=colors,
        text=avg_change.round(2),
        textposition='outside'
    ))

    fig.add_hline(y=0, line_dash="dash", line_color="black")

    fig.update_layout(
        title="Average VIX Change by Day of Week (%)",
        xaxis_title="Day of Week",
        yaxis_title="Average % Change",
        height=400
    )

    return fig


def create_holiday_periods_chart(periods_dict):
    """
    Create chart comparing VIX levels during holiday periods.

    Args:
        periods_dict: Dictionary of holiday period statistics

    Returns:
        plotly Figure
    """
    periods = list(periods_dict.keys())
    means = [periods_dict[p]['Mean VIX'] for p in periods]
    spike_rates = [periods_dict[p]['Spike Rate (>20)'] for p in periods]

    fig = go.Figure()

    # Mean VIX bars
    fig.add_trace(go.Bar(
        x=periods,
        y=means,
        name='Mean VIX',
        marker_color='steelblue',
        text=[f"{m:.1f}" for m in means],
        textposition='outside',
        yaxis='y'
    ))

    # Spike rate line
    fig.add_trace(go.Scatter(
        x=periods,
        y=spike_rates,
        name='Spike Rate (>20)',
        mode='lines+markers',
        line=dict(color='red', width=2),
        marker=dict(size=10),
        yaxis='y2'
    ))

    fig.update_layout(
        title="VIX Behavior During Holiday Periods",
        xaxis_title="Period",
        yaxis=dict(title="Mean VIX", side='left'),
        yaxis2=dict(title="Spike Rate (%)", side='right', overlaying='y'),
        hovermode='x unified',
        height=450,
        legend=dict(x=0.02, y=0.98)
    )

    return fig


def create_spike_probability_by_month(monthly_stats):
    """
    Create stacked bar chart showing spike probabilities by month.

    Args:
        monthly_stats: DataFrame with monthly statistics

    Returns:
        plotly Figure
    """
    months = monthly_stats['Month_Name'].values
    spike_prob = monthly_stats['Spike Prob (>20)'].values
    extreme_prob = monthly_stats['Extreme Prob (>30)'].values

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=months,
        y=extreme_prob,
        name='VIX > 30 (Extreme)',
        marker_color='darkred',
        text=extreme_prob.round(1),
        textposition='inside'
    ))

    fig.add_trace(go.Bar(
        x=months,
        y=spike_prob - extreme_prob,
        name='VIX 20-30 (Elevated)',
        marker_color='orange',
        text=(spike_prob - extreme_prob).round(1),
        textposition='inside'
    ))

    fig.update_layout(
        title="Probability of VIX Spikes by Month",
        xaxis_title="Month",
        yaxis_title="Probability (%)",
        barmode='stack',
        height=400
    )

    return fig


def create_day_of_month_chart(day_stats):
    """
    Create chart showing VIX patterns by day of month.

    Args:
        day_stats: DataFrame with day of month statistics

    Returns:
        plotly Figure
    """
    fig = go.Figure()

    days = day_stats.index.values
    means = day_stats['Mean'].values

    fig.add_trace(go.Scatter(
        x=days,
        y=means,
        mode='lines+markers',
        marker=dict(size=4),
        line=dict(color='steelblue', width=2),
        name='Mean VIX'
    ))

    # Add overall mean as reference
    overall_mean = means.mean()
    fig.add_hline(y=overall_mean, line_dash="dash", line_color="red",
                  annotation_text=f"Overall Mean: {overall_mean:.2f}")

    fig.update_layout(
        title="Average VIX by Day of Month",
        xaxis_title="Day of Month",
        yaxis_title="Average VIX",
        hovermode='x',
        height=400
    )

    return fig


def create_quarterly_comparison(quarter_stats):
    """
    Create chart comparing quarters.

    Args:
        quarter_stats: DataFrame with quarterly statistics

    Returns:
        plotly Figure
    """
    fig = go.Figure()

    quarters = quarter_stats['Quarter_Name'].values
    means = quarter_stats['Mean'].values
    spike_prob = quarter_stats['Spike Prob (>20)'].values

    # Mean VIX bars
    fig.add_trace(go.Bar(
        x=quarters,
        y=means,
        name='Mean VIX',
        marker_color='steelblue',
        text=means.round(1),
        textposition='outside'
    ))

    # Spike probability line
    fig.add_trace(go.Scatter(
        x=quarters,
        y=spike_prob,
        name='Spike Prob (>20)',
        mode='lines+markers',
        line=dict(color='red', width=3),
        marker=dict(size=12),
        yaxis='y2'
    ))

    fig.update_layout(
        title="VIX Characteristics by Quarter",
        xaxis_title="Quarter",
        yaxis=dict(title="Mean VIX", side='left'),
        yaxis2=dict(title="Spike Probability (%)", side='right', overlaying='y'),
        hovermode='x unified',
        height=400
    )

    return fig
