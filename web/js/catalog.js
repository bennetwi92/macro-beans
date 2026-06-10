/* Macro Beans publication catalog.
   Single source of truth for what's published on the site. Add a new
   piece by appending one object. Keep `added` in YYYY-MM-DD; the home
   page tags it as NEW for 14 days.

   type:     "strategy" | "calculator" | "portfolio" | "report"
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
    slug:  "portfolios",
    type:  "portfolio",
    title: "Pair Portfolios",
    blurb: "Relative-value long-short pairs, beta-hedged — from leveraged-ETF index pairs to UK single-share CFD pairs priced with real Trading 212 costs.",
    page:  "portfolios.html",
    added: "2026-06-08",
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
  { key: "calculator", label: "CALCULATORS",  blurb: "Tools to size, value, or score a trade." },
  { key: "portfolio",  label: "PORTFOLIOS",   blurb: "Multi-leg positions tracked over time." },
  { key: "report",     label: "REPORTS",      blurb: "Deep dives on what's been moving a market or a pair." },
];

export const NEW_BADGE_DAYS = 14;
