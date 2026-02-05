# Mean Reversion Strategy - Complete Guide

## Overview

Production-ready mean reversion strategy for swing trading mega-cap tech stocks using proper risk management and IBKR Lite commission structure.

**Performance:**
- **62.5% return** over 3 years (2022-2024)
- **Sharpe Ratio:** 6.67
- **Max Drawdown:** -5.5%
- **Win Rate:** 53.6%
- **Profit Factor:** 2.67

## Strategy Rules (Optimized)

### Entry Conditions (ALL must be met):
1. **RSI(2) < 30** - Extreme oversold condition
2. **Uptrend:** Price > MA50 > MA200 (clear uptrend)
3. **Pullback:** 2-8% pullback from recent 10-day high
4. **Near Support:** Price within 2% of MA20

### Exit Conditions (First to trigger):
1. **Profit Target:** +3% from entry
2. **Stop Loss:** -2% from entry OR 1.5× ATR (whichever is wider)
3. **Max Hold Period:** 7 days
4. **Trailing Stop:** DISABLED (net negative in backtests)

### Position Sizing (CRITICAL):
**Risk 1% of account balance per trade:**

```
Position Size = (Account Balance × 0.01) / (Entry Price - Stop Price)
```

**Example:**
- Account: $10,000
- Entry: $200
- Stop: $194 (ATR-based, $6 risk/share)
- Risk: $100 (1% of $10,000)
- Shares: $100 / $6 = 16 shares
- Position Value: $3,200 (32% of capital, varies by stop)

**NOT:** Fixed percentage of capital (5%, 10%, 20%)!

### Risk Management:
- Max 5 concurrent positions
- Max 1% risk per trade
- Stop loss ALWAYS used
- Position size varies based on stop distance

## Cost Structure (IBKR Lite)

- **Stock Commissions:** $0.00 (IBKR Lite commission-free)
- **Slippage:** $0.05/share (realistic for mega-cap stocks)
- **No monthly fees** (IBKR Lite free tier)

**Total per-trade cost:** ~$2-5 in slippage (negligible)

## Symbols (Mega-Cap Liquid Tech)

- AAPL (Apple)
- MSFT (Microsoft)
- GOOGL (Alphabet)
- AMZN (Amazon)
- META (Meta)
- NVDA (NVIDIA)
- TSLA (Tesla)

**Why these?** High liquidity, tight spreads, low slippage

## Usage

### 1. Backtest (Historical Performance)

```bash
python scripts/mean_reversion_v2_proper.py
```

Outputs:
- Trade-by-trade results
- Performance metrics (Sharpe, win rate, profit factor)
- Monthly P&L breakdown
- Parameter optimization comparison
- Saves to: `data/mean_reversion_v2_results.csv`

### 2. Scanner (Find Current Setups)

```bash
python scripts/mean_reversion_scanner_v2.py
```

Outputs:
- List of symbols meeting ALL entry criteria
- Entry price, stop, target for each setup
- Near-miss symbols showing which conditions failed
- Saves to: `data/mean_reversion_scan_latest.csv`

### 3. Live Trading Workflow

**Daily (Market Close or Next Morning):**
1. Run scanner: `python scripts/mean_reversion_scanner_v2.py`
2. Review valid setups
3. For each setup:
   - Verify conditions manually
   - Calculate position size based on current account balance
   - Place limit order at current price (or slightly below)
   - Set stop loss order immediately
   - Set profit target order (or use manual exit)

**During Trade:**
- Monitor daily for exit conditions
- Close at +3% profit OR -2% stop
- Close after 7 days if neither hit
- DO NOT move stop loss (stick to plan)

## Files

### Scripts:
- `scripts/mean_reversion_v2_proper.py` - Full backtest engine
- `scripts/mean_reversion_scanner_v2.py` - Real-time setup scanner

### Data:
- `data/mean_reversion_v2_results.csv` - Backtest results
- `data/mean_reversion_scan_latest.csv` - Latest scan results

### Documentation:
- `docs/mean_reversion_v2_results.md` - Detailed backtest analysis
- `docs/mean_reversion_strategy_guide.md` - This file

## Key Insights

### What We Fixed:
1. **Position Sizing:** Changed from fixed % of capital to 1% risk per trade
2. **Commissions:** Changed from $1/trade to $0 (IBKR Lite reality)
3. **Stops:** Added ATR-based dynamic stops instead of only fixed %
4. **Parameters:** Tested RSI(2)<30 vs RSI(5)<35 (RSI2 wins!)

### What Works:
- RSI(2) < 30 is extreme but generates best returns
- Uptrend filter (price>MA50>MA200) is essential
- ATR-based stops adapt to volatility
- 1% risk per trade prevents blowups
- Max 5 positions limits overexposure

### What Doesn't Work:
- Trailing stops (net negative in backtests)
- Fixed % of capital position sizing (leads to losses)
- Too many concurrent positions (increases correlation risk)
- Trading in downtrends (uptrend filter required)

## Risk Warnings

### Backtested on Bull Market:
- 2022-2024 was mostly bullish for tech
- Strategy untested in prolonged bear market
- Results may not repeat in different market conditions

### Limitations:
- Requires IBKR Lite ($0 commissions) to match backtest
- Only tested on mega-cap tech stocks
- Assumes ability to get fills at quoted prices
- Slippage may be higher during volatility
- Real-world execution may differ from backtest

### Maximum Risk Scenarios:
- 5 concurrent positions × 1% risk each = 5% of account at risk
- Max drawdown in backtest: -5.5%
- If all 5 positions hit stops simultaneously: -5% loss
- Account can withstand ~20 such events before significant damage

## Next Steps

### Before Live Trading:
1. ✅ Complete backtest (DONE)
2. ✅ Create scanner (DONE)
3. ⬜ Paper trade for 1-2 months
4. ⬜ Track real-time fills vs backtest assumptions
5. ⬜ Verify slippage is truly $0.05/share or less
6. ⬜ Test order execution during market open

### Potential Improvements:
- Add more symbols (test on SPY, QQQ, other mega-caps)
- Test different RSI periods (RSI3, RSI4)
- Explore volatility filters (avoid trading during VIX spikes)
- Build Streamlit dashboard for daily monitoring
- Add earnings calendar filter (avoid holding through earnings)
- Create automated alerts (email/SMS when setup appears)

## Configuration Reference

```python
from scripts.mean_reversion_v2_proper import StrategyConfig

# Optimized configuration
config = StrategyConfig(
    # Account
    initial_capital=10_000,
    risk_per_trade=0.01,      # 1% risk
    max_positions=5,

    # Entry
    rsi_period=2,             # RSI(2)
    rsi_threshold=30,         # < 30
    pullback_min=0.02,        # 2% min
    pullback_max=0.08,        # 8% max
    ma_fast=20,               # MA20
    ma_slow=50,               # MA50
    ma_long=200,              # MA200

    # Exit
    profit_target=0.03,       # 3%
    stop_loss=0.02,           # 2%
    max_hold_days=7,
    use_trailing_stop=False,  # Disabled

    # Costs
    commission_per_share=0.0,
    slippage_per_share=0.05
)
```

## Support

For questions or issues:
1. Review backtest results in `docs/mean_reversion_v2_results.md`
2. Check configuration in script files
3. Verify IBKR Lite account has $0 commissions

## License

This is for personal use. Not financial advice. Trade at your own risk.

---

**Last Updated:** 2026-02-05
**Version:** 2.0
**Status:** Production Ready (pending paper trading validation)
