"""The instrument registry -- one source of truth for every instrument.

Reads ``config/instruments.toml`` and ``config/portfolios.toml`` using the
stdlib ``tomllib`` (Python 3.11+), so this module has **no third-party
dependencies** and can be imported by the web build without pulling in duckdb.

An instrument is a logical exposure that may surface on the research side
(US-listed ticker, scanned/cached in DuckDB), the public web site (an
LSE-listed ETF), or both. Each entry carries the ticker(s) it needs and a
list of ``surfaces`` that controls where it shows up.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from src.data.paths import CONFIG_DIR

INSTRUMENTS_TOML = CONFIG_DIR / "instruments.toml"
PORTFOLIOS_TOML = CONFIG_DIR / "portfolios.toml"


@dataclass(frozen=True)
class Instrument:
    """A single instrument from the registry."""

    slug: str
    name: str
    category: str
    surfaces: tuple[str, ...] = ()
    research_ticker: str | None = None
    web_ticker: str | None = None
    sublabel: str | None = None

    def on(self, surface: str) -> bool:
        return surface in self.surfaces


@dataclass(frozen=True)
class PortfolioLeg:
    """One leg of a pair portfolio (the underlying + its LETF wrapper)."""

    underlying: str
    letf: str
    label: str
    lev: int


@dataclass(frozen=True)
class Portfolio:
    """A beta-hedged pair portfolio for the web site."""

    slug: str
    name: str
    blurb: str
    long: PortfolioLeg
    short: PortfolioLeg
    beta_clip: tuple[float, float] | None = None


def _load_toml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Registry file not found: {path}. "
            f"It should be checked into config/."
        )
    with path.open("rb") as fh:
        return tomllib.load(fh)


@lru_cache(maxsize=1)
def _all_instruments() -> tuple[Instrument, ...]:
    raw = _load_toml(INSTRUMENTS_TOML)
    out: list[Instrument] = []
    seen: set[str] = set()
    for entry in raw.get("instrument", []):
        slug = entry["slug"]
        if slug in seen:
            raise ValueError(f"Duplicate instrument slug in registry: {slug!r}")
        seen.add(slug)
        out.append(
            Instrument(
                slug=slug,
                name=entry["name"],
                category=entry["category"],
                surfaces=tuple(entry.get("surfaces", [])),
                research_ticker=entry.get("research_ticker"),
                web_ticker=entry.get("web_ticker"),
                sublabel=entry.get("sublabel"),
            )
        )
    return tuple(out)


def load_instruments(surface: str | None = None) -> list[Instrument]:
    """Return registry instruments, optionally filtered to one ``surface``.

    ``surface`` is e.g. ``"research"`` or ``"web"``. ``None`` returns all.
    """
    instruments = _all_instruments()
    if surface is None:
        return list(instruments)
    return [i for i in instruments if i.on(surface)]


def research_tickers() -> list[str]:
    """The yfinance tickers that make up the research/scanner universe."""
    return [
        i.research_ticker
        for i in load_instruments("research")
        if i.research_ticker
    ]


@lru_cache(maxsize=1)
def load_portfolios() -> list[Portfolio]:
    """Return the pair portfolios defined in ``config/portfolios.toml``."""
    raw = _load_toml(PORTFOLIOS_TOML)
    out: list[Portfolio] = []
    for entry in raw.get("portfolio", []):
        clip = entry.get("beta_clip")
        out.append(
            Portfolio(
                slug=entry["slug"],
                name=entry["name"],
                blurb=entry["blurb"],
                long=PortfolioLeg(**entry["long"]),
                short=PortfolioLeg(**entry["short"]),
                beta_clip=tuple(clip) if clip else None,
            )
        )
    return out


__all__ = [
    "Instrument",
    "Portfolio",
    "PortfolioLeg",
    "load_instruments",
    "load_portfolios",
    "research_tickers",
]
