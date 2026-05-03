"""QQQ3.L positive/negative streak conditional next-day study.

Tests: does observing N consecutive positive (or negative) return days
shift the distribution of the next day's return for QQQ3.L
(WisdomTree 3x Long Nasdaq 100 ETF on the LSE)?

Outputs (under data/event_studies/):
  qqq3l_streak_rows.csv       per-day table with prior-streak labels and next-day return
  qqq3l_streak_buckets.csv    bucketed conditional stats with Wilson CIs and tests
  qqq3l_streak_magnitude.csv  secondary view conditioning on cumulative N-day return quintile
  qqq3l_streak_study.png      price + conditional-probability chart

Console: unconditional baseline, Markov 2x2 chi-square independence verdict,
both bucket tables, magnitude-view table.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import binomtest, chi2_contingency
from statsmodels.stats.proportion import proportion_confint, proportions_ztest


SYMBOL = "QQQ3.L"
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "event_studies"

MAX_N = 7  # explicit buckets 1..MAX_N, then "MAX_N+1+" catch-all
MAGNITUDE_NS = (2, 3, 4)
N_QUINTILES = 5


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)
    return df


def load(symbol: str = SYMBOL) -> pd.DataFrame:
    df = yf.download(symbol, period="max", auto_adjust=True, progress=False)
    df = _flatten(df)
    df = df[df.index.dayofweek < 5]
    df["ret"] = df["Close"].pct_change()
    df = df.dropna(subset=["ret"])
    return df


def _streak_lengths(mask: pd.Series) -> pd.Series:
    """Streak length at each row for the True runs of `mask` (0 where mask is False).

    Mirrors the idiom at src/models/features.py:189-190.
    """
    m = mask.astype(int)
    return m.groupby((m != m.shift()).cumsum()).cumsum()


def compute_streaks(df: pd.DataFrame) -> pd.DataFrame:
    ret = df["ret"]
    pos_streak = _streak_lengths(ret > 0)
    neg_streak = _streak_lengths(ret < 0)
    out = pd.DataFrame(
        {
            "date": df.index,
            "close": df["Close"].values,
            "ret": ret.values,
            "pos_streak_prior": pos_streak.shift(1).values,
            "neg_streak_prior": neg_streak.shift(1).values,
        }
    )
    out["next_ret"] = out["ret"]
    out["next_sign"] = np.sign(out["next_ret"]).astype(int)
    out = out.dropna(subset=["pos_streak_prior", "neg_streak_prior"])
    out["pos_streak_prior"] = out["pos_streak_prior"].astype(int)
    out["neg_streak_prior"] = out["neg_streak_prior"].astype(int)
    return out


def _bucket_label(n: int, max_n: int) -> str:
    return str(n) if n <= max_n else f"{max_n + 1}+"


def bucket_by_streak(df: pd.DataFrame, side: str, baseline: float) -> pd.DataFrame:
    """For each streak length N, summarise the conditional next-day distribution.

    `side` = 'pos' tests P(next_ret > 0 | N consecutive positive prior days).
    `side` = 'neg' tests P(next_ret < 0 | N consecutive negative prior days).
    Binomial p-values are tested against `baseline` (unconditional same-direction rate).
    """
    if side == "pos":
        streak_col = "pos_streak_prior"
        success_full = (df["next_ret"] > 0).astype(int)
    elif side == "neg":
        streak_col = "neg_streak_prior"
        success_full = (df["next_ret"] < 0).astype(int)
    else:
        raise ValueError(f"side must be 'pos' or 'neg', got {side!r}")

    rel = df[df[streak_col] >= 1].copy()
    rel["bucket"] = rel[streak_col].clip(upper=MAX_N + 1)

    n_base = len(df)
    k_base = int(success_full.sum())

    rows = []
    for bucket_n in sorted(rel["bucket"].unique()):
        sub = rel[rel["bucket"] == bucket_n]
        n_obs = len(sub)
        k = int(success_full.loc[sub.index].sum())
        p_dir = k / n_obs
        wlo, whi = proportion_confint(k, n_obs, method="wilson")
        bt_two = binomtest(k, n_obs, baseline, alternative="two-sided")
        bt_one = binomtest(k, n_obs, baseline, alternative="greater")
        try:
            _, p_z = proportions_ztest([k, k_base], [n_obs, n_base])
        except (ValueError, ZeroDivisionError):
            p_z = np.nan
        next_bps = sub["next_ret"] * 1e4
        rows.append(
            {
                "side": side,
                "N": _bucket_label(int(bucket_n), MAX_N),
                "n_obs": n_obs,
                "p_next_dir": round(p_dir, 4),
                "wilson_lo": round(wlo, 4),
                "wilson_hi": round(whi, 4),
                "mean_next_ret_bps": round(next_bps.mean(), 1),
                "median_next_ret_bps": round(next_bps.median(), 1),
                "std_next_ret_bps": round(next_bps.std(), 1),
                "q10_bps": round(next_bps.quantile(0.10), 1),
                "q90_bps": round(next_bps.quantile(0.90), 1),
                "binom_p_two_sided": round(bt_two.pvalue, 4),
                "binom_p_one_sided": round(bt_one.pvalue, 4),
                "ztest_vs_baseline_p": round(p_z, 4) if not np.isnan(p_z) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def markov_independence_test(ret: pd.Series) -> dict:
    """Chi-square independence test on the 2x2 (prev_pos, today_pos) contingency table."""
    s = (ret > 0).astype(int)
    df = pd.DataFrame({"prev_pos": s.shift(1), "today_pos": s}).dropna()
    df["prev_pos"] = df["prev_pos"].astype(int)
    table = pd.crosstab(df["prev_pos"], df["today_pos"])
    chi2, p, dof, _ = chi2_contingency(table)
    return {"chi2": chi2, "p_value": p, "dof": dof, "table": table}


def magnitude_view(base_df: pd.DataFrame) -> pd.DataFrame:
    """For N in MAGNITUDE_NS, condition on N positive prior days AND quintile of cumulative
    N-day return ending at the prior close. Tells us whether next-day stats track magnitude
    rather than just count.
    """
    log_ret = np.log1p(base_df["ret"])
    pos_streak = _streak_lengths(base_df["ret"] > 0)
    pos_prior = pos_streak.shift(1)

    rows = []
    for n in MAGNITUDE_NS:
        cum_prior = np.expm1(log_ret.rolling(n).sum().shift(1))
        mask = (pos_prior >= n) & cum_prior.notna()
        sub = pd.DataFrame(
            {
                "cum_prior": cum_prior[mask],
                "next_ret": base_df["ret"][mask],
            }
        )
        if len(sub) < N_QUINTILES * 5:
            continue
        sub["quintile"] = pd.qcut(
            sub["cum_prior"], N_QUINTILES, labels=[f"Q{i + 1}" for i in range(N_QUINTILES)]
        )
        for q, grp in sub.groupby("quintile", observed=True):
            n_obs = len(grp)
            k_pos = int((grp["next_ret"] > 0).sum())
            rows.append(
                {
                    "N": n,
                    "cum_ret_quintile": str(q),
                    "cum_prior_lo_pct": round(grp["cum_prior"].min() * 100, 2),
                    "cum_prior_hi_pct": round(grp["cum_prior"].max() * 100, 2),
                    "n_obs": n_obs,
                    "p_next_pos": round(k_pos / n_obs, 4),
                    "mean_next_ret_bps": round((grp["next_ret"] * 1e4).mean(), 1),
                    "median_next_ret_bps": round((grp["next_ret"] * 1e4).median(), 1),
                }
            )
    return pd.DataFrame(rows)


def plot(
    base_df: pd.DataFrame,
    bucket_pos: pd.DataFrame,
    bucket_neg: pd.DataFrame,
    baseline: float,
    png_path: Path,
) -> None:
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(13, 9), gridspec_kw={"height_ratios": [1, 1.4]}
    )

    ax1.plot(base_df.index, base_df["Close"], color="navy", lw=1.0)
    ax1.set_yscale("log")
    ax1.set_ylabel("QQQ3.L close (log)")
    ax1.set_title(
        f"QQQ3.L price ({base_df.index[0].date()} → {base_df.index[-1].date()})"
    )
    ax1.grid(alpha=0.3)

    labels = sorted(set(bucket_pos["N"].tolist()) | set(bucket_neg["N"].tolist()),
                    key=lambda s: (len(s), s))
    x = np.arange(len(labels))

    def _series_for(bucket_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, list]:
        m = {row["N"]: row for _, row in bucket_df.iterrows()}
        p = np.array([m[lab]["p_next_dir"] if lab in m else np.nan for lab in labels])
        lo = np.array([m[lab]["wilson_lo"] if lab in m else np.nan for lab in labels])
        hi = np.array([m[lab]["wilson_hi"] if lab in m else np.nan for lab in labels])
        ns = [int(m[lab]["n_obs"]) if lab in m else 0 for lab in labels]
        return p, lo, hi, ns

    p_pos, lo_pos, hi_pos, n_pos = _series_for(bucket_pos)
    p_neg, lo_neg, hi_neg, n_neg = _series_for(bucket_neg)

    width = 0.38
    ax2.bar(x - width / 2, p_pos, width=width, color="tab:green", alpha=0.75,
            label="positive streak: P(next > 0)")
    ax2.errorbar(x - width / 2, p_pos, yerr=np.array([p_pos - lo_pos, hi_pos - p_pos]),
                 fmt="none", color="black", capsize=3, lw=1)
    ax2.bar(x + width / 2, p_neg, width=width, color="tab:red", alpha=0.75,
            label="negative streak: P(next < 0)")
    ax2.errorbar(x + width / 2, p_neg, yerr=np.array([p_neg - lo_neg, hi_neg - p_neg]),
                 fmt="none", color="black", capsize=3, lw=1)

    for xi, ni in zip(x - width / 2, n_pos):
        if ni:
            ax2.text(xi, 0.02, f"n={ni}", ha="center", va="bottom", fontsize=8, color="dimgrey")
    for xi, ni in zip(x + width / 2, n_neg):
        if ni:
            ax2.text(xi, 0.02, f"n={ni}", ha="center", va="bottom", fontsize=8, color="dimgrey")

    ax2.axhline(baseline, color="darkgreen", lw=1.0, ls="--",
                label=f"baseline P(next > 0) = {baseline:.3f}")
    ax2.axhline(1 - baseline, color="darkred", lw=1.0, ls="--",
                label=f"baseline P(next < 0) = {1 - baseline:.3f}")

    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)
    ax2.set_xlabel("Streak length N at prior close")
    ax2.set_ylabel("Conditional probability")
    ax2.set_ylim(0, 1)
    ax2.set_title("P(next-day moves in streak direction) by N, with 95% Wilson CIs")
    ax2.legend(loc="upper right", fontsize=9)
    ax2.grid(alpha=0.3, axis="y")

    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
    plt.close(fig)


def main() -> None:
    print(f"Loading {SYMBOL}...")
    raw = load()
    print(f"  {len(raw)} rows from {raw.index[0].date()} to {raw.index[-1].date()}")

    streaks = compute_streaks(raw)
    baseline_pos = float((streaks["next_ret"] > 0).mean())
    baseline_neg = float((streaks["next_ret"] < 0).mean())
    n_zero = int((streaks["next_ret"] == 0).sum())
    print(
        f"\nUnconditional: P(ret > 0) = {baseline_pos:.4f},"
        f" P(ret < 0) = {baseline_neg:.4f},"
        f" P(ret = 0) = {n_zero / len(streaks):.4f} (n={len(streaks)})"
    )

    mk = markov_independence_test(raw["ret"])
    print("\nMarkov 2x2 chi-square test on (prev_pos, today_pos):")
    print(mk["table"])
    print(f"  chi2 = {mk['chi2']:.3f}, dof = {mk['dof']}, p = {mk['p_value']:.4f}")
    if mk["p_value"] < 0.05:
        print("  -> REJECT independence at 5% (signs are serially dependent)")
    else:
        print("  -> CANNOT REJECT independence at 5% (signs look serially independent)")

    bucket_pos = bucket_by_streak(streaks, "pos", baseline_pos)
    bucket_neg = bucket_by_streak(streaks, "neg", baseline_neg)
    print("\n=== Positive streaks: P(next > 0 | N consecutive positive prior days) ===")
    print(bucket_pos.to_string(index=False))
    print("\n=== Negative streaks: P(next < 0 | N consecutive negative prior days) ===")
    print(bucket_neg.to_string(index=False))

    mag = magnitude_view(raw)
    print("\n=== Magnitude view: positive streak, conditional on cum-return quintile ===")
    if mag.empty:
        print("  (insufficient sample)")
    else:
        print(mag.to_string(index=False))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows_path = OUT_DIR / "qqq3l_streak_rows.csv"
    buckets_path = OUT_DIR / "qqq3l_streak_buckets.csv"
    mag_path = OUT_DIR / "qqq3l_streak_magnitude.csv"
    png_path = OUT_DIR / "qqq3l_streak_study.png"

    streaks_out = streaks.copy()
    streaks_out["date"] = streaks_out["date"].dt.strftime("%Y-%m-%d")
    streaks_out.to_csv(rows_path, index=False)
    pd.concat([bucket_pos, bucket_neg], ignore_index=True).to_csv(buckets_path, index=False)
    mag.to_csv(mag_path, index=False)
    plot(raw, bucket_pos, bucket_neg, baseline_pos, png_path)

    print(f"\nWrote: {rows_path}")
    print(f"       {buckets_path}")
    print(f"       {mag_path}")
    print(f"       {png_path}")


if __name__ == "__main__":
    main()
