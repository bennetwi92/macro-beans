"""Co-crash mean-reversion study: SPX vs NDX beta-hedged pair.

Hypothesis: on days when both S&P 500 and Nasdaq 100 crash hard (both daily
returns in the extreme left tail vs trailing vol), the beta-hedged residual
mean-reverts on the next session more reliably than either outright index.

Trade convention modelled here matches a real Trading 212 / LSE LETF workflow:
  * Crash detection uses close-to-close (cc) returns on day t.
  * Trade enters at the OPEN of day t+1 and exits at the CLOSE of day t+1.
    Forward returns are therefore open-to-close (oc) on the day after the
    event, not close-to-close.

Construction:
  beta[t]      = cov(r_ndx_cc, r_spx_cc over t-LOOKBACK..t-1) / var(same)
  r_pair_cc[t] = r_ndx_cc[t] - beta[t] * r_spx_cc[t]      # event detection
  r_pair_oc[t] = r_ndx_oc[t] - beta[t] * r_spx_oc[t]      # trade return
  z_x[t]       = r_x_cc[t] / rolling_std(r_x_cc, LOOKBACK, shifted)

Co-crash event: z_spx[t] < CRASH_Z AND z_ndx[t] < CRASH_Z.

Regime sub-sample: results are reported for the full sample AND for the
post-COVID regime (REGIME_START) where structurally low rates, retail flow,
and faster algorithmic mean-reversion arguably make the modern dynamics
non-stationary vs 1990s/2000s data.

LETF expression of the long-NDX / short-SPX reversion trade:
  QQQ3.L  weight = 1 / (1 + beta)
  3USS.L  weight = beta / (1 + beta)
  r_letf_oc = (3 / (1 + beta)) * r_pair_oc

Outputs:
  data/event_studies/spx_ndx_cocrash_daily.csv     full daily series
  data/event_studies/spx_ndx_cocrash_events.csv    one row per co-crash event
  data/event_studies/spx_ndx_cocrash_reversion.png equity curve + diagnostics
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

LOOKBACK = 60
CRASH_Z = -2.0
BOOTSTRAP_N = 2000
SEED = 7
START = "1985-10-01"        # NDX history begins Oct 1985
REGIME_START = "2020-03-01"  # post-COVID regime


def fetch_prices() -> pd.DataFrame:
    raw = yf.download(["^GSPC", "^NDX"], start=START, progress=False, auto_adjust=True)
    opens = raw["Open"].copy()
    closes = raw["Close"].copy()
    opens.columns = ["ndx" if c == "^NDX" else "spx" for c in opens.columns]
    closes.columns = ["ndx" if c == "^NDX" else "spx" for c in closes.columns]
    df = pd.DataFrame({
        "open_spx":  opens["spx"],
        "open_ndx":  opens["ndx"],
        "close_spx": closes["spx"],
        "close_ndx": closes["ndx"],
    }).dropna()
    return df


def build_pair(prices: pd.DataFrame) -> pd.DataFrame:
    r_spx_cc = prices["close_spx"].pct_change()
    r_ndx_cc = prices["close_ndx"].pct_change()
    r_spx_oc = prices["close_spx"] / prices["open_spx"] - 1.0
    r_ndx_oc = prices["close_ndx"] / prices["open_ndx"] - 1.0

    cov = r_ndx_cc.rolling(LOOKBACK).cov(r_spx_cc)
    var = r_spx_cc.rolling(LOOKBACK).var()
    beta = (cov / var).shift(1)
    sd_spx = r_spx_cc.rolling(LOOKBACK).std().shift(1)
    sd_ndx = r_ndx_cc.rolling(LOOKBACK).std().shift(1)

    r_pair_cc = r_ndx_cc - beta * r_spx_cc
    r_pair_oc = r_ndx_oc - beta * r_spx_oc
    z_spx = r_spx_cc / sd_spx
    z_ndx = r_ndx_cc / sd_ndx

    out = pd.DataFrame({
        "r_spx_cc": r_spx_cc, "r_ndx_cc": r_ndx_cc,
        "r_spx_oc": r_spx_oc, "r_ndx_oc": r_ndx_oc,
        "beta":     beta,
        "z_spx":    z_spx, "z_ndx": z_ndx,
        "r_pair_cc": r_pair_cc, "r_pair_oc": r_pair_oc,
    }).dropna()

    # Forward open-to-close returns: the next session's intraday move.
    # beta to use for sizing on t+1 is beta.shift(-1) at index t (= rolling through t).
    out["fwd1_pair_oc"] = out["r_pair_oc"].shift(-1)
    out["fwd1_spx_oc"]  = out["r_spx_oc"].shift(-1)
    out["fwd1_ndx_oc"]  = out["r_ndx_oc"].shift(-1)
    out["fwd1_letf_oc"] = (3.0 / (1.0 + out["beta"].shift(-1))) * out["fwd1_pair_oc"]
    return out


def detect_events(df: pd.DataFrame) -> pd.DataFrame:
    mask = (df["z_spx"] < CRASH_Z) & (df["z_ndx"] < CRASH_Z)
    return df.loc[mask].copy()


def bootstrap_mean(x: np.ndarray, rng: np.random.Generator, n: int) -> np.ndarray:
    if len(x) == 0:
        return np.array([np.nan])
    idx = rng.integers(0, len(x), size=(n, len(x)))
    return x[idx].mean(axis=1)


def _report_block(events: pd.DataFrame, df: pd.DataFrame, label: str,
                  rng: np.random.Generator) -> None:
    print(f"\n{'=' * 78}")
    print(f"REGIME: {label}    sample {df.index[0].date()} -> {df.index[-1].date()}  "
          f"(n_days={len(df)})    events n={len(events)}")
    print("=" * 78)

    print("\n-- Next-session open-to-close pair return, conditional on co-crash --")
    print(f"{'split':<32}{'n':>5}{'mean':>10}{'median':>10}{'pct_pos':>10}"
          f"{'95% CI (mean)':>26}")
    splits = [
        ("all co-crash events",           events),
        ("  r_pair[t] < 0 (NDX overshot)", events[events["r_pair_cc"] < 0]),
        ("  r_pair[t] > 0 (NDX held up)",  events[events["r_pair_cc"] > 0]),
        ("  |r_pair[t]| > 0.5%",           events[events["r_pair_cc"].abs() > 0.005]),
        ("  r_pair[t] < -0.5%",            events[events["r_pair_cc"] < -0.005]),
    ]
    for name, sub in splits:
        v = sub["fwd1_pair_oc"].dropna().values
        if len(v) < 2:
            print(f"{name:<32}{len(v):>5d}  (insufficient)")
            continue
        boot = bootstrap_mean(v, rng, BOOTSTRAP_N)
        lo, hi = np.percentile(boot, [2.5, 97.5])
        print(f"{name:<32}{len(v):>5d}{v.mean()*100:>+9.2f}%"
              f"{np.median(v)*100:>+9.2f}%{(v > 0).mean()*100:>9.1f}%"
              f"{f'[{lo*100:+.2f}%, {hi*100:+.2f}%]':>26}")

    print("\n-- Reversal correlation corr(r_pair_cc[t], r_pair_oc[t+1]) --")
    ev_pairs = events[["r_pair_cc", "fwd1_pair_oc"]].dropna()
    all_pairs = df[["r_pair_cc", "fwd1_pair_oc"]].dropna()
    ev_c = ev_pairs.corr().iloc[0, 1] if len(ev_pairs) >= 2 else np.nan
    all_c = all_pairs.corr().iloc[0, 1] if len(all_pairs) >= 2 else np.nan
    print(f"  on co-crash days:  {ev_c:+.3f}  (n={len(ev_pairs)})")
    print(f"  unconditional:     {all_c:+.3f}  (n={len(all_pairs)})")

    print("\n-- Outright benchmarks: next-session open-to-close after co-crash --")
    for asset_col, asset_name in (("fwd1_spx_oc", "SPX"), ("fwd1_ndx_oc", "NDX")):
        v = events[asset_col].dropna().values
        if len(v) < 2:
            continue
        boot = bootstrap_mean(v, rng, BOOTSTRAP_N)
        lo, hi = np.percentile(boot, [2.5, 97.5])
        print(f"  {asset_name}: mean={v.mean()*100:+.2f}%  med={np.median(v)*100:+.2f}%  "
              f"pct_pos={(v > 0).mean()*100:.1f}%  "
              f"95% CI [{lo*100:+.2f}%, {hi*100:+.2f}%]  n={len(v)}")

    print("\n-- LETF wrapper (QQQ3.L + 3USS.L, beta-hedged), next-session open-to-close --")
    for name, sub in splits[:3]:
        v = sub["fwd1_letf_oc"].dropna().values
        if len(v) < 2:
            continue
        boot = bootstrap_mean(v, rng, BOOTSTRAP_N)
        lo, hi = np.percentile(boot, [2.5, 97.5])
        print(f"  {name:<32} mean={v.mean()*100:+.2f}%  pct_pos={(v > 0).mean()*100:.1f}%  "
              f"95% CI [{lo*100:+.2f}%, {hi*100:+.2f}%]  n={len(v)}")


def summarise(df: pd.DataFrame, rng: np.random.Generator) -> None:
    print(f"\nFull data: {df.index[0].date()} -> {df.index[-1].date()} (n={len(df)})")
    print(f"Beta 60d (NDX on SPX): mean={df['beta'].mean():.3f}  "
          f"median={df['beta'].median():.3f}  "
          f"p05={df['beta'].quantile(0.05):.3f}  p95={df['beta'].quantile(0.95):.3f}")

    events_full = detect_events(df)
    _report_block(events_full, df, "FULL SAMPLE (1985+)", rng)

    df_regime = df.loc[REGIME_START:]
    events_regime = detect_events(df_regime)
    _report_block(events_regime, df_regime, f"POST-COVID ({REGIME_START}+)", rng)

    print("\n-- Most recent 12 events (full sample) --")
    cols = ["r_spx_cc", "r_ndx_cc", "z_spx", "z_ndx", "beta",
            "r_pair_cc", "fwd1_pair_oc", "fwd1_letf_oc"]
    print(events_full.tail(12)[cols].round(4).to_string())


def plot(df: pd.DataFrame, events_full: pd.DataFrame,
         events_regime: pd.DataFrame, df_regime: pd.DataFrame,
         out_path: Path) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(11, 13))

    eq = (1.0 + df["r_pair_cc"]).cumprod()
    eq.plot(ax=axes[0], color="C0", lw=0.9, label="Beta-hedged NDX/SPX pair (cc, 1x)")
    axes[0].scatter(events_full.index, eq.reindex(events_full.index),
                    color="C7", s=14, alpha=0.6, label=f"Pre-2020 events")
    axes[0].scatter(events_regime.index, eq.reindex(events_regime.index),
                    color="C3", s=28, zorder=5,
                    label=f"Post-COVID events (n={len(events_regime)})")
    axes[0].axvline(pd.Timestamp(REGIME_START), color="black", ls=":", lw=1)
    axes[0].set_title(f"Beta-hedged Long NDX / Short SPX — equity curve "
                      f"(lookback={LOOKBACK}d)")
    axes[0].set_ylabel("$1 start, no costs")
    axes[0].legend(loc="best"); axes[0].grid(alpha=0.3)

    uncond = df_regime["fwd1_pair_oc"].dropna() * 100
    cond = events_regime["fwd1_pair_oc"].dropna() * 100
    axes[1].hist(uncond, bins=80, color="C0", alpha=0.5, density=True,
                 label=f"Unconditional post-COVID (n={len(uncond)})")
    axes[1].hist(cond, bins=20, color="C3", alpha=0.75, density=True,
                 label=f"After co-crash, post-COVID (n={len(cond)})")
    axes[1].axvline(0, color="black", lw=0.8)
    axes[1].axvline(cond.mean(), color="C3", lw=1.5, ls="--",
                    label=f"cond mean={cond.mean():+.2f}%")
    axes[1].set_xlim(-4, 4)
    axes[1].set_xlabel("Next-day open-to-close pair return (%)")
    axes[1].set_title("Next-day OC pair return: post-COVID, conditional vs unconditional")
    axes[1].legend(loc="best"); axes[1].grid(alpha=0.3)

    ev = events_regime[["r_pair_cc", "fwd1_pair_oc"]].dropna()
    axes[2].scatter(ev["r_pair_cc"] * 100, ev["fwd1_pair_oc"] * 100,
                    color="C3", alpha=0.75, s=40)
    if len(ev) >= 2:
        m, b = np.polyfit(ev["r_pair_cc"] * 100, ev["fwd1_pair_oc"] * 100, 1)
        xs = np.linspace(ev["r_pair_cc"].min() * 100, ev["r_pair_cc"].max() * 100, 50)
        axes[2].plot(xs, m * xs + b, color="black", lw=1.5,
                     label=f"OLS slope={m:+.2f}  (revert if <0)")
    axes[2].axhline(0, color="grey", lw=0.5); axes[2].axvline(0, color="grey", lw=0.5)
    axes[2].set_xlabel("Crash-day pair return r_pair_cc[t] (%)")
    axes[2].set_ylabel("Next-day open-to-close pair return (%)")
    axes[2].set_title(f"Reversion test on co-crash events (post-COVID, n={len(ev)})")
    axes[2].legend(loc="best"); axes[2].grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print(f"\nChart saved -> {out_path}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "data" / "event_studies"
    out_dir.mkdir(parents=True, exist_ok=True)

    prices = fetch_prices()
    df = build_pair(prices)
    rng = np.random.default_rng(SEED)

    summarise(df, rng)

    daily_path = out_dir / "spx_ndx_cocrash_daily.csv"
    df.to_csv(daily_path)
    print(f"\nDaily saved   -> {daily_path}")

    events_full = detect_events(df)
    df_regime = df.loc[REGIME_START:]
    events_regime = detect_events(df_regime)

    ev_path = out_dir / "spx_ndx_cocrash_events.csv"
    events_full.to_csv(ev_path)
    print(f"Events saved  -> {ev_path}")

    plot(df, events_full, events_regime, df_regime,
         out_dir / "spx_ndx_cocrash_reversion.png")


if __name__ == "__main__":
    main()
