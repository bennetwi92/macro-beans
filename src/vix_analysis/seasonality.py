"""
Seasonality Analysis
====================
Functions for analyzing seasonal patterns in VIX behavior.
"""

import pandas as pd
import numpy as np
from datetime import datetime


def analyze_monthly_seasonality(vix_data):
    """
    Analyze VIX behavior by month of year.

    Args:
        vix_data: DataFrame with VIX historical data

    Returns:
        DataFrame: Monthly statistics (avg, median, std, spike probability)
    """
    df = vix_data.copy()
    df['Month'] = df.index.month
    df['Month_Name'] = df.index.strftime('%B')

    monthly_stats = df.groupby('Month').agg({
        'VIX': ['mean', 'median', 'std', 'min', 'max', 'count']
    }).round(2)

    monthly_stats.columns = ['Mean', 'Median', 'Std Dev', 'Min', 'Max', 'Count']
    monthly_stats['Month_Name'] = ['January', 'February', 'March', 'April', 'May', 'June',
                                     'July', 'August', 'September', 'October', 'November', 'December']

    # Calculate spike probability (VIX > 20)
    spike_prob = df[df['VIX'] > 20].groupby('Month').size() / df.groupby('Month').size() * 100
    monthly_stats['Spike Prob (>20)'] = spike_prob.round(1)

    # Calculate extreme spike probability (VIX > 30)
    extreme_spike_prob = df[df['VIX'] > 30].groupby('Month').size() / df.groupby('Month').size() * 100
    monthly_stats['Extreme Prob (>30)'] = extreme_spike_prob.round(1)

    return monthly_stats


def analyze_day_of_month_seasonality(vix_data):
    """
    Analyze VIX behavior by day of month.

    Args:
        vix_data: DataFrame with VIX historical data

    Returns:
        DataFrame: Day of month statistics
    """
    df = vix_data.copy()
    df['Day'] = df.index.day

    day_stats = df.groupby('Day').agg({
        'VIX': ['mean', 'median', 'std', 'count']
    }).round(2)

    day_stats.columns = ['Mean', 'Median', 'Std Dev', 'Count']

    # Calculate avg daily change
    df['VIX_Change'] = df['VIX'].pct_change() * 100
    day_change = df.groupby('Day')['VIX_Change'].mean().round(2)
    day_stats['Avg Daily Change %'] = day_change

    return day_stats


def analyze_day_of_week_seasonality(vix_data):
    """
    Analyze VIX behavior by day of week.

    Args:
        vix_data: DataFrame with VIX historical data

    Returns:
        DataFrame: Day of week statistics
    """
    df = vix_data.copy()
    df['DayOfWeek'] = df.index.dayofweek
    df['DayName'] = df.index.strftime('%A')

    dow_stats = df.groupby('DayOfWeek').agg({
        'VIX': ['mean', 'median', 'std', 'count']
    }).round(2)

    dow_stats.columns = ['Mean', 'Median', 'Std Dev', 'Count']
    dow_stats['Day'] = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    # Calculate average daily change
    df['VIX_Change'] = df['VIX'].pct_change() * 100
    dow_change = df.groupby('DayOfWeek')['VIX_Change'].mean().round(2)
    dow_stats['Avg Change %'] = dow_change

    # Up/down probability
    up_prob = (df.groupby('DayOfWeek')['VIX_Change'].apply(lambda x: (x > 0).sum()) /
               df.groupby('DayOfWeek')['VIX_Change'].count() * 100).round(1)
    dow_stats['Up Prob %'] = up_prob

    return dow_stats


def analyze_holiday_periods(vix_data):
    """
    Analyze VIX behavior during specific holiday periods.

    Args:
        vix_data: DataFrame with VIX historical data

    Returns:
        dict: Statistics for various holiday periods
    """
    df = vix_data.copy()
    df['Month'] = df.index.month
    df['Day'] = df.index.day

    periods = {}

    # Christmas period (Dec 20-31)
    christmas = df[(df['Month'] == 12) & (df['Day'] >= 20)]
    periods['Christmas (Dec 20-31)'] = {
        'Mean VIX': christmas['VIX'].mean(),
        'Median VIX': christmas['VIX'].median(),
        'Std Dev': christmas['VIX'].std(),
        'Days': len(christmas),
        'Spike Rate (>20)': (christmas['VIX'] > 20).sum() / len(christmas) * 100 if len(christmas) > 0 else 0
    }

    # New Year (Jan 1-10)
    new_year = df[(df['Month'] == 1) & (df['Day'] <= 10)]
    periods['New Year (Jan 1-10)'] = {
        'Mean VIX': new_year['VIX'].mean(),
        'Median VIX': new_year['VIX'].median(),
        'Std Dev': new_year['VIX'].std(),
        'Days': len(new_year),
        'Spike Rate (>20)': (new_year['VIX'] > 20).sum() / len(new_year) * 100 if len(new_year) > 0 else 0
    }

    # Tax Day period (Apr 10-20)
    tax_day = df[(df['Month'] == 4) & (df['Day'] >= 10) & (df['Day'] <= 20)]
    periods['Tax Day (Apr 10-20)'] = {
        'Mean VIX': tax_day['VIX'].mean(),
        'Median VIX': tax_day['VIX'].median(),
        'Std Dev': tax_day['VIX'].std(),
        'Days': len(tax_day),
        'Spike Rate (>20)': (tax_day['VIX'] > 20).sum() / len(tax_day) * 100 if len(tax_day) > 0 else 0
    }

    # Summer lull (July-August)
    summer = df[(df['Month'] >= 7) & (df['Month'] <= 8)]
    periods['Summer (Jul-Aug)'] = {
        'Mean VIX': summer['VIX'].mean(),
        'Median VIX': summer['VIX'].median(),
        'Std Dev': summer['VIX'].std(),
        'Days': len(summer),
        'Spike Rate (>20)': (summer['VIX'] > 20).sum() / len(summer) * 100 if len(summer) > 0 else 0
    }

    # September-October (historically volatile)
    fall = df[(df['Month'] >= 9) & (df['Month'] <= 10)]
    periods['Fall (Sep-Oct)'] = {
        'Mean VIX': fall['VIX'].mean(),
        'Median VIX': fall['VIX'].median(),
        'Std Dev': fall['VIX'].std(),
        'Days': len(fall),
        'Spike Rate (>20)': (fall['VIX'] > 20).sum() / len(fall) * 100 if len(fall) > 0 else 0
    }

    # Thanksgiving week (last week of November)
    thanksgiving = df[(df['Month'] == 11) & (df['Day'] >= 20)]
    periods['Thanksgiving Week'] = {
        'Mean VIX': thanksgiving['VIX'].mean(),
        'Median VIX': thanksgiving['VIX'].median(),
        'Std Dev': thanksgiving['VIX'].std(),
        'Days': len(thanksgiving),
        'Spike Rate (>20)': (thanksgiving['VIX'] > 20).sum() / len(thanksgiving) * 100 if len(thanksgiving) > 0 else 0
    }

    return periods


def analyze_quarter_seasonality(vix_data):
    """
    Analyze VIX behavior by quarter.

    Args:
        vix_data: DataFrame with VIX historical data

    Returns:
        DataFrame: Quarterly statistics
    """
    df = vix_data.copy()
    df['Quarter'] = df.index.quarter

    quarter_stats = df.groupby('Quarter').agg({
        'VIX': ['mean', 'median', 'std', 'min', 'max', 'count']
    }).round(2)

    quarter_stats.columns = ['Mean', 'Median', 'Std Dev', 'Min', 'Max', 'Count']
    quarter_stats['Quarter_Name'] = ['Q1 (Jan-Mar)', 'Q2 (Apr-Jun)', 'Q3 (Jul-Sep)', 'Q4 (Oct-Dec)']

    # Spike probabilities
    spike_prob = df[df['VIX'] > 20].groupby('Quarter').size() / df.groupby('Quarter').size() * 100
    quarter_stats['Spike Prob (>20)'] = spike_prob.round(1)

    return quarter_stats


def calculate_seasonal_trading_edge(vix_data, entry_vix=15.0):
    """
    Calculate which months/periods offer the best edge for VIX call entries.

    Args:
        vix_data: DataFrame with VIX historical data
        entry_vix: Entry VIX level to filter for

    Returns:
        DataFrame: Best months for entries ranked by subsequent spike probability
    """
    df = vix_data.copy()
    df['Month'] = df.index.month
    df['Month_Name'] = df.index.strftime('%B')

    # Find instances where VIX was near entry level
    tolerance = 1.0
    entry_instances = df[(df['VIX'] >= entry_vix - tolerance) &
                         (df['VIX'] <= entry_vix + tolerance)].copy()

    if len(entry_instances) == 0:
        return pd.DataFrame()

    # For each entry, check if VIX spiked >20 within next 30 days
    entry_instances['Spiked_30d'] = False

    for idx in entry_instances.index:
        future_data = df.loc[df.index > idx].head(30)
        if len(future_data) > 0 and future_data['VIX'].max() >= 20:
            entry_instances.loc[idx, 'Spiked_30d'] = True

    # Group by month and calculate spike probability
    monthly_edge = entry_instances.groupby('Month').agg({
        'Spiked_30d': ['sum', 'count', 'mean']
    })

    monthly_edge.columns = ['Spikes', 'Total Entries', 'Spike Probability']
    monthly_edge['Spike Probability'] = (monthly_edge['Spike Probability'] * 100).round(1)
    monthly_edge['Month_Name'] = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    # Sort by spike probability
    monthly_edge = monthly_edge.sort_values('Spike Probability', ascending=False)

    return monthly_edge


def analyze_specific_date(vix_data, month, day):
    """
    Analyze VIX behavior on a specific calendar date across all years.
    For example, all December 15ths throughout history.

    Args:
        vix_data: DataFrame with VIX historical data
        month: Month number (1-12)
        day: Day number (1-31)

    Returns:
        DataFrame: All instances of that date with VIX levels and forward returns
    """
    df = vix_data.copy()
    df['Month'] = df.index.month
    df['Day'] = df.index.day
    df['Year'] = df.index.year

    # Filter for specific date
    specific_dates = df[(df['Month'] == month) & (df['Day'] == day)].copy()

    if len(specific_dates) == 0:
        return pd.DataFrame()

    # Calculate forward returns (1 day, 1 week, 1 month ahead)
    results = []

    for idx in specific_dates.index:
        year = specific_dates.loc[idx, 'Year']
        vix_level = specific_dates.loc[idx, 'VIX']

        # Get future data
        future_data = df.loc[df.index > idx]

        # 1 day forward
        fwd_1d = future_data.head(1)['VIX'].iloc[0] if len(future_data) >= 1 else None
        fwd_1d_chg = ((fwd_1d - vix_level) / vix_level * 100) if fwd_1d else None

        # 5 days forward
        fwd_5d = future_data.head(5)['VIX'].iloc[-1] if len(future_data) >= 5 else None
        fwd_5d_chg = ((fwd_5d - vix_level) / vix_level * 100) if fwd_5d else None

        # 20 days forward (1 month)
        fwd_20d = future_data.head(20)['VIX'].iloc[-1] if len(future_data) >= 20 else None
        fwd_20d_chg = ((fwd_20d - vix_level) / vix_level * 100) if fwd_20d else None

        # Max VIX in next 30 days
        max_30d = future_data.head(30)['VIX'].max() if len(future_data) >= 30 else None
        max_30d_chg = ((max_30d - vix_level) / vix_level * 100) if max_30d else None

        # Check if spiked above 20
        spiked = future_data.head(30)['VIX'].max() >= 20 if len(future_data) >= 30 else False

        results.append({
            'Year': year,
            'Date': idx.strftime('%Y-%m-%d'),
            'VIX': vix_level,
            '1D Forward': fwd_1d,
            '1D Change %': fwd_1d_chg,
            '5D Forward': fwd_5d,
            '5D Change %': fwd_5d_chg,
            '20D Forward': fwd_20d,
            '20D Change %': fwd_20d_chg,
            'Max 30D': max_30d,
            'Max 30D Change %': max_30d_chg,
            'Spiked >20': spiked
        })

    return pd.DataFrame(results)


def get_date_statistics(specific_date_df):
    """
    Calculate summary statistics for a specific calendar date.

    Args:
        specific_date_df: DataFrame from analyze_specific_date()

    Returns:
        dict: Summary statistics
    """
    if len(specific_date_df) == 0:
        return {}

    stats = {
        'Total Instances': len(specific_date_df),
        'Avg VIX': specific_date_df['VIX'].mean(),
        'Median VIX': specific_date_df['VIX'].median(),
        'Min VIX': specific_date_df['VIX'].min(),
        'Max VIX': specific_date_df['VIX'].max(),
        'Avg 1D Change %': specific_date_df['1D Change %'].mean(),
        'Avg 5D Change %': specific_date_df['5D Change %'].mean(),
        'Avg 20D Change %': specific_date_df['20D Change %'].mean(),
        'Spike Rate (>20 in 30D)': (specific_date_df['Spiked >20'].sum() / len(specific_date_df) * 100),
        'Positive 1D %': (specific_date_df['1D Change %'] > 0).sum() / len(specific_date_df) * 100,
        'Positive 5D %': (specific_date_df['5D Change %'] > 0).sum() / len(specific_date_df) * 100,
        'Positive 20D %': (specific_date_df['20D Change %'] > 0).sum() / len(specific_date_df) * 100,
    }

    return stats
