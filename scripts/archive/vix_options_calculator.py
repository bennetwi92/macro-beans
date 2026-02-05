"""
VIX Options Trade Calculator
=============================
Interactive Streamlit calculator for VIX call option trades.
Models premium expansion, probability of success, and expected value.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import yfinance as yf

# Page config
st.set_page_config(
    page_title="VIX Options Calculator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .metric-positive {
        color: #28a745;
        font-weight: bold;
        font-size: 1.5rem;
    }
    .metric-negative {
        color: #dc3545;
        font-weight: bold;
        font-size: 1.5rem;
    }
    .metric-neutral {
        color: #ffc107;
        font-weight: bold;
        font-size: 1.5rem;
    }
    </style>
""", unsafe_allow_html=True)

# Fetch historical VIX data for probability analysis
@st.cache_data(ttl=3600)
def fetch_vix_historical():
    """Fetch VIX data for probability calculations"""
    vix = yf.download("^VIX", start="2004-01-01", end=datetime.now(), progress=False)[['Close']]
    vix.columns = ['VIX']
    return vix

def assign_recency_weight(date):
    """Assign weight based on how recent the data is"""
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
    """Calculate historical probability of VIX reaching target from entry level"""

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
    """Calculate probability of VIX dropping below entry level (recency-weighted)"""

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

def calculate_option_value(current_vix, strike, days_to_expiry, iv_multiplier=1.0):
    """
    Simplified option pricing model based on VIX level and time
    This is a rough approximation focusing on extrinsic value
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
    """Calculate option value after theta decay"""

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
    """Simulate different VIX spike scenarios"""

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

def main():
    # Header
    st.markdown('<div class="main-header">📊 VIX Call Options Calculator</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Model premium expansion from low volatility environment</div>', unsafe_allow_html=True)

    st.markdown("---")

    # Fetch historical data
    vix_data = fetch_vix_historical()
    current_vix = vix_data['VIX'].iloc[-1]

    # Sidebar inputs
    st.sidebar.title("⚙️ Trade Parameters")

    st.sidebar.markdown("### Contract Details")

    contract_choice = st.sidebar.radio(
        "Select Contract",
        ["January (36 DTE) - $1.00", "February (64 DTE) - $1.30", "Custom"]
    )

    if "January" in contract_choice:
        entry_premium = 1.00
        dte = 36
    elif "February" in contract_choice:
        entry_premium = 1.30
        dte = 64
    else:
        entry_premium = st.sidebar.number_input("Entry Premium ($)", value=1.00, min_value=0.10, max_value=10.0, step=0.05)
        dte = st.sidebar.number_input("Days to Expiration", value=45, min_value=7, max_value=180, step=1)

    strike = st.sidebar.number_input("Strike Price", value=20.0, min_value=15.0, max_value=35.0, step=0.5)

    num_contracts = st.sidebar.number_input("Number of Contracts", value=1, min_value=1, max_value=20, step=1)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Greeks (Optional)")
    st.sidebar.caption("Enter actual Greeks from your options chain for more accurate projections")

    use_greeks = st.sidebar.checkbox("Use Actual Greeks", value=False)

    if use_greeks:
        st.sidebar.info("""
        **How to find Greeks:**
        1. Look at your broker's options chain
        2. Find your strike/expiry
        3. Look for "Greeks" column
        4. Enter Theta and Vega here

        **Examples:**
        - Theta: -0.020 (lose $2/day)
        - Vega: 0.12 (gain $12 per 1% IV rise)
        """)

        theta_greek = st.sidebar.number_input("Theta (Daily)", value=-0.020, min_value=-0.10, max_value=0.0, step=0.001, format="%.3f",
                                              help="Negative value (e.g., -0.020 = lose $2/day)")
        vega_greek = st.sidebar.number_input("Vega", value=0.120, min_value=0.0, max_value=0.50, step=0.001, format="%.3f",
                                             help="Gain per 1% IV increase (e.g., 0.120 = $12 gain per 1% IV)")

        st.sidebar.caption(f"📉 Daily decay: ${abs(theta_greek)*100:.2f}")
        st.sidebar.caption(f"📈 IV sensitivity: ${vega_greek*100:.3f} per 1% IV")

        st.sidebar.success("✅ Using actual Greeks for precise calculations")
    else:
        theta_greek = None
        vega_greek = None
        st.sidebar.caption("Using estimated decay model")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Market Assumptions")

    entry_vix = st.sidebar.number_input("Entry VIX Level", value=15.75, min_value=10.0, max_value=25.0, step=0.25)

    target_vix = st.sidebar.number_input("Target VIX Level", value=20.0, min_value=15.0, max_value=40.0, step=0.5)

    if not use_greeks:
        theta_decay_monthly = st.sidebar.slider("Monthly Theta Decay (%)", min_value=20, max_value=50, value=35, step=5) / 100
    else:
        theta_decay_monthly = None  # Will use theta_greek instead

    analysis_window = st.sidebar.number_input("Analysis Window (days)", value=60, min_value=7, max_value=180, step=7,
                                              help="How far forward to look for VIX spike probability")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Exit Strategy")

    profit_target = st.sidebar.slider("Profit Target (%)", min_value=50, max_value=500, value=150, step=25)
    stop_loss = st.sidebar.slider("Stop Loss (%)", min_value=-80, max_value=-20, value=-50, step=5)

    # Calculate probability
    spike_prob, total_instances, days_to_spike_list = calculate_spike_probability(
        vix_data, entry_vix, target_vix, analysis_window
    )

    # Main content
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Current VIX", f"{current_vix:.2f}")

    with col2:
        st.metric("Entry VIX", f"{entry_vix:.2f}")

    with col3:
        st.metric("Target VIX", f"{target_vix:.2f}",
                 delta=f"+{target_vix - entry_vix:.2f}")

    with col4:
        position_cost = entry_premium * 100 * num_contracts  # Options are $100 multiplier
        st.metric("Position Cost", f"${position_cost:,.0f}")

    st.markdown("---")

    # Show Greeks info if being used
    if use_greeks:
        st.info(f"""
        ✅ **Using Actual Greeks for Calculations**
        - Theta: {theta_greek:.3f} (${abs(theta_greek)*100:.2f}/day decay)
        - Vega: {vega_greek:.3f} (${vega_greek*100:.3f} gain per 1% IV increase)

        These values from your options chain will provide more accurate projections than estimated models.
        """)

    # Probability Analysis
    st.subheader("📈 Probability Analysis")

    col1, col2, col3 = st.columns(3)

    with col1:
        prob_color = "metric-positive" if spike_prob > 0.5 else "metric-neutral" if spike_prob > 0.3 else "metric-negative"
        st.markdown(f'<p class="{prob_color}">{spike_prob*100:.1f}%</p>', unsafe_allow_html=True)
        st.caption(f"Probability VIX reaches {target_vix:.0f} within {analysis_window} days")
        st.caption(f"Based on {total_instances} historical instances")

    with col2:
        if len(days_to_spike_list) > 0:
            median_days = np.median(days_to_spike_list)
            st.markdown(f'<p class="metric-neutral">{median_days:.0f} days</p>', unsafe_allow_html=True)
            st.caption(f"Median time to reach {target_vix:.0f}")
            st.caption(f"Range: {min(days_to_spike_list)} - {max(days_to_spike_list)} days")
        else:
            st.markdown('<p class="metric-negative">N/A</p>', unsafe_allow_html=True)
            st.caption("No historical spikes found")

    with col3:
        # Calculate inverse probability (no spike)
        no_spike_prob = 1 - spike_prob
        decay_at_expiry = calculate_theta_decay(entry_premium, dte, dte, theta_decay_monthly)
        expected_loss_if_no_spike = (decay_at_expiry - entry_premium) / entry_premium * 100

        st.markdown(f'<p class="metric-negative">{no_spike_prob*100:.1f}%</p>', unsafe_allow_html=True)
        st.caption(f"Probability of NO spike")
        st.caption(f"Est. loss: {expected_loss_if_no_spike:.0f}%")

    # Visual probability distribution
    if len(days_to_spike_list) > 0:
        st.markdown("### Time to Spike Distribution")

        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=days_to_spike_list,
            nbinsx=20,
            name='Historical Spikes',
            marker_color='steelblue'
        ))

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

        st.plotly_chart(fig_hist, use_container_width=True)

    st.markdown("---")

    # Scenario Analysis
    st.subheader("🎯 Scenario Analysis")

    # Generate scenarios
    target_levels = [18, 20, 22, 25, 30]
    scenarios_df = simulate_scenarios(entry_vix, strike, entry_premium, dte,
                                      spike_prob, theta_decay_monthly,
                                      target_levels, days_to_spike_list,
                                      theta_greek, vega_greek)

    # Display scenario table
    st.markdown("### Potential Outcomes")

    # Format for display
    display_df = scenarios_df.copy()
    display_df['VIX Level'] = display_df['target_vix'].apply(lambda x: f"{x:.0f}")
    display_df['VIX Move'] = display_df['vix_move_pct'].apply(lambda x: f"{x:+.1f}%")
    display_df['Days'] = display_df['days_to_target'].astype(int)
    display_df['Option Value'] = display_df['option_value'].apply(lambda x: f"${x:.2f}")
    display_df['Gain/Loss'] = display_df['gain_pct'].apply(lambda x: f"{x:+.1f}%")
    display_df['P&L ($)'] = (display_df['gain_pct'] / 100 * position_cost).apply(lambda x: f"${x:+,.0f}")

    display_cols = ['VIX Level', 'VIX Move', 'Days', 'Option Value', 'Gain/Loss', 'P&L ($)']

    # Color code the dataframe
    def color_gain(val):
        if 'Decay' in str(val):
            return 'background-color: #fff3cd'
        return ''

    def color_numeric(val):
        try:
            num = float(val.replace('$', '').replace(',', '').replace('%', '').replace('+', ''))
            if num > 0:
                return 'background-color: #d4edda; color: #155724'
            elif num < 0:
                return 'background-color: #f8d7da; color: #721c24'
        except:
            pass
        return ''

    styled_df = display_df[display_cols].style.applymap(color_numeric, subset=['Gain/Loss', 'P&L ($)'])

    st.dataframe(styled_df, use_container_width=True)

    # Key scenarios highlight
    st.markdown("### Key Scenarios")

    col1, col2, col3 = st.columns(3)

    # Best realistic case (VIX 20)
    vix_20_scenario = scenarios_df[scenarios_df['target_vix'] == 20].iloc[0] if len(scenarios_df[scenarios_df['target_vix'] == 20]) > 0 else None

    if vix_20_scenario is not None:
        with col1:
            st.markdown("**🎯 Conservative Target (VIX 20)**")
            gain_20 = vix_20_scenario['gain_pct']
            pnl_20 = gain_20 / 100 * position_cost
            st.metric("Return", f"{gain_20:+.1f}%", delta=f"${pnl_20:+,.0f}")
            st.caption(f"If VIX reaches {target_vix:.0f} in ~{vix_20_scenario['days_to_target']:.0f} days")
            st.caption(f"Historical probability: {spike_prob*100:.1f}%")

    # Aggressive case (VIX 25)
    vix_25_scenario = scenarios_df[scenarios_df['target_vix'] == 25].iloc[0] if len(scenarios_df[scenarios_df['target_vix'] == 25]) > 0 else None

    if vix_25_scenario is not None:
        with col2:
            st.markdown("**🚀 Aggressive Target (VIX 25)**")
            gain_25 = vix_25_scenario['gain_pct']
            pnl_25 = gain_25 / 100 * position_cost
            st.metric("Return", f"{gain_25:+.1f}%", delta=f"${pnl_25:+,.0f}")

            # Calculate probability for VIX 25
            prob_25, _, _ = calculate_spike_probability(vix_data, entry_vix, 25, analysis_window)
            st.caption(f"If VIX reaches 25 in ~{vix_25_scenario['days_to_target']:.0f} days")
            st.caption(f"Historical probability: {prob_25*100:.1f}%")

    # Decay case
    decay_scenario = scenarios_df[scenarios_df['vix_move'] == 0].iloc[0]

    with col3:
        st.markdown(f"**📉 No Spike (Decay to expiry)**")
        gain_decay = decay_scenario['gain_pct']
        pnl_decay = gain_decay / 100 * position_cost
        st.metric("Return", f"{gain_decay:+.1f}%", delta=f"${pnl_decay:+,.0f}")
        st.caption(f"If VIX stays at {entry_vix:.2f}")
        st.caption(f"Historical probability: {(1-spike_prob)*100:.1f}%")

    st.markdown("---")

    # Expected Value Calculation
    st.subheader("💰 Expected Value Analysis")

    # Calculate EV
    ev_gain = spike_prob * (vix_20_scenario['gain_pct'] if vix_20_scenario is not None else 0)
    ev_loss = (1 - spike_prob) * decay_scenario['gain_pct']
    ev_total = ev_gain + ev_loss
    ev_dollars = ev_total / 100 * position_cost

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Expected Return", f"{ev_total:+.1f}%")

    with col2:
        st.metric("Expected P&L", f"${ev_dollars:+,.0f}")

    with col3:
        win_amount = vix_20_scenario['gain_pct'] if vix_20_scenario is not None else 0
        loss_amount = abs(decay_scenario['gain_pct'])
        risk_reward = win_amount / loss_amount if loss_amount > 0 else 0
        st.metric("Risk/Reward", f"{risk_reward:.2f}x")

    with col4:
        break_even_prob = loss_amount / (win_amount + loss_amount) if (win_amount + loss_amount) > 0 else 0
        st.metric("Breakeven Prob", f"{break_even_prob*100:.1f}%")

    # EV interpretation
    if ev_total > 20:
        st.success(f"✅ **Positive Expected Value**: This trade has a {ev_total:+.1f}% expected return, suggesting favorable odds.")
    elif ev_total > 0:
        st.info(f"⚠️ **Slightly Positive EV**: Expected return is {ev_total:+.1f}%, proceed with caution.")
    else:
        st.warning(f"❌ **Negative Expected Value**: Expected return is {ev_total:+.1f}%, unfavorable odds based on historical data.")

    st.markdown("---")

    # Time Decay Visualization
    st.subheader("📉 Theta Decay Over Time")

    days_array = np.arange(0, dte + 1)

    # Decay only scenario
    decay_values = [calculate_theta_decay(entry_premium, d, dte, theta_decay_monthly, theta_greek) for d in days_array]

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

    st.plotly_chart(fig_decay, use_container_width=True)

    st.markdown("---")

    # Downside Risk Analysis
    st.subheader("⚠️ Downside Risk & Stop Loss Analysis")

    st.markdown("""
    **Recency-weighted analysis** (last 1-5 years weighted more heavily):
    - Last 1 year: 3x weight
    - Last 3 years: 2x weight
    - Last 5 years: 1.5x weight
    - Older data: 1x weight
    """)

    # Calculate downside probabilities
    downside_probs = calculate_downside_risk(vix_data, entry_vix, dte)

    # Display downside risk table
    st.markdown(f"### Probability VIX Drops Below Levels ({dte} days)")

    downside_data = []
    for drop_pct in sorted(downside_probs.keys()):
        stop_vix = entry_vix * (1 - drop_pct/100)
        prob = downside_probs[drop_pct]

        if prob < 10:
            risk = "✅ Low"
            color = "green"
        elif prob < 20:
            risk = "⚠️ Moderate"
            color = "orange"
        else:
            risk = "🔴 High"
            color = "red"

        downside_data.append({
            'Stop Level': f'-{drop_pct}%',
            'VIX Level': f'{stop_vix:.2f}',
            'Probability': f'{prob:.1f}%',
            'Risk': risk,
            'Loss on $100': f'${drop_pct:.0f}'
        })

    downside_df = pd.DataFrame(downside_data)
    st.dataframe(downside_df, use_container_width=True, hide_index=True)

    # Recommend stop loss
    st.markdown("### 💡 Stop Loss Recommendations")

    col1, col2 = st.columns(2)

    # Find recommended stops
    conservative_stop = None
    balanced_stop = None

    for drop_pct in sorted(downside_probs.keys()):
        prob = downside_probs[drop_pct]
        if prob < 10 and conservative_stop is None:
            conservative_stop = (drop_pct, entry_vix * (1 - drop_pct/100), prob)
        if prob < 20 and balanced_stop is None:
            balanced_stop = (drop_pct, entry_vix * (1 - drop_pct/100), prob)

    with col1:
        if balanced_stop:
            st.success(f"""
            **⭐ Recommended: -{balanced_stop[0]}% Stop**
            - Stop at VIX {balanced_stop[1]:.2f}
            - Probability: {balanced_stop[2]:.1f}%
            - Loss: ${position_cost * balanced_stop[0]/100:.0f}
            - Good balance of protection & room
            """)
        else:
            st.info("No balanced stop found with <20% probability")

    with col2:
        if conservative_stop:
            st.info(f"""
            **Loose Stop: -{conservative_stop[0]}% Stop**
            - Stop at VIX {conservative_stop[1]:.2f}
            - Probability: {conservative_stop[2]:.1f}%
            - Loss: ${position_cost * conservative_stop[0]/100:.0f}
            - Maximum breathing room
            """)
        else:
            st.warning("VIX at very low levels - limited downside room")

    st.warning("""
    **⚠️ Spread Considerations:**
    - VIX options have WIDE bid-ask spreads ($0.20-0.50)
    - Tighter stops = more slippage from spreads
    - Consider: Use mental stop, only exit on close below level
    - Don't panic on intraday dips
    """)

    # Chart downside probabilities
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

    st.plotly_chart(fig_downside, use_container_width=True)

    st.markdown("---")

    # Trade Recommendation
    st.subheader("📋 Trade Summary & Recommendation")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Trade Setup")
        st.write(f"**Contract**: VIX ${strike:.0f} Call")
        st.write(f"**Expiration**: {dte} days")
        st.write(f"**Entry Premium**: ${entry_premium:.2f}")
        st.write(f"**Contracts**: {num_contracts}")
        st.write(f"**Total Cost**: ${position_cost:,.0f}")
        st.write(f"**Max Loss**: ${position_cost:,.0f} (-100%)")

    with col2:
        st.markdown("### Historical Context")
        st.write(f"**Entry VIX**: {entry_vix:.2f}")
        st.write(f"**Target VIX**: {target_vix:.2f} (+{(target_vix-entry_vix)/entry_vix*100:.1f}%)")
        st.write(f"**Success Probability**: {spike_prob*100:.1f}%")
        st.write(f"**Sample Size**: {total_instances} instances")
        if len(days_to_spike_list) > 0:
            st.write(f"**Median Time to Spike**: {np.median(days_to_spike_list):.0f} days")
        st.write(f"**Expected Value**: {ev_total:+.1f}%")

    # Final recommendation
    st.markdown("### 💡 Recommendation")

    if spike_prob >= 0.5 and ev_total > 20:
        st.success("""
        ✅ **HIGH PROBABILITY SETUP**

        This trade has favorable odds based on historical data:
        - High probability of VIX reaching target
        - Positive expected value
        - Reasonable risk/reward ratio

        **Action Plan:**
        1. Enter position when VIX remains below 16
        2. Set alerts for VIX reaching 18, 20, 22
        3. Take profits at 150-200% gain
        4. Cut losses at -50% if no movement by day 30
        """)
    elif spike_prob >= 0.35 and ev_total > 0:
        st.info("""
        ⚠️ **MODERATE PROBABILITY SETUP**

        This trade has mixed signals:
        - Moderate probability of success
        - Slightly positive expected value
        - Consider smaller position size

        **Action Plan:**
        1. Consider half position or wait for better entry
        2. Be prepared for theta decay
        3. Take profits quickly if VIX spikes
        4. Have strict stop loss discipline
        """)
    else:
        st.warning("""
        ❌ **LOW PROBABILITY SETUP**

        This trade has unfavorable odds:
        - Low historical probability of reaching target
        - Negative or low expected value
        - High risk of theta decay

        **Recommendation:**
        - Wait for better entry (lower VIX)
        - Consider different strike or expiration
        - Or skip this trade entirely
        """)

    # Educational note
    st.markdown("---")
    st.markdown("### 📚 Important Notes")

    st.markdown("""
    **This calculator models premium expansion, not expiration value:**
    - VIX spikes are brief (median 5-7 days elevated)
    - Profit comes from selling when IV expands, NOT holding to expiration
    - Exit within 1-3 days of VIX peak
    - Theta decay is your enemy - trade needs to work quickly

    **Historical probability is based on:**
    - ~20 years of VIX data (2004-present)
    - Actual instances where VIX was at your entry level
    - Looking forward to see if target was reached within timeframe
    - Past performance does not guarantee future results

    **Risk Factors:**
    - VIX can stay compressed for months (2017, 2024)
    - Theta decay accelerates as expiration approaches
    - Market regime changes can alter VIX behavior
    - Single contract = defined risk but high concentration
    """)

if __name__ == "__main__":
    main()
