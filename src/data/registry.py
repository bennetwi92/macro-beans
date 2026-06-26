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
STRATEGIES_TOML = CONFIG_DIR / "strategies.toml"


def _venue_of(ticker: str) -> str:
    """Classify a ticker into a display venue (for the reference pages).

    Purely cosmetic: ``.L`` is an LSE listing, ``=F`` a future, ``^`` an index,
    and anything else on the research side is treated as US-listed.
    """
    if ticker.endswith(".L"):
        return "LSE"
    if ticker.endswith("=F"):
        return "FUTURE"
    if ticker.startswith("^"):
        return "INDEX"
    return "US"


@dataclass(frozen=True)
class Symbol:
    """One concrete market ticker carried by an instrument.

    An instrument is a logical exposure; a symbol is the venue-specific ticker
    that actually points at price data. An instrument with both a web_ticker
    and a research_ticker yields two symbols.
    """

    ticker: str          # e.g. "VUSA.L" or "GLD"
    surface: str         # "web" | "research"
    venue: str           # "LSE" | "US" | "FUTURE" | "INDEX" (display only)
    role: str            # "web_ticker" | "research_ticker"


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
    # Dropdown section heading on the web strategy page (web surface only).
    group: str | None = None

    def on(self, surface: str) -> bool:
        return surface in self.surfaces

    def symbols(self) -> tuple[Symbol, ...]:
        """Every concrete ticker this exposure carries, one per (surface, role).

        Only emits a symbol when its surface is declared in ``surfaces`` -- the
        surfaces list stays the single source of truth for where an instrument
        is live.
        """
        out: list[Symbol] = []
        if self.web_ticker and self.on("web"):
            out.append(Symbol(self.web_ticker, "web", _venue_of(self.web_ticker), "web_ticker"))
        if self.research_ticker and self.on("research"):
            out.append(
                Symbol(self.research_ticker, "research", _venue_of(self.research_ticker), "research_ticker")
            )
        return tuple(out)


@dataclass(frozen=True)
class PortfolioLeg:
    """One leg of a pair portfolio.

    For a LETF pair the leg carries its ``letf`` wrapper ticker and ``lev``
    leverage factor. For a CFD pair (LSE single shares) it carries the plain
    ``ticker`` instead. ``underlying`` and ``label`` are common to both.
    """

    underlying: str
    label: str
    letf: str | None = None
    lev: int | None = None
    ticker: str | None = None


@dataclass(frozen=True)
class Portfolio:
    """A beta-hedged pair portfolio for the web site.

    ``kind`` selects how the second equity curve is built downstream:
    ``"letf"`` (leveraged-ETF wrapper) or ``"cfd"`` (spread net of Trading 212
    overnight financing).
    """

    slug: str
    name: str
    blurb: str
    long: PortfolioLeg
    short: PortfolioLeg
    kind: str = "letf"
    beta_clip: tuple[float, float] | None = None


@dataclass(frozen=True)
class Strategy:
    """A published strategy and the data surface it needs to run.

    An instrument is "covered" by a strategy iff it carries the symbol on
    ``requires_surface`` (see ``instrument_covers``).
    """

    slug: str
    name: str
    requires_surface: str
    page: str | None = None


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
                group=entry.get("group"),
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


def surface_tickers(surface: str) -> list[str]:
    """The yfinance tickers carried on one ``surface`` (e.g. "web"/"research").

    Deduplicated, registry order. Used by ``refresh.py`` to seed/update the
    DuckDB cache for a whole surface (e.g. every LSE ETF on the web surface).
    """
    out: list[str] = []
    for inst in load_instruments(surface):
        for sym in inst.symbols():
            if sym.surface == surface and sym.ticker not in out:
                out.append(sym.ticker)
    return out


def research_tickers() -> list[str]:
    """The yfinance tickers that make up the research/scanner universe."""
    return surface_tickers("research")


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
                kind=entry.get("kind", "letf"),
                beta_clip=tuple(clip) if clip else None,
            )
        )
    return out


@lru_cache(maxsize=1)
def load_strategies() -> list[Strategy]:
    """Return the published strategies defined in ``config/strategies.toml``."""
    raw = _load_toml(STRATEGIES_TOML)
    return [
        Strategy(
            slug=entry["slug"],
            name=entry["name"],
            requires_surface=entry["requires_surface"],
            page=entry.get("page"),
        )
        for entry in raw.get("strategy", [])
    ]


def instrument_covers(inst: Instrument, strat: Strategy) -> bool:
    """True iff the instrument carries the symbol the strategy consumes."""
    return inst.on(strat.requires_surface)


def coverage_map(inst: Instrument, strategies: list[Strategy]) -> dict[str, bool]:
    """Per-strategy coverage for one instrument, keyed by strategy slug."""
    return {s.slug: instrument_covers(inst, s) for s in strategies}


__all__ = [
    "Instrument",
    "Portfolio",
    "PortfolioLeg",
    "Strategy",
    "Symbol",
    "coverage_map",
    "instrument_covers",
    "load_instruments",
    "load_portfolios",
    "load_strategies",
    "research_tickers",
    "surface_tickers",
]
