// Currency + price helpers for the trading book. Loads the cockpit instrument
// menu (per-instrument quote currency + latest close) and the daily FX rates,
// then converts native-currency prices to GBP. GBp (pence) is a fixed /100;
// USD/EUR use the FX feed.

let MENU = {};
let FX = { gbpusd: null, gbpeur: null };

export const CURRENCIES = ["GBp", "GBP", "USD", "EUR"];

const normCcy = (c) => {
  const x = String(c || "").trim();
  return x === "GBX" ? "GBp" : x;
};

export async function loadPrices() {
  try {
    const [m, f] = await Promise.all([
      fetch("data/instruments.json", { cache: "no-cache" }).then((r) => r.json()),
      fetch("data/fx.json", { cache: "no-cache" }).then((r) => r.json()).catch(() => ({})),
    ]);
    MENU = {};
    for (const i of m.instruments || []) MENU[i.ticker.toUpperCase()] = i;
    FX = { gbpusd: f.gbpusd || null, gbpeur: f.gbpeur || null };
  } catch (_) { /* offline / not built yet — book still works with GBP defaults */ }
  // The weekly review's universe: every S&P 500 name with its last weekly
  // close (USD), so a US single bought off the shortlist is auto-marked on
  // every book page. Registry instruments keep their own entries.
  try {
    const sc = await fetch("data/scorecards.json", { cache: "no-cache" }).then((r) => r.json());
    for (const r of sc.rows || []) {
      const t = r.t.toUpperCase();
      if (!MENU[t] && r.c != null) MENU[t] = { ticker: t, name: r.n, currency: "USD", last: r.c };
    }
  } catch (_) { /* scorecards not built — registry marks only */ }
}

// Native -> GBP rate multiplier for a currency (null when an FX rate is missing).
export const fxRates = () => ({ ...FX });

// Smart default currency for a (possibly free-text) ticker.
export function guessCurrency(ticker) {
  const t = String(ticker || "").toUpperCase();
  const m = MENU[t];
  if (m && m.currency) return normCcy(m.currency);
  if (t.endsWith(".L")) return "GBp"; // LSE default is pence
  return "GBP";
}

export const inUniverse = (ticker) => Boolean(MENU[String(ticker || "").toUpperCase()]);

// Latest close in the instrument's NATIVE currency (for auto-marks), or null.
export function autoCloseNative(ticker) {
  const m = MENU[String(ticker || "").toUpperCase()];
  return m && m.last != null ? Number(m.last) : null;
}

// Convert a native-currency amount to GBP (null if an FX rate is needed but absent).
export function toGBP(amount, currency) {
  if (amount == null || amount === "") return null;
  const v = Number(amount);
  const c = normCcy(currency);
  if (c === "GBP") return v;
  if (c === "GBp") return v / 100;
  if (c === "USD") return FX.gbpusd ? v / FX.gbpusd : null;
  if (c === "EUR") return FX.gbpeur ? v / FX.gbpeur : null;
  return v; // unknown — assume already GBP
}
