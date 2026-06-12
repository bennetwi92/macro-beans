"""Validate the JSON the build scripts emit into web/data/ before it deploys.

The site has no backend and computes everything in the browser, so a malformed,
empty, or NaN-laden JSON file would only blow up at runtime in a reader's
browser. This script is the gate: run it after build_data.py / build_portfolios.py
(locally and in CI, before the Pages upload). It loads every generated file and
fails loudly — non-zero exit, naming the file and the problem — on anything the
browser code assumes but never checks.

Checks:
  * instruments.json / portfolios.json: menu present and non-empty, required
    keys on every entry, and a two-way match between menu slugs and the
    per-item files on disk (no orphan files, no dangling menu entries).
  * per-item files: required meta keys; non-empty bars; every bar a
    [iso_date, x, y] triple with a valid, strictly-increasing date and finite,
    strictly-positive numbers; meta.n_bars / first_date / last_date consistent
    with bars.
  * a soft cross-check against the registry (config/*.toml): a built set that
    differs from the registry is reported as a WARNING, not a failure, so a
    deliberately-skipped flaky ticker doesn't block the deploy.

Run:
    /usr/local/bin/python3 scripts/site/validate_data.py
"""

from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path

# Make `src` importable for the (soft) registry cross-check.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.data.registry import load_instruments, load_portfolios  # noqa: E402

import json  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "web" / "data"

INSTRUMENT_META_KEYS = {
    "slug", "ticker", "name", "label", "sublabel", "group",
    "first_date", "last_date", "n_bars", "built_at",
}
INSTRUMENT_MENU_KEYS = {
    "slug", "name", "ticker", "label", "sublabel", "group",
    "n_bars", "first_date", "last_date",
}
PORTFOLIO_META_KEYS = {
    "slug", "name", "kind", "blurb", "long", "short",
    "first_date", "last_date", "n_bars", "built_at",
}
PORTFOLIO_MENU_KEYS = {
    "slug", "name", "kind", "blurb", "long", "short",
    "first_date", "last_date", "n_bars",
}

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        err(f"{path.relative_to(REPO_ROOT)}: file is missing")
    except json.JSONDecodeError as exc:
        err(f"{path.relative_to(REPO_ROOT)}: invalid JSON ({exc})")
    return None


def valid_date(s) -> bool:
    if not isinstance(s, str):
        return False
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def check_bars(rel: str, bars, *, value_labels: tuple[str, str]) -> None:
    """A bar is [iso_date, x, y]: valid increasing date, finite positive x & y."""
    if not isinstance(bars, list) or len(bars) == 0:
        err(f"{rel}: 'bars' is empty or not a list")
        return
    prev_date = None
    for i, b in enumerate(bars):
        if not isinstance(b, list) or len(b) != 3:
            err(f"{rel}: bar {i} is not a [date, {value_labels[0]}, {value_labels[1]}] triple")
            return
        date, x, y = b
        if not valid_date(date):
            err(f"{rel}: bar {i} has an invalid date {date!r}")
            return
        if prev_date is not None and not (date > prev_date):
            err(f"{rel}: dates not strictly increasing at bar {i} ({prev_date} -> {date})")
            return
        prev_date = date
        for label, v in zip(value_labels, (x, y)):
            if not isinstance(v, (int, float)) or not math.isfinite(v):
                err(f"{rel}: bar {i} {label}={v!r} is not a finite number")
                return
            if v <= 0:
                err(f"{rel}: bar {i} {label}={v} is not positive")
                return


def check_meta_consistency(rel: str, meta: dict, bars) -> None:
    if meta.get("n_bars") != len(bars):
        err(f"{rel}: meta.n_bars={meta.get('n_bars')} != len(bars)={len(bars)}")
    if bars and meta.get("first_date") != bars[0][0]:
        err(f"{rel}: meta.first_date={meta.get('first_date')} != bars[0]={bars[0][0]}")
    if bars and meta.get("last_date") != bars[-1][0]:
        err(f"{rel}: meta.last_date={meta.get('last_date')} != bars[-1]={bars[-1][0]}")


def require_keys(rel: str, obj: dict, keys: set[str], what: str) -> None:
    if not isinstance(obj, dict):
        err(f"{rel}: {what} is not an object")
        return
    missing = keys - obj.keys()
    if missing:
        err(f"{rel}: {what} missing keys: {sorted(missing)}")


def validate_instruments() -> None:
    menu_path = DATA_DIR / "instruments.json"
    menu = load_json(menu_path)
    if menu is None:
        return
    if not menu.get("built_at"):
        err("instruments.json: missing 'built_at'")
    entries = menu.get("instruments")
    if not isinstance(entries, list) or len(entries) == 0:
        err("instruments.json: 'instruments' is empty or not a list")
        return

    menu_slugs = set()
    for e in entries:
        require_keys("instruments.json", e, INSTRUMENT_MENU_KEYS, f"menu entry {e.get('slug')!r}")
        slug = e.get("slug")
        if slug:
            menu_slugs.add(slug)

    # Per-instrument files: every menu slug must have one, validated.
    for slug in sorted(menu_slugs):
        path = DATA_DIR / f"{slug}.json"
        rel = str(path.relative_to(REPO_ROOT))
        payload = load_json(path)
        if payload is None:
            continue
        require_keys(rel, payload.get("meta", {}), INSTRUMENT_META_KEYS, "meta")
        bars = payload.get("bars")
        check_bars(rel, bars, value_labels=("open", "close"))
        if isinstance(payload.get("meta"), dict) and isinstance(bars, list) and bars:
            check_meta_consistency(rel, payload["meta"], bars)

    # No orphan per-instrument files (top-level *.json that isn't a menu).
    reserved = {"instruments.json", "portfolios.json", "reference.json"}
    for path in DATA_DIR.glob("*.json"):
        if path.name in reserved:
            continue
        if path.stem not in menu_slugs:
            err(f"{path.relative_to(REPO_ROOT)}: file has no entry in instruments.json")

    # Soft cross-check against the registry.
    registry_slugs = {i.slug for i in load_instruments("web")}
    for missing in sorted(registry_slugs - menu_slugs):
        warn(f"instrument {missing!r} is in the registry but was not built")
    for extra in sorted(menu_slugs - registry_slugs):
        warn(f"instrument {extra!r} was built but is not in the registry")


def validate_portfolios() -> None:
    menu_path = DATA_DIR / "portfolios.json"
    menu = load_json(menu_path)
    if menu is None:
        return
    if not menu.get("built_at"):
        err("portfolios.json: missing 'built_at'")
    entries = menu.get("portfolios")
    if not isinstance(entries, list) or len(entries) == 0:
        err("portfolios.json: 'portfolios' is empty or not a list")
        return

    menu_slugs = set()
    for e in entries:
        require_keys("portfolios.json", e, PORTFOLIO_MENU_KEYS, f"menu entry {e.get('slug')!r}")
        slug = e.get("slug")
        if slug:
            menu_slugs.add(slug)

    pdir = DATA_DIR / "portfolios"
    for slug in sorted(menu_slugs):
        path = pdir / f"{slug}.json"
        rel = str(path.relative_to(REPO_ROOT))
        payload = load_json(path)
        if payload is None:
            continue
        require_keys(rel, payload.get("meta", {}), PORTFOLIO_META_KEYS, "meta")
        bars = payload.get("bars")
        check_bars(rel, bars, value_labels=("equity_under", "equity_alt"))
        if isinstance(payload.get("meta"), dict) and isinstance(bars, list) and bars:
            check_meta_consistency(rel, payload["meta"], bars)

    if pdir.is_dir():
        for path in pdir.glob("*.json"):
            if path.stem not in menu_slugs:
                err(f"{path.relative_to(REPO_ROOT)}: file has no entry in portfolios.json")

    registry_slugs = {p.slug for p in load_portfolios()}
    for missing in sorted(registry_slugs - menu_slugs):
        warn(f"portfolio {missing!r} is in the registry but was not built")
    for extra in sorted(menu_slugs - registry_slugs):
        warn(f"portfolio {extra!r} was built but is not in the registry")


REFERENCE_INSTRUMENT_KEYS = {
    "slug", "name", "category", "group", "sublabel", "surfaces",
    "symbol_count", "tickers", "coverage", "covered", "n_strategies",
    "first_date", "last_date", "n_bars",
}
REFERENCE_SYMBOL_KEYS = {
    "ticker", "surface", "venue", "role", "instrument_slug",
    "instrument_name", "category", "tracked", "first_date", "last_date", "n_bars",
}


def validate_reference() -> None:
    """Schema + referential-integrity checks for reference.json.

    This is registry-derived (not price bars), so freshness fields may be null;
    we check shape and cross-references, not positivity/finiteness of bars.
    """
    path = DATA_DIR / "reference.json"
    if not path.exists():
        # Built alongside the others; absence in CI is a real problem.
        err("reference.json: file is missing")
        return
    ref = load_json(path)
    if ref is None:
        return
    if not ref.get("built_at"):
        err("reference.json: missing 'built_at'")

    strategies = ref.get("strategies")
    if not isinstance(strategies, list) or len(strategies) == 0:
        err("reference.json: 'strategies' is empty or not a list")

    insts = ref.get("instruments")
    if not isinstance(insts, list) or len(insts) == 0:
        err("reference.json: 'instruments' is empty or not a list")
        return
    syms = ref.get("symbols")
    if not isinstance(syms, list):
        err("reference.json: 'symbols' is not a list")
        return

    inst_slugs = set()
    sym_counts: dict[str, int] = {}
    for e in insts:
        require_keys("reference.json", e, REFERENCE_INSTRUMENT_KEYS, f"instrument {e.get('slug')!r}")
        slug = e.get("slug")
        if slug:
            inst_slugs.add(slug)

    for s in syms:
        require_keys("reference.json", s, REFERENCE_SYMBOL_KEYS, f"symbol {s.get('ticker')!r}")
        owner = s.get("instrument_slug")
        if owner not in inst_slugs:
            err(f"reference.json: symbol {s.get('ticker')!r} references unknown instrument {owner!r}")
        sym_counts[owner] = sym_counts.get(owner, 0) + 1

    # symbol_count must equal the number of symbol rows for each instrument.
    for e in insts:
        declared = e.get("symbol_count")
        actual = sym_counts.get(e.get("slug"), 0)
        if declared != actual:
            err(f"reference.json: instrument {e.get('slug')!r} symbol_count={declared} != {actual} symbol rows")

    # Soft cross-check against the registry (all surfaces).
    registry_slugs = {i.slug for i in load_instruments()}
    for missing in sorted(registry_slugs - inst_slugs):
        warn(f"reference: instrument {missing!r} is in the registry but not in reference.json")
    for extra in sorted(inst_slugs - registry_slugs):
        warn(f"reference: instrument {extra!r} is in reference.json but not in the registry")


def main() -> None:
    if not DATA_DIR.is_dir():
        print(f"No data directory at {DATA_DIR} — run the build scripts first.")
        sys.exit(1)

    validate_instruments()
    validate_portfolios()
    validate_reference()

    for w in warnings:
        print(f"  warning: {w}")
    if errors:
        print(f"\nData validation FAILED with {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print(f"Data validation passed ({len(warnings)} warning(s)).")
    sys.exit(0)


if __name__ == "__main__":
    main()
