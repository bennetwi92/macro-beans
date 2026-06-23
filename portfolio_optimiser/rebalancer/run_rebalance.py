"""CLI for the monthly contribution-driven rebalancer.

Reads the optimised target weights produced by the report pipeline
(``outputs/targets_{isa,sipp}.csv``) and computes the buy split for a new
contribution against your current holdings.

Examples
--------
First contribution into an empty SIPP Pie of £1,500:
    python -m portfolio_optimiser.rebalancer.run_rebalance --portfolio sipp --contribution 1500

Monthly top-up with current holdings from a CSV (columns: ticker,value):
    python -m portfolio_optimiser.rebalancer.run_rebalance \\
        --portfolio isa --contribution 500 --holdings my_isa.csv

The output prints (a) the £ to buy per holding, (b) resulting weights, (c) the
Trading 212 Pie target %, and (d) any drift flags that contributions can't fix.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .rebalance import rebalance

OUTPUTS = Path(__file__).resolve().parents[1] / "outputs"


def _load_targets(portfolio: str) -> pd.Series:
    path = OUTPUTS / f"targets_{portfolio}.csv"
    if not path.exists():
        raise SystemExit(
            f"No targets at {path}. Run the report first:\n"
            "    python -m portfolio_optimiser.report.build_report"
        )
    df = pd.read_csv(path)
    return pd.Series(df["weight"].values, index=df["ticker"].values)


def _load_holdings(path: str | None) -> dict[str, float]:
    if not path:
        return {}
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    tcol = cols.get("ticker") or df.columns[0]
    vcol = cols.get("value") or df.columns[1]
    return dict(zip(df[tcol], df[vcol].astype(float)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--portfolio", choices=["isa", "sipp"], required=True)
    ap.add_argument("--contribution", type=float, required=True, help="new money (GBP)")
    ap.add_argument("--holdings", help="CSV with columns ticker,value (current GBP per holding)")
    ap.add_argument("--allow-sells", action="store_true",
                    help="full rebalance incl. sells (Pie auto-invest off)")
    args = ap.parse_args()

    targets = _load_targets(args.portfolio)
    current = _load_holdings(args.holdings)

    plan = rebalance(current, args.contribution, targets, allow_sells=args.allow_sells)

    out = pd.DataFrame({
        "buy_gbp": plan.buys,
        "post_weight_%": (plan.post_weights * 100).round(1),
        "pie_target_%": plan.pie_targets,
    })
    out = out[out["pie_target_%"] > 0]
    print(f"\n{args.portfolio.upper()} — contribution £{args.contribution:,.2f} "
          f"-> portfolio £{plan.post_value:,.2f}\n")
    print(out.to_string())
    print(f"\nTotal to buy: £{plan.buys[plan.buys > 0].sum():,.2f}")

    if plan.flags:
        print("\n⚠ Drift flags (contributions alone can't fix — consider a sell/Pie pause):")
        for f in plan.flags:
            print(f"  - {f}")
    else:
        print("\nNo drift flags: contributions keep every holding within tolerance.")


if __name__ == "__main__":
    main()
