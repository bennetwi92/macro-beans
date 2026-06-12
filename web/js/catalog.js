/* Macro Beans publication catalog.
   Single source of truth for what's published on the site. Add a new
   piece by appending one object. Keep `added` in YYYY-MM-DD; the home
   page tags it as NEW for 14 days.

   type:     "strategy" | "calculator" | "portfolio" | "report" | "reference"
   slug:     short identifier (used as DOM id, must be unique)
   title:    display title for the card
   blurb:    one short sentence (~20 words)
   page:     relative URL of the destination page
   added:    ISO date the piece was first published (controls NEW badge)
   portfolio (reports only, optional): slug of the pair portfolio this report
             belongs to, so portfolios.html can surface a deep-dive link.
*/

export const CATALOG = [
  {
    slug:  "buy-the-bounce",
    type:  "strategy",
    title: "Buy the Bounce",
    blurb: "When the market drops hard in a single day, does it tend to recover over the next few days? Every historical example, side by side.",
    page:  "buy-the-bounce.html",
    added: "2026-06-08",
  },
  {
    slug:  "buy-the-bounce-league",
    type:  "strategy",
    title: "Buy the Bounce — League Table",
    blurb: "The same bounce setup applied across every instrument in one sortable view. Spot which markets bounce hardest.",
    page:  "buy-the-bounce-league.html",
    added: "2026-06-08",
  },
  {
    slug:  "red-streak",
    type:  "strategy",
    title: "Red Streak",
    blurb: "When a market closes down several days in a row, does it bounce? Every losing streak in history and what came next.",
    page:  "red-streak.html",
    added: "2026-06-11",
  },
  {
    slug:  "red-streak-league",
    type:  "strategy",
    title: "Red Streak — League Table",
    blurb: "The same losing-streak setup across every instrument in one sortable view. Spot which markets snap back hardest.",
    page:  "red-streak-league.html",
    added: "2026-06-11",
  },
  {
    slug:  "best-months",
    type:  "strategy",
    title: "Best Months",
    blurb: "Does the calendar matter? A colour-shaded year showing which months have historically been kind to a market — and which have not.",
    page:  "best-months.html",
    added: "2026-06-11",
  },
  {
    slug:  "best-months-league",
    type:  "strategy",
    title: "Best Months — League Table",
    blurb: "Every market's calendar footprint in one grid. Rank instruments by any month of the year.",
    page:  "best-months-league.html",
    added: "2026-06-11",
  },
  {
    slug:  "portfolios",
    type:  "portfolio",
    title: "Pair Portfolios",
    blurb: "Relative-value long-short pairs, beta-hedged — from leveraged-ETF index pairs to UK single-share CFD pairs priced with real Trading 212 costs.",
    page:  "portfolios.html",
    added: "2026-06-08",
  },
  {
    slug:  "instrument",
    type:  "tracker",
    title: "Price Tracker",
    blurb: "Pick any market and see its price at a glance — where it sits now, how far it has moved, and the recent run on one chart.",
    page:  "instrument.html",
    added: "2026-06-12",
  },
  {
    slug:  "scanner",
    type:  "signal",
    title: "Scanner",
    blurb: "One page that checks every strategy against every market and lists what's triggered as of the last close — so you only have to look here.",
    page:  "scanner.html",
    added: "2026-06-12",
  },
  {
    slug:  "reference-instruments",
    type:  "reference",
    title: "Instruments",
    blurb: "Every market we track in one sortable table — what it is, where it lists, and which strategies cover it.",
    page:  "reference-instruments.html",
    added: "2026-06-12",
  },
  {
    slug:  "reference-symbols",
    type:  "reference",
    title: "Symbols",
    blurb: "Every concrete ticker behind those markets — LSE ETFs and US tickers — with venue, surface and freshness.",
    page:  "reference-symbols.html",
    added: "2026-06-12",
  },
  {
    slug:      "report-shell-bp",
    type:      "report",
    title:     "Shell vs BP: What's Driving the Swings",
    blurb:     "The two London oil giants pulled apart all year. A plain-English walk through what moved Shell against BP — takeovers, buybacks and an oil shock.",
    page:      "report-shell-bp.html",
    portfolio: "shell-bp",
    added:     "2026-06-10",
  },
];

export const CATEGORIES = [
  { key: "strategy",   label: "STRATEGIES",   blurb: "Trade ideas with historical evidence." },
  { key: "signal",     label: "SCANNER",      blurb: "Every strategy checked across every market — the setups firing right now." },
  { key: "tracker",    label: "PRICES",       blurb: "Track a market's price and recent moves at a glance." },
  { key: "calculator", label: "CALCULATORS",  blurb: "Tools to size, value, or score a trade." },
  { key: "portfolio",  label: "PORTFOLIOS",   blurb: "Multi-leg positions tracked over time." },
  { key: "report",     label: "REPORTS",      blurb: "Deep dives on what's been moving a market or a pair." },
  { key: "reference",  label: "REFERENCE",    blurb: "The full map of markets and tickers behind the site." },
];

export const NEW_BADGE_DAYS = 14;
