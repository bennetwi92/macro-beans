"""Build the reference JSON for the Macro Beans web app.

Emits web/data/reference.json from the instrument + strategy registry. Unlike
build_data.py / build_portfolios.py this fetches NOTHING -- it reads the static
registry (stdlib tomllib, no yfinance, no duckdb) and enriches each web symbol
with freshness (first/last date, bar count) read back from the already-built
web/data/instruments.json when present.

The public site has no backend and cannot see the DuckDB research cache, so
research symbols carry honest nulls for freshness; `tracked` (from the registry
surfaces) is the signal the pages filter on.

Run locally (after build_data.py so freshness is populated):
    /usr/local/bin/python3 scripts/site/build_reference.py

Output:
    web/data/reference.json   {built_at, strategies[], instruments[], symbols[]}
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make `src` importable so we can read the shared registry.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.data.registry import (  # noqa: E402
    coverage_map,
    load_instruments,
    load_strategies,
)

# Shared build helpers (compact-JSON writer).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import write_json  # noqa: E402


def _web_freshness(data_dir: Path) -> dict[str, dict]:
    """Map web slug -> {first_date, last_date, n_bars} from instruments.json.

    Returns an empty map if the menu hasn't been built yet (fresh checkout /
    running before build_data.py) -- callers degrade freshness to null.
    """
    menu_path = data_dir / "instruments.json"
    if not menu_path.exists():
        return {}
    try:
        menu = json.loads(menu_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict] = {}
    for e in menu.get("instruments", []):
        slug = e.get("slug")
        if slug:
            out[slug] = {
                "first_date": e.get("first_date"),
                "last_date": e.get("last_date"),
                "n_bars": e.get("n_bars"),
            }
    return out


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "web" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    instruments = load_instruments()
    strategies = load_strategies()
    fresh = _web_freshness(out_dir)
    n_strategies = len(strategies)

    strat_payload = [
        {
            "slug": s.slug,
            "name": s.name,
            "requires_surface": s.requires_surface,
            "page": s.page,
        }
        for s in strategies
    ]

    inst_payload: list[dict] = []
    sym_payload: list[dict] = []

    for inst in instruments:
        syms = inst.symbols()
        web_fresh = fresh.get(inst.slug, {}) if inst.on("web") else {}
        cover = coverage_map(inst, strategies)
        covered = sum(1 for v in cover.values() if v)

        inst_payload.append({
            "slug": inst.slug,
            "name": inst.name,
            "category": inst.category,
            "group": inst.group,
            "sublabel": inst.sublabel,
            "surfaces": list(inst.surfaces),
            "symbol_count": len(syms),
            "tickers": {s.surface: s.ticker for s in syms},
            "coverage": cover,
            "covered": covered,
            "n_strategies": n_strategies,
            "first_date": web_fresh.get("first_date"),
            "last_date": web_fresh.get("last_date"),
            "n_bars": web_fresh.get("n_bars"),
        })

        for s in syms:
            sf = web_fresh if s.surface == "web" else {}
            sym_payload.append({
                "ticker": s.ticker,
                "surface": s.surface,
                "venue": s.venue,
                "role": s.role,
                "instrument_slug": inst.slug,
                "instrument_name": inst.name,
                "category": inst.category,
                "tracked": True,
                "first_date": sf.get("first_date"),
                "last_date": sf.get("last_date"),
                "n_bars": sf.get("n_bars"),
            })

    payload = {
        "built_at": built_at,
        "strategies": strat_payload,
        "instruments": inst_payload,
        "symbols": sym_payload,
    }
    path = out_dir / "reference.json"
    n_bytes = write_json(path, payload)
    print(
        f"reference.json written -> {len(inst_payload)} instruments, "
        f"{len(sym_payload)} symbols, {n_strategies} strategies "
        f"({n_bytes / 1024:.0f} kB)"
    )
    if not fresh:
        print("  note: no instruments.json found -- freshness fields are null")
    print(f"Built at {built_at}")


if __name__ == "__main__":
    main()
