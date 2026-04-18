"""
Storage Model Dashboard
=======================
An educational gas storage optimization analogy using exchange-traded assets.
Mirrors injection/withdrawal decisions subject to physical constraints.

Run with: streamlit run scripts/storage_model_dashboard.py
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from dataclasses import replace, asdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage_model.config import (
    StorageConfig, GLD_PRESET, CORN_PRESET,
    CONSERVATIVE_OVERRIDES, AGGRESSIVE_OVERRIDES,
)
from src.storage_model.data_loader import StorageDataLoader
from src.storage_model.engine import StorageEngine
from src.storage_model.signals import StorageSignalEngine
from src.storage_model import visualizations as viz

# ── Page config ──
st.set_page_config(
    page_title="Storage Model",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Sidebar ──
def render_sidebar() -> StorageConfig:
    """Render sidebar controls and return the active StorageConfig."""
    st.sidebar.title("Storage Configuration")

    # Asset selection
    asset = st.sidebar.selectbox(
        "Asset",
        ["GLD — Gold ETF", "CORN — Corn ETF", "Custom"],
        index=0,
    )
    if asset.startswith("GLD"):
        base_config = GLD_PRESET
    elif asset.startswith("CORN"):
        base_config = CORN_PRESET
    else:
        custom_ticker = st.sidebar.text_input("Ticker", "SPY")
        base_config = StorageConfig(
            ticker=custom_ticker,
            asset_name=f"Custom ({custom_ticker})",
        )

    # Risk preset
    risk_preset = st.sidebar.selectbox(
        "Risk Preset", ["Balanced", "Conservative", "Aggressive"], index=0
    )
    if risk_preset == "Conservative":
        config = replace(base_config, **CONSERVATIVE_OVERRIDES)
    elif risk_preset == "Aggressive":
        config = replace(base_config, **AGGRESSIVE_OVERRIDES)
    else:
        config = replace(base_config)

    # Advanced overrides
    with st.sidebar.expander("Storage Parameters", expanded=False):
        config = replace(config,
            max_inventory=st.number_input("Max Capacity (units)", value=config.max_inventory, min_value=100, step=100),
            min_inventory=st.number_input("Cushion (min units)", value=config.min_inventory, min_value=0, step=10),
            max_inject_per_day=st.number_input("Max Inject/Day", value=config.max_inject_per_day, min_value=1, step=5),
            max_withdraw_per_day=st.number_input("Max Withdraw/Day", value=config.max_withdraw_per_day, min_value=1, step=5),
            initial_inventory=st.number_input("Initial Inventory", value=config.min_inventory, min_value=config.min_inventory, max_value=config.max_inventory, step=10),
            use_ratchets=st.checkbox("Enable Ratchets", value=config.use_ratchets,
                help="Injection rate decreases as storage fills; withdrawal rate decreases as storage empties"),
        )

    with st.sidebar.expander("Signal Parameters", expanded=False):
        config = replace(config,
            zscore_window=st.slider("Z-Score Window (days)", 20, 126, config.zscore_window),
            inject_signal_threshold=st.slider("Inject Threshold", 0.05, 0.8, config.inject_signal_threshold, 0.05),
            withdraw_signal_threshold=st.slider("Withdraw Threshold", -0.8, -0.05, config.withdraw_signal_threshold, 0.05),
            seasonal_weight=st.slider("Seasonal Weight", 0.0, 1.0, config.seasonal_weight, 0.05),
            zscore_weight=st.slider("Z-Score Weight", 0.0, 1.0, config.zscore_weight, 0.05),
            momentum_weight=st.slider("Momentum Weight", 0.0, 1.0, config.momentum_weight, 0.05),
            seasonal_gate=st.selectbox("Seasonal Gate", ["soft", "hard", "none"], index=["soft", "hard", "none"].index(config.seasonal_gate),
                help="soft=penalize off-season trades, hard=block them, none=no restriction"),
        )

    with st.sidebar.expander("Date Range", expanded=False):
        config = replace(config,
            start_date=st.text_input("Start Date", config.start_date),
        )

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "**Gas Storage Analogy**: This model simulates a storage facility. "
        "'Inject' = buy when cheap. 'Withdraw' = sell when expensive. "
        "Capacity, rate limits, ratchets, and cushion are hard constraints."
    )

    return config


@st.cache_data(show_spinner="Loading price data...")
def load_data(ticker: str, start_date: str, end_date: str = None):
    cfg = StorageConfig(ticker=ticker, start_date=start_date, end_date=end_date)
    loader = StorageDataLoader(cfg)
    return loader.load()


@st.cache_data(show_spinner="Running backtest simulation...")
def run_backtest(_config_dict: dict, _data_hash: str, df: pd.DataFrame):
    """Run backtest. Uses _config_dict for cache key."""
    # Filter to only StorageConfig fields
    valid_fields = {f.name for f in StorageConfig.__dataclass_fields__.values()}
    filtered = {k: v for k, v in _config_dict.items() if k in valid_fields}
    config = StorageConfig(**filtered)
    engine = StorageEngine(config)
    return engine.run(df)


def config_to_hashable(config: StorageConfig) -> dict:
    """Convert config to hashable dict for cache key."""
    d = asdict(config)
    # Convert lists to tuples for hashability
    d["inject_months"] = tuple(d["inject_months"])
    d["withdraw_months"] = tuple(d["withdraw_months"])
    return d


# ── Tab renderers ──

def render_decision_tab(daily_df: pd.DataFrame, config: StorageConfig):
    """Tab 1: Today's Decision."""
    latest = daily_df.iloc[-1]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Current Price", f"${latest['price']:.2f}")
    col2.metric("Inventory", f"{int(latest['inventory'])} units")
    col3.metric("Capacity Used", f"{latest['inventory'] / config.max_inventory * 100:.0f}%")
    col4.metric("Composite Signal", f"{latest['composite_signal']:.3f}")

    st.markdown("---")

    # Decision box
    action = latest["action"]
    units = int(latest["units_transacted"])
    if action == "inject":
        eff_rate = config.effective_inject_rate(int(latest["inventory"]) - units)
        st.success(
            f"### INJECT: Buy {units} units at ${latest['price']:.2f}\n"
            f"Signal: {latest['composite_signal']:.3f} "
            f"(threshold: {config.inject_signal_threshold}) | "
            f"Effective rate: {eff_rate}/day"
        )
    elif action == "withdraw":
        eff_rate = config.effective_withdraw_rate(int(latest["inventory"]) + units)
        st.error(
            f"### WITHDRAW: Sell {units} units at ${latest['price']:.2f}\n"
            f"Signal: {latest['composite_signal']:.3f} "
            f"(threshold: {config.withdraw_signal_threshold}) | "
            f"Effective rate: {eff_rate}/day"
        )
    else:
        st.info(
            f"### HOLD: No action today\n"
            f"Composite signal ({latest['composite_signal']:.3f}) is between "
            f"thresholds ({config.withdraw_signal_threshold} to {config.inject_signal_threshold})"
        )

    st.markdown("---")
    st.subheader("Signal Breakdown")
    s1, s2, s3 = st.columns(3)
    with s1:
        st.metric("Seasonal Score", f"{latest['seasonal_score']:.3f}")
        if latest["seasonal_score"] > 0:
            st.caption("In injection season (buy window)")
        else:
            st.caption("In withdrawal season (sell window)")
    with s2:
        st.metric("Z-Score", f"{latest['zscore']:.3f}")
        if latest["zscore"] < -1:
            st.caption("Price is CHEAP vs recent history")
        elif latest["zscore"] > 1:
            st.caption("Price is EXPENSIVE vs recent history")
        else:
            st.caption("Price is near fair value")
    with s3:
        st.metric("Momentum (5d)", f"{latest['momentum']:.3%}")
        if latest["momentum"] < -0.02:
            st.caption("Strong downward momentum")
        elif latest["momentum"] > 0.02:
            st.caption("Strong upward momentum")
        else:
            st.caption("Neutral momentum")

    st.markdown("---")
    st.subheader("Constraint Check")
    c1, c2, c3, c4 = st.columns(4)
    inv = int(latest["inventory"])
    capacity_remaining = config.max_inventory - inv
    above_cushion = inv - config.min_inventory
    c1.metric("Capacity Remaining", f"{capacity_remaining} units")
    c2.metric("Above Cushion", f"{above_cushion} units")
    c3.metric("Eff. Inject Rate", f"{config.effective_inject_rate(inv)}/day")
    c4.metric("Eff. Withdraw Rate", f"{config.effective_withdraw_rate(inv)}/day")

    binding = []
    if capacity_remaining <= config.effective_inject_rate(inv):
        binding.append("Near max capacity — injection limited")
    if above_cushion <= config.effective_withdraw_rate(inv):
        binding.append("Near cushion — withdrawal limited")
    if config.use_ratchets:
        fill_pct = (inv - config.min_inventory) / (config.max_inventory - config.min_inventory)
        if fill_pct > 0.8:
            binding.append(f"Ratchet: injection slowed ({config.effective_inject_rate(inv)} vs {config.max_inject_per_day} max)")
        if fill_pct < 0.2:
            binding.append(f"Ratchet: withdrawal slowed ({config.effective_withdraw_rate(inv)} vs {config.max_withdraw_per_day} max)")
    if binding:
        st.warning("**Binding constraints:** " + "; ".join(binding))


def render_storage_status_tab(daily_df: pd.DataFrame, trades_df: pd.DataFrame, config: StorageConfig):
    """Tab 2: Storage Status."""
    col1, col2 = st.columns([1, 2])

    with col1:
        gauge = viz.create_inventory_gauge(int(daily_df["inventory"].iloc[-1]), config)
        st.plotly_chart(gauge, use_container_width=True)

    with col2:
        profile = viz.create_inventory_profile_chart(daily_df, config)
        st.plotly_chart(profile, use_container_width=True)

    price_chart = viz.create_price_signal_chart(daily_df, trades_df)
    st.plotly_chart(price_chart, use_container_width=True)


def render_backtest_tab(daily_df: pd.DataFrame, trades_df: pd.DataFrame, metrics: dict):
    """Tab 3: Backtest Results."""
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Return", f"{metrics['total_return_pct']:.1f}%")
    c2.metric("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}")
    c3.metric("Max Drawdown", f"{metrics['max_drawdown_pct']:.1f}%")

    c4, c5, c6 = st.columns(3)
    c4.metric("Inject Efficiency", f"{metrics['inject_efficiency_pct']:.1f}%")
    c5.metric("Withdraw Efficiency", f"{metrics['withdraw_efficiency_pct']:.1f}%")
    c6.metric("Spread Captured", f"{metrics['spread_captured_pct']:.2f}%")

    st.markdown("---")

    # Benchmarks
    b1, b2, b3 = st.columns(3)
    b1.metric("vs Buy & Hold", f"{metrics['buy_hold_return_pct']:.1f}%", help="Buy and hold the asset for the entire period")
    b2.metric("vs Naive Seasonal", f"{metrics['naive_seasonal_return_pct']:.1f}%", help="Fully invested during withdrawal months only")
    b3.metric("Off-Season Trades", f"{metrics.get('off_season_injects', 0)} inj / {metrics.get('off_season_withdrawals', 0)} wdl")

    st.markdown("---")

    portfolio_chart = viz.create_portfolio_vs_benchmark_chart(daily_df)
    st.plotly_chart(portfolio_chart, use_container_width=True)

    annual_chart = viz.create_annual_pnl_chart(daily_df)
    st.plotly_chart(annual_chart, use_container_width=True)

    st.markdown("---")
    st.subheader("Trade Log")
    extra = st.columns(3)
    extra[0].metric("Total Trades", metrics["total_trades"])
    extra[1].metric("Avg Inject Price", f"${metrics['avg_inject_price']:.2f}")
    extra[2].metric("Avg Withdraw Price", f"${metrics['avg_withdraw_price']:.2f}")

    if not trades_df.empty:
        display_df = trades_df.copy()
        display_df["price"] = display_df["price"].map("${:.2f}".format)
        display_df = display_df[["action", "units", "price", "inventory_after", "composite_signal"]]
        display_df.columns = ["Action", "Units", "Price", "Inventory After", "Signal"]
        st.dataframe(display_df.tail(100), use_container_width=True, height=400)


def render_storage_value_tab(daily_df: pd.DataFrame):
    """Tab 4: Storage Value."""
    latest = daily_df.iloc[-1]

    st.info(
        "**In real gas storage**, the facility's value has two components: "
        "*intrinsic value* (the locked-in calendar spread — inject now, withdraw at the seasonal peak) "
        "and *extrinsic/optionality value* (the ability to choose *when* to act, which increases with volatility). "
        "This tab shows those same components for your ETF storage analogy."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Intrinsic Value", f"${latest['intrinsic_value']:,.0f}")
    c2.metric("Optionality Value", f"${latest['optionality_value']:,.0f}")
    c3.metric("Total Storage Value", f"${latest['intrinsic_value'] + latest['optionality_value']:,.0f}")

    st.markdown("---")

    value_chart = viz.create_storage_value_chart(daily_df)
    st.plotly_chart(value_chart, use_container_width=True)

    st.markdown("---")
    st.subheader("How to read this")
    st.markdown("""
    - **Intrinsic Value** is positive when the seasonal forward estimate is above the current spot price
      and you hold inventory. This is equivalent to being long a calendar spread in gas futures.
      In this model, the "forward price" is estimated from historical monthly returns — a simplification.
      In real gas storage, intrinsic comes directly from the futures forward curve.
    - **Optionality Value** scales with volatility, spare capacity (room to inject on dips),
      and time remaining to the peak withdrawal month. It's highest at the start of injection season
      when the facility is empty and there's maximum flexibility.
    - In practice, storage operators use intrinsic + extrinsic to decide whether to
      *lease* their facility or *trade it themselves*. If intrinsic alone covers costs,
      the decision is straightforward. If you need the optionality to be profitable,
      execution quality matters much more.
    """)


def render_learn_tab(config: StorageConfig, monthly_stats: pd.DataFrame):
    """Tab 5: Learn — How It Works."""

    heatmap = viz.create_seasonal_heatmap(monthly_stats)
    st.plotly_chart(heatmap, use_container_width=True)

    with st.expander("What is gas storage?", expanded=True):
        st.markdown("""
        Natural gas storage facilities are underground reservoirs (depleted fields, salt caverns,
        or aquifers) that hold gas inventory. Their economic purpose is simple:
        **buy gas when it's cheap (summer) and sell it when it's expensive (winter).**

        The difference between the injection cost and withdrawal revenue is the **storage spread**.
        A storage facility's value comes from its ability to capture this spread, plus the
        **optionality** to time decisions optimally.

        **Important context**: The seasonal spread in US natural gas has compressed dramatically —
        from $2-4/MMBtu pre-2008 to near-zero or even negative since 2013 (driven by the shale
        production boom, year-round power burn, and LNG exports). This means modern storage
        value is increasingly driven by **extrinsic/optionality value** rather than the simple
        summer/winter spread. Your colleagues' models must account for this.
        """)

    with st.expander("The forward curve — what this model simplifies"):
        st.markdown("""
        **This is the single biggest simplification in this model.**

        In real gas storage, intrinsic value is calculated directly from the **forward curve** —
        a set of observable futures prices for each month out to 3+ years. For example, if the
        October Henry Hub futures price is $2.50 and the January price is $3.20, the calendar
        spread is $0.70/MMBtu. The intrinsic value LP maximizes the sum of these spreads
        subject to facility constraints.

        This model has no forward curve. Instead, it estimates future prices from **historical
        average monthly returns** — a much rougher approximation. This is like driving by
        looking in the rearview mirror: it captures the average seasonal pattern but misses
        what the market is pricing *right now*.

        **The real model**: solves a Linear Program (LP) over the forward curve:
        *maximize sum of F_t x q_t* (forward prices x net flows) subject to inventory bounds,
        rate limits, and ratchets. The `cmdty-storage` Python package (`pip install cmdty-storage`)
        implements this if you want to see the real thing.
        """)

    with st.expander("Injection & withdrawal decisions"):
        st.markdown("""
        Each day, the storage operator decides how much gas to **inject** (buy from the market
        and put into storage) or **withdraw** (take from storage and sell to the market).

        These decisions are constrained by:
        - **Capacity**: the facility can only hold so much gas (max working gas)
        - **Injection rate**: physical limits on how fast gas can be pumped in
        - **Withdrawal rate**: physical limits on how fast gas can be extracted
        - **Cushion gas**: a minimum level that must be maintained for pressure
        - **Ratchets**: rates change with inventory level (see below)

        **Bang-bang control**: Research (Secomandi, 2010) shows the optimal storage policy
        is always one of three actions: inject at maximum rate, withdraw at maximum rate, or
        do nothing. There's no benefit to partial-rate operations. This model implements
        this bang-bang approach.

        **Seasonal discipline**: In real gas storage, injection season (Apr-Oct) and withdrawal
        season (Nov-Mar) are enforced by market structure and physical operations. This model
        applies a seasonal gate that penalizes or blocks off-season trades.
        """)

    with st.expander("Ratchets — why rates change with inventory"):
        st.markdown("""
        **Ratchets** are the defining physical complexity of real gas storage.

        The key relationship is pressure-dependent:
        - As inventory **increases** (storage fills): pressure rises, making it **harder to inject**
          (injection rate decreases) but **easier to withdraw** (withdrawal rate increases)
        - As inventory **decreases** (storage empties): pressure drops, making it **easier to inject**
          but **harder to withdraw**

        Real contracts specify ratchet schedules:

        | Fill Level | Inject Rate | Withdraw Rate |
        |---|---|---|
        | 0-25% | 100% of max | 20% of max |
        | 25-75% | 50-80% of max | 50-80% of max |
        | 75-100% | 20% of max | 100% of max |

        This model uses a **linear ratchet**: injection rate scales from 100% (at cushion) to 20%
        (at max capacity), and withdrawal rate scales inversely. This is simpler than real
        piecewise schedules but captures the core concept.

        The practical impact: you must start injecting **before** prices hit their absolute bottom,
        because you can't fill the facility quickly when it's already mostly full.
        """)

    with st.expander("Intrinsic vs extrinsic value"):
        st.markdown("""
        **Intrinsic value** is what you'd earn from a simple, predetermined schedule:
        inject in summer, withdraw in winter. It's the calendar spread locked in today.
        Professional traders call this the "rolling intrinsic" because it's recalculated daily
        as the forward curve moves.

        A MathWorks reference implementation shows: static intrinsic ~$97k vs rolling intrinsic
        ~$249k — the rolling approach captures 2.5x more value by re-hedging as the curve evolves.

        **Extrinsic (optionality) value** is the *extra* value from being able to *choose*
        when to act. It depends on:
        1. **Volatility** — more price movement = more opportunities
        2. **Spare capacity** — room to inject on dips AND withdraw on spikes
        3. **Time remaining** — more time = more optionality (like option theta)

        Professional models compute extrinsic value via **Least-Squares Monte Carlo (LSMC)**
        or **stochastic dynamic programming**. This model uses a simplified formula based on
        volatility, flexibility, and time remaining.

        Total storage value = intrinsic + extrinsic. When traders say "storage is well-bid"
        or "contango is steep," they're talking about intrinsic. When they discuss "vol is high"
        making storage valuable, that's extrinsic.
        """)

    with st.expander("Physical constraints and why they matter"):
        st.markdown("""
        Constraints are what make storage optimization non-trivial. Without them,
        you'd simply buy all the gas when it's cheapest and sell it all at the peak.

        **Rate limits** mean you can't fill the facility in one day — you must start
        injecting before the absolute price bottom. Combined with **ratchets** (slower injection
        as storage fills), this creates a genuine optimization problem.

        **Cushion gas** is gas that cannot be withdrawn — it maintains pressure in the
        reservoir. It's a sunk cost that reduces effective capacity.

        **Cycling**: Storage facilities are categorized by how fast they can cycle:
        - **Seasonal storage** (>100 days to fill): ~1 cycle/year, depleted reservoirs
        - **Fast-churn** (<30 days): 5-12 cycles/year, salt caverns, much higher extrinsic value
        """)

    with st.expander("How this ETF analogy maps to real gas storage"):
        mapping_data = {
            "Gas Storage Term": [
                "Working gas capacity",
                "Cushion gas",
                "Injection rate",
                "Withdrawal rate",
                "Ratchets",
                "Injection season (Apr-Oct)",
                "Withdrawal season (Nov-Mar)",
                "Forward curve",
                "Intrinsic value (LP on forward curve)",
                "Extrinsic / optionality (LSMC)",
                "Rolling intrinsic",
                "Storage premium / calendar spread",
            ],
            "ETF Analogy": [
                "Max shares held",
                "Minimum reserve",
                "Max daily buy (at full rate)",
                "Max daily sell (at full rate)",
                "Linear rate scaling with inventory",
                "Seasonally cheap months (buy window)",
                "Seasonally expensive months (sell window)",
                "Estimated from historical monthly returns",
                "Seasonal return spread x inventory",
                "Volatility x flexibility x time remaining",
                "Daily re-evaluation of signals",
                "Avg withdraw price / avg inject price",
            ],
            "Model Parameter": [
                f"max_inventory = {config.max_inventory}",
                f"min_inventory = {config.min_inventory}",
                f"max_inject_per_day = {config.max_inject_per_day}",
                f"max_withdraw_per_day = {config.max_withdraw_per_day}",
                f"use_ratchets = {config.use_ratchets}",
                f"inject_months = {config.inject_months}",
                f"withdraw_months = {config.withdraw_months}",
                "Monthly seasonality heatmap above",
                "intrinsic_value (daily, in Storage Value tab)",
                "optionality_value (daily, in Storage Value tab)",
                "Backtest re-runs signals daily",
                "spread_captured_pct (in Backtest tab)",
            ],
        }
        st.table(pd.DataFrame(mapping_data))

    with st.expander("Limitations of this analogy"):
        st.markdown("""
        **What this model simplifies:**

        1. **No forward curve**: Real gas storage values are derived from the full forward
           curve (monthly futures prices out to 3+ years). This model estimates forward prices
           from historical seasonal patterns — much less accurate. See the `cmdty-storage`
           Python package for a real implementation.

        2. **No MILP optimization**: Professional storage models use linear programming
           to find the globally optimal injection/withdrawal schedule across the entire
           forward curve. This model uses rule-based signals — a heuristic approximation.
           Secomandi (2010) showed the rolling intrinsic heuristic performs near-optimally
           for seasonal storage under mean-reverting prices.

        3. **Simplified ratchets**: Real facilities have complex piecewise injection/withdrawal
           rate schedules. This model uses a linear approximation.

        4. **No basis risk**: Gas storage values depend on the specific delivery point
           (e.g., Henry Hub vs. local hub). ETFs don't have locational basis.

        5. **No fuel costs**: Injecting gas requires compressor fuel (0.5-2% of volume).
           We approximate this with a flat transaction cost.

        6. **No multi-factor price model**: Professional models use 2-3 factor price
           processes (short-term + long-term + seasonal spread). We use a single
           z-score on the spot price.

        7. **Gas seasonal spreads have collapsed**: The summer/winter spread went from
           $2-4/MMBtu pre-2008 to near-zero post-2013 (shale boom, LNG exports).
           Modern storage value is increasingly extrinsic, not intrinsic.

        Despite these simplifications, the core logic is the same: buy low, sell high,
        subject to physical constraints, and decompose value into intrinsic + optionality.
        """)

    with st.expander("References for further learning"):
        st.markdown("""
        **Academic Papers:**
        - Secomandi, N. (2010). "Optimal Commodity Trading with a Capacitated Storage Asset."
          *Management Science*, 56(3):449-467. [The canonical reference for storage optimization]
        - Boogert, A. & De Jong, C. "Gas Storage Valuation Using a Monte Carlo Method."
          *Journal of Derivatives*. [LSMC approach to extrinsic value]
        - Erb, C.B. & Harvey, C.R. (2013). "The Golden Dilemma."
          *Financial Analysts Journal*. [Gold as an asset class]

        **Industry Resources:**
        - EIA: "The Basics of Underground Natural Gas Storage" — eia.gov
        - CME Group: "Understanding Natural Gas Risk Management Spreads & Storage"
        - Timera Energy: "Cracking Gas Storage and Swing Valuation" — timera-energy.com
        - LaCima Group: Gas storage valuation white papers — lacimagroup.com

        **Open-Source Code:**
        - `cmdty-storage` (`pip install cmdty-storage`): Full implementation with
          intrinsic LP, trinomial tree, and multi-factor LSMC. Handles ratchets.
        - MathWorks File Exchange #44406: MATLAB intrinsic LP + rolling valuation
        """)


# ── Main ──

def main():
    st.title("Gas Storage Model")
    st.caption("An educational storage optimization analogy using exchange-traded assets")

    config = render_sidebar()

    # Validate weights
    weight_sum = config.seasonal_weight + config.zscore_weight + config.momentum_weight
    if abs(weight_sum - 1.0) > 0.01:
        st.warning(f"Signal weights sum to {weight_sum:.2f} — they should sum to 1.0. Adjust in sidebar.")
        return

    try:
        df = load_data(config.ticker, config.start_date, config.end_date)
    except Exception as e:
        st.error(f"Failed to load data for {config.ticker}: {e}")
        return

    config_dict = config_to_hashable(config)
    data_hash = str(hash(tuple(df.index[:5].astype(str)) + (len(df),)))

    try:
        results = run_backtest(config_dict, data_hash, df)
    except Exception as e:
        st.error(f"Backtest failed: {e}")
        return

    daily_df = results.to_daily_df()
    trades_df = results.to_trades_df()
    metrics = results.calculate_metrics()

    # Compute monthly seasonality for learn tab
    signal_engine = StorageSignalEngine(config)
    monthly_stats = signal_engine.compute_monthly_seasonality(df)

    # Render tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Today's Decision",
        "Storage Status",
        "Backtest Results",
        "Storage Value",
        "Learn: How It Works",
    ])

    with tab1:
        render_decision_tab(daily_df, config)
    with tab2:
        render_storage_status_tab(daily_df, trades_df, config)
    with tab3:
        render_backtest_tab(daily_df, trades_df, metrics)
    with tab4:
        render_storage_value_tab(daily_df)
    with tab5:
        render_learn_tab(config, monthly_stats)


if __name__ == "__main__":
    main()
