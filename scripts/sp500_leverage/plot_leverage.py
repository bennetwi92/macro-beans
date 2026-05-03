"""Charts for sp500_leverage analysis. Reads outputs from leverage_analysis.py."""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "sp500_leverage"
OUT = DATA_DIR


def main() -> None:
    nav = pd.read_csv(DATA_DIR / "nav_series.csv", index_col=0, parse_dates=True)
    monthly = pd.read_csv(DATA_DIR / "monthly_returns.csv", index_col=0, parse_dates=True)

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))

    ax = axes[0, 0]
    nav.plot(ax=ax, logy=True, lw=1.2)
    ax.set_title("Synthetic NAV (log scale, daily-compounded, TER + financing)")
    ax.set_ylabel("NAV (start = 1)")
    ax.grid(alpha=0.3)

    ax = axes[0, 1]
    dd = nav.divide(nav.cummax()).sub(1.0).mul(100.0)
    dd.plot(ax=ax, lw=1.0)
    ax.set_title("Drawdown from running peak (%)")
    ax.set_ylabel("Drawdown %")
    ax.grid(alpha=0.3)

    ax = axes[1, 0]
    bins = 60
    for col in monthly.columns:
        ax.hist(monthly[col].mul(100), bins=bins, alpha=0.45, label=col)
    ax.axvline(0, color="k", lw=0.8)
    ax.set_title("Monthly return distribution (%)")
    ax.set_xlabel("Monthly return %")
    ax.legend()
    ax.grid(alpha=0.3)

    ax = axes[1, 1]
    p_pos = (monthly > 0).mean().mul(100)
    p_pos.plot(kind="bar", ax=ax, color=["#1f77b4", "#ff7f0e", "#d62728"])
    ax.set_title("P(monthly return > 0)")
    ax.set_ylabel("Probability %")
    ax.set_ylim(0, 75)
    for i, v in enumerate(p_pos.values):
        ax.text(i, v + 0.5, f"{v:.1f}%", ha="center")
    ax.grid(alpha=0.3, axis="y")
    plt.setp(ax.get_xticklabels(), rotation=0)

    fig.suptitle("S&P 500: 1x vs 2x vs 3x daily-leveraged (synthetic, 1988–2026)", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "leverage_overview.png", dpi=120)
    print(f"Saved {OUT / 'leverage_overview.png'}")


if __name__ == "__main__":
    main()
