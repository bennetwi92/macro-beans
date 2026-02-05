"""
VIX Analysis Package
====================
Modular components for VIX options analysis and trading strategies.
"""

from .probability import calculate_spike_probability, calculate_downside_risk, assign_recency_weight
from .options_pricing import calculate_option_value, calculate_theta_decay, simulate_scenarios
from .visualizations import create_spike_histogram, create_theta_decay_chart, create_downside_chart
from .seasonality import (
    analyze_monthly_seasonality,
    analyze_day_of_month_seasonality,
    analyze_day_of_week_seasonality,
    analyze_holiday_periods,
    analyze_quarter_seasonality,
    calculate_seasonal_trading_edge,
    analyze_specific_date,
    get_date_statistics
)
from .seasonality_viz import (
    create_monthly_heatmap,
    create_monthly_box_plot,
    create_day_of_week_chart,
    create_holiday_periods_chart,
    create_spike_probability_by_month,
    create_day_of_month_chart,
    create_quarterly_comparison
)

__all__ = [
    'calculate_spike_probability',
    'calculate_downside_risk',
    'assign_recency_weight',
    'calculate_option_value',
    'calculate_theta_decay',
    'simulate_scenarios',
    'create_spike_histogram',
    'create_theta_decay_chart',
    'create_downside_chart',
    'analyze_monthly_seasonality',
    'analyze_day_of_month_seasonality',
    'analyze_day_of_week_seasonality',
    'analyze_holiday_periods',
    'analyze_quarter_seasonality',
    'calculate_seasonal_trading_edge',
    'analyze_specific_date',
    'get_date_statistics',
    'create_monthly_heatmap',
    'create_monthly_box_plot',
    'create_day_of_week_chart',
    'create_holiday_periods_chart',
    'create_spike_probability_by_month',
    'create_day_of_month_chart',
    'create_quarterly_comparison',
]
