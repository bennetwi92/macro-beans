"""
GDX.L volatility-squeeze backtest
=================================

Single, re-runnable research script. Tests whether a Bollinger/Keltner
volatility squeeze is a usable long-entry signal on GDX.L (VanEck Gold Miners
UCITS, LSE, USD line), with macro/event filters, several exit rules,
transaction costs, an in-sample / out-of-sample split, Monte-Carlo random-entry
baselines, a parameter-sensitivity grid, a longer-history robustness check on
the US GDX listing, and a squeeze-episode event analysis.

Usage
-----
    python3 scripts/gdx_squeeze/gdx_squeeze_backtest.py            # use cached raw CSVs
    python3 scripts/gdx_squeeze/gdx_squeeze_backtest.py --refresh  # re-download everything

Outputs
-------
    data/gdx_squeeze/raw/*.csv           raw downloads (cache; reruns don't re-download)
    data/gdx_squeeze/events.csv          FOMC decision + CPI release calendar
    data/gdx_squeeze/variants.csv        every variant, IS and OOS metrics
    data/gdx_squeeze/sensitivity.csv     percentile x hold grid
    data/gdx_squeeze/trades_selected.csv trades of the in-sample-selected rule
    data/gdx_squeeze/episodes_*.csv      squeeze episodes + resolution
    docs/gdx_squeeze/gdx_squeeze_report.html  self-contained HTML report

Design notes (lookahead guards)
-------------------------------
* Every signal is evaluated on the close of day t using data up to and
  including t; the trade is filled at the OPEN of t+1.
* Bollinger-width percentile and its median are trailing (252 days) - never
  full-sample.
* Macro series are aligned to GDX.L trading days by forward-fill only (never
  backfill) and then lagged one GDX.L session: US closes (gold, DXY, 10y) print
  after the 16:30 London close, and FRED publishes DFII10 for day t on t+1.
* The event filter only uses SCHEDULED FOMC meetings and CPI releases (both
  published in advance). Unscheduled FOMC actions are recorded in events.csv
  but excluded from the forward-looking filter.
* ATR for targets/stops is the ATR known at the signal close.
* If a bar touches both the target and the stop, the stop is assumed hit first.
* Parameters are chosen on the in-sample window only; the OOS window is
  reported for the chosen rule, and the full grid is shown for transparency.
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import math
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from src.data.paths import DATA_DIR  # noqa: E402

OUT_DIR = DATA_DIR / "gdx_squeeze"
RAW_DIR = OUT_DIR / "raw"
DOCS_DIR = REPO_ROOT / "docs" / "gdx_squeeze"
REPORT_PATH = DOCS_DIR / "gdx_squeeze_report.html"

YF_TICKERS = {
    "GDX.L": "GDX_L",
    "GDX": "GDX_US",
    "GC=F": "GOLD",
    "DX-Y.NYB": "DXY",
    "^TNX": "TNX",
}
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
FED_CAL_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FED_HIST_URL = "https://www.federalreserve.gov/monetarypolicy/fomchistorical{y}.htm"
ALFRED_URL = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
BLS_URL = "https://www.bls.gov/bls/news-release/cpi.htm"

COST_RT = 0.0015  # 0.15% round trip, half charged on entry and half on exit
BB_N, BB_K = 20, 2.0
KC_N, KC_ATR = 20, 1.5
ATR_N = 20
PCT_WIN = 252
Z_N = 60
IS_FRAC = 0.70
MIN_IS_TRADES = 20  # raised from 15 after a first run picked a rule with 3 OOS trades
N_MC = 1000
EVENT_LOOKAHEAD = 10
RNG_SEED = 20261010

# Reference palette (dataviz skill, light mode)
C = dict(
    s1="#2a78d6", s2="#eb6834", s3="#1baf7a", s4="#eda100", s5="#e87ba4",
    s7="#6250d6", s8="#e34948", ink="#0b0b0b", ink2="#52514e", muted="#898781",
    grid="#e1e0d9", base="#c3c2b7", surface="#fcfcfb", neutral="#f0efec",
)


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def _get(url: str, timeout: int = 60) -> bytes:
    """GET with exponential backoff. Uses requests' default User-Agent: FRED
    drops connections from some custom/browser-like agents."""
    import requests

    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            return r.content
        except Exception as e:  # network hiccup / block -> backoff
            last = e
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"GET failed: {url}: {last}")


def load_prices(refresh: bool) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for tkr, name in YF_TICKERS.items():
        path = RAW_DIR / f"{name}.csv"
        if refresh or not path.exists():
            print(f"  downloading {tkr}")
            df = yf.download(tkr, period="max", auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[["Open", "High", "Low", "Close", "Volume"]]
            df.index.name = "Date"
            df.to_csv(path)
        df = pd.read_csv(path, index_col="Date", parse_dates=True)
        out[name] = df
    path = RAW_DIR / "DFII10.csv"
    if refresh or not path.exists():
        print("  downloading FRED DFII10")
        path.write_bytes(_get(FRED_URL))
    d = pd.read_csv(path)
    d.columns = ["Date", "DFII10"]
    d["Date"] = pd.to_datetime(d["Date"])
    d["DFII10"] = pd.to_numeric(d["DFII10"], errors="coerce")
    out["DFII10"] = d.dropna().set_index("Date")["DFII10"]
    return out


def clean_ohlc(df: pd.DataFrame, label: str, notes: list[str]) -> pd.DataFrame:
    """Drop unusable bars; repair bars without a real intraday range."""
    df = df.copy()
    n0 = len(df)
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df = df[(df[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
    dropped = n0 - len(df)
    # Bars with H==L==O==C and zero volume = no trade printed (stale quote).
    stale = (df["High"] == df["Low"]) & (df["Volume"].fillna(0) == 0)
    df = df[~stale]
    # Make H/L consistent with O/C (a few vendor bars have O outside [L,H]).
    bad_hl = ((df["Open"] > df["High"]) | (df["Open"] < df["Low"])).sum()
    df["High"] = df[["High", "Open", "Close"]].max(axis=1)
    df["Low"] = df[["Low", "Open", "Close"]].min(axis=1)
    notes.append(
        f"{label}: {n0} raw bars; dropped {dropped} incomplete/non-positive, "
        f"{int(stale.sum())} zero-volume no-range bars; repaired {int(bad_hl)} bars "
        f"with Open outside High/Low."
    )
    return df


# --------------------------------------------------------------------------- #
# Event calendar
# --------------------------------------------------------------------------- #
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def month_num(txt: str):
    """'January', 'Jan', 'Jan/Feb', 'April/May' -> number of the LAST month named."""
    return _MONTHS.get(txt.strip().split("/")[-1][:3].lower())


def _fomc_from_heading(text: str, year: int):
    """'January 28-29 Meeting - 2020', 'Jan/Feb 31-1 Meeting', 'March 15 (unscheduled) Meeting',
    'October 7 Conference Call'. Returns (decision date, kind) or None."""
    t = text.strip()
    tl = t.lower()
    if "cancelled" in tl or not re.search(r"meeting|conference call|unscheduled", tl):
        return None
    m = re.match(r"([A-Za-z/]+)\s+(\d{1,2})(?:\s*-\s*(\d{1,2}))?", t)
    if not m:
        return None
    mon_txt, d1, d2 = m.groups()
    mon = month_num(mon_txt)
    if mon is None:
        return None
    kind = ("conference call" if "conference call" in tl else
            "unscheduled" if "unscheduled" in tl else "scheduled")
    return date(year, mon, int(d2 or d1)), kind


def fetch_fomc(refresh: bool, first_year: int, notes: list[str]) -> pd.DataFrame:
    cache = RAW_DIR / "fomc_raw.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["date"])
    rows = []
    cal = _get(FED_CAL_URL).decode("utf-8", "ignore")
    # Current calendar page: per-year panels with month/date cells.
    panels = re.split(r"<h4><a id=\"\d+\">(\d{4}) FOMC Meetings</a></h4>", cal)
    cal_years = set()
    for i in range(1, len(panels), 2):
        year = int(panels[i])
        body = panels[i + 1]
        cal_years.add(year)
        for mo, dd in re.findall(
            r"fomc-meeting__month[^>]*>\s*(?:<strong>)?([A-Za-z/]+)(?:</strong>)?\s*<"
            r".*?fomc-meeting__date[^>]*>([^<]+)<", body, flags=re.S):
            mon = month_num(mo)
            dd = dd.strip()
            if mon is None or not dd:
                continue
            kind = ("notation vote" if "notation" in dd.lower() else
                    "unscheduled" if "unscheduled" in dd.lower() else "scheduled")
            days = re.findall(r"\d{1,2}", dd)
            if not days:
                continue
            rows.append(dict(date=date(year, mon, int(days[-1])), type="FOMC",
                             kind=kind,
                             source="federalreserve.gov/fomccalendars"))
    hist_years = [y for y in range(first_year, min(cal_years) if cal_years else 2021)]
    for y in hist_years:
        try:
            page = _get(FED_HIST_URL.format(y=y)).decode("utf-8", "ignore")
        except RuntimeError:
            notes.append(f"FOMC: historical page for {y} unavailable.")
            continue
        for h in re.findall(r"<h5[^>]*>([^<]*)</h5>", page):
            r = _fomc_from_heading(h, y)
            if r:
                rows.append(dict(date=r[0], type="FOMC", kind=r[1],
                                 source=f"federalreserve.gov/fomchistorical{y}"))
    df = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
    df["scheduled"] = df["kind"] == "scheduled"
    df["date"] = pd.to_datetime(df["date"])
    df.to_csv(cache, index=False)
    return df


def fetch_cpi(refresh: bool, first_year: int, notes: list[str]) -> pd.DataFrame:
    """CPI release dates.

    BLS (the primary source) blocks automated clients with HTTP 403 from many
    networks. We try it first; if blocked, we recover the exact release dates
    from ALFRED (St. Louis Fed real-time archive of BLS's CPIAUCSL): the
    release date of month M's CPI is the first vintage date on which the
    observation for M exists.
    """
    cache = RAW_DIR / "cpi_raw.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["date"])
    rows = []
    try:
        page = _get(BLS_URL, timeout=30).decode("utf-8", "ignore")
        for mo, d, y in re.findall(r"([A-Z][a-z]+)\.?\s+(\d{1,2}),\s+(\d{4})", page):
            if month_num(mo) and int(y) >= first_year:
                rows.append(dict(date=date(int(y), month_num(mo), int(d)), type="CPI",
                                 kind="release", scheduled=True, source="bls.gov"))
    except RuntimeError:
        notes.append("CPI: bls.gov returned an error/403 to this client; release dates "
                     "were reconstructed from ALFRED vintages of CPIAUCSL (same BLS releases).")
    if not rows:
        from concurrent.futures import ThreadPoolExecutor

        days = [d for d in pd.bdate_range(f"{first_year}-01-01", pd.Timestamp(date.today()))]
        chunks = [days[i:i + 12] for i in range(0, len(days), 12)]  # ALFRED: max 12 series/request

        def last_obs(chunk):
            cosd = (chunk[0] - pd.DateOffset(months=4)).strftime("%Y-%m-01")
            url = (f"{ALFRED_URL}?id={','.join(['CPIAUCSL'] * len(chunk))}"
                   f"&vintage_date={','.join(d.strftime('%Y-%m-%d') for d in chunk)}"
                   f"&cosd={','.join([cosd] * len(chunk))}")
            df = pd.read_csv(io.StringIO(_get(url, timeout=120).decode()))
            df["observation_date"] = pd.to_datetime(df["observation_date"])
            df = df.set_index("observation_date")
            out = {}
            for col in df.columns:
                v = pd.Timestamp(datetime.strptime(col.split("_")[-1], "%Y%m%d"))
                out[v] = df[col].last_valid_index()
            return out

        print(f"  reconstructing CPI release dates from ALFRED ({len(chunks)} requests)")
        with ThreadPoolExecutor(4) as pool:
            parts = list(pool.map(last_obs, chunks))
        lo = {}
        for p_ in parts:
            lo.update(p_)
        prev = None
        for v in sorted(lo):
            cur = lo[v]
            if cur is None:
                continue
            if prev is not None and cur > prev:
                rows.append(dict(date=v.date(), type="CPI", kind="release", scheduled=True,
                                 source="ALFRED CPIAUCSL vintages (BLS release)"))
            prev = cur if prev is None else max(prev, cur)
    df = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
    df["date"] = pd.to_datetime(df["date"])
    df.to_csv(cache, index=False)
    return df


def build_events(refresh: bool, first_year: int, notes: list[str]) -> pd.DataFrame:
    fomc = fetch_fomc(refresh, first_year, notes)
    cpi = fetch_cpi(refresh, first_year, notes)
    ev = pd.concat([fomc, cpi]).sort_values("date").reset_index(drop=True)
    ev["year"] = ev["date"].dt.year
    # Gap report (with the known cause where there is one)
    known = {("FOMC", 2020): "the March 17-18 meeting was cancelled (replaced by the unscheduled March 15 cut)",
             ("CPI", 2025): "the October 2025 CPI was never published because of the federal shutdown; "
                            "September's CPI was delayed to Oct 24"}
    today = pd.Timestamp(date.today())
    for y in range(first_year, today.year + 1):
        nf = ((ev.type == "FOMC") & ev.scheduled & (ev.year == y)).sum()
        nc = ((ev.type == "CPI") & (ev.year == y) & (ev.date <= today)).sum()
        exp_c = 12 if y < today.year else today.month - (1 if today.day < 20 else 0)
        if nf != 8:
            why = known.get(("FOMC", y), "unexplained - check the Fed page")
            notes.append(f"FOMC {y}: {nf} scheduled meetings found (8 is normal) - {why}.")
        if abs(nc - exp_c) > 0:
            why = known.get(("CPI", y), "unexplained - check the BLS schedule")
            notes.append(f"CPI {y}: {nc} releases found (expected ~{exp_c}) - {why}.")
    ev[["date", "type", "kind", "scheduled", "source"]].to_csv(OUT_DIR / "events.csv", index=False)
    return ev


# --------------------------------------------------------------------------- #
# Indicators and alignment
# --------------------------------------------------------------------------- #
def rolling_pct_rank(s: pd.Series, n: int) -> pd.Series:
    """Fraction of the trailing n values (incl. today) <= today's value."""
    a = s.to_numpy()
    out = np.full(len(a), np.nan)
    for i in range(n - 1, len(a)):
        w = a[i - n + 1: i + 1]
        if np.isnan(w).any():
            continue
        out[i] = (w <= a[i]).mean()
    return pd.Series(out, index=s.index)


def add_indicators(px: pd.DataFrame) -> pd.DataFrame:
    df = px.copy()
    c, h, l = df["Close"], df["High"], df["Low"]
    mid = c.rolling(BB_N).mean()
    sd = c.rolling(BB_N).std(ddof=0)
    df["bb_up"], df["bb_lo"] = mid + BB_K * sd, mid - BB_K * sd
    df["bbw"] = (df["bb_up"] - df["bb_lo"]) / mid
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_N).mean()
    kc_atr = tr.rolling(KC_N).mean()
    df["kc_up"], df["kc_lo"] = mid + KC_ATR * kc_atr, mid - KC_ATR * kc_atr
    df["bbw_pct"] = rolling_pct_rank(df["bbw"], PCT_WIN)
    df["bbw_med"] = df["bbw"].rolling(PCT_WIN).median()
    lc = np.log(c)
    df["z60"] = (lc - lc.rolling(Z_N).mean()) / lc.rolling(Z_N).std()
    df["sq_kc"] = (df["bb_up"] < df["kc_up"]) & (df["bb_lo"] > df["kc_lo"])
    return df


def align_macro(idx: pd.DatetimeIndex, s: pd.Series) -> pd.Series:
    """Forward-fill onto idx (never backfill), then lag one session."""
    u = s.reindex(s.index.union(idx)).ffill()
    return u.reindex(idx).shift(1)


def event_flags(idx: pd.DatetimeIndex, ev: pd.DataFrame, horizon: int, london: bool,
                scheduled_only=True):
    """For each day t: is an event in sessions (t, t+horizon]?  Also a 0/1
    marker on the session each event maps to. FOMC (2pm ET) maps to the first
    session starting AFTER the statement for a London listing; CPI (8:30 ET)
    and US-listing FOMC map to the same-day session (or the next one if the
    venue is shut that day)."""
    e = ev[ev.scheduled] if scheduled_only else ev[ev.kind.isin(["scheduled", "unscheduled", "release"])]
    pos = []
    for d, typ in zip(e["date"], e["type"]):
        dd = d + pd.Timedelta(days=1) if (typ == "FOMC" and london) else d
        pos.append(idx.searchsorted(dd))
    pos = np.array([p for p in pos if p < len(idx)], dtype=int)
    has = np.zeros(len(idx), dtype=int)
    has[pos] = 1
    cs = np.concatenate([[0], np.cumsum(has)])
    n = len(idx)
    i = np.arange(n)
    hi = np.minimum(i + horizon, n - 1)
    flag = (cs[hi + 1] - cs[i + 1]) > 0
    return pd.Series(flag, index=idx), has


def build_frame(px: pd.DataFrame, raw: dict, ev: pd.DataFrame, london: bool) -> pd.DataFrame:
    df = add_indicators(px)
    idx = df.index
    gold = raw["GOLD"]["Close"].dropna()
    dxy = raw["DXY"]["Close"].dropna()
    tips = raw["DFII10"].dropna()
    tnx = raw["TNX"]["Close"].dropna()
    # MAs computed on each series' own calendar, then aligned + lagged.
    df["gold"] = align_macro(idx, gold)
    df["gold_ma200"] = align_macro(idx, gold.rolling(200).mean())
    df["tips"] = align_macro(idx, tips)
    df["tips_ma50"] = align_macro(idx, tips.rolling(50).mean())
    df["dxy"] = align_macro(idx, dxy)
    df["dxy_ma50"] = align_macro(idx, dxy.rolling(50).mean())
    df["tnx"] = align_macro(idx, tnx)
    df["f_gold"] = df["gold"] > df["gold_ma200"]
    df["f_realyld"] = df["tips"] < df["tips_ma50"]
    df["f_dxy"] = df["dxy"] < df["dxy_ma50"]
    df["f_event"], has = event_flags(idx, ev, EVENT_LOOKAHEAD, london)
    df["event_day"] = has
    _, has_all = event_flags(idx, ev, EVENT_LOOKAHEAD, london, scheduled_only=False)
    df["event_day_any"] = has_all
    need = ["bbw_pct", "bbw_med", "z60", "atr", "gold_ma200", "tips_ma50", "dxy_ma50"]
    df["valid"] = df[need].notna().all(axis=1)
    return df


# --------------------------------------------------------------------------- #
# Strategy definitions
# --------------------------------------------------------------------------- #
SIGNALS = {
    "BBW≤p10": lambda d: d["bbw_pct"] <= 0.10,
    "BBW≤p15": lambda d: d["bbw_pct"] <= 0.15,
    "BBW≤p20": lambda d: d["bbw_pct"] <= 0.20,
    "BB-in-KC": lambda d: d["sq_kc"],
    "BBW≤p20 & KC": lambda d: (d["bbw_pct"] <= 0.20) & d["sq_kc"],
}
FILTERS = {
    "none": [],
    "gold>MA200": ["f_gold"],
    "realyld<MA50": ["f_realyld"],
    "DXY<MA50": ["f_dxy"],
    "event≤10d": ["f_event"],
    "gold+realyld+DXY": ["f_gold", "f_realyld", "f_dxy"],
    "all four": ["f_gold", "f_realyld", "f_dxy", "f_event"],
}
EXITS = {
    "hold 10d": ("hold", 10),
    "hold 20d": ("hold", 20),
    "hold 40d": ("hold", 40),
    "+2/-1 ATR, 40d": ("atr", 40),
    "BBW>median": ("bbw", None),
}


def entry_signal(d: pd.DataFrame, sig: str, zvar: bool, filt: str) -> np.ndarray:
    s = SIGNALS[sig](d).fillna(False)
    if zvar:
        s &= d["z60"] < -1
    for f in FILTERS[filt]:
        s &= d[f].fillna(False)
    return (s & d["valid"]).to_numpy(bool)


@dataclass
class SimResult:
    daily: np.ndarray      # strategy daily return (net)
    inpos: np.ndarray      # bool exposure per day
    trades: pd.DataFrame


class Market:
    """Plain-list view of one listing for a fast event loop."""

    def __init__(self, d: pd.DataFrame):
        self.d = d
        self.idx = d.index
        self.o = d["Open"].tolist()
        self.h = d["High"].tolist()
        self.l = d["Low"].tolist()
        self.c = d["Close"].tolist()
        self.atr = d["atr"].tolist()
        bbw = d["bbw"].to_numpy()
        med = d["bbw_med"].to_numpy()
        self.bbw_hi = (bbw > med).tolist()
        self.n = len(d)


def simulate(m: Market, sig: np.ndarray, exit_key: str, lo: int, hi: int,
             hold_override: int | None = None) -> SimResult:
    """Long-only, one position at a time. Entries only on signal closes t in
    [lo, hi); positions may run past hi to their natural exit."""
    mode, hold = EXITS[exit_key] if exit_key in EXITS else exit_key
    if hold_override is not None:
        hold = hold_override
    o, h, l, c, atr, bbw_hi, n = m.o, m.h, m.l, m.c, m.atr, m.bbw_hi, m.n
    daily = np.zeros(n)
    inpos = np.zeros(n, dtype=bool)
    trades = []
    t = lo
    sig_idx = np.flatnonzero(sig[lo:hi]) + lo
    si = 0
    half = COST_RT / 2
    while si < len(sig_idx):
        t = sig_idx[si]
        e = t + 1
        if e >= n:
            break
        ep = o[e]
        a = atr[t]
        tp, sl = ep + 2 * a, ep - a
        x, xp, why = None, None, None
        prev = ep
        for k in range(e, n):
            dnum = k - e + 1
            if mode == "atr":
                if k > e and o[k] <= sl:
                    x, xp, why = k, o[k], "stop (gap)"
                elif k > e and o[k] >= tp:
                    x, xp, why = k, o[k], "target (gap)"
                elif l[k] <= sl:
                    x, xp, why = k, sl, "stop"
                elif h[k] >= tp:
                    x, xp, why = k, tp, "target"
                elif dnum >= hold:
                    x, xp, why = k, c[k], "time"
            elif mode == "hold":
                if dnum >= hold:
                    x, xp, why = k, c[k], "time"
            elif mode == "bbw":
                if k > e and bbw_hi[k - 1]:
                    x, xp, why = k, o[k], "bbw>median"
            if x is not None:
                daily[k] += xp / prev - 1
                inpos[k] = True
                break
            daily[k] += c[k] / prev - 1
            inpos[k] = True
            prev = c[k]
        if x is None:  # still open at end of data: mark at last close
            x, xp, why = n - 1, c[n - 1], "open@end"
        daily[e] -= half
        daily[x] -= half
        trades.append(dict(signal_date=m.idx[t], entry_date=m.idx[e], exit_date=m.idx[x],
                           entry=ep, exit=xp, days=x - e + 1, reason=why,
                           ret=xp / ep - 1 - COST_RT, atr_entry=a))
        if why == "open@end":
            break
        # Flat by the close of exit day x (whether we sold at its open or its
        # close), so the next eligible signal is the close of x -> open x+1.
        while si < len(sig_idx) and sig_idx[si] < x:
            si += 1
    return SimResult(daily, inpos, pd.DataFrame(trades))


def metrics(daily: np.ndarray, inpos: np.ndarray, trades: pd.DataFrame,
            lo: int, hi: int) -> dict:
    r = daily[lo:hi]
    n = len(r)
    eq = np.cumprod(1 + r)
    yrs = n / 252
    cagr = eq[-1] ** (1 / yrs) - 1 if yrs > 0 and eq[-1] > 0 else np.nan
    dd = (eq / np.maximum.accumulate(eq) - 1).min() if n else np.nan
    sd = r.std(ddof=1)
    sharpe = r.mean() / sd * np.sqrt(252) if sd > 0 else np.nan
    t = trades
    nt = len(t)
    if nt:
        w, ls = t.ret[t.ret > 0], t.ret[t.ret <= 0]
        exp_ = t.ret.mean()
        tstat = exp_ / (t.ret.std(ddof=1) / math.sqrt(nt)) if nt > 2 and t.ret.std() > 0 else np.nan
    else:
        w = ls = pd.Series(dtype=float)
        exp_ = tstat = np.nan
    return dict(
        trades=nt,
        win_rate=len(w) / nt if nt else np.nan,
        avg_win=w.mean() if len(w) else np.nan,
        avg_loss=ls.mean() if len(ls) else np.nan,
        expectancy=exp_,
        t_stat=tstat,
        avg_days=t.days.mean() if nt else np.nan,
        CAGR=cagr,
        max_dd=dd,
        sharpe=sharpe,
        time_in_mkt=inpos[lo:hi].mean(),
        total_ret=eq[-1] - 1 if n else np.nan,
    )


def run_variant(m: Market, sig: np.ndarray, exit_key, lo: int, hi: int, hold=None):
    res = simulate(m, sig, exit_key, lo, hi, hold)
    return res, metrics(res.daily, res.inpos, res.trades, lo, hi)


def buy_hold(m: Market, lo: int, hi: int) -> tuple[np.ndarray, dict]:
    c = np.array(m.c)
    r = np.zeros(m.n)
    r[lo + 1:hi] = c[lo + 1:hi] / c[lo:hi - 1] - 1
    r[lo + 1] -= COST_RT / 2
    r[hi - 1] -= COST_RT / 2
    inpos = np.zeros(m.n, dtype=bool)
    inpos[lo + 1:hi] = True
    tr = pd.DataFrame([dict(ret=c[hi - 1] / c[lo] - 1 - COST_RT, days=hi - lo - 1)])
    mt = metrics(r, inpos, tr, lo, hi)
    for k in ("trades", "win_rate", "avg_win", "avg_loss", "expectancy", "t_stat", "avg_days"):
        mt[k] = np.nan  # a single buy-and-hold "trade" has no meaningful trade statistics
    return r, mt


def monte_carlo(m: Market, exit_key, lo: int, hi: int, n_trades_target: int,
                time_in_mkt: float, allowed: np.ndarray | None, rng, n_runs=N_MC, hold=None):
    """Random entries (Bernoulli per flat day), same exit rule, same window.
    Entry probability is set so the expected trade count matches the strategy.
    `allowed` optionally restricts random entries to days where the filters hold."""
    pool = np.arange(lo, hi)
    if allowed is not None:
        pool = pool[allowed[lo:hi]]
    flat_days = max(1.0, len(pool) * (1 - time_in_mkt))
    p = min(1.0, n_trades_target / flat_days)
    out = []
    eqs = []
    for _ in range(n_runs):
        sig = np.zeros(m.n, dtype=bool)
        sig[pool[rng.random(len(pool)) < p]] = True
        res = simulate(m, sig, exit_key, lo, hi, hold)
        mt = metrics(res.daily, res.inpos, res.trades, lo, hi)
        out.append(mt)
        eqs.append(np.cumprod(1 + res.daily[lo:hi]))
    return pd.DataFrame(out), np.array(eqs)


# --------------------------------------------------------------------------- #
# Episode / event analysis
# --------------------------------------------------------------------------- #
def squeeze_episodes(d: pd.DataFrame, sq: pd.Series, label: str) -> pd.DataFrame:
    sq = (sq.fillna(False) & d["valid"]).to_numpy(bool)
    c = d["Close"].to_numpy()
    atr = d["atr"].to_numpy()
    ev = d["event_day_any"].to_numpy()
    rows = []
    i, n = 0, len(sq)
    while i < n:
        if not sq[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and sq[j + 1]:
            j += 1
        if j + 10 < n:
            w = slice(j + 1, j + 11)
            path = (c[w] - c[j]) / atr[j]
            move = path[-1]
            maxabs = path[np.argmax(np.abs(path))]
            rows.append(dict(
                definition=label, start=d.index[i], end=d.index[j], length=j - i + 1,
                ret_10d=c[j + 10] / c[j] - 1, move_atr_10d=move,
                max_excursion_atr=maxabs, direction="up" if move > 0 else "down",
                big=abs(maxabs) > 2, event_in_window=bool(ev[w].any()),
            ))
        i = j + 1
    return pd.DataFrame(rows)


def unconditional_windows(d: pd.DataFrame) -> pd.DataFrame:
    c = d["Close"].to_numpy()
    atr = d["atr"].to_numpy()
    ev = d["event_day_any"].to_numpy()
    valid = d["valid"].to_numpy()
    rows = []
    for j in range(len(c) - 10):
        if not valid[j]:
            continue
        path = (c[j + 1:j + 11] - c[j]) / atr[j]
        rows.append((abs(path).max() > 2, bool(ev[j + 1:j + 11].any())))
    return pd.DataFrame(rows, columns=["big", "event"])


def fisher_two_sided(a, b, c_, d_):
    """2x2 Fisher exact p-value [[a,b],[c,d]] - stdlib only."""
    n1, n2, k = a + b, c_ + d_, a + c_
    N = n1 + n2

    def pmf(x):
        return math.comb(n1, x) * math.comb(n2, k - x) / math.comb(N, k)

    p0 = pmf(a)
    lo, hi = max(0, k - n2), min(k, n1)
    return min(1.0, sum(pmf(x) for x in range(lo, hi + 1) if pmf(x) <= p0 * (1 + 1e-9)))


def event_summary(ep: pd.DataFrame, base: pd.DataFrame) -> dict:
    big = ep[ep.big]
    a = int((ep.big & ep.event_in_window).sum())
    b = int((ep.big & ~ep.event_in_window).sum())
    c_ = int((~ep.big & ep.event_in_window).sum())
    d_ = int((~ep.big & ~ep.event_in_window).sum())
    return dict(
        episodes=len(ep),
        up_share=(ep.direction == "up").mean() if len(ep) else np.nan,
        mean_move_atr=ep.move_atr_10d.mean() if len(ep) else np.nan,
        mean_abs_move_atr=ep.move_atr_10d.abs().mean() if len(ep) else np.nan,
        big_moves=len(big),
        big_up=int((big.direction == "up").sum()),
        big_event_share=big.event_in_window.mean() if len(big) else np.nan,
        all_event_share=ep.event_in_window.mean() if len(ep) else np.nan,
        p_big_given_event=a / (a + c_) if a + c_ else np.nan,
        p_big_given_noevent=b / (b + d_) if b + d_ else np.nan,
        fisher_p=fisher_two_sided(a, b, c_, d_) if len(ep) else np.nan,
        base_event_share=base.event.mean(),
        base_big_rate=base.big.mean(),
        base_big_event_share=base[base.big].event.mean(),
    )


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def _style(ax):
    ax.set_facecolor(C["surface"])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(C["base"])
    ax.tick_params(colors=C["muted"], labelsize=8.5)
    ax.grid(True, color=C["grid"], lw=0.6)
    ax.set_axisbelow(True)


def _fig(w=11, h=4.2):
    fig, ax = plt.subplots(figsize=(w, h), dpi=130)
    fig.patch.set_facecolor(C["surface"])
    _style(ax)
    return fig, ax


def _plain_log(ax):
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
    ax.yaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _shade(ax, idx, mask, color, alpha=0.18):
    m = np.asarray(mask, bool)
    i, n = 0, len(m)
    while i < n:
        if m[i]:
            j = i
            while j + 1 < n and m[j + 1]:
                j += 1
            ax.axvspan(idx[i], idx[min(j + 1, n - 1)], color=color, alpha=alpha, lw=0)
            i = j + 1
        else:
            i += 1


def chart_price(d, sq_mask, trades, split_date, title):
    fig, ax = _fig(11, 4.6)
    ax.plot(d.index, d["Close"], color=C["ink2"], lw=1.1)
    _shade(ax, d.index, sq_mask, C["s4"], 0.22)
    if len(trades):
        win = trades.ret > 0
        ax.scatter(trades.entry_date, trades.entry, marker="^", s=34, color=C["s1"],
                   edgecolor=C["surface"], lw=0.8, zorder=5, label="entry")
        ax.scatter(trades.exit_date[win], trades.exit[win], marker="v", s=34, color=C["s3"],
                   edgecolor=C["surface"], lw=0.8, zorder=5, label="exit (win)")
        ax.scatter(trades.exit_date[~win], trades.exit[~win], marker="v", s=34, color=C["s8"],
                   edgecolor=C["surface"], lw=0.8, zorder=5, label="exit (loss)")
    ax.axvline(split_date, color=C["ink"], lw=1, ls="--")
    ax.text(split_date, ax.get_ylim()[1], "  out-of-sample →", va="top", fontsize=8.5, color=C["ink2"])
    ax.set_yscale("log")
    _plain_log(ax)
    ax.set_ylabel("USD (log)", color=C["ink2"], fontsize=9)
    ax.set_title(title, loc="left", fontsize=11, color=C["ink"])
    from matplotlib.patches import Patch
    h, lab = ax.get_legend_handles_labels()
    h.append(Patch(color=C["s4"], alpha=0.35))
    lab.append("squeeze active")
    ax.legend(h, lab, frameon=False, fontsize=8.5, loc="upper left", ncols=4)
    return _png(fig)


def chart_equity(idx, curves: dict, band, split_date, title, log=True):
    fig, ax = _fig(11, 4.2)
    colors = [C["s1"], C["s2"], C["s7"], C["s3"]]
    if band is not None:
        lo, med, hi_ = band
        ax.fill_between(idx, lo, hi_, color=C["muted"], alpha=0.18, lw=0,
                        label="random entries, 5–95%")
        ax.plot(idx, med, color=C["muted"], lw=1.4, ls="--", label="random entries, median")
    for (name, eq), col in zip(curves.items(), colors):
        ax.plot(idx, eq, color=col, lw=2 if col == C["s1"] else 1.4, label=name)
    if split_date is not None:
        ax.axvline(split_date, color=C["ink"], lw=1, ls="--")
    if log:
        ax.set_yscale("log")
        _plain_log(ax)
    ax.set_ylabel("growth of $1", color=C["ink2"], fontsize=9)
    ax.set_title(title, loc="left", fontsize=11, color=C["ink"])
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    return _png(fig)


def _diverging(v, vmax):
    """blue(+)<->grey<->red(-) for expectancy."""
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("div", ["#c0392b", "#e98b85", C["neutral"],
                                                     "#86b6ef", "#1c5cab"])
    return cmap


def chart_heatmaps(grids: list[tuple[str, pd.DataFrame, pd.DataFrame]]):
    fig, axes = plt.subplots(1, len(grids), figsize=(5.4 * len(grids), 4.2), dpi=130)
    fig.patch.set_facecolor(C["surface"])
    vmax = max(np.nanmax(np.abs(g.values)) for _, g, _ in grids) or 1
    cmap = _diverging(None, vmax)
    for ax, (title, g, nt) in zip(np.atleast_1d(axes), grids):
        ax.set_facecolor(C["surface"])
        im = ax.imshow(g.values, cmap=cmap, vmin=-vmax, vmax=vmax, aspect="auto")
        ax.set_xticks(range(g.shape[1]), [str(c) for c in g.columns], fontsize=8.5, color=C["ink2"])
        ax.set_yticks(range(g.shape[0]), [f"p{int(round(i*100))}" for i in g.index], fontsize=8.5,
                      color=C["ink2"])
        ax.set_xlabel("hold (trading days)", fontsize=9, color=C["ink2"])
        ax.set_ylabel("BB-width percentile threshold", fontsize=9, color=C["ink2"])
        for i in range(g.shape[0]):
            for j in range(g.shape[1]):
                v = g.values[i, j]
                if np.isnan(v):
                    continue
                ax.text(j, i, f"{v*100:+.1f}%\n n={int(nt.values[i, j])}", ha="center",
                        va="center", fontsize=7, color=C["ink"])
        ax.set_title(title, loc="left", fontsize=10.5, color=C["ink"])
        for s in ax.spines.values():
            s.set_visible(False)
    cb = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02)
    cb.set_label("expectancy per trade (net)", fontsize=8.5, color=C["ink2"])
    cb.ax.tick_params(labelsize=8, colors=C["muted"])
    cb.ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    return _png(fig)


def chart_mc_hist(mc: pd.DataFrame, actual: float, title: str, field="expectancy"):
    fig, ax = _fig(5.4, 3.3)
    v = mc[field].dropna().to_numpy()
    ax.hist(v, bins=40, color=C["s1"], alpha=0.85, edgecolor=C["surface"], lw=0.6)
    ax.axvline(actual, color=C["s2"], lw=2)
    pct = (v < actual).mean()
    ax.annotate(f"strategy\n(beats {pct:.0%} of random)", (actual, ax.get_ylim()[1] * 0.9),
                xytext=(6, 0), textcoords="offset points", fontsize=8, color=C["ink"], va="top")
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=1))
    ax.set_title(title, loc="left", fontsize=10, color=C["ink"])
    ax.set_ylabel("runs", fontsize=9, color=C["ink2"])
    return _png(fig)


def chart_episodes(ep: pd.DataFrame, title: str):
    fig, ax = _fig(5.4, 3.3)
    for flag, col, lab in ((True, C["s2"], "FOMC/CPI in window"), (False, C["s1"], "no event")):
        e = ep[ep.event_in_window == flag]
        ax.scatter(e.end, e.max_excursion_atr, s=22, color=col, edgecolor=C["surface"], lw=0.6,
                   label=f"{lab} (n={len(e)})")
    for y in (2, -2):
        ax.axhline(y, color=C["base"], lw=1, ls="--")
    ax.axhline(0, color=C["base"], lw=0.8)
    ax.set_ylabel("max 10-day excursion (ATR)", fontsize=9, color=C["ink2"])
    ax.set_title(title, loc="left", fontsize=10, color=C["ink"])
    ax.legend(frameon=False, fontsize=8)
    return _png(fig)


# --------------------------------------------------------------------------- #
# Report helpers
# --------------------------------------------------------------------------- #
PCT_COLS = {"win_rate", "avg_win", "avg_loss", "expectancy", "CAGR", "max_dd", "time_in_mkt",
            "total_ret"}
NICE = {"trades": "Trades", "win_rate": "Win %", "avg_win": "Avg win", "avg_loss": "Avg loss",
        "expectancy": "Expectancy", "t_stat": "t-stat", "avg_days": "Avg days", "CAGR": "CAGR",
        "max_dd": "Max DD", "sharpe": "Sharpe", "time_in_mkt": "Time in mkt",
        "total_ret": "Total ret", "mc_pct": "Beats random"}


def fmt(v, col):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    if col in PCT_COLS or col == "mc_pct":
        return f"{v*100:.1f}%" if col not in ("win_rate", "time_in_mkt", "mc_pct") else f"{v*100:.0f}%"
    if col in ("sharpe", "t_stat"):
        return f"{v:.2f}"
    if col == "avg_days":
        return f"{v:.1f}"
    if col == "trades":
        return f"{int(v)}"  # NaN handled above
    return html.escape(str(v))


def table(df: pd.DataFrame, cols: list[str], label_cols: list[str], highlight=None,
          small_n=15) -> str:
    th = "".join(f"<th class='lbl'>{html.escape(NICE.get(c, c))}</th>" for c in label_cols)
    th += "".join(f"<th>{html.escape(NICE.get(c, c))}</th>" for c in cols)
    rows = []
    for i, r in df.iterrows():
        cls = []
        if highlight is not None and highlight(r):
            cls.append("hl")
        tds = "".join(f"<td class='lbl'>{html.escape(str(r[c]))}</td>" for c in label_cols)
        for c in cols:
            v = r.get(c)
            extra = ""
            if c == "trades" and isinstance(v, (int, float)) and not np.isnan(v) and v < small_n:
                extra = " class='warn' title='small sample'"
            elif c in ("expectancy", "CAGR", "sharpe", "total_ret") and isinstance(v, float) and not np.isnan(v):
                extra = " class='pos'" if v > 0 else " class='neg'"
            tds += f"<td{extra}>{fmt(v, c)}</td>"
        rows.append(f"<tr class='{' '.join(cls)}'>{tds}</tr>")
    return f"<div class='tw'><table><thead><tr>{th}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def img(b64, alt):
    return f"<figure><img alt='{html.escape(alt)}' src='data:image/png;base64,{b64}'/></figure>"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download all raw data")
    ap.add_argument("--mc", type=int, default=N_MC, help="Monte-Carlo runs")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    rng = np.random.default_rng(RNG_SEED)

    print("[1/8] data")
    raw = load_prices(args.refresh)
    data_notes: list[str] = []
    gdxl = clean_ohlc(raw["GDX_L"], "GDX.L", data_notes)
    gdxu = clean_ohlc(raw["GDX_US"], "GDX (US)", data_notes)
    first_year = gdxu.index[0].year

    print("[2/8] event calendar")
    ev = build_events(args.refresh, first_year, notes)

    print("[3/8] indicators + alignment")
    D = build_frame(gdxl, raw, ev, london=True)
    DU = build_frame(gdxu, raw, ev, london=False)
    m = Market(D)
    valid_pos = np.flatnonzero(D["valid"].to_numpy())
    start = int(valid_pos[0])
    end = m.n
    split = start + int(IS_FRAC * (end - start))
    IS, OOS, FULL = (start, split), (split, end), (start, end)
    d_start, d_split, d_end = D.index[start], D.index[split], D.index[end - 1]
    print(f"   usable {d_start.date()} → {d_end.date()}; split at {d_split.date()}")

    print("[4/8] variant grid")
    rows = []
    sims = {}
    for sig in SIGNALS:
        for zv in (False, True):
            for filt in FILTERS:
                s = entry_signal(D, sig, zv, filt)
                for ex in EXITS:
                    for seg, (lo, hi) in (("IS", IS), ("OOS", OOS)):
                        res, mt = run_variant(m, s, ex, lo, hi)
                        rows.append(dict(signal=sig, zscore="z<-1" if zv else "–", filter=filt,
                                         exit=ex, segment=seg, **mt))
                        sims[(sig, zv, filt, ex, seg)] = res
    V = pd.DataFrame(rows)
    V.to_csv(OUT_DIR / "variants.csv", index=False, float_format="%.6f")
    key = ["signal", "zscore", "filter", "exit"]
    Vis = V[V.segment == "IS"].drop(columns="segment").set_index(key)
    Voos = V[V.segment == "OOS"].drop(columns="segment").set_index(key)

    # In-sample selection: highest IS Sharpe among variants with enough trades.
    elig = Vis[(Vis.trades >= MIN_IS_TRADES)]
    best_key = elig["sharpe"].idxmax()
    b_sig, b_z, b_filt, b_ex = best_key
    b_zv = b_z != "–"
    n_tested = len(Vis)
    n_elig = len(elig)
    print(f"   selected (IS Sharpe): {best_key}")
    # Also the best UNFILTERED variant, to isolate the filters' contribution.
    elig_nf = elig.xs("none", level="filter")
    nf_key = elig_nf["sharpe"].idxmax()
    nf_sig, nf_z, nf_ex = nf_key

    print("[5/8] baselines + Monte Carlo")
    sig_best = entry_signal(D, b_sig, b_zv, b_filt)
    res_full = simulate(m, sig_best, b_ex, *FULL)
    res_full.trades["segment"] = np.where(res_full.trades.entry_date < d_split, "IS", "OOS")
    res_full.trades.to_csv(OUT_DIR / "trades_selected.csv", index=False, float_format="%.6f")
    bh = {}
    for seg, (lo, hi) in (("IS", IS), ("OOS", OOS), ("FULL", FULL)):
        bh[seg] = buy_hold(m, lo, hi)
    mc = {}
    filt_mask = np.ones(m.n, dtype=bool)
    for f in FILTERS[b_filt]:
        filt_mask &= D[f].fillna(False).to_numpy()
    filt_mask &= D["valid"].to_numpy()
    for seg, (lo, hi) in (("IS", IS), ("OOS", OOS), ("FULL", FULL)):
        mt = Vis.loc[best_key] if seg == "IS" else (Voos.loc[best_key] if seg == "OOS" else
                                                     metrics(res_full.daily, res_full.inpos,
                                                             res_full.trades, lo, hi))
        mt = dict(mt)
        mc[(seg, "any")] = monte_carlo(m, b_ex, lo, hi, mt["trades"], mt["time_in_mkt"], None, rng,
                                       args.mc)
        mc[(seg, "filt")] = monte_carlo(m, b_ex, lo, hi, mt["trades"], mt["time_in_mkt"],
                                        filt_mask if FILTERS[b_filt] else None, rng, args.mc)
        mc[(seg, "metrics")] = mt

    def mc_rank(seg, kind, field):
        dfm, _ = mc[(seg, kind)]
        v = dfm[field].dropna()
        return (v < mc[(seg, "metrics")][field]).mean() if len(v) else np.nan

    # Quick MC (fewer runs) for every filter row of the selected signal/exit, OOS and IS.
    print("   per-filter random baselines")
    filt_rows = []
    for filt in FILTERS:
        k = (b_sig, b_z, filt, b_ex)
        for seg, (lo, hi), VV in (("IS", IS, Vis), ("OOS", OOS, Voos)):
            mt = dict(VV.loc[k])
            if mt["trades"] >= 3:
                dfm, _ = monte_carlo(m, b_ex, lo, hi, mt["trades"], mt["time_in_mkt"], None, rng,
                                     max(200, args.mc // 5))
                pr = (dfm.expectancy.dropna() < mt["expectancy"]).mean()
            else:
                pr = np.nan
            filt_rows.append(dict(filter=filt, segment=seg, mc_pct=pr, **mt))
    FT = pd.DataFrame(filt_rows)

    print("[6/8] sensitivity grid")
    pcts = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    holds = [5, 10, 15, 20, 30, 40]
    sens = []
    for p in pcts:
        s = (D["bbw_pct"] <= p).fillna(False)
        if b_zv:
            s &= D["z60"] < -1
        for f in FILTERS[b_filt]:
            s &= D[f].fillna(False)
        s = (s & D["valid"]).to_numpy(bool)
        for hd in holds:
            for seg, (lo, hi) in (("IS", IS), ("OOS", OOS)):
                _, mt = run_variant(m, s, ("hold", hd), lo, hi)
                sens.append(dict(pct=p, hold=hd, segment=seg, **mt))
    S = pd.DataFrame(sens)
    S.to_csv(OUT_DIR / "sensitivity.csv", index=False, float_format="%.6f")
    g_is = S[S.segment == "IS"].pivot(index="pct", columns="hold", values="expectancy")
    n_is = S[S.segment == "IS"].pivot(index="pct", columns="hold", values="trades")
    g_oos = S[S.segment == "OOS"].pivot(index="pct", columns="hold", values="expectancy")
    n_oos = S[S.segment == "OOS"].pivot(index="pct", columns="hold", values="trades")
    pos_is = (g_is > 0).values.mean()
    pos_oos = (g_oos > 0).values.mean()
    bi, bj = np.unravel_index(np.nanargmax(g_is.values), g_is.shape)
    neigh = [g_is.values[i, j] for i in range(bi - 1, bi + 2) for j in range(bj - 1, bj + 2)
             if 0 <= i < g_is.shape[0] and 0 <= j < g_is.shape[1] and (i, j) != (bi, bj)]
    peak, neigh_med = g_is.values[bi, bj], float(np.nanmedian(neigh))
    isolated_peak = neigh_med < 0.5 * peak
    corr_is_oos = pd.Series(g_is.values.ravel()).corr(pd.Series(g_oos.values.ravel()))

    print("[7/8] US GDX robustness")
    mu = Market(DU)
    vpu = np.flatnonzero(DU["valid"].to_numpy())
    us_lo = int(vpu[0])
    us_l_start = DU.index.searchsorted(D.index[0])
    us_rows = []
    sig_us = entry_signal(DU, b_sig, b_zv, b_filt)
    sig_us_nf = entry_signal(DU, nf_sig, nf_z != "–", "none")
    us_res = {}
    for lab, (lo, hi) in (("pre-GDX.L (unseen)", (us_lo, us_l_start)),
                          ("GDX.L era", (us_l_start, mu.n)), ("full", (us_lo, mu.n))):
        for rule, sg, ex in (("selected rule", sig_us, b_ex), ("best unfiltered", sig_us_nf, nf_ex)):
            res, mt = run_variant(mu, sg, ex, lo, hi)
            dfm, _ = monte_carlo(mu, ex, lo, hi, mt["trades"], mt["time_in_mkt"], None, rng,
                                 max(200, args.mc // 5))
            us_rows.append(dict(period=lab, rule=rule, mc_pct=(dfm.expectancy.dropna() < mt["expectancy"]).mean(),
                                **mt))
            us_res[(lab, rule)] = res
        _, bm = buy_hold(mu, lo, hi)
        us_rows.append(dict(period=lab, rule="buy & hold", mc_pct=np.nan, **bm))
    US = pd.DataFrame(us_rows)
    US.to_csv(OUT_DIR / "us_gdx_robustness.csv", index=False, float_format="%.6f")

    print("[8/8] event analysis + report")
    ep_frames, ev_sum = [], []
    for lab, dd in (("GDX.L", D), ("GDX US", DU)):
        base = unconditional_windows(dd)
        for defn, sq in (("BBW≤p20", dd["bbw_pct"] <= 0.20), ("BB-in-KC", dd["sq_kc"])):
            ep = squeeze_episodes(dd, sq, defn)
            ep["listing"] = lab
            ep_frames.append(ep)
            ev_sum.append(dict(listing=lab, definition=defn, **event_summary(ep, base)))
    EP = pd.concat(ep_frames)
    EP.to_csv(OUT_DIR / "episodes.csv", index=False, float_format="%.4f")
    ES = pd.DataFrame(ev_sum)

    # ---------------- charts ----------------
    sq_mask_best = SIGNALS[b_sig](D).fillna(False) & D["valid"]
    ch_price = chart_price(D.iloc[start:], sq_mask_best.iloc[start:], res_full.trades, d_split,
                           f"GDX.L — squeeze periods ({b_sig}) and trades of the selected rule")
    idx = D.index[start:end]
    strat_eq = np.cumprod(1 + res_full.daily[start:end])
    bh_eq = np.cumprod(1 + bh["FULL"][0][start:end])
    nf_full = simulate(m, entry_signal(D, nf_sig, nf_z != "–", "none"), nf_ex, *FULL)
    nf_eq = np.cumprod(1 + nf_full.daily[start:end])
    eqs = mc[("FULL", "any")][1]
    band = (np.percentile(eqs, 5, axis=0), np.median(eqs, axis=0), np.percentile(eqs, 95, axis=0))
    ch_eq = chart_equity(idx, {"selected rule": strat_eq, "buy & hold": bh_eq,
                               "best unfiltered squeeze": nf_eq}, band, d_split,
                         "Equity curves vs baselines (net of 0.15% round trip)")
    ch_mc_is = chart_mc_hist(mc[("IS", "any")][0], mc[("IS", "metrics")]["expectancy"],
                             "In-sample: expectancy vs 1,000 random-entry runs")
    ch_mc_oos = chart_mc_hist(mc[("OOS", "any")][0], mc[("OOS", "metrics")]["expectancy"],
                              "Out-of-sample: expectancy vs 1,000 random-entry runs")
    ch_heat = chart_heatmaps([("In-sample", g_is, n_is), ("Out-of-sample", g_oos, n_oos)])
    ep_l = EP[(EP.listing == "GDX.L") & (EP.definition == "BBW≤p20")]
    ep_u = EP[(EP.listing == "GDX US") & (EP.definition == "BBW≤p20")]
    ch_ep_l = chart_episodes(ep_l, "GDX.L squeeze episodes (BBW≤p20)")
    ch_ep_u = chart_episodes(ep_u, "US GDX squeeze episodes (BBW≤p20)")
    us_full = us_res[("full", "selected rule")]
    us_bh = np.cumprod(1 + buy_hold(mu, us_lo, mu.n)[0][us_lo:])
    ch_us = chart_equity(DU.index[us_lo:], {"selected rule (US GDX)": np.cumprod(1 + us_full.daily[us_lo:]),
                                            "buy & hold": us_bh,
                                            "best unfiltered (US GDX)": np.cumprod(1 + us_res[("full", "best unfiltered")].daily[us_lo:])},
                         None, D.index[0], "US GDX: same rule on the longer history (dashed line = GDX.L listing date)")

    # ---------------- verdict logic ----------------
    frac_pos_is = (Vis.expectancy > 0).mean()
    mis, moos = mc[("IS", "metrics")], mc[("OOS", "metrics")]
    r_is_any, r_oos_any = mc_rank("IS", "any", "expectancy"), mc_rank("OOS", "any", "expectancy")
    r_oos_filt = mc_rank("OOS", "filt", "expectancy")
    r_oos_sh = mc_rank("OOS", "any", "sharpe")
    ft_oos = FT[FT.segment == "OOS"].set_index("filter")
    ft_is = FT[FT.segment == "IS"].set_index("filter")
    base_exp_is, base_exp_oos = ft_is.loc["none", "expectancy"], ft_oos.loc["none", "expectancy"]
    single = ["gold>MA200", "realyld<MA50", "DXY<MA50", "event≤10d"]
    uplift = pd.DataFrame({
        "IS": [ft_is.loc[f, "expectancy"] - base_exp_is for f in single],
        "OOS": [ft_oos.loc[f, "expectancy"] - base_exp_oos for f in single],
    }, index=single)
    uplift["both"] = uplift.min(axis=1)
    best_filter = uplift["both"].idxmax()
    us_unseen = US[(US.period == "pre-GDX.L (unseen)") & (US.rule == "selected rule")].iloc[0]
    oos_pass = (moos["trades"] >= 10 and moos["expectancy"] > 0 and r_oos_any >= 0.9)
    us_pass = us_unseen["expectancy"] > 0 and us_unseen["mc_pct"] >= 0.9
    bh_oos = bh["OOS"][1]

    if oos_pass and us_pass and not isolated_peak:
        headline = "There is some evidence of an edge, but it is modest and fragile."
    elif moos["expectancy"] > 0 and (r_oos_any >= 0.75 or us_pass):
        headline = "Weak evidence at best — not distinguishable from chance with confidence."
    else:
        headline = "No reliable edge: the squeeze does not beat random entries once you leave the sample it was tuned on."

    es_l = ES[(ES.listing == "GDX.L") & (ES.definition == "BBW≤p20")].iloc[0]
    es_u = ES[(ES.listing == "GDX US") & (ES.definition == "BBW≤p20")].iloc[0]

    pct = lambda v: "–" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v*100:.1f}%"
    pc0 = lambda v: "–" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v*100:.0f}%"

    verdict = f"""
<p class='lede'><strong>{html.escape(headline)}</strong></p>
<ul>
<li><strong>Selected rule (chosen in-sample out of {n_tested} variants, {n_elig} with ≥{MIN_IS_TRADES} trades):</strong>
{html.escape(b_sig)}{' + z<−1' if b_zv else ''}, filter <em>{html.escape(b_filt)}</em>, exit <em>{html.escape(b_ex)}</em>.
In-sample: {int(mis['trades'])} trades, expectancy {pct(mis['expectancy'])}, Sharpe {mis['sharpe']:.2f}.
Out-of-sample: {int(moos['trades'])} trades, expectancy {pct(moos['expectancy'])}, Sharpe {moos['sharpe']:.2f},
CAGR {pct(moos['CAGR'])} vs buy-and-hold {pct(bh_oos['CAGR'])}.</li>
{f"<li><strong>Nothing worked in-sample.</strong> The best in-sample Sharpe among the {n_elig} eligible variants is only {mis['sharpe']:.2f}"
 f" ({pc0(frac_pos_is)} of all variants had positive IS expectancy). Choosing the 'best' of a flat, noisy surface is close to choosing at random;"
 f" any OOS strength then says more about the OOS period than about the rule.</li>" if mis['sharpe'] < 0.5 else ""}
<li><strong>Versus chance:</strong> the OOS expectancy beats {pc0(r_oos_any)} of 1,000 random-entry runs with the same exit
(and {pc0(r_oos_filt)} of random entries restricted to days when the filter was on); OOS Sharpe beats {pc0(r_oos_sh)}.
In-sample it beat {pc0(r_is_any)} — but in-sample is where it was picked from {n_tested} candidates, so that number is inflated by selection.
A 95th-percentile result is the bar a single pre-registered test would need; after a {n_tested}-way search the honest bar is far higher.</li>
<li><strong>Which filter adds the most:</strong> judged by the smaller of its IS and OOS expectancy uplift over the unfiltered
{html.escape(b_sig)} signal, <em>{html.escape(best_filter)}</em> adds the most
(IS {pct(uplift.loc[best_filter,'IS'])}, OOS {pct(uplift.loc[best_filter,'OOS'])} per trade).
{('It is the only filter that helps in both halves.' if (uplift['both'] > 0).sum() == 1 else
  f"{int((uplift['both'] > 0).sum())} of 4 single filters help in both halves." if (uplift['both'] > 0).sum() > 1 else
  'No single filter helps in both halves — every apparent filter benefit flips sign between in-sample and out-of-sample.')}
Filters cut the trade count sharply, so each row rests on fewer trades.</li>
<li><strong>Parameter sensitivity:</strong> {pc0(pos_is)} of the 36 percentile×hold cells are positive in-sample and {pc0(pos_oos)} out-of-sample;
the IS/OOS cell correlation is {corr_is_oos:.2f}.
{'The in-sample peak is isolated (neighbours average less than half of it) — a classic overfitting signature.' if isolated_peak else 'The in-sample peak is not isolated: neighbouring cells tell a similar story.'}
{' A low or negative IS/OOS correlation means the shape of the surface does not persist.' if corr_is_oos < 0.3 else ''}</li>
<li><strong>Longer history (US GDX):</strong> on 2006–{D.index[0].year} data that was never used for selection, the same rule made
{int(us_unseen['trades'])} trades with expectancy {pct(us_unseen['expectancy'])} (beats {pc0(us_unseen['mc_pct'])} of random entries).
{'That is supportive.' if us_pass else 'That does not confirm the GDX.L result.'}</li>
<li><strong>Events:</strong> on GDX.L, {pc0(es_l['big_event_share'])} of the big post-squeeze moves (>2 ATR within 10 days) had an FOMC/CPI release in the window —
but {pc0(es_l['base_event_share'])} of <em>all</em> 10-day windows contain one, because there are ~20 such releases a year.
P(big | event) = {pc0(es_l['p_big_given_event'])} vs P(big | no event) = {pc0(es_l['p_big_given_noevent'])}
(Fisher p = {es_l['fisher_p']:.2f}). On US GDX: {pc0(es_u['big_event_share'])} event-driven vs {pc0(es_u['base_event_share'])} base rate.
"Event-driven" is therefore mostly a base-rate artefact; the event filter is nearly always on and barely filters.</li>
</ul>
<h3>What would make it fail</h3>
<ul>
<li><strong>Sample size.</strong> The OOS window is ~{(d_end - d_split).days/365.25:.1f} years with {int(moos['trades'])} trades; a single gold-miner rally or crash moves the result more than the signal does.</li>
<li><strong>Regime dependence.</strong> GDX is a ~2–3× levered bet on gold. The OOS window overlaps a historic gold bull market, so any long-only rule looks good in absolute terms;
the random-entry comparison, not CAGR, is the test that matters.</li>
<li><strong>Direction-agnostic signal, long-only trade.</strong> A squeeze predicts that volatility will expand, not which way. The trade only profits when the expansion is upward — which is mostly a bet on the gold trend, i.e. on the filters, not on the squeeze.</li>
<li><strong>Selection bias.</strong> {n_tested} variants were tested; the best of many noisy backtests always looks good. The full grid is shown so you can see the spread.</li>
<li><strong>Execution on GDX.L.</strong> The LSE line is thinly traded (early history has no-trade days and vendor bars with Open outside High/Low). Real spreads at the open can exceed the 0.15% assumed; the USD line is also quoted while the US market is shut, so the London open often just reprices the prior US close.</li>
<li><strong>Stops on daily bars.</strong> The ATR target/stop assumes fills at the level unless the open gaps through it, and assumes the stop is hit first when a bar touches both.</li>
</ul>
"""

    # ---------------- tables ----------------
    cols = ["trades", "win_rate", "avg_win", "avg_loss", "expectancy", "t_stat", "avg_days", "CAGR",
            "max_dd", "sharpe", "time_in_mkt"]
    hl_sel = lambda r: (r.get("signal", b_sig), r.get("zscore", b_z), r.get("filter", b_filt),
                        r.get("exit", b_ex)) == best_key

    def seg_table(df_is, df_oos, label_cols, hl=None):
        a = df_is.reset_index().assign(segment="IS")
        b = df_oos.reset_index().assign(segment="OOS")
        both = pd.concat([a, b]).sort_values(label_cols + ["segment"], kind="stable")
        return table(both, cols, label_cols + ["segment"], hl)

    # Signal table: best unfiltered exit, filter none
    sig_is = Vis.xs(("none", b_ex), level=("filter", "exit"))
    sig_oos = Voos.xs(("none", b_ex), level=("filter", "exit"))
    t_signals = seg_table(sig_is, sig_oos, ["signal", "zscore"])
    # Filter table
    ft = FT.copy()
    ft["segment"] = pd.Categorical(ft.segment, ["IS", "OOS"])
    ft["filter"] = pd.Categorical(ft["filter"], list(FILTERS))
    t_filters = table(ft.sort_values(["filter", "segment"]), cols + ["mc_pct"], ["filter", "segment"],
                      lambda r: r["filter"] == b_filt)
    # Exit table
    ex_is = Vis.xs((b_sig, b_z, b_filt), level=("signal", "zscore", "filter"))
    ex_oos = Voos.xs((b_sig, b_z, b_filt), level=("signal", "zscore", "filter"))
    t_exits = seg_table(ex_is, ex_oos, ["exit"])
    # Baselines table
    bl = []
    for seg in ("IS", "OOS", "FULL"):
        bl.append(dict(rule="selected rule", segment=seg, **mc[(seg, "metrics")]))
        bl.append(dict(rule="buy & hold", segment=seg, **bh[seg][1]))
        mcm = mc[(seg, "any")][0].median(numeric_only=True).to_dict()
        bl.append(dict(rule="random entries (median of 1,000)", segment=seg, **mcm))
        if FILTERS[b_filt]:
            mcf = mc[(seg, "filt")][0].median(numeric_only=True).to_dict()
            bl.append(dict(rule="random entries on filter-on days (median)", segment=seg, **mcf))
    t_base = table(pd.DataFrame(bl), cols, ["rule", "segment"], lambda r: r["rule"] == "selected rule")
    t_us = table(US, cols + ["mc_pct"], ["period", "rule"], lambda r: r["rule"] == "selected rule")
    # Top 15 IS variants with their OOS
    top = Vis[Vis.trades >= MIN_IS_TRADES].sort_values("sharpe", ascending=False).head(15)
    top_tbl = top[["trades", "expectancy", "sharpe"]].join(
        Voos[["trades", "expectancy", "sharpe"]], rsuffix="_oos").reset_index()
    top_tbl.columns = ["signal", "zscore", "filter", "exit", "IS trades", "IS expectancy", "IS Sharpe",
                       "OOS trades", "OOS expectancy", "OOS Sharpe"]
    th = "".join(f"<th class='lbl'>{c}</th>" if i < 4 else f"<th>{c}</th>"
                 for i, c in enumerate(top_tbl.columns))
    trs = ""
    for _, r in top_tbl.iterrows():
        cells = ""
        for c in top_tbl.columns:
            v = r[c]
            if "expectancy" in c:
                cells += f"<td class='{'pos' if v > 0 else 'neg'}'>{pct(v)}</td>"
            elif "Sharpe" in c:
                cells += f"<td class='{'pos' if v > 0 else 'neg'}'>{v:.2f}</td>"
            elif "trades" in c:
                cells += f"<td>{int(v)}</td>"
            else:
                cells += f"<td class='lbl'>{html.escape(str(v))}</td>"
        trs += f"<tr>{cells}</tr>"
    t_top = f"<div class='tw'><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>"
    oos_rank_all = (Voos.loc[top.index[0]]["sharpe"])
    n_top_pos_oos = int((top_tbl["OOS expectancy"] > 0).sum())
    # Full variants table (collapsible)
    allv = Vis[["trades", "expectancy", "sharpe"]].join(Voos[["trades", "expectancy", "sharpe"]],
                                                        rsuffix="_oos").reset_index()
    frac_pos_is = (allv.expectancy > 0).mean()
    frac_pos_oos = (allv.expectancy_oos > 0).mean()
    corr_all = allv[allv.trades >= 5][["expectancy", "expectancy_oos"]].corr().iloc[0, 1]
    trs = "".join(
        f"<tr><td class='lbl'>{html.escape(r.signal)}</td><td class='lbl'>{r.zscore}</td>"
        f"<td class='lbl'>{html.escape(r['filter'])}</td><td class='lbl'>{html.escape(r.exit)}</td>"
        f"<td>{int(r.trades)}</td><td>{pct(r.expectancy)}</td><td>{fmt(r.sharpe,'sharpe')}</td>"
        f"<td>{int(r.trades_oos)}</td><td>{pct(r.expectancy_oos)}</td><td>{fmt(r.sharpe_oos,'sharpe')}</td></tr>"
        for _, r in allv.iterrows())
    t_all = ("<div class='tw'><table><thead><tr><th>Signal</th><th>z</th><th>Filter</th><th>Exit</th>"
             "<th>IS trades</th><th>IS exp.</th><th>IS Sharpe</th><th>OOS trades</th><th>OOS exp.</th>"
             f"<th>OOS Sharpe</th></tr></thead><tbody>{trs}</tbody></table></div>")
    es_cols = ["listing", "definition", "episodes", "up_share", "mean_abs_move_atr", "big_moves", "big_up",
               "big_event_share", "base_event_share", "p_big_given_event", "p_big_given_noevent", "fisher_p",
               "base_big_rate"]
    es_nice = ["Listing", "Definition", "Episodes", "Resolved up", "Mean |move| (ATR)", "Big moves",
               "…of which up", "Big moves with event", "All 10d windows with event", "P(big | event)",
               "P(big | no event)", "Fisher p", "Unconditional P(big)"]
    trs = ""
    for _, r in ES.iterrows():
        cells = ""
        for c in es_cols:
            v = r[c]
            if c in ("up_share", "big_event_share", "base_event_share", "p_big_given_event",
                     "p_big_given_noevent", "base_big_rate"):
                cells += f"<td>{pc0(v)}</td>"
            elif c in ("mean_abs_move_atr", "fisher_p"):
                cells += f"<td>{v:.2f}</td>"
            elif c in ("episodes", "big_moves", "big_up"):
                cells += f"<td>{int(v)}</td>"
            else:
                cells += f"<td class='lbl'>{html.escape(str(v))}</td>"
        trs += f"<tr>{cells}</tr>"
    t_events = ("<div class='tw'><table><thead><tr>" + "".join(f"<th>{c}</th>" for c in es_nice) +
                f"</tr></thead><tbody>{trs}</tbody></table></div>")
    # Episode list (GDX.L)
    epl = EP[EP.listing == "GDX.L"].sort_values(["definition", "end"])
    trs = "".join(
        f"<tr><td class='lbl'>{html.escape(r.definition)}</td><td>{r.start.date()}</td><td>{r.end.date()}</td>"
        f"<td>{r.length}</td><td class='{'pos' if r.ret_10d > 0 else 'neg'}'>{r.ret_10d*100:+.1f}%</td>"
        f"<td>{r.move_atr_10d:+.2f}</td><td>{r.max_excursion_atr:+.2f}</td><td>{'yes' if r.big else ''}</td>"
        f"<td>{'yes' if r.event_in_window else ''}</td></tr>" for _, r in epl.iterrows())
    t_eplist = ("<div class='tw'><table><thead><tr><th>Definition</th><th>Start</th><th>End</th><th>Days</th>"
                "<th>10d return</th><th>10d move (ATR)</th><th>Max excursion (ATR)</th><th>Big</th>"
                f"<th>Event in window</th></tr></thead><tbody>{trs}</tbody></table></div>")

    n_ev_f = int(((ev.type == "FOMC") & ev.scheduled).sum())
    n_ev_u = int((ev.kind == "unscheduled").sum())
    n_ev_cc = int(ev.kind.isin(["conference call", "notation vote"]).sum())
    n_ev_c = int((ev.type == "CPI").sum())
    notes_html = "".join(f"<li>{html.escape(n)}</li>" for n in notes) or "<li>No gaps detected.</li>"
    data_notes_html = "".join(f"<li>{html.escape(n)}</li>" for n in data_notes)

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GDX.L Squeeze Backtest</title>
<style>
:root {{ --bg:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --grid:#e1e0d9;
  --pos:#006300; --neg:#b42323; --hl:#eef4fc; --warn:#8a5a00; --border:rgba(11,11,11,.10); }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#0d0d0d; --surface:#1a1a19;
  --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --pos:#0ca30c; --neg:#e66767; --hl:#1d2836;
  --warn:#eda100; --border:rgba(255,255,255,.10); }} }}
:root[data-theme="dark"] {{ --bg:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --grid:#2c2c2a;
  --pos:#0ca30c; --neg:#e66767; --hl:#1d2836; --warn:#eda100; --border:rgba(255,255,255,.10); }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:1180px; margin:0 auto; padding:24px 16px 64px; }}
h1 {{ font-size:1.6rem; margin:.2em 0 .1em }} h2 {{ font-size:1.2rem; margin:2.2em 0 .5em; padding-top:.6em; border-top:1px solid var(--grid) }}
h3 {{ font-size:1rem; margin:1.4em 0 .4em }}
.sub {{ color:var(--ink2); margin:0 0 1em }} .lede {{ font-size:1.08rem }}
figure {{ margin:12px 0; background:#fcfcfb; border:1px solid var(--border); border-radius:8px; padding:8px; }}
figure img {{ width:100%; height:auto; display:block }}
.row {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:12px }}
.tw {{ overflow-x:auto; border:1px solid var(--border); border-radius:8px; background:var(--surface); margin:10px 0 }}
table {{ border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums }}
th, td {{ padding:5px 9px; text-align:right; white-space:nowrap; border-bottom:1px solid var(--grid) }}
th {{ color:var(--ink2); font-weight:600; position:sticky; top:0; background:var(--surface) }}
td.lbl, th.lbl, th:first-child {{ text-align:left }} td.pos {{ color:var(--pos) }} td.neg {{ color:var(--neg) }}
td.warn {{ color:var(--warn); font-weight:600 }} tr.hl td {{ background:var(--hl) }}
.note {{ color:var(--ink2); font-size:13.5px }} .card {{ background:var(--surface); border:1px solid var(--border);
  border-radius:8px; padding:14px 18px; margin:12px 0 }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:14px 0 }}
.kpi {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:10px 14px }}
.kpi b {{ display:block; font-size:1.35rem }} .kpi span {{ color:var(--ink2); font-size:12.5px }}
details summary {{ cursor:pointer; color:var(--ink2); margin:8px 0 }}
code {{ font-size:12.5px }}
</style></head><body><main>
<h1>GDX.L volatility-squeeze backtest</h1>
<p class="sub">VanEck Gold Miners UCITS (LSE, USD line) · usable history {d_start.date()} → {d_end.date()} ·
in-sample to {D.index[split-1].date()}, out-of-sample from {d_split.date()} · generated {datetime.now():%Y-%m-%d %H:%M} by
<code>scripts/gdx_squeeze/gdx_squeeze_backtest.py</code></p>

<div class="kpis">
<div class="kpi"><span>Selected rule — OOS trades</span><b>{int(moos['trades'])}</b></div>
<div class="kpi"><span>OOS expectancy / trade (net)</span><b>{pct(moos['expectancy'])}</b></div>
<div class="kpi"><span>OOS beats random entries</span><b>{pc0(r_oos_any)}</b></div>
<div class="kpi"><span>OOS CAGR (buy &amp; hold)</span><b>{pct(moos['CAGR'])} <small>({pct(bh_oos['CAGR'])})</small></b></div>
<div class="kpi"><span>Variants tested</span><b>{n_tested}</b></div>
</div>

<h2>Verdict</h2>
<div class="card">{verdict}</div>

<h2>1. Price, squeezes and trades</h2>
<p class="note">Shaded = days the selected squeeze definition is on. Triangles = entries (next open after the signal) and exits.
The dashed line marks the in-sample / out-of-sample boundary.</p>
{img(ch_price, 'GDX.L price with squeeze shading and trades')}

<h2>2. Equity vs baselines</h2>
<p class="note">All curves net of 0.15% round trip. Grey band = 5th–95th percentile of 1,000 runs that enter on random days
(entry probability matched to the strategy's trade count) and use the same exit rule. "Best unfiltered squeeze" =
highest in-sample Sharpe with no macro/event filter ({html.escape(nf_sig)}{' + z<−1' if nf_z != '–' else ''}, {html.escape(nf_ex)}).</p>
{img(ch_eq, 'Equity curves')}
<div class="row">{img(ch_mc_is, 'MC histogram in-sample')}{img(ch_mc_oos, 'MC histogram out-of-sample')}</div>
{t_base}

<h2>3. Variant tables</h2>
<h3>3a. Squeeze definitions (no filter, exit = {html.escape(b_ex)})</h3>
{t_signals}
<h3>3b. Filters, alone and combined ({html.escape(b_sig)}{' + z<−1' if b_zv else ''}, exit = {html.escape(b_ex)})</h3>
<p class="note">"Beats random" = share of {max(200, args.mc // 5)} random-entry runs (same exit, same trade count) whose expectancy is below this row's.</p>
{t_filters}
<h3>3c. Exits ({html.escape(b_sig)}{' + z<−1' if b_zv else ''}, filter = {html.escape(b_filt)})</h3>
{t_exits}
<h3>3d. Selection bias check — top 15 in-sample variants and what they did out-of-sample</h3>
<p class="note">{n_top_pos_oos} of the top 15 in-sample variants stayed positive out-of-sample.
Across all {n_tested} variants, {pc0(frac_pos_is)} have positive IS expectancy and {pc0(frac_pos_oos)} positive OOS;
the IS→OOS correlation of expectancy (variants with ≥5 trades) is {corr_all:.2f}. A correlation near zero means in-sample ranking carries little information.</p>
{t_top}
<details><summary>All {n_tested} variants (IS and OOS)</summary>{t_all}</details>
<p class="note">Highlighted rows = the selected rule. Orange trade counts = fewer than 15 trades (treat as anecdote).</p>

<h2>4. Parameter sensitivity</h2>
<p class="note">BB-width percentile threshold × fixed hold, with the selected filter{' and z<−1' if b_zv else ''}. Cells show net expectancy per trade and trade count.
{pc0(pos_is)} of cells positive in-sample, {pc0(pos_oos)} out-of-sample; IS/OOS cell correlation {corr_is_oos:.2f};
in-sample peak p{int(round(g_is.index[bi]*100))}/{g_is.columns[bj]}d = {pct(peak)} vs neighbour median {pct(neigh_med)}
→ <strong>{'ISOLATED PEAK — likely overfit' if isolated_peak else 'not an isolated peak'}</strong>.</p>
{img(ch_heat, 'Sensitivity heatmaps')}

<h2>5. US GDX — longer history</h2>
<p class="note">Same parameters, no re-optimisation. "pre-GDX.L (unseen)" ({DU.index[us_lo].date()} → {D.index[0].date()}) was never used to pick anything, so it is a true hold-out.</p>
{img(ch_us, 'US GDX equity')}
{t_us}

<h2>6. Squeeze episodes and macro events</h2>
<p class="note">An episode = a run of consecutive squeeze days. Resolution window = the 10 sessions after the last squeeze day.
"Big" = the close moved more than 2 ATR (ATR at episode end) away from the episode-end close at any point in the window.
"Event" = an FOMC decision (scheduled or not) or a CPI release inside the window. FOMC statements land after the London close, so for GDX.L
they are mapped to the next London session.</p>
{t_events}
<div class="row">{img(ch_ep_l, 'GDX.L episodes')}{img(ch_ep_u, 'US GDX episodes')}</div>
<details><summary>GDX.L episode list</summary>{t_eplist}</details>

<h2>7. Method, data and lookahead guards</h2>
<div class="card note"><ul>
<li><strong>Data.</strong> yfinance daily, auto-adjusted OHLC (GDX.L is accumulating so adjustment is a no-op; US GDX is dividend-adjusted).
Gold = GC=F front-month future (roll gaps are present but only its 200-day MA is used). DXY = DX-Y.NYB. 10y TIPS real yield = FRED DFII10.
^TNX downloaded and aligned for reference but not used in a rule. Raw files in <code>data/gdx_squeeze/raw/</code>; pass <code>--refresh</code> to re-download. Cleaning:<ul>{data_notes_html}</ul></li>
<li><strong>Event calendar.</strong> FOMC from federalreserve.gov (historical pages for {first_year}–2020, current calendar after):
{n_ev_f} scheduled decisions, {n_ev_u} unscheduled meetings, and {n_ev_cc} conference calls / notation votes (kept in events.csv but not treated as events;
note this drops the emergency cuts decided on calls in Jan and Oct 2008, which predate GDX.L).
CPI: {n_ev_c} release dates. bls.gov returns HTTP 403 to scripted clients, so the dates are rebuilt from ALFRED's archive of BLS's CPIAUCSL:
a release date is the first vintage date on which a new month's CPI appears. This reproduces the 2013 and 2025 shutdown delays.
Saved as <code>data/gdx_squeeze/events.csv</code>. Gaps:<ul>{notes_html}</ul></li>
<li><strong>Signals</strong> evaluated at close t, entry at open t+1. BB(20, 2σ) width percentile is a trailing 252-day rank including today; the exit median is a trailing 252-day median.
Keltner = 20-day SMA ± 1.5 × 20-day ATR (same mid as Bollinger, so "BB inside KC" ⇔ 2σ &lt; 1.5 ATR). z-score = 60-day z of log close.</li>
<li><strong>Macro alignment.</strong> Each series' moving average is computed on its own calendar, forward-filled onto GDX.L sessions (never backfilled), then lagged one session,
because US closes print after the London close and DFII10 for day t is published on t+1.</li>
<li><strong>Event filter</strong> uses only scheduled FOMC meetings and CPI release dates, which are published in advance — no knowledge of unscheduled actions.</li>
<li><strong>Trades.</strong> Long only, one position at a time, 0.15% round-trip cost (half on entry, half on exit day). Fixed holds exit at the close of the Nth session (entry day = 1).
ATR exit: +2 ATR target / −1 ATR stop from the entry price, ATR as of the signal close; gaps through a level fill at the open; if a bar touches both, the stop is assumed first; 40-session time stop.
BBW exit: sell at the next open after a close with width above its trailing median.</li>
<li><strong>Split.</strong> Usable history (after the 272-session warm-up) split 70/30 by sessions. Entries are confined to each window; a trade opened in-sample may finish a few days into OOS.
Selection = highest in-sample Sharpe among variants with ≥{MIN_IS_TRADES} in-sample trades.</li>
<li><strong>Random baseline.</strong> Each run enters on random sessions (Bernoulli, probability set so the expected trade count matches the strategy) and uses the same exit rule, window and costs.
A second set restricts random entries to days when the selected filter was on, isolating what the squeeze adds on top of the filter.</li>
<li><strong>Not modelled:</strong> FX (the USD line is used, so no GBP conversion), borrow/financing, slippage beyond the flat cost, capacity.</li>
</ul></div>
</main></body></html>"""
    REPORT_PATH.write_text(page, encoding="utf-8")
    print(f"report → {REPORT_PATH.relative_to(REPO_ROOT)}")
    print(f"selected: {best_key}; IS exp {mis['expectancy']:.4f} n={mis['trades']}; "
          f"OOS exp {moos['expectancy']:.4f} n={moos['trades']}; OOS beats random {r_oos_any:.0%}")


if __name__ == "__main__":
    main()
