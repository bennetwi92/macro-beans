"""
Probability Calculations
========================
Functions for calculating VIX spike and downside probabilities.
"""

from datetime import datetime


def assign_recency_weight(date):
    """
    Assign weight based on how recent the data is.
    Recent data is weighted more heavily to reflect current market regime.

    Args:
        date: Datetime object representing the data point date

    Returns:
        float: Weight multiplier (1.0 to 3.0)
    """
    now = datetime.now()
    days_ago = (now - date).days

    if days_ago <= 365:
        return 3.0  # Last year: 3x weight
    elif days_ago <= 365 * 3:
        return 2.0  # Last 3 years: 2x weight
    elif days_ago <= 365 * 5:
        return 1.5  # Last 5 years: 1.5x weight
    else:
        return 1.0  # Older: normal weight


def calculate_spike_probability(vix_data, entry_vix, target_vix, days_window):
    """
    Calculate historical probability of VIX reaching target from entry level.

    Args:
        vix_data: DataFrame with VIX historical data
        entry_vix: Entry VIX level
        target_vix: Target VIX level to reach
        days_window: Number of days to look forward

    Returns:
        tuple: (probability, total_instances, days_to_spike_list)
    """
    # Find instances where VIX was near entry level
    tolerance = 1.0
    entry_dates = vix_data[(vix_data['VIX'] >= entry_vix - tolerance) &
                           (vix_data['VIX'] <= entry_vix + tolerance)].index

    successful_spikes = 0
    total_instances = 0
    days_to_spike_list = []

    for entry_date in entry_dates:
        # Look forward
        future_data = vix_data.loc[vix_data.index > entry_date].head(days_window)

        if len(future_data) == 0:
            continue

        total_instances += 1

        # Check if VIX reached target
        spike_days = future_data[future_data['VIX'] >= target_vix]

        if len(spike_days) > 0:
            successful_spikes += 1
            days_to_spike = (spike_days.index[0] - entry_date).days
            days_to_spike_list.append(days_to_spike)

    if total_instances == 0:
        return 0, 0, []

    probability = successful_spikes / total_instances

    return probability, total_instances, days_to_spike_list


def calculate_downside_risk(vix_data, entry_vix, days_window=30):
    """
    Calculate probability of VIX dropping below entry level (recency-weighted).

    Args:
        vix_data: DataFrame with VIX historical data
        entry_vix: Entry VIX level
        days_window: Number of days to analyze (default 30)

    Returns:
        dict: {drop_percentage: probability}
    """
    tolerance = 1.0
    entry_dates = vix_data[(vix_data['VIX'] >= entry_vix - tolerance) &
                           (vix_data['VIX'] <= entry_vix + tolerance)].index

    drop_levels = [0.90, 0.85, 0.80, 0.75, 0.70]  # 10%, 15%, 20%, 25%, 30% drops
    weighted_breaches = {int((1-level)*100): 0 for level in drop_levels}
    total_weight = 0

    for entry_date in entry_dates:
        entry_level = vix_data.loc[entry_date, 'VIX']
        weight = assign_recency_weight(entry_date)

        future_data = vix_data.loc[vix_data.index > entry_date].head(days_window)

        if len(future_data) == 0:
            continue

        total_weight += weight
        min_vix = future_data['VIX'].min()

        # Check which levels were breached
        for level in drop_levels:
            threshold = entry_level * level
            if min_vix <= threshold:
                drop_pct = int((1-level)*100)
                weighted_breaches[drop_pct] += weight

    # Calculate weighted probabilities
    probabilities = {}
    for drop_pct, weighted_count in weighted_breaches.items():
        if total_weight > 0:
            probabilities[drop_pct] = (weighted_count / total_weight) * 100
        else:
            probabilities[drop_pct] = 0

    return probabilities
