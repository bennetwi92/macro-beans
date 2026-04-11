import pandas as pd

from src.strategy.base import Strategy, StrategyConfig


class MonthlySeasonal(Strategy):
    """Long during historically strong months for oil."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        long_months = self.config.params.get("long_months", [1, 2, 6, 9])
        return data["month"].isin(long_months).astype(float)

    def required_features(self) -> list[str]:
        return ["month"]


class DayOfWeekSeasonal(Strategy):
    """Long on historically positive weekdays for oil."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        # Compute historical average return by day of week using expanding window
        returns = data["close"].pct_change()
        dow = data["day_of_week"]

        signal = pd.Series(0.0, index=data.index)
        # Use a simple rule: long on days that historically have positive average returns
        # Computed on expanding window to avoid look-ahead
        for i in range(len(data)):
            if i < 252:  # Need at least 1 year of history
                continue
            hist_returns = returns.iloc[:i]
            hist_dow = dow.iloc[:i]
            today_dow = dow.iloc[i]
            avg = hist_returns[hist_dow == today_dow].mean()
            if avg > 0:
                signal.iloc[i] = 1.0

        return signal

    def required_features(self) -> list[str]:
        return ["day_of_week"]


def create_variants() -> list[Strategy]:
    return [
        MonthlySeasonal(StrategyConfig(
            name="Seasonal_Monthly",
            params={"long_months": [1, 2, 6, 9]}
        )),
        DayOfWeekSeasonal(StrategyConfig(
            name="Seasonal_DOW", params={}
        )),
    ]
