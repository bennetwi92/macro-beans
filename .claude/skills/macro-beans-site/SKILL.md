---
name: macro-beans-site
description: Use this skill when developing, modifying, or deploying the Macro Beans static web platform — the site under web/ served at https://bennetwi92.github.io/macro-beans/. Triggers include any work in web/, scripts/site/, .github/workflows/deploy.yml, or requests to add an instrument, add a portfolio, add a strategy page, change the site design, or deploy the site. Covers architecture, design system, copy/tone rules, code conventions, how to add new things, local testing, and the deploy pipeline.
---

# Macro Beans web platform

The Macro Beans website is a free arcade-styled analytics playground for beginner retail traders. This skill is the source of truth for how to build for it. Read it before making any change to `web/`, `scripts/site/`, or `.github/workflows/deploy.yml`.

## TL;DR

- **Site**: vanilla HTML / CSS / vanilla-ES-module JS. No frameworks. Hosted free on **GitHub Pages** at `https://bennetwi92.github.io/macro-beans/`.
- **Data**: pre-built JSON in `web/data/` (**gitignored**), regenerated nightly by GitHub Actions.
- **Build scripts**: `scripts/site/build_data.py` (instruments) and `scripts/site/build_portfolios.py` (pair portfolios). Both use yfinance.
- **Local test**: `cd web && python3 -m http.server 8765` then open the page in a browser.
- **Deploy**: any push to `main` triggers the workflow. Manual: `gh workflow run deploy.yml -R bennetwi92/macro-beans`.
- **Python**: always use `/usr/local/bin/python3` directly (conda is not on PATH on this machine — see CLAUDE.md).

## Architecture

```
   ┌─────────────────────┐         ┌────────────────────────┐         ┌──────────────────┐
   │  yfinance (raw)     │  build  │  web/data/*.json       │ static  │  GitHub Pages    │
   │  ─ instruments      │  ───►   │  (built in CI,         │ ─────►  │  (free, public)  │
   │  ─ pair underlyings │         │   never committed)     │  serve  └──────────────────┘
   └─────────────────────┘         └────────────────────────┘                  │
                                                                                ▼
                                                              ┌──────────────────────────────┐
                                                              │  Browser loads JSON via fetch│
                                                              │  computes events / stats /   │
                                                              │  chart on every interaction  │
                                                              └──────────────────────────────┘
```

Three components:
1. **Build scripts** (Python, yfinance) emit compact JSON.
2. **Static site** (HTML/CSS/JS) reads JSON via `fetch`, computes everything client-side.
3. **CI/CD** (GitHub Actions) runs the build scripts then publishes `web/` to Pages as an artifact (JSON is never committed to any branch).

There is **no backend, no database, no API keys, no auth**. Keep it that way.

## Repository layout

```
web/
  index.html                   home page (publication index)
  buy-the-bounce.html          single-instrument strategy page (TEMPLATE)
  buy-the-bounce-league.html   cross-instrument comparison table
  portfolios.html              pair-portfolio equity-curve dashboard
  glossary.html                term definitions
  about.html                   project description
  css/macro-beans.css          all styles (one file)
  js/
    strategy-engine.js         shared pure functions (findEvents, computeStats, formatters)
    catalog.js                 publication index — list of every published piece
    home.js                    home page logic (renders cards from catalog.js)
    buy-the-bounce.js          strategy page logic
    buy-the-bounce-league.js   league page logic
    portfolios.js              portfolios page logic
  data/                        gitignored — built fresh in CI
    instruments.json           instrument menu
    <slug>.json                per-instrument daily bars
    portfolios.json            portfolio menu
    portfolios/<slug>.json     per-portfolio equity curves

scripts/site/
  build_data.py                fetches LSE ETFs → web/data/<slug>.json
  build_portfolios.py          fetches pair underlyings, computes
                               beta-hedged + LETF equity curves
                               → web/data/portfolios/<slug>.json

.github/workflows/deploy.yml   build + deploy on push & nightly cron
```

## Design system

### Color palette (defined as CSS variables in `:root` at the top of `web/css/macro-beans.css`)

| Variable    | Hex      | Used for |
|-------------|----------|----------|
| `--bg`      | #0e0e16  | Page background (near-black) |
| `--panel`   | #16161f  | Panel background |
| `--inset`   | #11111a  | Control cell / chart background |
| `--ink`     | #e9e9f2  | Primary text |
| `--dim`     | #82839a  | Secondary / subtitle text |
| `--line`    | #2c2c3c  | Borders, gridlines |
| `--line-2`  | #383850  | Slightly brighter borders |
| `--cyan`    | #58cdd6  | Active controls, primary chart line, sort arrows, nav-on |
| `--magenta` | #d96aa6  | Logo accent, secondary chart line |
| `--lime`    | #9fcf5e  | Section ticks, secondary indicators |
| `--gold`    | #e3b452  | Verdict highlights, £1 break-even line, badges |
| `--win`     | #54bd7e  | Positive returns text |
| `--win-bg`  | #142a1f  | Positive return cell background |
| `--loss`    | #d96570  | Negative returns text + warning state |
| `--loss-bg` | #2c161b  | Negative return cell background |

**Never hard-code these hex values in new code — always reference the CSS variable.** If you need a new colour, add it to `:root` so it stays consistent.

### Fonts

Two fonts only, both Google Fonts:

- **`--pixel`** = `'Press Start 2P'` — pixel font. Use for **small labels and headers only** (~8–13px). It's painful to read at larger sizes. Examples: section titles, control labels, table column headers, tickers underneath instrument names.
- **`--term`** = `'VT323'` — terminal font. Default for **all body text, prose, data values, and numbers**. Sizes 14–30px work well.

Rule of thumb: pixel font for **labels** (LIKE THIS); VT323 for **everything else**.

Both are preconnected and loaded once in `<head>` on every page — keep the link as is.

### Shared components

These patterns are repeated across pages. New pages should reuse them rather than reinventing.

#### Masthead + nav
```html
<header class="mast">
  <div class="logo">
    <span class="bean">MACRO</span><span class="dot"></span><span class="rest">BEANS</span>
  </div>
  <nav class="nav">
    <a href="buy-the-bounce.html">STRATEGIES</a>
    <a href="portfolios.html">PORTFOLIOS</a>
    <a href="glossary.html">GLOSSARY</a>
    <a href="about.html">ABOUT</a>
  </nav>
</header>
```
Add `class="on"` to the link matching the current page.

#### Strategy header
```html
<div class="strat">
  <div>
    <h1>PAGE TITLE</h1>
    <div class="lede">One-sentence explanation in plain English.</div>
    <!-- optional cross-page link -->
    <a class="strat-link" href="...">RELATED PAGE →</a>
  </div>
</div>
```

#### Panel
Every section of content is a panel.
```html
<section class="panel">
  <div class="sec-h">
    <span class="tick"></span>
    <h2>SECTION TITLE</h2>
    <span class="note">optional subtitle on the right</span>
  </div>
  <!-- content -->
</section>
```

#### Control grid + control cell
```html
<div class="ctl-grid">             <!-- or .ctl-grid-4, .ctl-grid-2 -->
  <div class="ctl">
    <div class="clab">LABEL</div>
    <!-- chips / slider / picker -->
  </div>
</div>
```
- `.ctl-grid`: 5 columns (default for strategy controls)
- `.ctl-grid-4`: 4 columns (league table — no instrument picker)
- `.ctl-grid-2`: 2 columns (portfolios)

#### Segmented control (chips)
```html
<div class="seg" id="something-seg">
  <button type="button" class="opt on" data-value="a">A</button>
  <button type="button" class="opt"    data-value="b">B</button>
</div>
```
Add `.on` to the active chip. Wire with one click handler on the seg that reads `data-value`.

#### Slider
Use a real `<input type="range">` with the `.range` class. The visible value above it lives in a separate element you update from JS on every `input` event; trigger filtering on `change` only (so dragging is smooth and the filter doesn't thrash).

#### Picker (dropdown)
A native `<select>` absolutely positioned over the visible label with `opacity:0`. The visible label is two stacked lines: a name (VT323 large) and a ticker/subtext (pixel-font small).
```html
<label class="pick">
  <span class="pick-text">
    <span id="something-name">—</span>
    <span id="something-ticker"></span>
  </span>
  <span class="car">▾</span>
  <select id="something-select"></select>
</label>
```

#### Cells with positive/negative state
Use `.cell-pos` / `.cell-neg` for `<td>` (dark-green / dark-red background + colored text). Use `.pos` / `.neg` for text-only colouring.

### Responsive / mobile

**Every page must look good on a phone.** A large share of retail readers
arrive on mobile, so a layout that only works at desktop width is a bug, not
a polish item. The responsive rules live in one place: the
`/* responsive / mobile */` section at the bottom of `web/css/macro-beans.css`,
driven by two breakpoints — **760px** (phones + small tablets) and **440px**
(narrow phones). Build to these patterns and you get mobile for free; invent a
new full-width layout and you have to handle it yourself.

Rules:

- **Always ship the viewport tag.** Every page `<head>` already has
  `<meta name="viewport" content="width=device-width, initial-scale=1.0">`.
  A new page copied from a template inherits it — keep it.
- **Reuse the shared components** (panel, control grid, picker, seg, tables,
  stat-grid, glossary). They already collapse correctly at both breakpoints,
  so a page assembled from them needs **no bespoke mobile CSS**.
- **Multi-column grids must collapse.** `.ctl-grid`/`.ctl-grid-4`/`.ctl-grid-2`
  and `.stat-grid` go to 2 columns at 760px and 1 column at 440px; the home
  `.card-grid` goes to 1 column at 820px. If you add a new grid, give it the
  same treatment in the responsive section — never leave 4–5 columns fixed.
- **Dense data tables scroll, they don't crush.** Wrap any wide table
  (4+ data columns) in `.logwrap`, which is `overflow-x:auto`. At the 760px
  breakpoint the table keeps a `min-width` so columns stay readable and the
  user swipes horizontally instead of reading squashed cells. Add a `min-width`
  rule for any new wide table class. The compact 4-column scoreboard
  (`.score`) is the exception — it just shrinks to fit.
- **No fixed pixel widths that exceed a phone.** Avoid `width:`/`min-width:`
  in px on layout containers (the glossary's old `200px` term column is the
  kind of thing that breaks — it stacks to one column on mobile). Use grid
  fractions, `max-width`, and `ch`.
- **SVG charts get a narrower viewBox on mobile.** An SVG that stretches to the
  container width scales its text down with it; on a phone a 1000-unit viewBox
  renders axis labels at ~5px. `portfolios.js` `renderChart` switches to a
  ~480-unit viewBox when `window.innerWidth <= 700` and re-renders on resize
  (cheap — payloads are cached). Copy that pattern for any new chart.
- **Tap targets and no zoom-on-focus.** Native form controls (`<select>`,
  `.range`) use font-size ≥ 16px so iOS Safari doesn't zoom when they're
  focused. Keep chips/buttons comfortably tappable.
- **Test at phone width before pushing.** Serve locally and check at ~375px
  (DevTools device toolbar, or just narrow the window): no horizontal page
  scroll on the `<body>`, controls reachable, tables swipe, nothing clipped.

### What NOT to do visually

- **No scanlines, no CRT curvature, no glow blur.** These were tried and explicitly cut.
- **No sound effects, no animations beyond hover.**
- **No emoji in copy** (except the single `⚠` in the footer warning line).
- **No drop shadows beyond the chunky pixel border** (`box-shadow:0 4px 0 0 #00000055` on panels).

## Copy & tone

Two rules above all:

1. **Arcade *look*, plain trustworthy *words*.** Use the design system to be playful; use the words to be trustworthy. **Never use game-speak in labels.** Write "WINS", "INSTRUMENT", "EVENTS", "WORST TRADE" — not "FRAGS", "SELECT YOUR FIGHTER", "BATTLES", "GAME OVER". The site is read by people who may put real money on it.

2. **Beginner-first.** No Sharpe ratios, t-stats, confidence intervals, Greeks, or other quant jargon in user-facing UI. If a metric needs a paragraph to explain, leave it out. Stats that survived the first round: win rate, average return, median, worst trade, max drawdown. Stats that did not: Sharpe, info ratio, t-statistic, p-value, hit-rate Sharpe.

Warning state matters: when a result is misleading (e.g. sample size < 10), say so loudly. A 100% win rate over 3 events is **not** an edge — it's noise. Surface that to the user.

Page voice is direct, second-person where useful ("you'd be up 1.8%"), and short. Avoid hedging language and qualifiers — the disclaimer in the footer handles the legal aspect.

## Code conventions

- **Vanilla HTML / CSS / vanilla ES-module JS.** No React, Vue, Svelte, jQuery, Tailwind, build steps, transpilers, or bundlers. The site is small; a framework is pure overhead and locks future development into an ecosystem.
- **ES modules with explicit `.js` extensions** in imports (`import { foo } from './strategy-engine.js'`). The browser is the runtime — no resolver magic.
- **All computation in the browser.** Build scripts fetch and pre-process; the site filters, aggregates, formats, and renders. This is critical — if you find yourself wanting to do computation server-side, the answer is to do it at build time and ship the result as JSON.
- **Pure functions in `strategy-engine.js`.** Anything shared between pages (event detection, stats, formatters, `escapeHtml`) lives there. No DOM, no state, no fetch in that file. Both `buy-the-bounce.js` and `buy-the-bounce-league.js` import from it so they cannot disagree on numbers.
- **One CSS file** (`web/css/macro-beans.css`). All pages share it. Add new component styles here, grouped under a section comment (`/* ---------- <name> ---------- */`).
- **One JS module per page** (`web/js/<page>.js`). Page-specific glue (DOM wiring, control state, render) stays in the page module.
- **JSON is the only data interface.** Build scripts emit compact JSON (`json.dumps(..., separators=(",", ":"))`). Pages consume via `fetch`. No CSV, no XML, no protobuf, no client-side parsing of anything else.
- **Cache JSON in memory after first load.** See the `cache` Map pattern in `buy-the-bounce.js` and `portfolios.js`.
- **Bars are arrays, not objects**, to keep payloads small: `[[iso_date, open, close], ...]` for instruments; `[[iso_date, equity_1x, equity_letf], ...]` for portfolios.
- **All sites use `cache:"no-cache"` on fetch** so the freshly deployed data loads immediately rather than via the browser cache.

## How to add a new instrument

Instruments live in the **shared registry** (`config/instruments.toml`), not in
`build_data.py` — the build script reads `load_instruments("web")` from it.

1. Add an `[[instrument]]` block to `config/instruments.toml` with
   `surfaces = ["web"]`:
   ```toml
   [[instrument]]
   slug = "slug"             # lowercase id; JSON filename + dropdown value
   name = "Display Name"
   category = "Commodities"  # free-form; mirror the group for web instruments
   surfaces = ["web"]
   web_ticker = "YAHOO.L"    # Yahoo Finance ticker
   sublabel = "Sublabel"     # per-row caption under the name
   group = "Commodities"     # dropdown SECTION heading (must match an existing
                             # group: Stock Markets | US Sectors | Themes |
                             # Bonds & Credit | Commodities | Property)
   ```
   - `web_ticker`: verify with `yf.download("TICKER", period="5d")` first — it must exist and have volume
   - `group` controls which dropdown section the instrument appears under; reuse an existing group name unless you deliberately want a new section
   - **Pick liquid LSE ETFs** for tradability. Check 60-day average notional turnover; aim for £100k/day+
   - For asset classes the existing set doesn't cover, look at iShares / Vanguard / Invesco LSE listings first — they're usually the most liquid
2. Test locally: `/usr/local/bin/python3 scripts/site/build_data.py`
3. Spot-check the JSON: dates, first/last bars look sane, no NaN
4. Commit and push (`config/instruments.toml` is the only source edit). CI redeploys; the new instrument appears in every dropdown and the league table with no other changes.

## How to add a new portfolio

Portfolios live in the **shared registry** (`config/portfolios.toml`);
`build_portfolios.py` reads `load_portfolios()` from it.

1. Add a `[[portfolio]]` block to `config/portfolios.toml`. Pick the `kind`:

   **LETF pair** (`kind = "letf"`) — leveraged-ETF wrapper on index/future underlyings:
   ```toml
   [[portfolio]]
   slug = "long-short"
   name = "Long / Short"
   kind = "letf"
   blurb = "Plain-English explanation of what the pair captures."
   beta_clip = [0.1, 2.0]   # OMIT this line if beta is stable

   [portfolio.long]
   underlying = "TICKER"     # yfinance ticker for the raw index/future (^GSPC, GC=F) — NOT the ETF
   letf = "XXX.L"            # LSE LETF ticker, display only
   label = "Long Leg"
   lev = 3                   # absolute leverage of the LETF wrapper (3 for 3SIL, 2 for 2MCL)

   [portfolio.short]
   underlying = "TICKER"
   letf = "YYY.L"
   label = "Short Leg"
   lev = 3
   ```

   **CFD pair** (`kind = "cfd"`) — LSE single shares traded as CFDs on Trading 212;
   the second curve is the spread net of overnight financing (no `letf`/`lev`):
   ```toml
   [[portfolio]]
   slug = "a-b"
   name = "A / B"
   kind = "cfd"
   blurb = "Plain-English explanation of what the pair captures."
   beta_clip = [0.2, 3.0]    # single-share betas wander; clipping is usually wise

   [portfolio.long]
   underlying = "AAA.L"      # LSE-listed GBP share (use the .L underlying)
   ticker = "AAA"            # plain ticker, display only
   label = "A"

   [portfolio.short]
   underlying = "BBB.L"
   ticker = "BBB"
   label = "B"
   ```
2. Test locally: `/usr/local/bin/python3 scripts/site/build_portfolios.py`
3. Sanity-check the equity curve (last value, drawdown range). If the LETF curve hits absurd numbers (>100x) over a long history, that's mathematically correct daily-compound LETF behavior on a strongly trending pair — but warn the user when reviewing.
4. Commit and push.

## How to publish a new page (any type)

Whenever you ship a new page, **also add an entry to `web/js/catalog.js`**.
The home page (`index.html`) auto-renders every catalog entry as a card
under the right category section, with a NEW badge for 14 days. Skipping
this step is the single most common way a published piece becomes
invisible to readers.

```js
// web/js/catalog.js → CATALOG array
{
  slug:  "my-new-thing",
  type:  "strategy",          // or "calculator" | "portfolio"
  title: "My New Thing",
  blurb: "One short sentence describing what it does.",
  page:  "my-new-thing.html",
  added: "YYYY-MM-DD",
},
```

To introduce a brand-new category (beyond strategy/calculator/portfolio),
append to the `CATEGORIES` array in the same file and add a corresponding
nav link if it warrants top-level visibility.

## How to add a new strategy page

If the new strategy fits the "filter → events → summary" pattern:

1. **Copy the template**: `cp web/buy-the-bounce.html web/<slug>.html` and `cp web/js/buy-the-bounce.js web/js/<slug>.js`
2. **Update the page**: title, lede, anything in the strategy-specific copy
3. **Adjust the event-detection logic**:
   - If the new logic is a tweak of `findEvents`, add an option to it in `strategy-engine.js`
   - If it's a fundamentally different shape, write a new function (e.g. `findCrossoverEvents`) in `strategy-engine.js` and import from the new page
4. **Update masthead nav** on all pages (`index.html`, `buy-the-bounce.html`, `-league.html`, `portfolios.html`, `glossary.html`, `about.html`) only if it deserves a new top-level nav slot. Most new pages don't — readers find them via the home page.
5. **Add a CATALOG entry** in `web/js/catalog.js` (see above) so it shows on the home page.
6. **Test locally — including at phone width** (see [Responsive / mobile](#responsive--mobile)): no horizontal page scroll, controls reachable, wide tables swipe. Then commit, push.

If the new page is an analysis/calculator/chart (not strategy-shaped), use `portfolios.html` as the template instead — that pattern covers picker + chart + stats + blurb.

## How to add a new comparison/league page

Use `buy-the-bounce-league.html` + `buy-the-bounce-league.js` as the template. The pattern is:
- 4 shared controls (no instrument picker)
- Load all instruments in parallel (`Promise.all`)
- One row per instrument, sortable columns
- Default sort by the most-decision-relevant column

## Local testing

```bash
# 1. Build fresh data (if not present)
/usr/local/bin/python3 scripts/site/build_data.py
/usr/local/bin/python3 scripts/site/build_portfolios.py

# 2. Serve the site
cd web && python3 -m http.server 8765

# 3. Open a page
open http://localhost:8765/buy-the-bounce.html
```

You can iterate on HTML/CSS/JS without re-running the build scripts — just reload the page.

### Tests & data validation

Two safety nets guard the site. Run them before pushing changes to the engines
or the build scripts:

```bash
# Unit tests for the shared browser engines (pure functions — no browser, no
# data build needed). Node's built-in runner; zero dependencies.
node --test "tests/web/**/*.test.js"          # or: npm test

# Schema + sanity check of the built JSON (run after the build scripts).
/usr/local/bin/python3 scripts/site/validate_data.py
```

- `tests/web/*.test.js` lock the user-facing numbers and event detection in
  `web/js/strategy-engine.js` and `web/js/seasonality-engine.js`. If you change
  a formula or formatter there, update the tests in the same commit.
- `scripts/site/validate_data.py` rejects empty/NaN/zero-or-negative prices,
  out-of-order dates, and menu↔file mismatches. The build scripts now also
  **skip a flaky ticker** (retry, then drop it) instead of aborting the whole
  refresh, and fail only if coverage drops below `MIN_OK_FRACTION` (see
  `scripts/site/_common.py`).

**Check mobile too.** Open the browser DevTools device toolbar (or just drag the
window down to ~375px wide) and confirm each page you touched: the `<body>` has
no horizontal scrollbar, control grids have collapsed, wide tables swipe inside
their bordered box, and nothing is clipped or overlapping. See
[Responsive / mobile](#responsive--mobile) for the rules these checks enforce.

## Deploy

- **Workflow**: `.github/workflows/deploy.yml`
- **Triggers**: push to `main` (when web/, scripts/site/, or the workflow itself changes), manual dispatch, nightly cron at 22:30 UTC Mon-Fri (after US close)
- **Steps**: checkout → set up Python 3.11 → install `yfinance` + `pandas` → run `build_data.py` → run `build_portfolios.py` → **`validate_data.py`** (gates the deploy on data sanity) → `actions/upload-pages-artifact` on `web/` → `actions/deploy-pages`
- **Engine tests** run separately in `.github/workflows/ci.yml` (Node built-in runner) on every push/PR that touches `web/js/`, `tests/web/`, or `package.json`.

### Common deploy commands

```bash
# Trigger a manual run
gh workflow run deploy.yml -R bennetwi92/macro-beans

# List recent runs
gh run list -R bennetwi92/macro-beans --limit 5

# Watch a specific run until it finishes
gh run watch <run-id> -R bennetwi92/macro-beans --exit-status

# Verify live URLs
curl -s -o /dev/null -w "%{http_code}\n" https://bennetwi92.github.io/macro-beans/buy-the-bounce.html
```

### Site URL

`https://bennetwi92.github.io/macro-beans/`

Entry points:
- `/buy-the-bounce.html` — primary strategy page
- `/buy-the-bounce-league.html` — comparison across instruments
- `/portfolios.html` — pair-portfolio dashboard
- `/glossary.html`
- `/about.html`

### If Pages stops working

```bash
gh api repos/bennetwi92/macro-beans/pages    # 404 means disabled
gh api -X POST repos/bennetwi92/macro-beans/pages -f build_type=workflow    # re-enable
```

Repository **must be public** for free GitHub Pages. Don't change it back to private without a hosting alternative.

## Hard rules — do not break these

- ❌ Don't introduce a JS framework (React, Vue, Svelte, etc.) or a build step (Vite, webpack, esbuild, etc.).
- ❌ Don't commit `web/data/*.json` — they're gitignored on purpose. Data lives only in CI artifacts.
- ❌ Don't add a backend, database, auth, or runtime API call. If the feature needs that, reconsider whether it belongs here.
- ❌ Don't use Sharpe ratios, t-stats, confidence intervals, p-values, or Greeks in user-facing UI copy.
- ❌ Don't use game-speak in labels (FRAGS, BOSS LEVEL, SELECT YOUR FIGHTER, GAME OVER, etc.). Plain English only.
- ❌ Don't add scanlines, CRT curvature, glow blur, neon outer shadows, or sound effects.
- ❌ Don't make the repo private (free Pages requires public).
- ❌ Don't pull in a charting library for what an SVG polyline can do.
- ❌ Don't hard-code hex colors — reference CSS variables from `:root`.
- ❌ Don't ship a page that breaks on a phone — multi-column grids must collapse, wide tables must scroll inside `.logwrap`, and no layout container may exceed phone width. See [Responsive / mobile](#responsive--mobile).

## Cheat sheet

| Need to | Touch |
|---|---|
| Add a tradeable instrument | `config/instruments.toml` → `[[instrument]]` (web surface) |
| Add a pair portfolio | `config/portfolios.toml` → `[[portfolio]]` |
| Change colors / fonts | `web/css/macro-beans.css` → `:root` |
| Adjust mobile / responsive behaviour | `web/css/macro-beans.css` → `/* responsive / mobile */` (760px & 440px breakpoints) |
| Change event-detection logic | `web/js/strategy-engine.js` (update `tests/web/*.test.js` too) |
| Run engine unit tests | `node --test "tests/web/**/*.test.js"` (or `npm test`) |
| Validate built JSON | `python scripts/site/validate_data.py` |
| Add a strategy page | Copy `buy-the-bounce.html` + `.js` |
| Add a comparison page | Copy `buy-the-bounce-league.html` + `.js` |
| Add a chart/calculator page | Copy `portfolios.html` + `.js` |
| Add a glossary term | `web/glossary.html` (alphabetical) |
| Publish a new page on the home page | `web/js/catalog.js` (append a CATALOG entry) |
| Change deploy schedule | `.github/workflows/deploy.yml` `cron:` |
| Trigger a fresh deploy | `gh workflow run deploy.yml -R bennetwi92/macro-beans` |
| Check site is live | `curl https://bennetwi92.github.io/macro-beans/` |
