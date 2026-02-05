"""
Visualization Functions
=======================
Functions for creating charts and visualizations.
"""

import plotly.graph_objects as go
import numpy as np
from .options_pricing import calculate_theta_decay, calculate_option_value


def create_spike_histogram(days_to_spike_list, dte):
    """
    Create histogram of time to spike distribution.

    Args:
        days_to_spike_list: List of historical days to spike
        dte: Days to expiration (for reference line)

    Returns:
        plotly Figure
    """
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=days_to_spike_list,
        nbinsx=20,
        name='Historical Spikes',
        marker_color='steelblue'
    ))

    if len(days_to_spike_list) > 0:
        fig_hist.add_vline(x=np.median(days_to_spike_list),
                          line_dash="dash", line_color="red",
                          annotation_text=f"Median: {np.median(days_to_spike_list):.0f}d")

    fig_hist.add_vline(x=dte,
                      line_dash="dash", line_color="orange",
                      annotation_text=f"Your DTE: {dte}d")

    fig_hist.update_layout(
        xaxis_title="Days to Spike",
        yaxis_title="Frequency",
        showlegend=False,
        height=300
    )

    return fig_hist


def create_theta_decay_chart(entry_premium, dte, theta_decay_monthly, theta_greek,
                             entry_vix, strike, profit_target, days_to_spike_list):
    """
    Create theta decay visualization with spike scenarios.

    Args:
        entry_premium: Entry option price
        dte: Days to expiration
        theta_decay_monthly: Monthly decay rate
        theta_greek: Actual theta (if available)
        entry_vix: Entry VIX level
        strike: Strike price
        profit_target: Profit target percentage
        days_to_spike_list: Historical spike timing data

    Returns:
        plotly Figure
    """
    days_array = np.arange(0, dte + 1)

    # Decay only scenario
    decay_values = [calculate_theta_decay(entry_premium, d, dte, theta_decay_monthly, theta_greek)
                   for d in days_array]

    # Spike scenarios
    vix_levels_to_plot = [18, 20, 25]

    fig_decay = go.Figure()

    # Add decay line
    fig_decay.add_trace(go.Scatter(
        x=days_array,
        y=decay_values,
        mode='lines',
        name='Theta Decay (No Spike)',
        line=dict(color='red', width=2, dash='dash')
    ))

    # Add spike scenarios
    colors = ['orange', 'green', 'purple']
    for vix_level, color in zip(vix_levels_to_plot, colors):
        # Assume spike happens at median days
        median_days = int(np.median(days_to_spike_list)) if len(days_to_spike_list) > 0 else 14

        if median_days <= dte:
            # Before spike: decay
            before_spike = [calculate_theta_decay(entry_premium, d, dte, theta_decay_monthly, theta_greek)
                           for d in range(0, median_days + 1)]

            # At spike: value jumps
            vix_rise_factor = vix_level / entry_vix
            iv_multiplier = 1.5 + (vix_rise_factor - 1) * 1.5
            spike_value = calculate_option_value(vix_level, strike, dte - median_days, iv_multiplier)

            # After spike: hold value (simplified)
            after_spike = [spike_value] * (dte - median_days + 1)

            spike_line = before_spike + after_spike
            days_line = list(range(len(spike_line)))

            fig_decay.add_trace(go.Scatter(
                x=days_line,
                y=spike_line,
                mode='lines',
                name=f'VIX → {vix_level}',
                line=dict(color=color, width=2)
            ))

    # Add entry premium line
    fig_decay.add_hline(y=entry_premium, line_dash="dot", line_color="black",
                       annotation_text=f"Entry: ${entry_premium:.2f}")

    # Add profit target line
    profit_target_value = entry_premium * (1 + profit_target / 100)
    fig_decay.add_hline(y=profit_target_value, line_dash="dot", line_color="green",
                       annotation_text=f"Target: ${profit_target_value:.2f}")

    fig_decay.update_layout(
        xaxis_title="Days Since Entry",
        yaxis_title="Option Value ($)",
        hovermode='x unified',
        height=500,
        legend=dict(x=0.7, y=0.95)
    )

    return fig_decay


def create_downside_chart(downside_probs, dte):
    """
    Create bar chart showing downside risk probabilities.

    Args:
        downside_probs: Dictionary of {drop_percentage: probability}
        dte: Days to expiration

    Returns:
        plotly Figure
    """
    fig_downside = go.Figure()

    stops = sorted(downside_probs.keys())
    probs = [downside_probs[s] for s in stops]
    colors = ['green' if p < 10 else 'orange' if p < 20 else 'red' for p in probs]

    fig_downside.add_trace(go.Bar(
        x=[f'-{s}%' for s in stops],
        y=probs,
        marker_color=colors,
        text=[f'{p:.1f}%' for p in probs],
        textposition='outside'
    ))

    fig_downside.add_hline(y=10, line_dash="dash", line_color="green",
                          annotation_text="Low Risk (<10%)")
    fig_downside.add_hline(y=20, line_dash="dash", line_color="orange",
                          annotation_text="Moderate Risk (<20%)")

    fig_downside.update_layout(
        title=f"Probability of Hitting Stop Levels ({dte} days)",
        xaxis_title="Stop Loss Level",
        yaxis_title="Probability (%)",
        showlegend=False,
        height=400
    )

    return fig_downside
