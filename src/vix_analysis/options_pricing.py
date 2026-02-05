"""
Options Pricing Models
======================
Functions for calculating option values, decay, and scenario simulations.
"""

import numpy as np
import pandas as pd


def calculate_option_value(current_vix, strike, days_to_expiry, iv_multiplier=1.0):
    """
    Simplified option pricing model based on VIX level and time.
    This is a rough approximation focusing on extrinsic value.

    Args:
        current_vix: Current VIX level
        strike: Option strike price
        days_to_expiry: Days until expiration
        iv_multiplier: Implied volatility multiplier (default 1.0)

    Returns:
        float: Estimated option value
    """
    # Distance from strike
    moneyness = current_vix - strike

    # Time value (decreases with time)
    time_factor = np.sqrt(days_to_expiry / 365)

    # Implied volatility increases when VIX rises
    iv_factor = iv_multiplier * (current_vix / 15.0)  # IV expands as VIX rises

    # Intrinsic value
    intrinsic = max(0, moneyness)

    # Extrinsic value (simplified Black-Scholes-like)
    base_extrinsic = 0.15 * current_vix * time_factor * iv_factor

    # Total value
    option_value = intrinsic + base_extrinsic

    return max(0.05, option_value)  # Minimum 0.05


def calculate_theta_decay(initial_price, days_elapsed, total_days, decay_rate_monthly, theta_greek=None):
    """
    Calculate option value after theta decay.

    Args:
        initial_price: Starting option price
        days_elapsed: Number of days that have passed
        total_days: Total days to expiration
        decay_rate_monthly: Monthly decay rate (0.35 = 35%)
        theta_greek: Actual theta from options chain (optional)

    Returns:
        float: Option value after decay
    """
    if theta_greek is not None:
        # Use actual theta if provided
        remaining_value = initial_price + (theta_greek * days_elapsed)
        return max(0.01, remaining_value)  # Can't go below $0.01
    else:
        # Convert monthly decay to daily
        if decay_rate_monthly is None:
            decay_rate_monthly = 0.35  # Default to 35% if not provided

        daily_decay = 1 - (1 - decay_rate_monthly) ** (1/30)

        # Apply decay
        remaining_value = initial_price * ((1 - daily_decay) ** days_elapsed)

        return remaining_value


def simulate_scenarios(entry_vix, strike, entry_premium, dte, spike_probability,
                       theta_decay_monthly, target_vix_levels, days_to_spike_list,
                       theta_greek=None, vega_greek=None):
    """
    Simulate different VIX spike scenarios.

    Args:
        entry_vix: Entry VIX level
        strike: Option strike
        entry_premium: Entry option price
        dte: Days to expiration
        spike_probability: Historical spike probability
        theta_decay_monthly: Monthly theta decay rate
        target_vix_levels: List of target VIX levels to simulate
        days_to_spike_list: Historical days to spike data
        theta_greek: Actual theta (optional)
        vega_greek: Actual vega (optional)

    Returns:
        DataFrame: Scenario analysis results
    """
    scenarios = []

    # Scenario 1: Fast spike (7 days) - if historically possible
    if len(days_to_spike_list) > 0:
        fast_spike_days = min(7, int(np.percentile(days_to_spike_list, 25)) if len(days_to_spike_list) > 3 else 7)
    else:
        fast_spike_days = 7

    for target_vix in target_vix_levels:
        days_to_target = fast_spike_days if target_vix <= 22 else min(14, fast_spike_days * 2)

        # Calculate option value at spike
        if vega_greek is not None:
            # Use Vega to estimate gain from IV expansion
            vix_rise_pct = (target_vix - entry_vix) / entry_vix
            # IV typically rises 2-3x more than VIX move
            iv_expansion = vix_rise_pct * 2.5  # 2.5x multiplier for IV expansion
            vega_contribution = vega_greek * iv_expansion * 100  # Vega is per 1% IV change

            # Add intrinsic value if ITM
            intrinsic = max(0, target_vix - strike)

            option_value_spike = entry_premium + vega_contribution + intrinsic

            # Subtract theta decay to spike
            if theta_greek is not None:
                option_value_spike += (theta_greek * days_to_target)
        else:
            # Fallback to model-based calculation
            vix_rise_factor = target_vix / entry_vix
            iv_multiplier = 1.5 + (vix_rise_factor - 1) * 1.5
            option_value_spike = calculate_option_value(target_vix, strike,
                                                         dte - days_to_target,
                                                         iv_multiplier)

        # Adjust for decay until spike
        theta_adjusted_entry = calculate_theta_decay(entry_premium, days_to_target,
                                                      dte, theta_decay_monthly, theta_greek)

        # Gain calculation
        gain_pct = (option_value_spike - entry_premium) / entry_premium
        gain_from_decayed = (option_value_spike - theta_adjusted_entry) / entry_premium

        scenarios.append({
            'target_vix': target_vix,
            'vix_move': target_vix - entry_vix,
            'vix_move_pct': (target_vix - entry_vix) / entry_vix * 100,
            'days_to_target': days_to_target,
            'option_value': option_value_spike,
            'gain_pct': gain_pct * 100,
            'gain_from_decayed': gain_from_decayed * 100,
            'probability': 'High' if gain_pct > 1.0 else 'Medium' if gain_pct > 0.5 else 'Low'
        })

    # No spike scenario (theta decay only) - just show at expiration
    decayed_value = calculate_theta_decay(entry_premium, dte, dte, theta_decay_monthly, theta_greek)
    loss_pct = (decayed_value - entry_premium) / entry_premium * 100

    scenarios.append({
        'target_vix': entry_vix,  # No movement
        'vix_move': 0,
        'vix_move_pct': 0,
        'days_to_target': dte,
        'option_value': decayed_value,
        'gain_pct': loss_pct,
        'gain_from_decayed': loss_pct,
        'probability': 'No Spike (Decay to Expiry)'
    })

    return pd.DataFrame(scenarios)
