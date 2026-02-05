"""
UI Components
=============
Streamlit UI components and display functions.
"""

import streamlit as st
import pandas as pd


def render_sidebar_inputs():
    """
    Render all sidebar input controls.

    Returns:
        dict: All input values from sidebar
    """
    st.sidebar.title("⚙️ Configuration")

    # Contract selection
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

    # Greeks
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

        theta_greek = st.sidebar.number_input("Theta (Daily)", value=-0.020, min_value=-0.10, max_value=0.0,
                                             step=0.001, format="%.3f",
                                             help="Negative value (e.g., -0.020 = lose $2/day)")
        vega_greek = st.sidebar.number_input("Vega", value=0.120, min_value=0.0, max_value=0.50,
                                            step=0.001, format="%.3f",
                                            help="Gain per 1% IV increase (e.g., 0.120 = $12 gain per 1% IV)")

        st.sidebar.caption(f"📉 Daily decay: ${abs(theta_greek)*100:.2f}")
        st.sidebar.caption(f"📈 IV sensitivity: ${vega_greek*100:.3f} per 1% IV")
        st.sidebar.success("✅ Using actual Greeks for precise calculations")
    else:
        theta_greek = None
        vega_greek = None
        st.sidebar.caption("Using estimated decay model")

    # Market assumptions
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Market Assumptions")

    entry_vix = st.sidebar.number_input("Entry VIX Level", value=15.75, min_value=10.0, max_value=25.0, step=0.25)
    target_vix = st.sidebar.number_input("Target VIX Level", value=20.0, min_value=15.0, max_value=40.0, step=0.5)

    if not use_greeks:
        theta_decay_monthly = st.sidebar.slider("Monthly Theta Decay (%)", min_value=20, max_value=50, value=35, step=5) / 100
    else:
        theta_decay_monthly = None

    analysis_window = st.sidebar.number_input("Analysis Window (days)", value=60, min_value=7, max_value=180, step=7,
                                              help="How far forward to look for VIX spike probability")

    # Exit strategy
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Exit Strategy")

    profit_target = st.sidebar.slider("Profit Target (%)", min_value=50, max_value=500, value=150, step=25)
    stop_loss = st.sidebar.slider("Stop Loss (%)", min_value=-80, max_value=-20, value=-50, step=5)

    return {
        'entry_premium': entry_premium,
        'dte': dte,
        'strike': strike,
        'num_contracts': num_contracts,
        'theta_greek': theta_greek,
        'vega_greek': vega_greek,
        'use_greeks': use_greeks,
        'entry_vix': entry_vix,
        'target_vix': target_vix,
        'theta_decay_monthly': theta_decay_monthly,
        'analysis_window': analysis_window,
        'profit_target': profit_target,
        'stop_loss': stop_loss
    }


def render_header(current_vix, entry_vix, target_vix, position_cost, use_greeks, theta_greek, vega_greek):
    """Render dashboard header with key metrics."""
    st.markdown('<div class="main-header">📊 VIX Call Options Calculator</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Model premium expansion from low volatility environment</div>',
                unsafe_allow_html=True)
    st.markdown("---")

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

    if use_greeks:
        st.info(f"""
        ✅ **Using Actual Greeks for Calculations**
        - Theta: {theta_greek:.3f} (${abs(theta_greek)*100:.2f}/day decay)
        - Vega: {vega_greek:.3f} (${vega_greek*100:.3f} gain per 1% IV increase)

        These values from your options chain will provide more accurate projections than estimated models.
        """)


def render_downside_analysis(downside_probs, entry_vix, dte, position_cost):
    """Render downside risk analysis section."""
    st.subheader("⚠️ Downside Risk & Stop Loss Analysis")

    st.markdown("""
    **Recency-weighted analysis** (last 1-5 years weighted more heavily):
    - Last 1 year: 3x weight
    - Last 3 years: 2x weight
    - Last 5 years: 1.5x weight
    - Older data: 1x weight
    """)

    # Display downside risk table
    st.markdown(f"### Probability VIX Drops Below Levels ({dte} days)")

    downside_data = []
    for drop_pct in sorted(downside_probs.keys()):
        stop_vix = entry_vix * (1 - drop_pct/100)
        prob = downside_probs[drop_pct]

        if prob < 10:
            risk = "✅ Low"
        elif prob < 20:
            risk = "⚠️ Moderate"
        else:
            risk = "🔴 High"

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
