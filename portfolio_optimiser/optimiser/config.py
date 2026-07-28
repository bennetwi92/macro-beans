"""Load the editable TOML configs into typed objects.

Three files under ``config/``:
  * ``universe.toml``    -- instruments + proxy series
  * ``cma.toml``         -- capital-market assumptions (building blocks + formulas)
  * ``constraints.toml`` -- per-portfolio constraints, data window, validation

Everything downstream reads from the dataclasses here, so the rest of the code
never touches a hard-coded ticker, return, or limit.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


@dataclass(frozen=True)
class Instrument:
    key: str
    ticker: str
    name: str
    isin: str
    ter: float
    accumulating: bool
    sleeve: str
    role: str
    isa_eligible: bool
    sipp_eligible: bool
    proxy: str


@dataclass(frozen=True)
class ProxySpec:
    key: str
    source: str
    ccy: str  # "GBP" or "USD"
    note: str


@dataclass
class Universe:
    instruments: dict[str, Instrument]
    proxies: dict[str, ProxySpec]

    def keys(self) -> list[str]:
        return list(self.instruments.keys())

    def sleeve_of(self, key: str) -> str:
        return self.instruments[key].sleeve

    def tickers(self, keys: list[str]) -> dict[str, str]:
        return {k: self.instruments[k].ticker for k in keys}


@dataclass
class CMA:
    meta: dict
    blocks: dict[str, float]
    formulas: dict[str, str]   # key -> formula string
    explicit: dict[str, float]  # key -> explicit mu (overrides formula)


@dataclass
class PortfolioConstraints:
    name: str
    value_gbp: float
    objective: str
    weight_min: float
    weight_max: float
    universe: list[str]
    sleeve_caps: dict[str, float]
    sleeve_floors: dict[str, float] = field(default_factory=dict)
    # ISA-only (None for SIPP)
    liquidity_floor_gbp: float | None = None
    ballast_sleeve: str | None = None
    cvar_alpha: float | None = None
    cvar_limit: float | None = None
    fixed_fee_gbp: float = 0.0
    # SIPP-only: the contribution stream, glidepath schedule and platform
    # execution limits. Left empty for the ISA, which is a single seed pot.
    contributions: dict = field(default_factory=dict)
    execution: dict = field(default_factory=dict)


@dataclass
class Settings:
    data_start: str
    frequency: str
    trading_periods: int
    resample_draws: int
    random_seed: int
    min_holding: float
    shrinkage: str
    mc_paths: int
    benchmark: str
    benchmark_proxy: str
    benchmark_proxy_ccy: str
    sensitivity_shift: float
    rebalance_drift_abs: float
    rebalance_drift_rel: float


def _load_toml(name: str) -> dict:
    with open(CONFIG_DIR / name, "rb") as fh:
        return tomllib.load(fh)


def load_universe() -> Universe:
    raw = _load_toml("universe.toml")
    instruments: dict[str, Instrument] = {}
    for block in raw["instrument"]:
        instruments[block["key"]] = Instrument(**block)
    proxies: dict[str, ProxySpec] = {}
    for key, spec in raw.get("proxy", {}).items():
        proxies[key] = ProxySpec(key=key, **spec)
    return Universe(instruments=instruments, proxies=proxies)


def load_cma() -> CMA:
    raw = _load_toml("cma.toml")
    formulas: dict[str, str] = {}
    explicit: dict[str, float] = {}
    for key, spec in raw.get("instrument", {}).items():
        if "mu" in spec:
            explicit[key] = float(spec["mu"])
        if "formula" in spec:
            formulas[key] = spec["formula"]
    return CMA(
        meta=raw.get("meta", {}),
        blocks={k: float(v) for k, v in raw.get("blocks", {}).items()},
        formulas=formulas,
        explicit=explicit,
    )


def load_constraints() -> tuple[PortfolioConstraints, PortfolioConstraints, Settings]:
    raw = _load_toml("constraints.toml")
    data = raw["data"]
    opt = raw["optimiser"]
    val = raw["validation"]
    reb = raw["rebalance"]

    settings = Settings(
        data_start=data["start"],
        frequency=data["frequency"],
        trading_periods=int(data["trading_periods"]),
        resample_draws=int(opt["resample_draws"]),
        random_seed=int(opt["random_seed"]),
        min_holding=float(opt["min_holding"]),
        shrinkage=opt["shrinkage"],
        mc_paths=int(val["mc_paths"]),
        benchmark=val["benchmark"],
        benchmark_proxy=val["benchmark_proxy"],
        benchmark_proxy_ccy=val["benchmark_proxy_ccy"],
        sensitivity_shift=float(val["sensitivity_shift"]),
        rebalance_drift_abs=float(reb["drift_abs_pts"]),
        rebalance_drift_rel=float(reb["drift_rel"]),
    )

    sipp_raw = raw["sipp"]
    sipp = PortfolioConstraints(
        name="SIPP",
        value_gbp=float(sipp_raw["value_gbp"]),
        objective=sipp_raw["objective"],
        weight_min=float(sipp_raw["weight_min"]),
        weight_max=float(sipp_raw["weight_max"]),
        universe=list(sipp_raw["universe"]),
        sleeve_caps={k: float(v) for k, v in sipp_raw.get("sleeve_caps", {}).items()},
        sleeve_floors={k: float(v) for k, v in sipp_raw.get("sleeve_floors", {}).items()},
        fixed_fee_gbp=float(sipp_raw.get("fixed_fee_gbp", 0.0)),
        contributions=dict(sipp_raw.get("contributions", {})),
        execution=dict(sipp_raw.get("execution", {})),
    )

    isa_raw = raw["isa"]
    isa = PortfolioConstraints(
        name="ISA",
        value_gbp=float(isa_raw["value_gbp"]),
        objective=isa_raw["objective"],
        weight_min=float(isa_raw["weight_min"]),
        weight_max=float(isa_raw["weight_max"]),
        universe=list(isa_raw["universe"]),
        sleeve_caps={k: float(v) for k, v in isa_raw.get("sleeve_caps", {}).items()},
        sleeve_floors={k: float(v) for k, v in isa_raw.get("sleeve_floors", {}).items()},
        liquidity_floor_gbp=float(isa_raw["liquidity_floor_gbp"]),
        ballast_sleeve=isa_raw["ballast_sleeve"],
        cvar_alpha=float(isa_raw["cvar_alpha"]),
        cvar_limit=float(isa_raw["cvar_limit"]),
    )

    return isa, sipp, settings


@dataclass
class Config:
    universe: Universe
    cma: CMA
    isa: PortfolioConstraints
    sipp: PortfolioConstraints
    settings: Settings


def load_all() -> Config:
    universe = load_universe()
    cma = load_cma()
    isa, sipp, settings = load_constraints()
    return Config(universe=universe, cma=cma, isa=isa, sipp=sipp, settings=settings)
