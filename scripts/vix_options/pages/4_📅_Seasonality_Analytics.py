"""
Seasonality Analytics Page
===========================
Analyze seasonal patterns in VIX behavior across different time periods.
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.vix_analysis.shared_state import load_vix_data, apply_custom_css
import src.vix_analysis.seasonality as seasonality_module

# Import functions directly from module
analyze_monthly_seasonality = seasonality_module.analyze_monthly_seasonality
analyze_day_of_month_seasonality = seasonality_module.analyze_day_of_month_seasonality
analyze_day_of_week_seasonality = seasonality_module.analyze_day_of_week_seasonality
analyze_holiday_periods = seasonality_module.analyze_holiday_periods
analyze_quarter_seasonality = seasonality_module.analyze_quarter_seasonality
calculate_seasonal_trading_edge = seasonality_module.calculate_seasonal_trading_edge
analyze_specific_date = seasonality_module.analyze_specific_date
get_date_statistics = seasonality_module.get_date_statistics
from src.vix_analysis.seasonality_viz import (
    create_monthly_heatmap,
    create_monthly_box_plot,
    create_day_of_week_chart,
    create_holiday_periods_chart,
    create_spike_probability_by_month,
    create_day_of_month_chart,
    create_quarterly_comparison
)

# Page configuration
st.set_page_config(page_title="Seasonality Analytics", page_icon="📅", layout="wide")
apply_custom_css()

# Import sidebar to keep inputs visible
from src.vix_analysis.ui_components import render_sidebar_inputs
from src.vix_analysis.shared_state import set_shared_inputs

# Load VIX data
vix_data = load_vix_data()

# Render sidebar on this page too (to keep settings visible)
inputs = render_sidebar_inputs()
set_shared_inputs(inputs)

# =======================
# HEADER
# =======================
st.markdown('<div class="main-header">📅 Seasonality Analytics</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Historical patterns in VIX across different time periods</div>',
            unsafe_allow_html=True)
st.markdown("---")

# =======================
# OVERVIEW
# =======================
st.info("""
**Understanding VIX Seasonality:**

This page analyzes historical VIX behavior across different calendar periods to identify recurring patterns.
Seasonality can help you:
- Choose better entry timing for VIX call options
- Understand when VIX tends to spike or remain compressed
- Identify high-probability periods for volatility plays

**Data Range:** {start} to {end} ({days:,} trading days)
""".format(
    start=vix_data.index[0].strftime('%Y-%m-%d'),
    end=vix_data.index[-1].strftime('%Y-%m-%d'),
    days=len(vix_data)
))

st.markdown("---")

# =======================
# MONTHLY SEASONALITY
# =======================
st.subheader("📆 Monthly Seasonality")

st.markdown("""
Which months historically see higher or lower VIX levels? This section shows average VIX by month
and the probability of spikes occurring.
""")

monthly_stats = analyze_monthly_seasonality(vix_data)

# Create tabs for different views
tab1, tab2, tab3 = st.tabs(["📊 Statistics", "📈 Visualization", "🎯 Trading Edge"])

with tab1:
    st.markdown("### Monthly VIX Statistics")

    # Display table
    display_df = monthly_stats[['Month_Name', 'Mean', 'Median', 'Std Dev', 'Spike Prob (>20)', 'Extreme Prob (>30)']].copy()

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            'Month_Name': st.column_config.TextColumn('Month', width='medium'),
            'Mean': st.column_config.NumberColumn('Mean VIX', format="%.2f"),
            'Median': st.column_config.NumberColumn('Median VIX', format="%.2f"),
            'Std Dev': st.column_config.NumberColumn('Std Dev', format="%.2f"),
            'Spike Prob (>20)': st.column_config.NumberColumn('Spike % (>20)', format="%.1f%%"),
            'Extreme Prob (>30)': st.column_config.NumberColumn('Extreme % (>30)', format="%.1f%%")
        }
    )

    # Key insights
    highest_month = monthly_stats.loc[monthly_stats['Mean'].idxmax(), 'Month_Name']
    lowest_month = monthly_stats.loc[monthly_stats['Mean'].idxmin(), 'Month_Name']
    highest_spike_month = monthly_stats.loc[monthly_stats['Spike Prob (>20)'].idxmax(), 'Month_Name']

    st.success(f"""
    **Key Insights:**
    - **Highest avg VIX:** {highest_month} ({monthly_stats['Mean'].max():.2f})
    - **Lowest avg VIX:** {lowest_month} ({monthly_stats['Mean'].min():.2f})
    - **Most spike-prone:** {highest_spike_month} ({monthly_stats['Spike Prob (>20)'].max():.1f}% probability of VIX >20)
    """)

with tab2:
    st.markdown("### Average VIX by Month")
    fig_monthly = create_monthly_box_plot(monthly_stats)
    st.plotly_chart(fig_monthly, use_container_width=True)

    st.markdown("### Spike Probability by Month")
    fig_spike_prob = create_spike_probability_by_month(monthly_stats)
    st.plotly_chart(fig_spike_prob, use_container_width=True)

    st.markdown("### VIX Heatmap (Last 10 Years)")
    fig_heatmap = create_monthly_heatmap(vix_data)
    st.plotly_chart(fig_heatmap, use_container_width=True)

with tab3:
    st.markdown("### Best Months for VIX Call Entries")

    entry_vix = st.slider("Entry VIX Level", min_value=12.0, max_value=18.0, value=15.0, step=0.5)

    trading_edge = calculate_seasonal_trading_edge(vix_data, entry_vix=entry_vix)

    if len(trading_edge) > 0:
        st.markdown(f"""
        When VIX is at **{entry_vix}±1.0**, which months historically saw the best follow-through
        (VIX reaching 20+ within next 30 days)?
        """)

        st.dataframe(
            trading_edge[['Month_Name', 'Total Entries', 'Spikes', 'Spike Probability']],
            use_container_width=True,
            column_config={
                'Month_Name': st.column_config.TextColumn('Month'),
                'Total Entries': st.column_config.NumberColumn('Instances'),
                'Spikes': st.column_config.NumberColumn('Successes'),
                'Spike Probability': st.column_config.NumberColumn('Success Rate', format="%.1f%%")
            }
        )

        best_month = trading_edge.iloc[0]['Month_Name']
        best_prob = trading_edge.iloc[0]['Spike Probability']

        st.info(f"""
        **Best month for entries at VIX {entry_vix}:** {best_month} ({best_prob:.1f}% historical success rate)
        """)
    else:
        st.warning(f"No historical instances of VIX at {entry_vix}±1.0 found in the dataset")

st.markdown("---")

# =======================
# QUARTERLY SEASONALITY
# =======================
st.subheader("📊 Quarterly Patterns")

quarter_stats = analyze_quarter_seasonality(vix_data)

col1, col2 = st.columns([1, 2])

with col1:
    st.markdown("### Quarterly Statistics")
    display_quarter = quarter_stats[['Quarter_Name', 'Mean', 'Spike Prob (>20)']].copy()
    st.dataframe(
        display_quarter,
        use_container_width=True,
        hide_index=True,
        column_config={
            'Quarter_Name': st.column_config.TextColumn('Quarter'),
            'Mean': st.column_config.NumberColumn('Mean VIX', format="%.2f"),
            'Spike Prob (>20)': st.column_config.NumberColumn('Spike %', format="%.1f%%")
        }
    )

with col2:
    fig_quarter = create_quarterly_comparison(quarter_stats)
    st.plotly_chart(fig_quarter, use_container_width=True)

st.markdown("---")

# =======================
# DAY OF WEEK SEASONALITY
# =======================
st.subheader("📅 Day of Week Patterns")

st.markdown("""
Does VIX behave differently on different days of the week? This can help with entry/exit timing.
""")

dow_stats = analyze_day_of_week_seasonality(vix_data)

col1, col2 = st.columns([1, 2])

with col1:
    st.markdown("### Daily Statistics")
    display_dow = dow_stats[['Day', 'Mean', 'Avg Change %', 'Up Prob %']].copy()
    st.dataframe(
        display_dow,
        use_container_width=True,
        hide_index=True,
        column_config={
            'Day': st.column_config.TextColumn('Day of Week'),
            'Mean': st.column_config.NumberColumn('Avg VIX', format="%.2f"),
            'Avg Change %': st.column_config.NumberColumn('Avg Change', format="%.2f%%"),
            'Up Prob %': st.column_config.NumberColumn('Up Probability', format="%.1f%%")
        }
    )

    # Find best/worst days
    best_day = dow_stats.loc[dow_stats['Avg Change %'].idxmin(), 'Day']
    worst_day = dow_stats.loc[dow_stats['Avg Change %'].idxmax(), 'Day']

    st.info(f"""
    **Patterns:**
    - VIX tends to drop most on **{best_day}**
    - VIX tends to rise most on **{worst_day}**
    """)

with col2:
    fig_dow = create_day_of_week_chart(dow_stats)
    st.plotly_chart(fig_dow, use_container_width=True)

st.markdown("---")

# =======================
# DAY OF MONTH SEASONALITY
# =======================
st.subheader("📍 Day of Month Patterns")

st.markdown("""
Are there patterns within the month? For example, does VIX behave differently at month-end vs month-start?
""")

day_stats = analyze_day_of_month_seasonality(vix_data)

fig_day_of_month = create_day_of_month_chart(day_stats)
st.plotly_chart(fig_day_of_month, use_container_width=True)

# Identify patterns
first_week = day_stats.loc[1:7, 'Mean'].mean()
mid_month = day_stats.loc[11:20, 'Mean'].mean()
month_end = day_stats.loc[25:31, 'Mean'].mean()

st.info(f"""
**Month Period Comparison:**
- First week (days 1-7): Average VIX = {first_week:.2f}
- Mid-month (days 11-20): Average VIX = {mid_month:.2f}
- Month-end (days 25-31): Average VIX = {month_end:.2f}
""")

st.markdown("---")

# =======================
# HOLIDAY PERIODS
# =======================
st.subheader("🎄 Holiday Period Analysis")

st.markdown("""
VIX behavior during specific holiday periods and traditionally notable times of year.
""")

periods = analyze_holiday_periods(vix_data)

col1, col2 = st.columns([1, 2])

with col1:
    st.markdown("### Period Statistics")

    periods_df = pd.DataFrame(periods).T
    periods_df = periods_df.reset_index()
    periods_df.columns = ['Period', 'Mean VIX', 'Median VIX', 'Std Dev', 'Days', 'Spike Rate']

    st.dataframe(
        periods_df[['Period', 'Mean VIX', 'Spike Rate']],
        use_container_width=True,
        hide_index=True,
        column_config={
            'Period': st.column_config.TextColumn('Holiday Period'),
            'Mean VIX': st.column_config.NumberColumn('Avg VIX', format="%.2f"),
            'Spike Rate': st.column_config.NumberColumn('Spike Rate', format="%.1f%%")
        }
    )

with col2:
    fig_holidays = create_holiday_periods_chart(periods)
    st.plotly_chart(fig_holidays, use_container_width=True)

# Key insights
christmas_vix = periods['Christmas (Dec 20-31)']['Mean VIX']
fall_vix = periods['Fall (Sep-Oct)']['Mean VIX']

st.warning(f"""
**Holiday Insights:**
- **Christmas period** tends to have {"low" if christmas_vix < 16 else "elevated"} VIX (avg {christmas_vix:.2f})
- **Fall (Sep-Oct)** historically most volatile (avg {fall_vix:.2f})
- **Summer lull (Jul-Aug)** typically sees compressed volatility
""")

st.markdown("---")

# =======================
# SUMMARY & RECOMMENDATIONS
# =======================
st.subheader("💡 Seasonal Trading Insights")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🟢 Best Times for VIX Call Entries")

    # Find months with lowest avg VIX (good for entries)
    low_vix_months = monthly_stats.nsmallest(3, 'Mean')['Month_Name'].values
    high_spike_months = monthly_stats.nlargest(3, 'Spike Prob (>20)')['Month_Name'].values

    st.success(f"""
    **Typically Low VIX Months:**
    - {', '.join(low_vix_months)}

    **Most Spike-Prone Months:**
    - {', '.join(high_spike_months)}

    **Strategy:** Enter VIX calls when VIX is low in historically calm months,
    targeting exits during historically volatile months.
    """)

with col2:
    st.markdown("### ⚠️ High Risk Periods")

    high_vix_months = monthly_stats.nlargest(3, 'Mean')['Month_Name'].values

    st.warning(f"""
    **Historically High VIX Months:**
    - {', '.join(high_vix_months)}

    **Caution:** These months tend to already have elevated VIX.
    Entering VIX calls when VIX is already high can be risky due to
    mean reversion back to lower levels.

    **Better Strategy:** Use these periods to take profits on existing positions.
    """)

st.markdown("---")

# =======================
# SPECIFIC DATE LOOKUP
# =======================
st.subheader("📍 Specific Date Lookup")

st.markdown("""
Look up VIX behavior on a specific calendar date across all years of history.
For example, see what happened on every December 15th, or every January 2nd.
""")

col1, col2 = st.columns(2)

with col1:
    lookup_month = st.selectbox(
        "Select Month",
        options=list(range(1, 13)),
        format_func=lambda x: ['January', 'February', 'March', 'April', 'May', 'June',
                                'July', 'August', 'September', 'October', 'November', 'December'][x-1],
        index=11  # Default to December
    )

with col2:
    lookup_day = st.selectbox(
        "Select Day",
        options=list(range(1, 32)),
        index=14  # Default to 15th
    )

month_name = ['January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December'][lookup_month-1]

if st.button("🔍 Analyze This Date", type="primary"):
    st.markdown(f"### Historical VIX Data for {month_name} {lookup_day}")

    specific_date_df = analyze_specific_date(vix_data, lookup_month, lookup_day)

    if len(specific_date_df) > 0:
        # Get statistics
        stats = get_date_statistics(specific_date_df)

        # Display summary stats
        st.markdown("#### 📊 Summary Statistics")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Years", f"{stats['Total Instances']}")
            st.metric("Avg VIX", f"{stats['Avg VIX']:.2f}")

        with col2:
            st.metric("Median VIX", f"{stats['Median VIX']:.2f}")
            st.metric("Range", f"{stats['Min VIX']:.1f} - {stats['Max VIX']:.1f}")

        with col3:
            st.metric("Avg 1-Day Chg", f"{stats['Avg 1D Change %']:.2f}%")
            st.metric("Avg 5-Day Chg", f"{stats['Avg 5D Change %']:.2f}%")

        with col4:
            st.metric("Avg 20-Day Chg", f"{stats['Avg 20D Change %']:.2f}%")
            st.metric("Spike Rate (30D)", f"{stats['Spike Rate (>20 in 30D)']:.1f}%")

        st.markdown("---")

        # Display detailed data
        st.markdown("#### 📅 Year-by-Year Historical Data")

        display_cols = ['Year', 'VIX', '1D Change %', '5D Change %', '20D Change %', 'Max 30D Change %', 'Spiked >20']

        st.dataframe(
            specific_date_df[display_cols].sort_values('Year', ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                'Year': st.column_config.NumberColumn('Year', format="%d"),
                'VIX': st.column_config.NumberColumn('VIX Level', format="%.2f"),
                '1D Change %': st.column_config.NumberColumn('1-Day Change', format="%.2f%%"),
                '5D Change %': st.column_config.NumberColumn('5-Day Change', format="%.2f%%"),
                '20D Change %': st.column_config.NumberColumn('20-Day Change', format="%.2f%%"),
                'Max 30D Change %': st.column_config.NumberColumn('Max 30D Gain', format="%.2f%%"),
                'Spiked >20': st.column_config.CheckboxColumn('Spiked >20?')
            }
        )

        # Key insights
        st.markdown("#### 💡 Key Insights")

        # Find best and worst years
        best_year = specific_date_df.loc[specific_date_df['20D Change %'].idxmax()]
        worst_year = specific_date_df.loc[specific_date_df['20D Change %'].idxmin()]

        col1, col2 = st.columns(2)

        with col1:
            st.success(f"""
            **Best Performance (20-day forward):**
            - Year: {int(best_year['Year'])}
            - VIX on {month_name} {lookup_day}: {best_year['VIX']:.2f}
            - 20-day change: {best_year['20D Change %']:.1f}%
            - Max spike in 30D: {best_year['Max 30D Change %']:.1f}%
            """)

        with col2:
            st.error(f"""
            **Worst Performance (20-day forward):**
            - Year: {int(worst_year['Year'])}
            - VIX on {month_name} {lookup_day}: {worst_year['VIX']:.2f}
            - 20-day change: {worst_year['20D Change %']:.1f}%
            """)

        # Pattern insights
        positive_rate_1d = stats['Positive 1D %']
        positive_rate_20d = stats['Positive 20D %']

        if positive_rate_20d > 60:
            pattern = "🟢 **Bullish Pattern**: VIX tends to rise after this date"
        elif positive_rate_20d < 40:
            pattern = "🔴 **Bearish Pattern**: VIX tends to fall after this date"
        else:
            pattern = "⚪ **Neutral Pattern**: No clear directional bias"

        st.info(f"""
        **Pattern Analysis for {month_name} {lookup_day}:**

        {pattern}

        - {positive_rate_1d:.0f}% of years saw VIX rise the next day
        - {stats['Positive 5D %']:.0f}% of years saw VIX rise over next 5 days
        - {positive_rate_20d:.0f}% of years saw VIX rise over next 20 days
        - {stats['Spike Rate (>20 in 30D)']:.0f}% of years saw VIX spike above 20 within 30 days
        """)

    else:
        st.warning(f"No historical data found for {month_name} {lookup_day}")

st.markdown("---")

st.caption("""
**Note:** Seasonality patterns are based on historical data and do not guarantee future results.
Market structure, macro conditions, and geopolitical events can override seasonal patterns.
Use seasonality as one factor among many in your analysis.
""")
