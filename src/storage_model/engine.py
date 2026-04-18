"""Storage engine — daily simulation with physical constraints and value decomposition"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from datetime import datetime

from src.storage_model.config import StorageConfig
from src.storage_model.signals import StorageSignalEngine


@dataclass
class StorageTrade:
    """A single injection or withdrawal event."""
    date: datetime
    action: str             # "inject" or "withdraw"
    units: int
    price: float
    transaction_cost: float
    inventory_before: int
    inventory_after: int
    composite_signal: float
    seasonal_score: float
    zscore: float
    momentum: float


@dataclass
class StorageDayState:
    """Full state snapshot for one day."""
    date: datetime
    price: float
    inventory: int
    cash: float
    portfolio_value: float  # cash + inventory * price
    composite_signal: float
    seasonal_score: float
    zscore: float
    momentum: float
    action: str             # "inject", "withdraw", "hold"
    units_transacted: int
    intrinsic_value: float
    optionality_value: float
    cumulative_pnl: float


@dataclass
class StorageBacktestResults:
    """Complete backtest output."""
    trades: List[StorageTrade]
    daily_states: List[StorageDayState]
    config: StorageConfig

    def to_daily_df(self) -> pd.DataFrame:
        """Convert daily states to DataFrame."""
        records = []
        for s in self.daily_states:
            records.append({
                "date": s.date,
                "price": s.price,
                "inventory": s.inventory,
                "cash": s.cash,
                "portfolio_value": s.portfolio_value,
                "composite_signal": s.composite_signal,
                "seasonal_score": s.seasonal_score,
                "zscore": s.zscore,
                "momentum": s.momentum,
                "action": s.action,
                "units_transacted": s.units_transacted,
                "intrinsic_value": s.intrinsic_value,
                "optionality_value": s.optionality_value,
                "cumulative_pnl": s.cumulative_pnl,
            })
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return df

    def to_trades_df(self) -> pd.DataFrame:
        """Convert trades to DataFrame."""
        if not self.trades:
            return pd.DataFrame()
        records = []
        for t in self.trades:
            records.append({
                "date": t.date,
                "action": t.action,
                "units": t.units,
                "price": t.price,
                "transaction_cost": t.transaction_cost,
                "inventory_before": t.inventory_before,
                "inventory_after": t.inventory_after,
                "composite_signal": t.composite_signal,
            })
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return df

    def calculate_metrics(self) -> Dict:
        """Calculate performance and storage-specific KPIs."""
        daily_df = self.to_daily_df()
        trades_df = self.to_trades_df()

        # Portfolio metrics
        initial_value = daily_df["portfolio_value"].iloc[0]
        final_value = daily_df["portfolio_value"].iloc[-1]
        total_return = (final_value / initial_value - 1) * 100

        # Daily returns for Sharpe
        daily_returns = daily_df["portfolio_value"].pct_change().dropna()
        sharpe = (daily_returns.mean() / (daily_returns.std() + 1e-10)) * np.sqrt(252)

        # Max drawdown
        cummax = daily_df["portfolio_value"].cummax()
        drawdown = (daily_df["portfolio_value"] - cummax) / cummax
        max_drawdown = drawdown.min() * 100

        # Buy & hold benchmark
        first_price = daily_df["price"].iloc[0]
        last_price = daily_df["price"].iloc[-1]
        buy_hold_return = (last_price / first_price - 1) * 100

        # Naive seasonal benchmark: fully invested during withdraw months, cash otherwise
        naive = self._compute_naive_seasonal_benchmark(daily_df)

        metrics = {
            "total_return_pct": round(total_return, 2),
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "buy_hold_return_pct": round(buy_hold_return, 2),
            "naive_seasonal_return_pct": round(naive, 2),
            "total_trades": len(trades_df),
            "num_days": len(daily_df),
        }

        if not trades_df.empty:
            injects = trades_df[trades_df["action"] == "inject"]
            withdrawals = trades_df[trades_df["action"] == "withdraw"]

            metrics["num_injections"] = len(injects)
            metrics["num_withdrawals"] = len(withdrawals)
            metrics["avg_inject_price"] = round(injects["price"].mean(), 2) if len(injects) > 0 else 0
            metrics["avg_withdraw_price"] = round(withdrawals["price"].mean(), 2) if len(withdrawals) > 0 else 0

            if metrics["avg_inject_price"] > 0 and metrics["avg_withdraw_price"] > 0:
                metrics["spread_captured_pct"] = round(
                    (metrics["avg_withdraw_price"] / metrics["avg_inject_price"] - 1) * 100, 2
                )
            else:
                metrics["spread_captured_pct"] = 0.0

            # Injection efficiency: fraction of inject-season days that had injections
            inject_season_days = daily_df[daily_df.index.month.isin(self.config.inject_months)]
            inject_days_active = inject_season_days[inject_season_days["action"] == "inject"]
            metrics["inject_efficiency_pct"] = round(
                len(inject_days_active) / max(len(inject_season_days), 1) * 100, 1
            )

            # Withdrawal efficiency
            withdraw_season_days = daily_df[daily_df.index.month.isin(self.config.withdraw_months)]
            withdraw_days_active = withdraw_season_days[withdraw_season_days["action"] == "withdraw"]
            metrics["withdraw_efficiency_pct"] = round(
                len(withdraw_days_active) / max(len(withdraw_season_days), 1) * 100, 1
            )

            # Off-season trade counts
            metrics["off_season_injects"] = len(injects[~injects.index.month.isin(self.config.inject_months)])
            metrics["off_season_withdrawals"] = len(withdrawals[~withdrawals.index.month.isin(self.config.withdraw_months)])

            metrics["total_transaction_costs"] = round(
                sum(t.transaction_cost for t in self.trades), 2
            )
        else:
            metrics.update({
                "num_injections": 0, "num_withdrawals": 0,
                "avg_inject_price": 0, "avg_withdraw_price": 0,
                "spread_captured_pct": 0, "inject_efficiency_pct": 0,
                "withdraw_efficiency_pct": 0, "off_season_injects": 0,
                "off_season_withdrawals": 0, "total_transaction_costs": 0,
            })

        return metrics

    def _compute_naive_seasonal_benchmark(self, daily_df: pd.DataFrame) -> float:
        """Naive seasonal benchmark: fully invested during withdrawal months, cash otherwise.
        This is a fairer comparison than buy-and-hold since the storage strategy
        is designed to hold varying exposure.
        """
        initial_value = daily_df["portfolio_value"].iloc[0]
        prices = daily_df["price"]
        in_market = pd.Series(daily_df.index.month.isin(self.config.withdraw_months), index=daily_df.index)

        # Track benchmark: buy at start of withdraw season, sell at end
        benchmark_value = initial_value
        position = 0  # shares held
        cash = initial_value

        for i in range(1, len(daily_df)):
            today_in = in_market.iloc[i]
            yesterday_in = in_market.iloc[i - 1]

            if today_in and not yesterday_in:
                # Enter: buy as many shares as cash allows
                position = int(cash / prices.iloc[i])
                cash -= position * prices.iloc[i]
            elif not today_in and yesterday_in:
                # Exit: sell all
                cash += position * prices.iloc[i]
                position = 0

        # Final value
        benchmark_value = cash + position * prices.iloc[-1]
        return (benchmark_value / initial_value - 1) * 100


class StorageEngine:
    """Main simulation engine: runs day-by-day storage optimization.

    Key design choices informed by research:
    - Bang-bang control: when signal crosses threshold, trade at full rate (Secomandi 2010)
    - Linear ratchets: injection/withdrawal rates vary with inventory level
    - Seasonal discipline: off-season trades are penalized or blocked
    """

    def __init__(self, config: StorageConfig):
        self.config = config
        self.signal_engine = StorageSignalEngine(config)

    def run(self, df: pd.DataFrame) -> StorageBacktestResults:
        """Execute the full backtest simulation."""
        cfg = self.config
        signals_df = self.signal_engine.compute_composite_signal(df)
        monthly_stats = self.signal_engine.compute_monthly_seasonality(df)

        # Merge price and signals
        sim = df[["Close"]].copy()
        sim = sim.join(signals_df)
        sim = sim.dropna()

        inventory = cfg.initial_inventory
        cash = cfg.initial_capital - (inventory * sim["Close"].iloc[0])

        trades: List[StorageTrade] = []
        daily_states: List[StorageDayState] = []

        initial_portfolio = cash + inventory * sim["Close"].iloc[0]

        # Precompute months remaining to best withdrawal month for intrinsic calc
        withdraw_stats = monthly_stats.loc[monthly_stats.index.isin(cfg.withdraw_months)]
        best_withdraw_month = withdraw_stats["mean_return"].idxmax() if not withdraw_stats.empty else 1

        for i, (date, row) in enumerate(sim.iterrows()):
            price = row["Close"]
            composite = row["composite"]
            seasonal = row["seasonal_score"]
            zscore = row["zscore"]
            momentum = row["momentum"]

            # Decide action
            current_month = date.month
            action, units = self._decide(composite, inventory, price, cash, current_month)

            # Execute
            tx_cost = 0.0
            if action == "inject" and units > 0:
                cost = units * price
                tx_cost = cost * cfg.transaction_cost_pct
                cash -= (cost + tx_cost)
                inventory += units
                trades.append(StorageTrade(
                    date=date, action="inject", units=units, price=price,
                    transaction_cost=tx_cost,
                    inventory_before=inventory - units, inventory_after=inventory,
                    composite_signal=composite, seasonal_score=seasonal,
                    zscore=zscore, momentum=momentum,
                ))
            elif action == "withdraw" and units > 0:
                revenue = units * price
                tx_cost = revenue * cfg.transaction_cost_pct
                cash += (revenue - tx_cost)
                inventory -= units
                trades.append(StorageTrade(
                    date=date, action="withdraw", units=units, price=price,
                    transaction_cost=tx_cost,
                    inventory_before=inventory + units, inventory_after=inventory,
                    composite_signal=composite, seasonal_score=seasonal,
                    zscore=zscore, momentum=momentum,
                ))
            else:
                action = "hold"
                units = 0

            portfolio_value = cash + inventory * price
            cumulative_pnl = portfolio_value - initial_portfolio

            # Value decomposition
            intrinsic = self._compute_intrinsic_value(
                price, inventory, date, monthly_stats, best_withdraw_month
            )
            optionality = self._compute_optionality(
                sim["Close"].iloc[max(0, i - 63):i + 1], inventory, date,
                best_withdraw_month
            )

            daily_states.append(StorageDayState(
                date=date, price=price, inventory=inventory,
                cash=cash, portfolio_value=portfolio_value,
                composite_signal=composite, seasonal_score=seasonal,
                zscore=zscore, momentum=momentum,
                action=action, units_transacted=units,
                intrinsic_value=intrinsic, optionality_value=optionality,
                cumulative_pnl=cumulative_pnl,
            ))

        return StorageBacktestResults(
            trades=trades, daily_states=daily_states, config=cfg
        )

    def _decide(
        self, composite: float, inventory: int, price: float, cash: float,
        current_month: int,
    ) -> Tuple[str, int]:
        """Apply bang-bang decision logic with physical constraints and seasonal gate.

        Bang-bang control (Secomandi 2010): optimal storage policy is always
        inject at max rate, withdraw at max rate, or do nothing.
        """
        cfg = self.config

        # Apply seasonal gate
        effective_composite = composite
        if cfg.seasonal_gate == "hard":
            # Block off-season trades entirely
            if composite > 0 and current_month not in cfg.inject_months:
                effective_composite = 0.0
            elif composite < 0 and current_month not in cfg.withdraw_months:
                effective_composite = 0.0
        elif cfg.seasonal_gate == "soft":
            # Penalize off-season trades
            if composite > 0 and current_month not in cfg.inject_months:
                effective_composite *= cfg.seasonal_penalty
            elif composite < 0 and current_month not in cfg.withdraw_months:
                effective_composite *= cfg.seasonal_penalty

        if effective_composite > cfg.inject_signal_threshold:
            # Bang-bang: inject at full effective rate
            effective_rate = cfg.effective_inject_rate(inventory)
            capacity_available = cfg.max_inventory - inventory
            affordable = int(cash / (price * (1 + cfg.transaction_cost_pct))) if price > 0 else 0
            units = min(effective_rate, capacity_available, affordable)
            if units > 0:
                return "inject", units

        elif effective_composite < cfg.withdraw_signal_threshold:
            # Bang-bang: withdraw at full effective rate
            effective_rate = cfg.effective_withdraw_rate(inventory)
            above_cushion = inventory - cfg.min_inventory
            units = min(effective_rate, above_cushion)
            if units > 0:
                return "withdraw", units

        return "hold", 0

    def _compute_intrinsic_value(
        self,
        current_price: float,
        inventory: int,
        current_date: datetime,
        monthly_stats: pd.DataFrame,
        best_withdraw_month: int,
    ) -> float:
        """Estimate intrinsic value: the locked-in profit from holding inventory
        through to the seasonal peak withdrawal month.

        In gas storage terms, this is the calendar spread value:
        (forward price at withdrawal peak) - (current spot) x inventory.

        In a real model, the forward price comes from the futures curve.
        Here we estimate it from empirical monthly seasonal returns.
        """
        cfg = self.config
        current_month = current_date.month

        # If we're already at the peak withdrawal month, intrinsic is ~0
        # (no spread left to capture)
        if current_month == best_withdraw_month:
            return 0.0

        # Sum mean monthly returns from current month to best withdrawal month
        cumulative = 0.0
        m = current_month
        months_traversed = 0
        while m != best_withdraw_month and months_traversed < 12:
            m = m % 12 + 1
            months_traversed += 1
            if m in monthly_stats.index:
                cumulative += monthly_stats.loc[m, "mean_return"]

        forward_price = current_price * (1 + cumulative)
        spread = forward_price - current_price
        # Only sell-side transaction cost — the buy is already a sunk cost
        tx_cost = current_price * cfg.transaction_cost_pct

        intrinsic = (spread - tx_cost) * inventory
        return round(intrinsic, 2)

    def _compute_optionality(
        self, price_series: pd.Series, inventory: int,
        current_date: datetime, best_withdraw_month: int,
    ) -> float:
        """Optionality value based on volatility, spare capacity, and time remaining.

        Extrinsic value in real storage depends on:
        1. Price volatility (more vol = more opportunities)
        2. Spare capacity (room to inject on dips) + inventory above cushion (room to withdraw on spikes)
        3. Time remaining to peak withdrawal (more time = more optionality)
        """
        if len(price_series) < 10:
            return 0.0

        cfg = self.config
        daily_vol = price_series.pct_change().std()
        annualized_vol = daily_vol * np.sqrt(252)
        last_price = price_series.iloc[-1]

        # Spare capacity for injection
        spare_capacity = cfg.max_inventory - inventory
        # Spare inventory for withdrawal (above cushion)
        above_cushion = inventory - cfg.min_inventory
        # Total degrees of freedom — optionality is highest when both directions are available
        flexibility = spare_capacity + above_cushion

        # Time decay: months remaining to peak withdrawal
        current_month = current_date.month
        months_to_peak = 0
        m = current_month
        while m != best_withdraw_month and months_to_peak < 12:
            m = m % 12 + 1
            months_to_peak += 1
        time_factor = months_to_peak / 12.0  # 0 at peak, ~1 at start of injection

        # Optionality ~ vol × price × flexibility × time_factor × scaling
        optionality = 0.3 * annualized_vol * last_price * flexibility * max(time_factor, 0.1)
        return round(optionality, 2)
