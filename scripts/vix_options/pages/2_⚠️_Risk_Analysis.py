"""
Risk Analysis Page
==================
Theta decay visualization and downside risk analysis.
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.vix_analysis import create_theta_decay_chart, create_downside_chart
from src.vix_analysis.ui_components import render_downside_analysis
from src.vix_analysis.shared_state import (
    get_shared_inputs,
    get_calculated_data,
    apply_custom_css
)

# Page configuration
st.set_page_config(page_title="Risk Analysis", page_icon="⚠️", layout="wide")
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

downside_probs = calculate_downside_risk(vix_data, entry_vix, dte)
position_cost = entry_premium * 100 * num_contracts

calculated_data = {
    'spike_prob': spike_prob,
    'days_to_spike_list': days_to_spike_list,
    'downside_probs': downside_probs,
    'position_cost': position_cost
}

# Extract data
entry_premium = inputs['entry_premium']
entry_vix = inputs['entry_vix']
strike = inputs['strike']
dte = inputs['dte']
theta_decay_monthly = inputs['theta_decay_monthly']
theta_greek = inputs['theta_greek']
vega_greek = inputs['vega_greek']
use_greeks = inputs['use_greeks']
profit_target = inputs['profit_target']

days_to_spike_list = calculated_data['days_to_spike_list']
downside_probs = calculated_data['downside_probs']
position_cost = calculated_data['position_cost']

# =======================
# HEADER
# =======================
st.markdown('<div class="main-header">⚠️ Risk Analysis</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Understanding theta decay and downside risk</div>', unsafe_allow_html=True)
st.markdown("---")

# =======================
# THETA DECAY VISUALIZATION
# =======================
st.subheader("⏰ Theta Decay vs Spike Scenarios")

st.markdown("""
This chart shows the **race between theta decay and potential VIX spikes**. It illustrates:
- How your option value decays over time if VIX doesn't move (red dashed line)
- How your option value could increase if VIX spikes to different levels (colored lines)
- Your entry premium and profit target as reference lines
""")

fig_decay = create_theta_decay_chart(
    entry_premium, dte, theta_decay_monthly, theta_greek,
    entry_vix, strike, profit_target, days_to_spike_list
)
st.plotly_chart(fig_decay, use_container_width=True)

st.info("""
**📉 Reading This Chart:**
- **Red dashed line**: Pure theta decay (worst case - no VIX movement)
- **Colored lines**: Value if VIX spikes to 18, 20, or 25 at median historical timing
- **Black dotted line**: Your entry premium (break-even if you sell here)
- **Green dotted line**: Your profit target

**Key Insight:** You need VIX to spike before theta decay erodes too much value.
The spike timing matters as much as the spike magnitude!
""")

st.markdown("---")

# =======================
# THETA DECAY DETAILS
# =======================
st.subheader("📉 Theta Decay Impact")

if use_greeks and theta_greek is not None:
    daily_decay_dollars = abs(theta_greek) * 100  # Convert to dollars

    st.metric(
        "Daily Theta Decay",
        f"${daily_decay_dollars:.2f}",
        delta=f"{theta_greek:.3f} theta",
        help="Amount your option loses per day due to time decay"
    )

    # Calculate decay over different time periods
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        decay_7d = daily_decay_dollars * 7
        st.metric("7-Day Decay", f"${decay_7d:.0f}")

    with col2:
        decay_14d = daily_decay_dollars * 14
        st.metric("14-Day Decay", f"${decay_14d:.0f}")

    with col3:
        decay_30d = daily_decay_dollars * 30
        st.metric("30-Day Decay", f"${decay_30d:.0f}")

    with col4:
        decay_dte = daily_decay_dollars * dte
        st.metric(f"{dte}-Day Decay", f"${decay_dte:.0f}")

    st.success(f"""
    ✅ **Using Actual Theta** from your options chain (more accurate)

    At your current theta of **{theta_greek:.3f}**, you're losing **${daily_decay_dollars:.2f}/day**.

    Over {dte} days, theta decay alone would cost **${decay_dte:.0f}** if VIX doesn't move.
    This is why timing matters!
    """)

else:
    monthly_decay_pct = (theta_decay_monthly or 0.35) * 100

    st.metric(
        "Monthly Theta Decay",
        f"{monthly_decay_pct:.0f}%",
        help="Estimated monthly decay rate"
    )

    st.info(f"""
    **Using Estimated Decay Model** (consider entering actual Greeks for more accuracy)

    Estimated monthly decay: **{monthly_decay_pct:.0f}%**

    For more precise projections, enter actual Theta from your options chain in the sidebar.
    """)

st.markdown("---")

# =======================
# DOWNSIDE RISK ANALYSIS
# =======================
render_downside_analysis(downside_probs, entry_vix, dte, position_cost)

# Downside chart
st.markdown("### 📊 Downside Risk Visualization")

fig_downside = create_downside_chart(downside_probs, dte)
st.plotly_chart(fig_downside, use_container_width=True)

st.info("""
**Understanding Downside Risk:**

When VIX is already at low levels (like 15-16), there's limited room for it to fall further.
VIX rarely stays below 10 for extended periods.

**The chart above shows:**
- Probability of VIX dropping to various levels below your entry
- Based on recency-weighted historical data (last 1-5 years weighted more)
- Green bars = Low risk (<10% probability)
- Orange bars = Moderate risk (10-20% probability)
- Red bars = High risk (>20% probability)
""")

st.markdown("---")

# =======================
# RISK SUMMARY
# =======================
st.subheader("⚖️ Risk/Reward Summary")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Upside Potential:**")

    # Find best realistic scenario
    spike_scenarios = calculated_data['spike_scenarios']
    if len(spike_scenarios) > 0:
        # Use VIX 20 scenario as "realistic" target
        target_20_scenario = spike_scenarios[spike_scenarios['target_vix'] == 20]

        if len(target_20_scenario) > 0:
            target_gain_pct = target_20_scenario.iloc[0]['gain_pct']
            target_gain_dollars = (target_20_scenario.iloc[0]['option_value'] - entry_premium) * 100

            st.success(f"""
            **If VIX reaches 20:**
            - Gain: **{target_gain_pct:+.1f}%**
            - Dollar gain: **${target_gain_dollars:,.0f}**
            - Historical probability: **{calculated_data['spike_prob']*100:.1f}%**
            """)
        else:
            st.info("No VIX 20 scenario available")
    else:
        st.warning("No upside scenarios calculated")

with col2:
    st.markdown("**Downside Risk:**")

    # Find recommended stop
    balanced_stop = None
    for drop_pct in sorted(downside_probs.keys()):
        if downside_probs[drop_pct] < 20 and balanced_stop is None:
            balanced_stop = drop_pct
            break

    if balanced_stop:
        stop_dollars = position_cost * balanced_stop / 100
        stop_prob = downside_probs[balanced_stop]

        st.error(f"""
        **Recommended stop loss:**
        - Stop level: **-{balanced_stop}%**
        - Dollar loss: **${stop_dollars:,.0f}**
        - Probability of hitting: **{stop_prob:.1f}%**
        """)
    else:
        st.warning("VIX at extreme lows - very limited downside room")

st.markdown("---")

# =======================
# KEY RISKS
# =======================
st.subheader("🚨 Key Risk Factors")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Time Decay Risk**")

    st.warning("""
    ⏰ **Theta is your enemy**

    - Every day that passes without VIX spiking costs you money
    - Decay accelerates as you get closer to expiration
    - You need VIX to move relatively quickly

    **Mitigation:**
    - Don't hold too long if VIX isn't moving
    - Consider exiting if no movement in first 2 weeks
    - Use longer-dated options for more time
    """)

with col2:
    st.markdown("**Downside Risk**")

    st.warning("""
    📉 **VIX could drop further**

    - Although VIX is low, it can still compress more
    - Extended calm markets can grind VIX lower
    - Your option could lose value even from decay alone

    **Mitigation:**
    - Use recommended stop loss
    - Don't over-leverage this trade
    - VIX at 15 has limited downside (rarely <10)
    """)

st.markdown("---")

st.caption("💡 **Next:** Review Trade Plan for position sizing and execution strategy")
