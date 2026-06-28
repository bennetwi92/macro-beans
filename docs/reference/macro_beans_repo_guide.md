# Macro Beans — Repository Guide & Direction of Travel

A current map of the Macro Beans repository: what each track is, how the data
layer works, how the public website is built and deployed, and where things are
heading. Upload this as Claude Project knowledge so ad-hoc questions are
answered from what the repo actually contains rather than a stale snapshot.

> **Scope.** This is the orientation doc. For the website specifically, the
> authoritative rules live in `.claude/skills/macro-beans-site/SKILL.md`; for
> repo conventions, `CLAUDE.md`. This guide ties the pieces together.

---

## What Macro Beans is, in one paragraph

A personal UK trading-research repository **and** a public analytics website.
The research side is a set of independent Python tracks that fetch market data,
compute, and emit CSV/PNG outputs plus markdown notes. The website side is a
static, GitHub-Pages-hosted app — now in its second generation, a dense
terminal-style "cockpit" — that surfaces a subset of the research to the owner
(and, in the legacy v1 form, to beginner retail traders). A single DuckDB price
cache, fed from a single instrument registry, sits underneath everything.

## The two halves (don't conflate them)

| | Research / studies | Public web platform |
|---|---|---|
| Lives in | `scripts/<topic>/`, `src/<topic>/`, `data/<topic>/`, `docs/<topic>/`, `portfolio_optimiser/` | `web/` (sources), `scripts/site/` (builders), `.github/workflows/deploy.yml` |
| Output | CSV / PNG / markdown notes; Streamlit dashboards | Static site at `https://bennetwi92.github.io/macro-beans/` |
| Audience | The owner; fully technical | v2 = power-user cockpit; v1 = beginner retail |

A change usually belongs to exactly one half. If a task seems to straddle both,
split it.

---

## Data layer — the spine of the repo (`src/data/`)

Everything reads from one place:

- **`data/market.duckdb`** — a single DuckDB price cache. **Gitignored and
  regenerable** (no precious state); there are no per-symbol CSVs anymore.
- **Read:** `from src.data.store import MarketStore` →
  `MarketStore().get_prices("AAPL")` returns a Date-indexed OHLCV frame.
  Read-only and safe from many processes.
- **Write/refresh:** `python -m src.data.refresh [--full] [--surface web|research|cockpit] [--tickers AAPL,MSFT]`
  is the **only** writer (single-writer, ACID). Default is an incremental update
  of the research universe.
- **Registry:** `config/instruments.toml` is the single source of truth for the
  instrument universe (~178 blocks today), read via `src.data.registry`
  (`load_instruments`, `load_instruments_multi`, `load_portfolios`) using stdlib
  `tomllib` only — so the web build can use it with no duckdb dependency.
- **Surfaces** on each instrument control where it appears:
  - `research` (~53) — US-listed ticker, scanned/cached for studies.
  - `web` (~39) — LSE-listed ETF shown on the public (beginner) site.
  - `cockpit` (~84) — v2-only leveraged/inverse ETFs deliberately kept off the
    beginner site.
- **Paths:** `from src.data.paths import REPO_ROOT, DATA_DIR, CONFIG_DIR, DB_PATH`
  instead of recomputing `Path(__file__).resolve().parents[...]`.
- **Fresh clone / CI:** build the cache with `python -m src.data.refresh --full`
  (or per surface). `scripts/tools/seed_duckdb.py` was the one-off CSV→DuckDB
  migration (June 2026).

Other config files: `config/portfolios.toml` (beta-hedged long/short pairs,
`kind = "letf"` or `"cfd"`), `config/strategies.toml` (the published web
strategies and the surface each needs).

---

## Research tracks

### Mean reversion — `scripts/mean_reversion/`, `src/models/`
A model + daily scanner that looks for mean-reversion setups in liquid US
mega-caps, walk-forward backtested. Library code (config, features, model) is in
`src/models/`. See `docs/mean_reversion/mean_reversion_strategy_guide.md`,
the 270-day walk-forward writeup, and the trend-aware upgrade note.

### Scanner strategy — `scripts/scanner_strategy/`, `data/scanner_strategy/`
A daily long-only **BUY shortlist** with an explicit trade-picking playbook —
the strategy behind the cockpit's Scanner page. The signal math is shared with
the website via `web/js/strategy-engine.js` (tested in `tests/web/`), so the
research and the site can't disagree on numbers. See `docs/guides/scanner_guide.md`
and `docs/guides/scanner_trade_strategy.md`.

### Event studies — `scripts/event_studies/`, `docs/event_studies/`
Studies of historical price reactions to oil/copper geopolitical catalysts,
feeding an event-driven trading framework and LSE inverse/leveraged ETF pair
trades. See `docs/event_studies/event_driven_trading_framework.md`,
`copper_event_study.md`, `shell_bp_pair_drivers.md`, and trade records under
`docs/event_studies/trades/`.

### VIX options — `scripts/vix_options/` (Streamlit multipage), `src/vix_analysis/`
A calculator for sizing VIX call positions: dashboard → probability/scenarios →
risk → trade plan. Run with `streamlit run scripts/vix_options/vix_options_calculator.py`.
Docs under `docs/vix_options/` (app structure, Greeks guide, seasonality,
range-low strategy).

### Gas storage — `scripts/storage_model/`, `src/storage_model/`
A replica of a real gas-storage valuation model, presented as a Streamlit
dashboard.

### Portfolio optimiser — `portfolio_optimiser/` (standalone package)
A config-driven tool that builds quantitatively optimised target allocations for
**two long-horizon UK Trading-212 accounts** — an **ISA (A)** and a **SIPP (B)** —
and drives monthly contribution rebalancing. Run with `python -m portfolio_optimiser`.
Uses forward-looking CMAs (not raw historical means) for expected returns,
shrinkage covariance on month-end GBP total returns, and robust/CVaR-aware
objectives (SIPP maximises geometric growth; ISA adds a liquidity floor and a
95% CVaR / drawdown cap). Outputs land in `portfolio_optimiser/outputs/`; see
`portfolio_optimiser/README.md` and `docs/portfolio/isa_5y_growth_options.md`.
This is a longer-horizon allocation tool, distinct from the short-term
trade-idea research above.

> **Note on account context.** Older project instructions framed Macro Beans as
> a single "£189 IBKR event-driven oil co-pilot". That persona is now just one
> slice of the work; the repo also runs multi-year ISA/SIPP allocation. Don't
> assume one fixed broker, balance, or asset class — check which track a
> question is about.

---

## The public web platform

Two generations, one deploy pipeline. **New work targets v2.**

### v2 — "the cockpit" (active, preferred)
A dense, monospace, Bloomberg/Reuters-style trading **terminal** under
`web/v2/`, served at `…/macro-beans/v2/…`. Vanilla HTML/CSS/ES-module JS, no
build step or framework. Two sanctioned third-party libs, both via CDN:
**Tabulator** (data grids) and the **Neon** JS client (private pages).

- **Public analytical pages** (no login), fed by pre-built JSON in
  `web/v2/data/` (gitignored, built in CI): **Price sheet**, **Scanner**,
  **Chart**, **Reports** (the research library). Every metric is computed in the
  browser or at build time.
- **Private pages** (Neon login: JWT auth + Postgres Row-Level Security):
  **Trades**, **Positions**, **Portfolio**, **Requests** — the owner's trading
  book. Neon is the only backend; there is no app server of our own.
- Styling: `web/v2/css/cockpit.css` re-points the shared CSS tokens (from
  `web/css/macro-beans.css`) to the terminal palette. Reference CSS variables —
  never hard-code hex.

### v1 — "the arcade site" (deprecated, legacy)
The original beginner-first, pixel/arcade-styled static site at the `web/` root
(`…/macro-beans/`). Kept live partly because its tested
`web/js/strategy-engine.js` + `tests/web/*.test.js` are **reused by v2's
Scanner** — shared infrastructure, not dead code. Don't build new v1
strategy/league pages by default; don't use quant jargon or game-speak in v1 UI
copy.

### Build & deploy
- **Builders** (`scripts/site/`): v2 — `build_price_sheet.py`, `build_charts.py`,
  `build_fx.py`, `build_reports.py`; v1 — `build_data.py`, `build_portfolios.py`,
  `build_reference.py`, `validate_data.py`. All read the DuckDB cache via
  `MarketStore` (no network in the build except `build_fx.py`).
- **Reports** auto-publish from markdown: `build_reports.py` indexes every
  `docs/**/*.md` (except `docs/web_v2/`) into the v2 Reports page — first `# H1`
  becomes the title, first prose paragraph the summary, the topic directory the
  category. Drop a note in `docs/` and it appears with no page wiring.
- **Deploy** (`.github/workflows/deploy.yml`): a push to `main` touching
  `web/**`, `scripts/site/**`, `src/data/**`, `config/**`, or `docs/**` rebuilds
  v1 + v2 and deploys `web/` to Pages (uploading `web/` is why v2 lands at
  `/v2/`). Also nightly cron (22:30 UTC, Mon–Fri) and manual dispatch.

---

## Repository layout (quick reference)

```
config/            instruments.toml · portfolios.toml · strategies.toml  (registry = source of truth)
scripts/
  mean_reversion/  scanner_strategy/  event_studies/  vix_options/  storage_model/
  site/            web build scripts (v1 + v2)
  tools/           generic market tools (seed_duckdb.py migration)
  archive/         deprecated scripts
src/
  data/            unified data layer: paths · registry · store (MarketStore) · refresh (writer)
  models/          mean-reversion model package
  storage_model/   gas-storage valuation engine
  vix_analysis/    VIX options components
portfolio_optimiser/  standalone ISA+SIPP allocation optimiser + rebalancer
docs/
  mean_reversion/  event_studies/  vix_options/  guides/  portfolio/  reference/
data/              market.duckdb (gitignored) + committed CSV/PNG outputs per topic
web/               v1 (root) + v2/ cockpit
.github/workflows/ deploy.yml (Pages) · ci.yml (engine tests)
.claude/skills/    macro-beans-site (read before any website work)
```

---

## Conventions that matter when proposing changes

- **Python:** use `/usr/local/bin/python3` directly on the working machine
  (conda is not on PATH; `environment.yml` is the documented human setup).
- **New research:** script into the matching `scripts/<topic>/`; read prices via
  `MarketStore`, locate paths via `src.data.paths`; write outputs to
  `data/<topic>/`; factor reusable code into `src/<topic>/`; document in
  `docs/<topic>/`.
- **New instrument:** one `[[instrument]]` block in `config/instruments.toml`
  with the right `surfaces`, then a `src.data.refresh` for that surface.
- **Website:** obey the `macro-beans-site` skill — no new libraries beyond
  Tabulator + Neon, no build step/framework, all analytics in browser or at
  build time, never commit built JSON, never hard-code hex, never put secrets in
  the repo/browser, RLS-scope every private table.
- **Shared engine:** don't change `web/js/strategy-engine.js` without updating
  `tests/web/*.test.js` in the same commit (it's shared by v1 and v2).

## Direction of travel

- **v2 cockpit is the destination** for the public surface; v1 is maintained but
  frozen. New tradeable things and pages go to v2.
- **The registry + DuckDB cache are the single source of truth** — the long-run
  direction is "define it once in config, let every surface consume it," scaling
  to many instruments with few failure points.
- **Research notes flow to the site automatically** via the Reports pipeline, so
  writing good markdown under `docs/` is the publishing mechanism.
- **Backend stays minimal** — static JSON for analytics, Neon (auth + RLS) only
  for the owner's private book. No app server of our own is planned.
