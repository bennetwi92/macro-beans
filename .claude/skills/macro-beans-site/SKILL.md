---
name: macro-beans-site
description: Use this skill when developing, modifying, or deploying the Macro Beans web platform served at https://bennetwi92.github.io/macro-beans/. The platform has two generations — the active v2 "cockpit" (a dense terminal-style app under web/v2/) and the deprecated v1 arcade site (under web/). Triggers include any work in web/, web/v2/, scripts/site/, .github/workflows/deploy.yml, or requests to add an instrument, add a portfolio, add a scanner strategy, add a page, publish a report, change the site design, or deploy the site. Covers architecture, design systems, data pipeline, code conventions, how to add things, local testing, and the deploy pipeline for BOTH generations — but defaults new work to v2.
---

# Macro Beans web platform

The Macro Beans website is served at `https://bennetwi92.github.io/macro-beans/`.
This skill is the source of truth for how to build for it. Read it before
making any change to `web/`, `scripts/site/`, or `.github/workflows/deploy.yml`.

## Two generations — prefer v2

There are **two** web apps in this repo, both deployed by the same pipeline:

| | **v2 — the cockpit** (ACTIVE, preferred) | **v1 — the arcade site** (DEPRECATED, legacy) |
|---|---|---|
| Location | `web/v2/` + `web/v2/css/cockpit.css` + `web/v2/js/` | `web/` root (`index.html`, `buy-the-bounce.html`, …) + `web/css/macro-beans.css` + `web/js/` |
| URL | `…/macro-beans/v2/price-sheet.html` | `…/macro-beans/` (site root) |
| Look | Dense monospace trading **terminal** (Bloomberg/Reuters) | Arcade **pixel** aesthetic (Press Start 2P / VT323) |
| Audience | The owner — a power-user cockpit (quant metrics OK) | Beginner retail traders (no jargon) |
| Backend | Pre-built JSON **+ Neon Postgres** (auth/RLS) for private pages | Pre-built JSON only, fully static |
| Libraries | Tabulator (tables), Neon JS client — via CDN/esm.sh | None |

**Default rule: new work targets v2.** Add a tradeable thing to the cockpit
(an instrument, a scanner strategy, a new cockpit page) unless the user
explicitly asks for the v1 arcade site. Do **not** build new v1 strategy/league
pages by default — v2's Scanner subsumes them. The bulk of this skill is the v2
section; v1 is documented at the end as **legacy** (it is still live and, crucially,
its tested `web/js/strategy-engine.js` is **reused by v2's Scanner**, so v1's
engine + tests are shared infrastructure, not dead code).

- **Python**: always use `/usr/local/bin/python3` directly (conda is not on PATH
  on this machine — see CLAUDE.md).

---

# v2 — the cockpit

## TL;DR

- **App**: vanilla HTML / CSS / ES-module JS, terminal-styled, under `web/v2/`.
  Two third-party libs, both via CDN: **Tabulator** (data grids) and the
  **Neon** JS client (private pages). No build step, no framework, no bundler.
- **Two kinds of page**:
  - **Public analytical** (no login): Price sheet, Scanner, Chart, Reports —
    fed by pre-built JSON in `web/v2/data/` (**gitignored**, built in CI).
  - **Private / personal** (Neon login): Trades, Positions, Portfolio, Requests —
    the owner's trading book, stored in **Neon Postgres** with Auth (JWT) +
    Row-Level Security. One sign-in covers all four.
- **Data source**: the shared **DuckDB price cache** (`data/market.duckdb`), not
  yfinance directly. Build scripts read the cache via `MarketStore`.
- **Build scripts** (`scripts/site/`): `build_price_sheet.py`, `build_charts.py`,
  `build_fx.py`, `build_reports.py`, `build_sim.py`.
- **Local test**: `cd web && python3 -m http.server 8765`, then open
  `http://localhost:8765/v2/price-sheet.html` (serve from `web/`, not `web/v2/`,
  because cockpit pages load `../css/macro-beans.css`).
- **Deploy**: any push to `main` triggers `.github/workflows/deploy.yml` (builds
  v1 **and** v2). Manual: `gh workflow run deploy.yml -R bennetwi92/macro-beans`.

## Architecture

```
   ┌──────────────────┐  refresh  ┌──────────────────┐  build   ┌────────────────────────┐
   │  yfinance (raw)  │  ───────► │  DuckDB cache    │  ──────► │  web/v2/data/*.json    │
   │  web + cockpit   │           │  market.duckdb   │          │  (built in CI,         │
   │  surfaces        │           │  (single writer) │          │   never committed)     │
   └──────────────────┘           └──────────────────┘          └───────────┬────────────┘
                                                                             │ static serve
                                                                             ▼
   ┌──────────────────┐   Neon JS    ┌──────────────────┐        ┌────────────────────────┐
   │  Neon Postgres   │ ◄──────────► │  Browser (cockpit│ ◄───── │  GitHub Pages (/v2/)   │
   │  Auth + RLS      │   fetch/CRUD │  pages compute   │  fetch └────────────────────────┘
   │  (private pages) │              │  everything)     │
   └──────────────────┘              └──────────────────┘
```

Components:
1. **DuckDB cache** is the single yfinance reader (`python -m src.data.refresh`).
   Build scripts only consume it via `MarketStore` (no network in the build).
2. **Build scripts** emit compact JSON into `web/v2/data/` (gitignored).
3. **Public analytical pages** fetch that JSON and compute every metric in the
   browser (as-of date, RSI, vols, edge-vs-baseline, etc.).
4. **Private pages** talk to **Neon** directly from the browser via the Neon JS
   client; security is JWT auth + Postgres Row-Level Security at the database,
   not by hiding endpoints. **No app server of our own** — Neon is the only
   "backend", and it enforces per-user isolation.

## Repository layout

```
web/v2/
  price-sheet.html      public — Tabulator grid, metrics as-of a picked date
  scanner.html          public — daily long-only BUY shortlist + edge vs baseline
  chart.html            public — full-bleed SVG line chart + search + zoom
  reports.html          public — research library (docs/ markdown → reader)
  simulator.html        public — swing-trading trainer (random S&P 500 chart)
  trades.html           private — trade blotter (Neon)
  positions.html        private — average-cost positions per account (Neon)
  portfolio.html        private — portfolio roll-up + cash flows (Neon)
  requests.html         private — personal wishlist tracker (Neon)
  css/cockpit.css       v2-only styles: overrides v1 tokens + adds the app shell
  js/
    nav.js              shared top app-bar; PAGES is the single page list
    options-bar.js      createOptionsBar() — expandable control strip
    neon-config.js      Neon AUTH_URL / DATA_API_URL (public by design)
    neon.js             Neon client (db), requireAuth, mountAccountBar, esc/fmt
    price-sheet.js      price-sheet page
    price-metrics.js    pure as-of metrics (RSI, vols, px/200d, returns)
    scanner.js          scanner page (imports v1's strategy-engine.js for MATH)
    chart.js            chart page
    reports.js          reports page (list ↔ reader)
    simulator.js        simulator page (state machine + candle/indicator SVG)
    sim-indicators.js   pure indicator math (EMA/SMA/MACD/RSI/ATR), unit-tested
    sim-engine.js       pure trade accounting (fills, stop, P&L in % and R)
    prices.js           cockpit menu + FX → native-currency-to-GBP helpers
    book.js             pure trading-book accounting (average cost, GBP)
    trades.js / positions.js / portfolio.js / requests.js   private pages
  data/                 gitignored — built fresh in CI
    price-sheet.json    {built_at, instruments:[{ticker,name,theme,bars:[[iso,close]]}]}
    instruments.json    chart/scanner menu {ticker,name,theme,lev,currency,last}
    charts/<ticker>.json full history {ticker,name,theme,bars:[[iso,open,close]]}
    fx.json             {built_at, gbpusd, gbpeur}  (units per GBP)
    reports.json        {built_at, reports:[{slug,title,category,summary,…}]}
    reports/<slug>.html rendered markdown fragment per research note
    sim-universe.json   {built_at, tickers:[{t,n,s,b,f,l}]}  simulator index
    sim/<TICKER>.json   {ticker,name,sector,bars:[[iso,o,h,l,c,v]]} ~7y OHLCV

scripts/site/
  build_price_sheet.py  cache → web/v2/data/price-sheet.json (800 bars/inst)
  build_charts.py       cache → instruments.json + charts/<ticker>.json (full)
  build_fx.py           yfinance (2 calls) → fx.json (GBP rates)
  build_reports.py      docs/*.md → reports.json + reports/<slug>.html
  build_sim.py          cache → sim-universe.json + sim/<TICKER>.json (S&P 500)
  _common.py            BuildTally (coverage gate) + write_json (compact)

.github/workflows/deploy.yml   builds v1 + v2, deploys web/ (so v2 is at /v2/)
```

> **Nav vs. reality:** `nav.js` `PAGES` also lists `instruments.html` and
> `systems.html`. Those pages are **planned but not yet built** — the links 404
> until someone adds them. If you build one, drop the HTML into `web/v2/` and it
> lights up automatically (the entry is already in `PAGES`).

## Page shell

Every cockpit page is the same three-part shell. `nav.js` renders the app bar;
`options-bar.js` (or a page module) fills the options bar; the page owns the rest.

```html
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <!-- IBM Plex Mono (one font), Tabulator CSS only on grid pages -->
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../css/macro-beans.css">  <!-- shared tokens first -->
  <link rel="stylesheet" href="css/cockpit.css">          <!-- then v2 overrides  -->
</head>
<body>
  <header id="appbar" class="appbar"></header>   <!-- nav.js fills this -->
  <div id="optbar"></div>                         <!-- options-bar.js fills this -->
  <!-- page content (a #ps-grid / #scan-grid / #chart / <main class="page">) -->
  <script type="module" src="js/<page>.js"></script>
</body>
```

`cockpit.css` loads **after** `macro-beans.css` and re-points the shared CSS
variables (`--bg`, `--ink`, fonts, …) to the terminal palette. So v1 and v2
share the same *token names* but render with different *values*; the v1 site
never loads `cockpit.css`, so it is never affected by v2 changes.

## Design system (terminal, not arcade)

The cockpit aesthetic is a **professional trading terminal**: monospace, dense,
high-contrast, zero page chrome. It deliberately drops the v1 pixel/arcade look.

### Tokens (overridden in `cockpit.css` `:root`)

- **Font**: one family — `--mono` = `'IBM Plex Mono'`. `--pixel` and `--term`
  are both re-aliased to `--mono`, so any shared component that referenced the v1
  fonts renders monospace here. Base `body` size is **12px**, `color-scheme:dark`
  so native controls (date pickers) render dark.
- **Palette** (re-pointed): `--bg` #0c0c13, `--panel` #14141d, `--inset` #0a0a10,
  `--ink` #eef0f7, `--dim` #9aa0b5, `--line` #2e2e42, `--cyan` #4fe3ef (active
  accent), `--win` #3ec07e (up), `--loss` #f06673 (down). The logo accents
  (`--lime`, `--magenta`, `--gold`) carry over from `macro-beans.css`.

**Never hard-code hex in new code — reference the variable.** Add new colours to
`cockpit.css` `:root`, not inline.

### Shared components

- **App bar** (`.appbar`) — macOS-menu-bar style: wordmark + every page listed
  horizontally, 26px tall, sticky, horizontally swipeable on narrow screens.
  Rendered by `nav.js`; the active page is marked from `location.pathname`. To
  add/rename/reorder pages, edit the `PAGES` array in `nav.js` — it is the single
  source of truth.
- **Options bar** (`.optbar`) — the per-page control strip, built with
  `createOptionsBar(mount, { primary, extra, onChange })` from `options-bar.js`.
  Field `type`s: `date`, `text`, `search` (text + a page-attached `<datalist>`),
  and `seg` (segmented buttons, exactly one active). `extra` fields hide behind a
  `···` expander that only appears when extras exist. `onChange(id, value,
  fields)` fires on change. See `scanner.js` (rich) and `price-sheet.js` (minimal).
- **Tabulator grids** (Price sheet, Scanner) — `import { TabulatorFull as
  Tabulator } from "https://cdn.jsdelivr.net/npm/tabulator-tables@6.5.2/…"`.
  Conventions: `layout:"fitData"`, `height:"100%"` (the grid fills
  `calc(100vh - 52px)` under the two bars), frozen first column, `initialSort`,
  per-column `formatter` functions. Colour cells with the `paint(cell, up, down)`
  helper (toggles `.up`/`.down` — always toggle **both** so reused cells don't
  keep a stale colour). Tabulator 6.5 has no `setPlaceholder()` on the instance
  for dynamic empties — write into `.tabulator-placeholder-contents` (see
  `setEmptyMsg` in `scanner.js`).
- **Reports reader** — two screens in one page: a drill-in list (`.report-index`
  / `.report-item`) and a reader (`.reader-bar` + `.report-body`). `.report-body`
  is the one place that uses a **sans-serif** body font (long-form prose), not
  the mono terminal face.
- **Auth + account bar** (private pages) — `requireAuth(root)` renders the
  `.auth-card` sign-in gate and resolves with the session; `mountAccountBar(optbar,
  session)` shows "SIGNED IN … / Sign out". Both from `neon.js`.
- **Trading-book tables** — `.np-tbl` (generic), `.trade-tbl` (fixed dense
  blotter), `.pos-tbl`, `.pf-card`. Use `.up`/`.down` for coloured P&L.

### Responsive / mobile

The shell is mobile-first by construction: the app bar and options bar are
`overflow-x:auto` (swipe horizontally, scrollbar hidden); grids and the chart
fill the viewport below the two 26px bars (`calc(100vh - 52px)`) and Tabulator
manages its own internal scroll. Keep the viewport meta tag. For bespoke layouts
(portfolio metric grids, etc.) follow the `@media (max-width:680px/440px)`
collapses already in `cockpit.css`. Still check at ~375px before pushing.

## Code conventions

These extend (and in two places relax) the v1 conventions:

- **Vanilla HTML / CSS / ES-module JS, no build step.** Same as v1.
- **Two third-party libraries are allowed in v2, both via CDN/esm.sh**:
  **Tabulator** (data grids — far better than hand-rolled sortable tables) and
  the **Neon** JS client (private pages). This is the deliberate exception to
  v1's "no libraries" rule. Do **not** add more — no React/Vue, no charting lib
  (the SVG line chart in `chart.js` is enough), no bundler.
- **ES modules with explicit `.js`** and full CDN URLs for third-party imports.
- **All analytical computation in the browser.** Build scripts only fetch +
  pre-process; pages compute metrics, stats, edge, formatting. If you're tempted
  to compute server-side, do it at build time and ship JSON.
- **Reuse v1's tested engine for strategy math.** `scanner.js` imports
  `findEvents`, `computeStats`, the `live*` detectors, `HORIZONS`, etc. from
  `../../js/strategy-engine.js` so the cockpit and the v1 pages can never
  disagree on numbers. If you change a formula there, update `tests/web/*.test.js`
  in the same commit. Cockpit-only pure math (as-of metrics, accounting) lives in
  v2 modules (`price-metrics.js`, `book.js`) — no DOM, no fetch in those.
- **JSON is the only data interface; bars are arrays** — `[iso, close]` for the
  price sheet, `[iso, open, close]` for charts/scanner (open is needed to model
  next-open entry — you can't buy at the close you detect on). Fetch with
  `cache:"no-cache"`; cache payloads in memory after first load.
- **Neon endpoints are public by design** (`neon-config.js`). Security is
  JWT + RLS at the DB. **Never** put a DB connection string, password, or service
  key in the repo or the browser. Every private table is RLS-scoped to the
  signed-in user; new private tables must be created with RLS enabled.
- **Escape user/DB strings** with `esc` from `neon.js` before injecting into HTML.

## Data pipeline & the `cockpit` surface

The cockpit universe is the **union of two registry surfaces**:

- `web` — the public LSE ETFs (also shown on the v1 site).
- `cockpit` — v2-only instruments (leveraged / inverse ETFs) deliberately kept
  **off** the beginner v1 site.

Build scripts call `load_instruments_multi("web", "cockpit")`, and the cache
refresh seeds both: `python -m src.data.refresh --surface web` then
`--surface cockpit`. The registry (`config/instruments.toml`) is the single
source of truth; an instrument's `surfaces` list controls where it appears.

The **simulator** universe is the exception to the registry: 503 S&P 500
constituents live in `config/sp500.csv` (a flat `ticker,name,sector` list read
by `load_ticker_csv`), because 503 `[[instrument]]` blocks would drown the
registry. They are cached like anything else —
`python -m src.data.refresh --tickers-file config/sp500.csv --start 2019-01-01`
(`--start` bounds a cold seed; incremental runs continue from the last bar).

Build order (mirrors the deploy workflow), all reading the DuckDB cache:

```bash
# 0. ensure the cache exists / is fresh (the ONLY yfinance reader)
python -m src.data.refresh --surface web
python -m src.data.refresh --surface cockpit
# 1. v2 builds
/usr/local/bin/python3 scripts/site/build_price_sheet.py   # price-sheet.json
/usr/local/bin/python3 scripts/site/build_charts.py        # instruments.json + charts/
/usr/local/bin/python3 scripts/site/build_fx.py            # fx.json (needs network)
/usr/local/bin/python3 scripts/site/build_reports.py       # reports.json + reports/
/usr/local/bin/python3 scripts/site/build_sim.py           # sim-universe.json + sim/
```

Each build uses `BuildTally` from `_common.py` as a coverage gate: a flaky
ticker is skipped (not fatal) and the build fails only if too much is missing.
**Note:** `scripts/site/validate_data.py` validates the **v1** JSON only; there
is no separate validator for `web/v2/data/` — the per-build coverage gate is the
safety net there.

## How to add things (v2)

### Add a tradeable instrument

Same flow as always — edit the registry; the cockpit picks it up via
`load_instruments_multi`.

1. Add an `[[instrument]]` block to `config/instruments.toml`:
   - **Public** instrument (also on the v1 site): `surfaces = ["web"]` with a
     `web_ticker`, `group`, `sublabel` (see the v1 "add an instrument" steps).
   - **Cockpit-only** instrument (e.g. a leveraged / inverse ETF you do **not**
     want on the beginner site): `surfaces = ["cockpit"]`, `web_ticker` =
     the LSE ETF, `category = "Leveraged & Inverse"` (this is what flags the
     ⚡ decay warning + `lev` in `build_charts.py`).
2. Seed it into the cache: `python -m src.data.refresh --surface cockpit`
   (or `--surface web`), then rebuild (`build_price_sheet.py` + `build_charts.py`).
3. Verify with `yf.download("TICKER.L", period="5d")` first — must exist + have
   volume; prefer liquid LSE ETFs. It then appears in the price sheet, the
   chart/scanner menu, and (if it carries a live setup) the scanner.

### Add a scanner strategy

The Scanner replaces v1's per-strategy pages. To add one:

1. **Put the math in `web/js/strategy-engine.js`** (the shared, tested engine):
   a `findXEvents(bars, opts)` builder **and** a `liveX(bars, opts)` detector,
   plus a `X_HORIZONS` array if the holds differ. Add unit tests in
   `tests/web/strategy-engine.test.js` in the same commit.
2. **Register it in `scanner.js`** — append an entry to the `STRATEGIES` array
   with `{ key, label, style: "dip"|"breakout"|"range", hold, detect, signal,
   sigVal, z, events }`. The scanner then runs it across the whole universe,
   computes win rate, **edge vs the instrument's own drift baseline**, MAE,
   median, worst, sample size, and ranks by shrinkage-adjusted per-day edge.
3. No new HTML/page needed — it shows up as rows in the existing grid.

### Add a new cockpit page

1. Create `web/v2/<page>.html` from the [page-shell](#page-shell) template
   (app bar + options bar + content + `<script type="module" src="js/<page>.js">`).
2. Add `web/v2/js/<page>.js`: `import "./nav.js"`, build the options bar with
   `createOptionsBar`, fetch its JSON (public) or `requireAuth` + `db` (private).
3. **Add the page to `PAGES` in `nav.js`** so it appears in the app bar
   everywhere (if it isn't one of the already-listed planned pages).
4. If it needs new build-time data, add a `scripts/site/build_<thing>.py` that
   reads the DuckDB cache via `MarketStore`, writes compact JSON into
   `web/v2/data/`, and wire it into `deploy.yml`. Update `.gitignore` if it emits
   a new path under `web/v2/data/`.

### Work on the simulator

`simulator.html` is a single-screen app, not a document: the app bar, a status
strip, the chart and the action bar fill `100dvh` and the page never scrolls.
Two rules make changes there safe:

1. **Keep the math out of the page module.** Indicator formulas belong in
   `sim-indicators.js` and fill/P&L rules in `sim-engine.js` — both pure, both
   covered by `tests/web/sim-*.test.js`. Update the tests in the same commit.
2. **Lay the bars out before measuring the chart.** `render()` draws the status
   strip and the action bar first, then the chart, which sizes its SVG to
   whatever height is left. Drawing the chart first sizes it against a stale
   box and pushes the RSI panel under the action bar.

The trading model it teaches (decision at the close, entry at the next open,
close fills for discretionary exits, an intraday stop that fills at the open on
a gap, a stop that can be trailed towards the price but never away from it,
results in % and R) is documented at the top of `sim-engine.js`. Change it
there, not in the page.

Two invariants in that model are easy to break by accident:

- **`R` is measured off `initialStop`**, frozen when the trade opens. Trailing
  the stop must never rescale a result that has already been earned.
- **The stop ratchets one way.** `moveStop` refuses a widening move and a move
  through the price; the page hands it raw drag positions and lets it decide,
  rather than reimplementing the rule in the drag handler.

`?t=<TICKER>&d=<ISO date>` deals a fixed hand — use it when testing.

### Publish a research report

Reports are just markdown under `docs/` rendered at build time.

1. Write a markdown note under `docs/<topic>/<name>.md` (first `# H1` becomes the
   title, first prose paragraph the summary). The topic directory becomes the
   category (`CATEGORY_NAMES` in `build_reports.py` maps nicer names).
2. Run `build_reports.py`; it emits `reports/<slug>.html` + a `reports.json`
   index entry. The `docs/web_v2/` directory is excluded from the public library.
3. No page wiring — the Reports page lists every indexed note automatically.

## Local testing (v2)

```bash
# build data (needs the DuckDB cache — refresh first if absent)
python -m src.data.refresh --surface web && python -m src.data.refresh --surface cockpit
/usr/local/bin/python3 scripts/site/build_price_sheet.py
/usr/local/bin/python3 scripts/site/build_charts.py
/usr/local/bin/python3 scripts/site/build_fx.py
/usr/local/bin/python3 scripts/site/build_reports.py

# serve from web/ (NOT web/v2/ — cockpit pages reference ../css/macro-beans.css)
cd web && python3 -m http.server 8765
# open http://localhost:8765/v2/price-sheet.html

# engine tests (shared with v1; run if you touched strategy-engine.js)
node --test tests/web/*.test.js        # or: npm test
```

Private pages need a live Neon connection (the endpoints in `neon-config.js`),
so they only fully work online; sign in with a test account. You can iterate on
HTML/CSS/JS without re-running the build scripts — just reload.

---

# v1 — the arcade site (LEGACY / deprecated)

The original Macro Beans site lives at the repo's `web/` root and is served at
the site root (`…/macro-beans/`). It is a **beginner-first, arcade-styled**
static site. It is **deprecated in favour of v2** — do not build new strategy or
league pages here unless the user explicitly asks for the v1 site. It is kept
running because it is still public and because **its `web/js/strategy-engine.js`
+ `tests/web/*.test.js` are reused by v2's Scanner** (shared infrastructure).

What still matters about v1:

- **Fully static, no libraries, no backend** — vanilla HTML/CSS/ES-module JS,
  pre-built JSON in `web/data/` (gitignored). The opposite of v2's Tabulator +
  Neon: do **not** introduce those into v1 pages.
- **Design system**: pixel font `--pixel` = `'Press Start 2P'` (small labels
  only) + terminal font `--term` = `'VT323'` (body). Palette + components are
  defined in `web/css/macro-beans.css` `:root`. Shared patterns: `.mast` nav,
  `.strat` header + `js/strategy-nav.js` switcher, `.panel`, `.ctl-grid`, `.seg`,
  `.pick`, `.cell-pos`/`.cell-neg`. Reference CSS variables, never hard-code hex.
- **Copy & tone**: arcade *look*, plain trustworthy *words*. **Beginner-first** —
  no Sharpe/t-stat/Greeks/p-values in UI; surface small-sample warnings loudly;
  no game-speak in labels; no emoji beyond the footer `⚠`. (v2 relaxes the
  no-jargon rule because it is a power-user cockpit, but v1 does not.)
- **Pages**: `index.html` (catalog home, rendered from `web/js/catalog.js`),
  per-strategy pages (`buy-the-bounce.html` + `.js`) and league tables
  (`*-league.html`), `portfolios.html`, `scanner.html`, `reference-*.html`,
  `glossary.html`, `about.html`. Publishing a v1 page still means adding a
  `CATALOG` entry in `web/js/catalog.js` or it stays invisible.
- **Build scripts** (v1): `build_data.py` (instruments → `web/data/<slug>.json`),
  `build_portfolios.py` (pair equity curves), `build_reference.py`
  (registry → `web/data/reference.json`, public surfaces only). `validate_data.py`
  gates the v1 JSON before deploy.
- **Add a portfolio**: `config/portfolios.toml` → `[[portfolio]]`
  (`kind = "letf"` or `"cfd"`), then `build_portfolios.py`. The pair-portfolios
  dashboard is currently v1-only.

If you must touch a v1 page, the full v1 component/copy/responsive rules above
still apply to it — match the existing pixel-arcade patterns and beginner tone.

---

# Deploy (both generations)

- **Workflow**: `.github/workflows/deploy.yml` — one pipeline builds v1 **and** v2.
- **Triggers**: push to `main` (when `web/**`, `scripts/site/**`, `src/data/**`,
  `config/**`, or the workflow changes), manual dispatch, nightly cron 22:30 UTC
  Mon-Fri (after US close).
- **Steps**: checkout → Python 3.11 → install deps → **restore DuckDB cache**
  (rolling `actions/cache`) → v1 builds (`build_data` → `build_reference` →
  `build_portfolios` → `validate_data`) → **refresh cache** (`--surface web`,
  `--surface cockpit`) → v2 builds (`build_price_sheet` → `build_charts` →
  `build_fx` → `build_reports`) → upload `web/` artifact → deploy to Pages.
  Uploading `web/` is why v2 lands at `/v2/`.
- **Engine tests** run separately in `.github/workflows/ci.yml` (Node built-in
  runner) on pushes/PRs touching `web/js/`, `tests/web/`, or `package.json` —
  these guard the engine shared by v1 and v2.

```bash
gh workflow run deploy.yml -R bennetwi92/macro-beans      # manual run
gh run list -R bennetwi92/macro-beans --limit 5           # recent runs
gh run watch <run-id> -R bennetwi92/macro-beans --exit-status
curl -s -o /dev/null -w "%{http_code}\n" https://bennetwi92.github.io/macro-beans/v2/price-sheet.html
```

### If Pages stops working

```bash
gh api repos/bennetwi92/macro-beans/pages                              # 404 = disabled
gh api -X POST repos/bennetwi92/macro-beans/pages -f build_type=workflow  # re-enable
```

Repository **must be public** for free GitHub Pages — don't make it private
without a hosting alternative.

---

# Hard rules — do not break these

**Shared (both apps)**
- ❌ Don't commit built JSON (`web/data/*.json`, `web/v2/data/**`) — gitignored on
  purpose; data lives only in CI artifacts.
- ❌ Don't hard-code hex colors — reference CSS variables (`cockpit.css` for v2,
  `macro-beans.css` for v1).
- ❌ Don't make the repo private (free Pages requires public).
- ❌ Don't add an app server / our own database / runtime API of our own. (Neon,
  with auth + RLS, is the only permitted backend, and v2-private-pages only.)
- ❌ Don't put secrets (DB strings, passwords, keys) in the repo or browser.
- ❌ Don't change `web/js/strategy-engine.js` without updating `tests/web/*.test.js`
  in the same commit — it is shared by v1 and v2.

**v2 cockpit**
- ❌ Don't add libraries beyond the two sanctioned ones (Tabulator, Neon client).
  No framework, no bundler, no charting library.
- ❌ Don't create a private (personal-data) table without Postgres Row-Level
  Security scoping it to the signed-in user.
- ❌ Don't compute analytics server-side — do it at build time (JSON) or in the
  browser.

**v1 arcade (legacy)**
- ❌ Don't build new v1 strategy/league pages by default — prefer v2.
- ❌ Don't introduce a JS framework, build step, **or any library** into v1.
- ❌ Don't use quant jargon (Sharpe, t-stat, CI, p-value, Greeks) or game-speak
  in v1 UI copy; no scanlines/CRT/glow; no emoji beyond the footer `⚠`.

---

# Cheat sheet

| Need to | Touch |
|---|---|
| **Add a tradeable instrument** | `config/instruments.toml` → `[[instrument]]` (`surfaces=["web"]` public, `["cockpit"]` v2-only) |
| **Add a scanner strategy (v2)** | `web/js/strategy-engine.js` (math + tests) → register in `web/v2/js/scanner.js` `STRATEGIES` |
| **Add a cockpit page (v2)** | new `web/v2/<page>.html` + `js/<page>.js`, add to `PAGES` in `nav.js` |
| **Change the simulator** | `web/v2/js/simulator.js` (page) · `sim-indicators.js` / `sim-engine.js` (math + `tests/web/sim-*.test.js`) |
| **Change the simulator universe** | `config/sp500.csv`, then `refresh --tickers-file` + `build_sim.py` |
| **Publish a report (v2)** | drop a `.md` under `docs/<topic>/`; `build_reports.py` indexes it |
| **Change v2 colors / fonts** | `web/v2/css/cockpit.css` → `:root` |
| **Change a price-sheet/scanner metric** | `web/v2/js/price-metrics.js` / `scanner.js` (browser-side) |
| **Refresh the price cache** | `python -m src.data.refresh --surface web` / `--surface cockpit` |
| **Build v2 data** | `build_price_sheet.py` · `build_charts.py` · `build_fx.py` · `build_reports.py` |
| **Add a pair portfolio (v1)** | `config/portfolios.toml` → `[[portfolio]]`; `build_portfolios.py` |
| **Add/edit a v1 page** | `web/*.html` + `web/js/*.js`; add a `CATALOG` entry in `web/js/catalog.js` |
| **Change v1 colors / fonts** | `web/css/macro-beans.css` → `:root` |
| **Run engine unit tests** | `node --test tests/web/*.test.js` (or `npm test`) |
| **Serve locally** | `cd web && python3 -m http.server 8765` → `/v2/price-sheet.html` or `/index.html` |
| **Trigger a deploy** | `gh workflow run deploy.yml -R bennetwi92/macro-beans` |
| **Check site is live** | `curl …/macro-beans/v2/price-sheet.html` (v2) · `…/macro-beans/` (v1) |
</content>
</invoke>
