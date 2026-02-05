"""
Probability & Scenarios Page
=============================
Detailed probability analysis and scenario modeling.
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.vix_analysis import create_spike_histogram
from src.vix_analysis.shared_state import (
    get_shared_inputs,
    get_calculated_data,
    apply_custom_css,
    format_currency,
    format_percentage
)

# Page configuration
st.set_page_config(page_title="Probability & Scenarios", page_icon="📈", layout="wide")
apply_custom_css()

# Import sidebar to keep inputs visible
from src.vix_analysis.ui_components import render_sidebar_inputs
from src.vix_analysis.shared_state import set_shared_inputs, load_vix_data
from src.vix_analysis import calculate_spike_probability, calculate_downside_risk, simulate_scenarios

# Render sidebar on this page too
vix_data = load_vix_data()
inputs = render_sidebar_inputs()
set_shared_inputs(inputs)

# Recalculate data with current inputs
entry_premium = inputs['entry_premium']
dte = inputs['dte']
strike = inputs['strike']
num_contracts = inputs['num_contracts']
entry_vix = inputs['entry_vix']
target_vix = inputs['target_vix']
analysis_window = inputs['analysis_window']
theta_decay_monthly = inputs['theta_decay_monthly']
theta_greek = inputs['theta_greek']
vega_greek = inputs['vega_greek']

spike_prob, total_instances, days_to_spike_list = calculate_spike_probability(
    vix_data, entry_vix, target_vix, analysis_window
)

target_levels = [18, 20, 22, 25, 30]
scenarios_df = simulate_scenarios(
    entry_vix, strike, entry_premium, dte, spike_prob,
    theta_decay_monthly, target_levels, days_to_spike_list,
    theta_greek, vega_greek
)

downside_probs = calculate_downside_risk(vix_data, entry_vix, dte)
spike_scenarios = scenarios_df[scenarios_df['vix_move'] > 0].copy()

if len(spike_scenarios) > 0:
    prob_per_scenario = spike_prob / len(spike_scenarios)
    no_spike_prob = 1 - spike_prob
    spike_scenarios['scenario_prob'] = prob_per_scenario
    spike_scenarios['ev_contribution'] = (
        spike_scenarios['scenario_prob'] *
        (spike_scenarios['option_value'] - entry_premium) * 100 * num_contracts
    )
    spike_ev = spike_scenarios['ev_contribution'].sum()
    decay_scenario = scenarios_df[scenarios_df['vix_move'] == 0].iloc[0]
    decay_ev = no_spike_prob * (decay_scenario['option_value'] - entry_premium) * 100 * num_contracts
    total_ev = spike_ev + decay_ev
else:
    total_ev = 0
    spike_ev = 0
    decay_ev = 0

position_cost = entry_premium * 100 * num_contracts

calculated_data = {
    'spike_prob': spike_prob,
    'total_instances': total_instances,
    'days_to_spike_list': days_to_spike_list,
    'scenarios_df': scenarios_df,
    'downside_probs': downside_probs,
    'total_ev': total_ev,
    'spike_ev': spike_ev,
    'decay_ev': decay_ev,
    'position_cost': position_cost,
    'spike_scenarios': spike_scenarios
}

# Extract data
entry_premium = inputs['entry_premium']
entry_vix = inputs['entry_vix']
target_vix = inputs['target_vix']
num_contracts = inputs['num_contracts']
profit_target = inputs['profit_target']
stop_loss = inputs['stop_loss']
dte = inputs['dte']
analysis_window = inputs['analysis_window']

spike_prob = calculated_data['spike_prob']
total_instances = calculated_data['total_instances']
days_to_spike_list = calculated_data['days_to_spike_list']
scenarios_df = calculated_data['scenarios_df']
total_ev = calculated_data['total_ev']
spike_ev = calculated_data['spike_ev']
decay_ev = calculated_data['decay_ev']
position_cost = calculated_data['position_cost']

# =======================
# HEADER
# =======================
st.markdown('<div class="main-header">📈 Probability & Scenarios</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Historical analysis and outcome modeling</div>', unsafe_allow_html=True)
st.markdown("---")

# =======================
# PROBABILITY ANALYSIS
# =======================
st.subheader("🎯 Historical Spike Probability")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "Spike Probability",
        f"{spike_prob*100:.1f}%",
        help=f"Historical probability of VIX reaching {target_vix} from {entry_vix} within {analysis_window} days"
    )

with col2:
    if len(days_to_spike_list) > 0:
        median_days = int(pd.Series(days_to_spike_list).median())
        st.metric(
            "Median Days to Spike",
            f"{median_days} days",
            help="Historical median time to reach target VIX level"
        )
    else:
        st.metric("Median Days to Spike", "N/A")

with col3:
    st.metric(
        "Historical Instances",
        f"{total_instances}",
        help=f"Number of times VIX was at {entry_vix}±1.0 in historical data"
    )

st.markdown("---")

# =======================
# SPIKE TIMING DISTRIBUTION
# =======================
if len(days_to_spike_list) > 0:
    st.subheader("⏱️ Time to Spike Distribution")

    st.markdown(f"""
    When VIX was at **{entry_vix}±1.0** levels, here's how long it took to reach **{target_vix}**
    in historical instances that did spike:
    """)

    # Histogram
    fig_hist = create_spike_histogram(days_to_spike_list, dte)
    st.plotly_chart(fig_hist, use_container_width=True)

    # Statistics
    st.markdown("**📊 Detailed Statistics:**")
    spike_series = pd.Series(days_to_spike_list)

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Min Days", f"{spike_series.min():.0f}")
    with col2:
        st.metric("25th %ile", f"{spike_series.quantile(0.25):.0f}")
    with col3:
        st.metric("Median", f"{spike_series.median():.0f}")
    with col4:
        st.metric("75th %ile", f"{spike_series.quantile(0.75):.0f}")
    with col5:
        st.metric("Max Days", f"{spike_series.max():.0f}")

    # Interpretation
    if spike_series.median() < dte:
        st.success(f"""
        ✅ **Good timing alignment:** The median time to spike ({spike_series.median():.0f} days)
        is less than your DTE ({dte} days), giving you room for the move to happen.
        """)
    else:
        st.warning(f"""
        ⚠️ **Timing risk:** The median time to spike ({spike_series.median():.0f} days)
        is greater than your DTE ({dte} days). Consider longer-dated options.
        """)

else:
    st.warning(f"""
    ⚠️ **No historical instances** of VIX reaching {target_vix} from {entry_vix}
    within {analysis_window} days. Consider:
    - Lowering target VIX
    - Increasing analysis window
    - Choosing different entry level
    """)

st.markdown("---")

# =======================
# SCENARIO ANALYSIS
# =======================
st.subheader("💰 Potential Outcome Scenarios")

st.markdown(f"""
Below are modeled outcomes if VIX moves to various levels. Each scenario shows:
- Expected option value at that VIX level
- Your gain/loss percentage
- Total P&L on your {num_contracts} contract position
""")

# Format the dataframe for display
display_df = scenarios_df.copy()
display_df['Target VIX'] = display_df['target_vix'].apply(lambda x: f"{x:.1f}")
display_df['VIX Move'] = display_df['vix_move_pct'].apply(lambda x: f"+{x:.1f}%" if x > 0 else "0%")
display_df['Days'] = display_df['days_to_target'].astype(int)
display_df['Option Value'] = display_df['option_value'].apply(lambda x: f"${x:.2f}")
display_df['Gain/Loss'] = display_df['gain_pct'].apply(
    lambda x: f"+{x:.1f}%" if x > 0 else f"{x:.1f}%"
)
display_df['Position P&L'] = (scenarios_df['option_value'] - entry_premium) * 100 * num_contracts
display_df['Position P&L'] = display_df['Position P&L'].apply(
    lambda x: f"+${x:,.0f}" if x > 0 else f"-${abs(x):,.0f}"
)

# Highlight profitable scenarios - need to use the original scenarios_df for gain_pct
def highlight_profit(row):
    # Get the gain_pct from the original dataframe using the index
    gain_pct = scenarios_df.loc[row.name, 'gain_pct']
    if gain_pct > profit_target:
        return ['background-color: #d4edda'] * len(row)
    elif gain_pct < stop_loss:
        return ['background-color: #f8d7da'] * len(row)
    else:
        return [''] * len(row)

st.dataframe(
    display_df[['Target VIX', 'VIX Move', 'Days', 'Option Value', 'Gain/Loss', 'Position P&L', 'probability']].style.apply(highlight_profit, axis=1),
    use_container_width=True,
    hide_index=True
)

st.caption(f"""
🟢 Green = Hits {profit_target}% profit target |
🔴 Red = Hits {stop_loss}% stop loss |
⚪ White = Between target and stop
""")

st.markdown("---")

# =======================
# EXPECTED VALUE ANALYSIS
# =======================
st.subheader("📈 Expected Value Breakdown")

st.markdown(f"""
Expected Value (EV) is the probability-weighted average outcome. This accounts for both:
1. **Spike scenarios** ({spike_prob*100:.1f}% probability)
2. **Decay scenario** ({(1-spike_prob)*100:.1f}% probability)
""")

col1, col2, col3 = st.columns(3)

with col1:
    ev_pct = (total_ev / position_cost * 100) if position_cost > 0 else 0
    st.metric(
        "Total Expected Value",
        format_currency(total_ev),
        delta=format_percentage(ev_pct),
        help="Probability-weighted average outcome"
    )

with col2:
    st.metric(
        "Spike Scenarios EV",
        format_currency(spike_ev),
        help=f"Expected value if spike occurs ({spike_prob*100:.1f}% probability)"
    )

with col3:
    st.metric(
        "Decay Scenario EV",
        format_currency(decay_ev),
        delta=f"{(1-spike_prob)*100:.1f}% prob",
        help="Expected value if no spike (theta decay to expiration)"
    )

# Interpretation
if total_ev > 0:
    st.success(f"""
    ✅ **Positive Expected Value**

    This trade has a {spike_prob*100:.1f}% historical probability of the VIX spiking to your target.
    When you account for all scenarios (weighted by probability), the expected outcome is a
    gain of **{format_currency(total_ev)}** ({ev_pct:+.1f}%).

    This suggests the trade has a mathematical edge over many repetitions.
    """)
else:
    st.error(f"""
    ❌ **Negative Expected Value**

    Expected loss of **{format_currency(total_ev)}** ({ev_pct:.1f}%).

    The probability of success ({spike_prob*100:.1f}%) and potential gains do not overcome
    the probability of loss and theta decay. Consider:
    - Waiting for better entry conditions
    - Adjusting strike or expiration
    - Looking for higher probability setups
    """)

st.markdown("---")

# =======================
# PROBABILITY CONTEXT
# =======================
st.subheader("📊 Understanding the Probability")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**What does this probability mean?**")

    success_count = int(spike_prob * total_instances)
    fail_count = total_instances - success_count

    st.info(f"""
    Out of **{total_instances}** historical instances where VIX was at {entry_vix}±1.0:
    - ✅ **{success_count}** times ({spike_prob*100:.1f}%) VIX reached {target_vix} within {analysis_window} days
    - ❌ **{fail_count}** times ({(1-spike_prob)*100:.1f}%) it did not

    This is based on data since 2004.
    """)

with col2:
    st.markdown("**How to interpret this:**")

    if spike_prob >= 0.7:
        interpretation = "This is a **high probability** setup. Historically, this happens more than 70% of the time."
    elif spike_prob >= 0.5:
        interpretation = "This is a **coin flip to favorable** setup. Historically, this happens more than half the time."
    elif spike_prob >= 0.3:
        interpretation = "This is a **lower probability** setup. It happens, but less than half the time historically."
    else:
        interpretation = "This is a **low probability** setup. Historically, this is an uncommon occurrence."

    st.info(f"""
    {interpretation}

    Remember: Past performance doesn't guarantee future results, but it provides useful context
    for decision-making.
    """)

st.markdown("---")

# =======================
# FOOTER
# =======================
st.caption("💡 **Next:** Review Risk Analysis to understand downside scenarios and theta decay impact")
