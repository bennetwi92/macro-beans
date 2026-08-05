"""Figures for the report.

Colour discipline follows the house data-viz method rather than matplotlib's
defaults:

* At most **three** categorical hues carry identity (blue / orange / aqua).
  Those three slots are validated all-pairs for colour-vision deficiency
  (worst pair deutan dE 9.2, normal-vision dE 24.0). Charts with more series
  than that use *emphasis* -- a few highlighted, the rest in recessive grey --
  rather than cycling hues, because a fourteen-colour legend is unreadable and
  fails CVD by construction.
* Aqua sits below 3:1 against the light surface, so every series carries a
  visible direct label. That is the documented relief for a contrast warning,
  not an optional flourish.
* One y-axis per plot, always. Never two scales on one chart.
* Grid and axes are recessive; the data is the darkest thing on the page.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from src.rebalancing.config import CHARTS_DIR  # noqa: E402
from src.rebalancing.metrics import drawdown_curve  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8880"
GRID = "#e6e5e1"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")
RECESSIVE = "#cfcec8"
POSITIVE = "#2a78d6"
NEGATIVE = "#e34948"

# The non-investable reference policy, excluded from scale-sensitive charts.
CONTROL = "Daily (constant mix)"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_SECONDARY,
        "axes.titlecolor": INK,
        "text.color": INK,
        "xtick.color": INK_SECONDARY,
        "ytick.color": INK_SECONDARY,
        "grid.color": GRID,
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "figure.dpi": 130,
        "savefig.bbox": "tight",
    }
)

_PCT = FuncFormatter(lambda v, _: f"{v:.0%}")


def _style(ax: plt.Axes, *, title: str = "", subtitle: str = "", ylabel: str = "") -> None:
    ax.grid(True, linewidth=0.6, alpha=0.9)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if title:
        ax.set_title(title, loc="left", pad=18 if subtitle else 8)
    if subtitle:
        ax.text(
            0.0,
            1.02,
            subtitle,
            transform=ax.transAxes,
            fontsize=9,
            color=INK_SECONDARY,
            va="bottom",
        )
    if ylabel:
        ax.set_ylabel(ylabel)


def _save(fig: plt.Figure, name: str) -> Path:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHARTS_DIR / name
    fig.savefig(path)
    plt.close(fig)
    return path


def _spread(values: list[float], min_gap: float) -> list[float]:
    """Push values apart so labels do not overlap, preserving their order."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = list(values)
    for position, index in enumerate(order):
        if position == 0:
            continue
        previous = out[order[position - 1]]
        if out[index] - previous < min_gap:
            out[index] = previous + min_gap
    return out


def _label_ends(
    series: dict[str, pd.Series], ax: plt.Axes, colours: tuple[str, ...] = SERIES
) -> None:
    """Direct-label several lines at their right edge without collisions.

    Direct labels are the documented relief for the aqua slot's sub-3:1
    contrast against the light surface, so they are not optional here -- which
    means they have to be readable, hence the de-collision.
    """
    names = list(series)
    log_scale = ax.get_yscale() == "log"

    def _fwd(v: float) -> float:
        return float(np.log10(v)) if log_scale else float(v)

    def _inv(v: float) -> float:
        return float(10**v) if log_scale else float(v)

    ends = [_fwd(float(series[n].iloc[-1])) for n in names]
    lo, hi = (_fwd(v) for v in ax.get_ylim())
    positioned = _spread(ends, (hi - lo) * 0.05)

    x_end = series[names[0]].index[-1]
    for i, name in enumerate(names):
        displaced = abs(positioned[i] - ends[i]) > (hi - lo) * 0.002
        ax.annotate(
            name,
            xy=(x_end, _inv(ends[i])),
            xytext=(10, _inv(positioned[i])),
            textcoords=("offset points", "data"),
            color=colours[i],
            fontsize=9,
            fontweight="bold",
            va="center",
            annotation_clip=False,
            arrowprops=(
                {"arrowstyle": "-", "color": colours[i], "linewidth": 0.8}
                if displaced
                else None
            ),
        )


def _declutter(
    ax: plt.Axes, xs: list[float], ys: list[float], texts: list[str]
) -> None:
    """Scatter point labels, nudged apart vertically with leader lines."""
    lo, hi = ax.get_ylim()
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    placed = _spread([ys[i] for i in order], (hi - lo) * 0.05)
    for slot, index in enumerate(order):
        target_y = placed[slot]
        ax.annotate(
            texts[index],
            xy=(xs[index], ys[index]),
            xytext=(10, target_y),
            textcoords=("offset points", "data"),
            fontsize=8,
            color=INK_SECONDARY,
            va="center",
            arrowprops=(
                {"arrowstyle": "-", "color": GRID, "linewidth": 0.8}
                if abs(target_y - ys[index]) > (hi - lo) * 0.005
                else None
            ),
        )


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def equity_curves(
    wealth: dict[str, pd.Series], highlight: list[str], currency: str
) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5.6))
    for name, series in wealth.items():
        if name in highlight:
            continue
        ax.plot(series.index, series / series.iloc[0], color=RECESSIVE, linewidth=1.0)
    for i, name in enumerate(highlight):
        series = wealth[name]
        norm = series / series.iloc[0]
        ax.plot(norm.index, norm, color=SERIES[i], linewidth=2.0, label=name, zorder=5)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}x"))
    _style(
        ax,
        title=f"Growth of £1, {currency}, by rebalancing policy",
        subtitle=(
            f"Log scale. Grey lines are the other {len(wealth) - len(highlight)} "
            "policies — they overlap almost entirely. The one clearly below is "
            "the daily constant-mix control, eaten by trading costs."
        ),
        ylabel="Multiple of starting wealth",
    )
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    _label_ends(
        {name: wealth[name] / wealth[name].iloc[0] for name in highlight}, ax
    )
    return _save(fig, "equity_curves.png")


def drawdowns(wealth: dict[str, pd.Series], highlight: list[str]) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5.0))
    for name, series in wealth.items():
        if name in highlight:
            continue
        ax.plot(
            series.index,
            drawdown_curve(series.pct_change().fillna(0.0)),
            color=RECESSIVE,
            linewidth=0.9,
        )
    for i, name in enumerate(highlight):
        curve = drawdown_curve(wealth[name].pct_change().fillna(0.0))
        ax.plot(curve.index, curve, color=SERIES[i], linewidth=1.8, label=name, zorder=5)
    ax.yaxis.set_major_formatter(_PCT)
    _style(
        ax,
        title="Drawdown from previous peak",
        subtitle="Rebalancing changes the depth of drawdowns far more reliably than it changes returns.",
        ylabel="Drawdown",
    )
    ax.legend(frameon=False, loc="lower left", fontsize=9)
    return _save(fig, "drawdowns.png")


def rolling_correlations(
    equity_bond: pd.Series, equity_gold: pd.Series, currency: str
) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5.0))
    ax.axhline(0.0, color=INK_MUTED, linewidth=1.0)
    for i, (series, label) in enumerate(
        ((equity_bond, "Equity vs bonds"), (equity_gold, "Equity vs gold"))
    ):
        ax.plot(series.index, series, color=SERIES[i], linewidth=1.8, label=label)
    ax.axvspan(
        pd.Timestamp("2022-01-01"),
        pd.Timestamp("2022-12-31"),
        color=INK_MUTED,
        alpha=0.12,
        zorder=0,
    )
    ax.annotate(
        "2022",
        xy=(pd.Timestamp("2022-07-01"), ax.get_ylim()[1] * 0.92),
        ha="center",
        fontsize=9,
        color=INK_SECONDARY,
    )
    _style(
        ax,
        title=f"Rolling 52-week correlation with global equities ({currency})",
        subtitle=(
            "Weekly returns — daily sampling is contaminated by the LBMA fix "
            "being struck 5½ hours before the US close."
        ),
        ylabel="Correlation",
    )
    ax.legend(frameon=False, loc="lower left", fontsize=9)
    _label_ends({"Equity vs bonds": equity_bond, "Equity vs gold": equity_gold}, ax)
    return _save(fig, "rolling_correlations.png")


def turnover_vs_return(frame: pd.DataFrame) -> Path:
    # The daily constant-mix control is excluded: at 115% turnover it is an
    # order of magnitude off every investable policy and would compress the
    # rest of the chart into a single blob. It is reported in the tables.
    frame = frame[frame["policy"] != CONTROL]
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    x = (frame["turnover_per_year"] * 100).tolist()
    y = (frame["cagr"] * 100).tolist()
    sizes = 40 + frame["cost_drag_bps"] * 12
    ax.scatter(
        x, y, s=sizes, color=SERIES[0], alpha=0.85, edgecolor=SURFACE, linewidth=1.5,
        zorder=5,
    )
    ax.set_xlim(-2, max(x) * 1.55)
    _declutter(ax, x, y, frame["policy"].tolist())
    _style(
        ax,
        title="More trading did not buy more return",
        subtitle=(
            "Marker size is annual cost drag. 60/20/20, GBP. The daily "
            "constant-mix control (115% turnover, 7.2% CAGR) is off-chart."
        ),
        ylabel="CAGR (%)",
    )
    ax.set_xlabel("Annual one-way turnover (% of portfolio)")
    return _save(fig, "turnover_vs_return.png")


def bootstrap_distributions(results: list, benchmark: str) -> Path:
    """Small multiples: one histogram per policy, shared x-axis."""
    results = [r for r in results if r.policy != CONTROL]
    n = len(results)
    ncols = 3
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(
        nrows, ncols, figsize=(11, 2.5 * nrows), sharex=True, sharey=True
    )
    flat = axes.flatten()
    lo = min(np.percentile(r.differences_bps, 0.5) for r in results)
    hi = max(np.percentile(r.differences_bps, 99.5) for r in results)
    bins = np.linspace(lo, hi, 60)

    for ax, result in zip(flat, results):
        ax.hist(result.differences_bps, bins=bins, color=SERIES[0], alpha=0.85)
        ax.axvline(0.0, color=NEGATIVE, linewidth=1.4)
        ax.set_title(
            f"{result.policy}\n{result.share_policy_wins:.0%} of paths beat {benchmark}",
            loc="left",
            fontsize=9,
            fontweight="normal",
            color=INK_SECONDARY,
        )
        ax.grid(True, linewidth=0.5, alpha=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.set_yticks([])
    for ax in flat[n:]:
        ax.set_visible(False)

    fig.suptitle(
        f"Bootstrap: CAGR difference vs {benchmark} (bps/yr)",
        x=0.02,
        ha="left",
        fontsize=12,
        fontweight="bold",
    )
    fig.text(
        0.02,
        0.955,
        f"Stationary-block resamples, mean block 63 days. Red line is zero — "
        f"distributions straddling it are noise. The {CONTROL.lower()} control "
        "is excluded; it loses ~200bps/yr to costs and would flatten the rest.",
        fontsize=9,
        color=INK_SECONDARY,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return _save(fig, "bootstrap_distributions.png")


def weight_drift(weights: dict[str, pd.Series], target: float) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5.0))
    ax.axhline(target, color=INK_MUTED, linewidth=1.2, linestyle="--")
    ax.annotate(
        f"target {target:.0%}",
        xy=(list(weights.values())[0].index[10], target),
        xytext=(0, -14),
        textcoords="offset points",
        fontsize=9,
        color=INK_SECONDARY,
    )
    for i, (name, series) in enumerate(weights.items()):
        ax.plot(series.index, series, color=SERIES[i], linewidth=1.6, label=name)
    ax.yaxis.set_major_formatter(_PCT)
    _style(
        ax,
        title="Realised equity weight over time",
        subtitle="This is what rebalancing actually controls: how far the portfolio drifts from the risk you chose.",
        ylabel="Equity weight",
    )
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    _label_ends(weights, ax)
    return _save(fig, "weight_drift.png")


def crash_windows(frame: pd.DataFrame, policies: list[str]) -> Path:
    events = list(dict.fromkeys(frame["event"]))
    panels = [
        ("drawdown_window_return", "Return during the fall"),
        ("post_1y_cagr", "1 year from the trough"),
        ("post_3y_cagr", "3 years from the trough (p.a.)"),
        ("post_5y_cagr", "5 years from the trough (p.a.)"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.4))
    width = 0.8 / len(policies)

    for ax, (column, title) in zip(axes.flatten(), panels):
        positions = np.arange(len(events))
        for i, policy in enumerate(policies):
            sub = frame[frame["policy"] == policy].set_index("event")
            values = [sub[column].get(e, np.nan) for e in events]
            ax.bar(
                positions + i * width - 0.4 + width / 2,
                values,
                width=width * 0.88,  # 2px-equivalent gap between adjacent bars
                color=SERIES[i],
                label=policy,
            )
        ax.axhline(0.0, color=INK_MUTED, linewidth=1.0)
        ax.set_xticks(positions)
        ax.set_xticklabels(events, fontsize=9)
        ax.yaxis.set_major_formatter(_PCT)
        _style(ax, title=title)

    axes[0, 0].legend(frameon=False, fontsize=8, loc="lower left")
    fig.suptitle(
        "Crash-conditional performance, per event",
        x=0.02,
        ha="left",
        fontsize=12,
        fontweight="bold",
    )
    fig.text(
        0.02,
        0.945,
        f"All {len(events)} equity drawdowns of 15%+ in the sample, shown per "
        "event and never averaged — a mean would hide whether the effect is "
        "consistent or driven by one episode. Blank bars: not enough history yet.",
        fontsize=9,
        color=INK_SECONDARY,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _save(fig, "crash_windows.png")


def rolling_difference(frame: pd.DataFrame, policies: list[str], years: int) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5.0))
    ax.axhline(0.0, color=INK_MUTED, linewidth=1.2)
    lines: dict[str, pd.Series] = {}
    for i, policy in enumerate(policies):
        series = pd.Series(frame[policy].to_numpy(), index=frame["end"])
        lines[policy] = series
        ax.plot(series.index, series, color=SERIES[i], linewidth=1.8, label=policy)
    _style(
        ax,
        title=f"Rolling {years}-year CAGR difference vs monthly rebalancing",
        subtitle=(
            "Overlapping windows — these show consistency across eras, not "
            "statistical significance. The bootstrap does that job."
        ),
        ylabel="Difference (bps per year)",
    )
    ax.set_xlabel(f"End of {years}-year window")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    _label_ends(lines, ax)
    return _save(fig, f"rolling_{years}y_difference.png")


def decomposition(frame: pd.DataFrame) -> Path:
    """Stacked contribution bars: why each policy differs from monthly."""
    ordered = frame[frame["policy"] != CONTROL].sort_values("cagr")
    labels = ordered["policy"].tolist()
    positions = np.arange(len(labels))
    components = [
        ("allocation_effect_bps", "Allocation (held more equity)", SERIES[1]),
        ("rebalancing_effect_bps", "Rebalancing (the actual effect)", SERIES[0]),
        ("cost_effect_bps", "Costs avoided vs monthly", SERIES[2]),
    ]

    fig, ax = plt.subplots(figsize=(10, 6.2))
    left_pos = np.zeros(len(labels))
    left_neg = np.zeros(len(labels))
    for column, label, colour in components:
        values = ordered[column].to_numpy()
        starts = np.where(values >= 0, left_pos, left_neg)
        ax.barh(
            positions,
            values,
            left=starts,
            color=colour,
            label=label,
            height=0.7,
            edgecolor=SURFACE,
            linewidth=1.5,  # the 2px surface gap between stacked segments
        )
        left_pos += np.where(values >= 0, values, 0.0)
        left_neg += np.where(values < 0, values, 0.0)

    ax.axvline(0.0, color=INK, linewidth=1.2)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=9)
    _style(
        ax,
        title="Where each policy's difference from monthly rebalancing comes from",
        subtitle=(
            "Components sum exactly to the realised CAGR difference. Orange is "
            "not skill — it is extra equity risk. Daily constant mix excluded "
            "(-207bps, almost all cost)."
        ),
    )
    ax.set_xlabel("Contribution to CAGR difference vs monthly (bps per year)")
    ax.legend(
        frameon=False, fontsize=9, loc="lower center",
        bbox_to_anchor=(0.5, -0.30), ncol=3,
    )
    return _save(fig, "decomposition.png")


def fx_effect(gbp: pd.Series, usd: pd.Series) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5.0))
    normalised = {
        label: series / series.iloc[0]
        for label, series in (("In sterling", gbp), ("In dollars", usd))
    }
    for i, (label, norm) in enumerate(normalised.items()):
        ax.plot(norm.index, norm, color=SERIES[i], linewidth=1.9, label=label)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}x"))
    _style(
        ax,
        title="The same portfolio, measured in two currencies",
        subtitle=(
            "Unhedged FX is a first-order driver of a UK investor's experience — "
            "larger than any rebalancing policy choice in this study."
        ),
        ylabel="Multiple of starting wealth",
    )
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    _label_ends(normalised, ax)
    return _save(fig, "fx_effect.png")


__all__ = [
    "bootstrap_distributions",
    "crash_windows",
    "decomposition",
    "drawdowns",
    "equity_curves",
    "fx_effect",
    "rolling_correlations",
    "rolling_difference",
    "turnover_vs_return",
    "weight_drift",
]
