"""
VIX Options Calculator - Dashboard
===================================
Main dashboard page providing quick overview and trade verdict.

Run with: streamlit run scripts/vix_options_calculator.py
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vix_analysis import (
    calculate_spike_probability,
    calculate_downside_risk,
    simulate_scenarios
)
from src.vix_analysis.ui_components import render_sidebar_inputs
from src.vix_analysis.shared_state import (
    load_vix_data,
    get_shared_inputs,
    set_shared_inputs,
    set_calculated_data,
    apply_custom_css,
    format_currency,
    format_percentage
)


# Page configuration
st.set_page_config(
    page_title="VIX Options Calculator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

apply_custom_css()


def calculate_all_data(vix_data, inputs):
    """Calculate all analysis data and store in session state."""
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

    # Calculate spike probability
    spike_prob, total_instances, days_to_spike_list = calculate_spike_probability(
        vix_data, entry_vix, target_vix, analysis_window
    )

    # Calculate scenarios
    target_levels = [18, 20, 22, 25, 30]
    scenarios_df = simulate_scenarios(
        entry_vix, strike, entry_premium, dte, spike_prob,
        theta_decay_monthly, target_levels, days_to_spike_list,
        theta_greek, vega_greek
    )

    # Calculate downside risk
    downside_probs = calculate_downside_risk(vix_data, entry_vix, dte)

    # Calculate expected value
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

    # Store all calculated data
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

    set_calculated_data(calculated_data)
    return calculated_data


def main():
    # Load VIX data
    vix_data = load_vix_data()
    current_vix = vix_data['VIX'].iloc[-1]

    # Render sidebar and get inputs
    inputs = render_sidebar_inputs()
    set_shared_inputs(inputs)

    # Calculate all data
    calculated_data = calculate_all_data(vix_data, inputs)

    # Extract key values
    entry_premium = inputs['entry_premium']
    entry_vix = inputs['entry_vix']
    target_vix = inputs['target_vix']
    use_greeks = inputs['use_greeks']
    spike_prob = calculated_data['spike_prob']
    total_ev = calculated_data['total_ev']
    position_cost = calculated_data['position_cost']
    downside_probs = calculated_data['downside_probs']

    # =======================
    # HEADER
    # =======================
    st.markdown('<div class="main-header">📊 VIX Options Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Quick overview and trade verdict</div>', unsafe_allow_html=True)
    st.markdown("---")

    # =======================
    # KEY METRICS ROW
    # =======================
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Current VIX", f"{current_vix:.2f}")

    with col2:
        st.metric("Entry VIX", f"{entry_vix:.2f}")

    with col3:
        st.metric("Target VIX", f"{target_vix:.2f}", delta=f"+{target_vix - entry_vix:.2f}")

    with col4:
        st.metric("Position Cost", f"${position_cost:,.0f}")

    st.markdown("---")

    # =======================
    # OVERALL VERDICT
    # =======================
    st.subheader("🎯 Overall Trade Verdict")

    # Determine status
    if spike_prob >= 0.6 and total_ev > 0:
        status = "FAVORABLE"
        status_class = "status-good"
        status_emoji = "🟢"
    elif spike_prob >= 0.4 and total_ev > 0:
        status = "MODERATE"
        status_class = "status-moderate"
        status_emoji = "🟡"
    else:
        status = "UNFAVORABLE"
        status_class = "status-poor"
        status_emoji = "🔴"

    st.markdown(f'<div class="big-metric {status_class}">{status_emoji} {status} SETUP</div>',
                unsafe_allow_html=True)

    # Key statistics in columns
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Spike Probability",
            f"{spike_prob*100:.1f}%",
            help=f"Historical probability of VIX reaching {target_vix} from {entry_vix}"
        )
        if spike_prob >= 0.6:
            st.success("✅ High probability")
        elif spike_prob >= 0.4:
            st.warning("⚠️ Moderate probability")
        else:
            st.error("❌ Low probability")

    with col2:
        ev_pct = (total_ev / position_cost * 100) if position_cost > 0 else 0
        st.metric(
            "Expected Value",
            format_currency(total_ev),
            delta=format_percentage(ev_pct)
        )
        if total_ev > 0:
            st.success("✅ Positive EV")
        else:
            st.error("❌ Negative EV")

    with col3:
        # Find balanced stop loss
        balanced_stop = None
        for drop_pct in sorted(downside_probs.keys()):
            if downside_probs[drop_pct] < 20 and balanced_stop is None:
                balanced_stop = drop_pct
                break

        if balanced_stop:
            st.metric(
                "Recommended Stop",
                f"-{balanced_stop}%",
                help="Stop loss with <20% probability of being hit"
            )
            st.info(f"Risk: ${position_cost * balanced_stop/100:,.0f}")
        else:
            st.metric("Recommended Stop", "N/A")
            st.warning("Limited downside room")

    st.markdown("---")

    # =======================
    # QUICK SUMMARY
    # =======================
    st.subheader("📋 Quick Summary")

    if status == "FAVORABLE":
        st.success(f"""
        **🟢 This is a favorable setup:**
        - ✅ High probability ({spike_prob*100:.1f}%) of VIX reaching target
        - ✅ Positive expected value ({format_currency(total_ev)})
        - ✅ VIX at low level ({entry_vix:.2f}) with limited downside
        - ✅ Risk/reward profile is attractive

        **Next Steps:**
        1. Review detailed probability analysis (📈 Page 2)
        2. Confirm risk parameters (⚠️ Page 3)
        3. Plan your execution (💡 Page 4)
        """)
    elif status == "MODERATE":
        st.warning(f"""
        **🟡 This is a moderate setup:**
        - ⚠️ Moderate probability ({spike_prob*100:.1f}%) of reaching target
        - ✅ Positive expected value ({format_currency(total_ev)})
        - 💡 Consider smaller position size for risk management

        **Next Steps:**
        1. Review scenario analysis carefully (📈 Page 2)
        2. Understand downside risks (⚠️ Page 3)
        3. Consider position sizing recommendations (💡 Page 4)
        """)
    else:
        st.error(f"""
        **🔴 This setup is not favorable:**
        - ❌ Low probability ({spike_prob*100:.1f}%) or negative expected value
        - 💡 Consider waiting for better entry conditions
        - 💡 Try adjusting: entry VIX, target VIX, or DTE

        **Suggestions:**
        - Wait for VIX to drop further (closer to 12-13 range)
        - Increase analysis window to see longer-term probabilities
        - Consider different strike or expiration
        """)

    st.markdown("---")

    # =======================
    # MARKET CONTEXT
    # =======================
    st.subheader("🌍 Market Context")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**VIX Historical Percentile**")

        # Calculate where current VIX sits historically
        vix_percentile = (vix_data['VIX'] <= current_vix).sum() / len(vix_data) * 100

        st.progress(vix_percentile / 100)
        st.caption(f"Current VIX ({current_vix:.2f}) is at {vix_percentile:.0f}th percentile")

        if vix_percentile < 25:
            st.info("VIX is in the bottom quartile - historically compressed")
        elif vix_percentile < 50:
            st.info("VIX is below median levels")
        else:
            st.warning("VIX is above median - already somewhat elevated")

    with col2:
        st.markdown("**Recent VIX History**")

        # Show 30-day stats
        recent_30d = vix_data['VIX'].tail(30)
        st.metric("30-Day Average", f"{recent_30d.mean():.2f}")
        st.metric("30-Day Low", f"{recent_30d.min():.2f}")
        st.metric("30-Day High", f"{recent_30d.max():.2f}")

    st.markdown("---")

    # =======================
    # NAVIGATION HINTS
    # =======================
    st.subheader("📍 Navigation Guide")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.info("""
        **📈 Probability & Scenarios**

        View detailed:
        - Historical spike patterns
        - Multiple outcome scenarios
        - Expected value breakdowns
        """)

    with col2:
        st.info("""
        **⚠️ Risk Analysis**

        Understand:
        - Theta decay impact
        - Downside probabilities
        - Stop loss recommendations
        """)

    with col3:
        st.info("""
        **💡 Trade Plan**

        Get actionable:
        - Position sizing advice
        - Entry checklist
        - Exit strategy details
        """)

    # =======================
    # FOOTER
    # =======================
    st.markdown("---")
    st.caption(f"""
    **Data as of:** {vix_data.index[-1].strftime('%Y-%m-%d')} |
    **Greeks:** {'Actual (from chain)' if use_greeks else 'Estimated'} |
    **Historical data:** {len(vix_data)} days since 2004
    """)


if __name__ == "__main__":
    main()
