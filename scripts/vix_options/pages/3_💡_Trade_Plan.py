"""
Trade Plan Page
===============
Position sizing, entry checklist, and exit strategy.
"""

import streamlit as st
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.vix_analysis.shared_state import (
    get_shared_inputs,
    get_calculated_data,
    apply_custom_css,
    format_currency
)

# Page configuration
st.set_page_config(page_title="Trade Plan", page_icon="💡", layout="wide")
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
num_contracts = inputs['num_contracts']
strike = inputs['strike']
dte = inputs['dte']
profit_target = inputs['profit_target']
entry_vix = inputs['entry_vix']

spike_prob = calculated_data['spike_prob']
position_cost = calculated_data['position_cost']
downside_probs = calculated_data['downside_probs']
spike_scenarios = calculated_data['spike_scenarios']

# Calculate cost per single contract for Kelly sizing
cost_per_contract = entry_premium * 100

# =======================
# HEADER
# =======================
st.markdown('<div class="main-header">💡 Trade Plan</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Position sizing, entry, and exit strategy</div>', unsafe_allow_html=True)
st.markdown("---")

# =======================
# POSITION SIZING
# =======================
st.subheader("📊 Position Sizing Recommendations")

st.markdown("""
Position sizing is critical for risk management. Here are recommendations based on your account size
and the Kelly Criterion (a mathematical framework for optimal bet sizing).
""")

# Find balanced stop loss
balanced_stop = None
for drop_pct in sorted(downside_probs.keys()):
    if downside_probs[drop_pct] < 20 and balanced_stop is None:
        balanced_stop = drop_pct
        break

if balanced_stop:
    recommended_stop_loss = -balanced_stop
    max_loss_per_contract = (entry_premium * 100) * (balanced_stop / 100)

    st.info(f"""
    **Recommended Stop Loss:** {recommended_stop_loss}%
    - Max loss per contract: ${max_loss_per_contract:,.0f}
    - Probability of hitting stop: {downside_probs[balanced_stop]:.1f}%
    """)

    # Kelly Criterion calculation
    if spike_prob > 0 and spike_prob < 1 and len(spike_scenarios) > 0:
        avg_gain = spike_scenarios['gain_pct'].mean() / 100
        avg_loss = abs(recommended_stop_loss) / 100

        if avg_gain > 0 and avg_loss > 0:
            win_rate = spike_prob
            kelly_fraction = (win_rate * avg_gain - (1 - win_rate) * avg_loss) / avg_gain
            kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%

            if kelly_fraction > 0:
                st.markdown("### 💰 Kelly Criterion Position Sizing")

                st.success(f"""
                **Full Kelly:** {kelly_fraction*100:.1f}% of trading capital

                This is the mathematically optimal bet size to maximize long-term growth,
                given the probabilities and payoffs.
                """)

                # Show sizing for different account sizes
                account_sizes = [10000, 25000, 50000, 100000]

                col1, col2, col3, col4 = st.columns(4)

                for i, (col, size) in enumerate(zip([col1, col2, col3, col4], account_sizes)):
                    with col:
                        full_kelly = size * kelly_fraction
                        half_kelly = full_kelly / 2
                        quarter_kelly = full_kelly / 4

                        num_contracts_full = int(full_kelly / cost_per_contract)
                        num_contracts_half = int(half_kelly / cost_per_contract)
                        num_contracts_quarter = int(quarter_kelly / cost_per_contract)

                        st.markdown(f"**${size:,} Account**")
                        st.metric("Full Kelly", f"{num_contracts_full} contracts")
                        st.caption(f"${full_kelly:,.0f}")
                        st.metric("1/2 Kelly", f"{num_contracts_half} contracts")
                        st.caption(f"${half_kelly:,.0f}")
                        st.metric("1/4 Kelly", f"{num_contracts_quarter} contracts")
                        st.caption(f"${quarter_kelly:,.0f}")

                st.warning("""
                ⚠️ **Important:** Many professional traders use **1/2 Kelly** or **1/4 Kelly** for more conservative sizing.
                Full Kelly can be aggressive and lead to large drawdowns.

                **Recommended approach:**
                - Conservative: Use 1/4 Kelly
                - Moderate: Use 1/2 Kelly
                - Aggressive: Use Full Kelly (not recommended for most traders)
                """)
            else:
                st.warning("Kelly calculation suggests zero position size (negative edge)")
    else:
        st.info("Unable to calculate Kelly sizing with current parameters")

else:
    st.warning("Unable to determine recommended stop loss at current VIX levels")

st.markdown("---")

# =======================
# ENTRY CHECKLIST
# =======================
st.subheader("✅ Entry Checklist")

st.markdown("""
Before entering this trade, confirm the following conditions are met:
""")

# Create checklist items
checklist_items = []

# 1. VIX level check
if entry_vix <= 16:
    checklist_items.append(("✅", f"VIX at low level ({entry_vix:.2f} ≤ 16)", True))
else:
    checklist_items.append(("⚠️", f"VIX not at ideal entry ({entry_vix:.2f} > 16)", False))

# 2. Probability check
if spike_prob >= 0.5:
    checklist_items.append(("✅", f"High probability setup ({spike_prob*100:.1f}% ≥ 50%)", True))
elif spike_prob >= 0.4:
    checklist_items.append(("⚠️", f"Moderate probability ({spike_prob*100:.1f}% ≥ 40%)", True))
else:
    checklist_items.append(("❌", f"Low probability setup ({spike_prob*100:.1f}% < 40%)", False))

# 3. DTE check
if dte >= 30:
    checklist_items.append(("✅", f"Sufficient time ({dte} days ≥ 30)", True))
else:
    checklist_items.append(("⚠️", f"Limited time ({dte} days < 30)", False))

# 4. Expected value check
total_ev = calculated_data['total_ev']
if total_ev > 0:
    checklist_items.append(("✅", f"Positive expected value ({format_currency(total_ev)})", True))
else:
    checklist_items.append(("❌", f"Negative expected value ({format_currency(total_ev)})", False))

# 5. Position sizing check
if balanced_stop:
    max_risk_pct = (position_cost * balanced_stop / 100) / position_cost * 100
    if max_risk_pct <= 2:
        checklist_items.append(("✅", "Position sized appropriately (risk ≤2% of account)", True))
    else:
        checklist_items.append(("⚠️", "Consider reducing position size", False))
else:
    checklist_items.append(("⚠️", "Review position sizing carefully", False))

# Display checklist
for emoji, text, status in checklist_items:
    if status:
        st.success(f"{emoji} {text}")
    else:
        st.warning(f"{emoji} {text}")

all_good = all(status for _, _, status in checklist_items)

if all_good:
    st.success("🎯 **All conditions met!** This setup looks favorable for entry.")
else:
    st.warning("⚠️ **Some conditions not met.** Review carefully before entering.")

st.markdown("---")

# =======================
# EXIT STRATEGY
# =======================
st.subheader("🎯 Exit Strategy")

st.markdown("### 💰 Profit Taking")

profit_target_value = entry_premium * (1 + profit_target/100)
profit_target_dollars = (profit_target_value - entry_premium) * 100 * num_contracts

st.info(f"""
**Primary Profit Target:** {profit_target}% gain

- Target option price: **${profit_target_value:.2f}**
- Total gain: **{format_currency(profit_target_dollars)}**

**Scaling Out Strategy:**
1. **Sell 50%** of position at {profit_target}% profit
2. **Let 50% run** with a trailing stop
3. **Don't hold for expiration** - VIX spikes are brief (5-7 days typically)

**Why scale out?**
- Locks in profits on half your position
- Lets you capture bigger moves if VIX keeps rising
- Reduces psychological pressure
""")

st.markdown("### 🛑 Stop Loss Strategy")

if balanced_stop:
    stop_vix = entry_vix * (1 - balanced_stop/100)
    stop_dollars = position_cost * balanced_stop / 100

    st.error(f"""
    **Recommended Stop Loss:** -{balanced_stop}%

    - Stop at VIX level: **{stop_vix:.2f}**
    - Maximum loss: **${stop_dollars:,.0f}**
    - Probability of hitting: **{downside_probs[balanced_stop]:.1f}%**

    **Implementation:**
    - Consider using a **mental stop** rather than hard stop due to wide spreads
    - Only exit on **close below** stop level (not intraday)
    - Don't panic on small intraday dips
    - VIX options have wide bid-ask spreads ($0.20-0.50)
    """)
else:
    st.warning("Set a maximum loss amount you're comfortable with")

st.markdown("### ⏰ Time-Based Exits")

st.warning(f"""
**Exit if VIX doesn't move within 2 weeks:**

If VIX hasn't shown movement toward your target within 14 days:
- Consider exiting to preserve capital
- Theta decay becomes increasingly painful
- Reassess whether the setup is still valid

**At 50% of DTE remaining ({int(dte/2)} days):**
- If still at entry level, strongly consider exiting
- Theta decay accelerates in final weeks
- Need significant movement to overcome decay
""")

st.markdown("---")

# =======================
# EXECUTION NOTES
# =======================
st.subheader("⚙️ Execution Tips")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Order Entry:**")

    st.info("""
    📋 **Best Practices:**

    - **Use limit orders**, never market orders
    - VIX options have WIDE spreads ($0.20-0.50)
    - Try to get filled closer to mid-price
    - Be patient - don't chase fills
    - Best liquidity during market hours (9:30-4:00 ET)
    - Avoid trading at open/close when spreads widen
    """)

with col2:
    st.markdown("**Position Monitoring:**")

    st.info(f"""
    📊 **Track These Metrics:**

    - Current VIX level vs entry ({entry_vix:.2f})
    - Days held vs median spike timing
    - Current P&L vs targets
    - VIX term structure (watch for backwardation)
    - Implied volatility of your option
    - Upcoming events that could spike VIX
    """)

st.markdown("---")

# =======================
# FINAL SUMMARY
# =======================
st.subheader("📋 Quick Reference")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**Position Details:**")
    st.info(f"""
    - Strike: ${strike}
    - DTE: {dte} days
    - Contracts: {num_contracts}
    - Entry: ${entry_premium:.2f}
    - Cost: ${position_cost:,.0f}
    """)

with col2:
    st.markdown("**Targets:**")
    st.success(f"""
    - Profit target: +{profit_target}%
    - Target price: ${profit_target_value:.2f}
    - Profit: {format_currency(profit_target_dollars)}
    """)

with col3:
    st.markdown("**Risk:**")
    if balanced_stop:
        st.error(f"""
        - Stop loss: -{balanced_stop}%
        - Max loss: ${stop_dollars:,.0f}
        - Exit if no move in 14d
        """)
    else:
        st.warning("Set your risk limits")

st.markdown("---")

st.success("""
🎯 **You're ready to execute!**

Remember:
1. Follow your plan
2. Don't overtrade
3. Use proper position sizing
4. Be patient with entries
5. Don't hesitate on exits

Good luck!
""")

st.markdown("---")
st.caption("💡 Return to Dashboard to modify parameters or review analysis")
