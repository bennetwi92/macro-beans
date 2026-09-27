// Shared top navigation for the v2 cockpit.
// macOS-menu-bar style: wordmark on the left, every page listed horizontally.
// One source of truth for the page list; each page includes this module and the
// bar renders itself with the current page marked active.
//
// The first group is the WEEKLY REVIEW — the five steps of the Sunday routine
// (docs/web_v2/scorecard_strategy_spec.md §4), numbered and in order, because
// the order is the routine. The second group is the toolbox the routine draws
// on: the LSE execution surface (price sheet, scanner, chart), the research
// library, the trainer, and the trading book's ledgers.

export const PAGES = [
  { label: "1 Tape",      file: "tape.html",      group: "review" },
  { label: "2 Shortlist", file: "shortlist.html", group: "review" },
  { label: "3 Card",      file: "card.html",      group: "review" },
  { label: "4 Book",      file: "book.html",      group: "review" },
  { label: "5 Orders",    file: "orders.html",    group: "review" },
  { label: "Price sheet", file: "price-sheet.html" },
  { label: "Scanner",     file: "scanner.html" },
  { label: "Chart",       file: "chart.html" },
  { label: "Reports",     file: "reports.html" },
  { label: "Simulator",   file: "simulator.html" },
  { label: "Trades",      file: "trades.html" },
  { label: "Positions",   file: "positions.html" },
  { label: "Portfolio",   file: "portfolio.html" },
  { label: "Requests",    file: "requests.html" },
];

export const HOME = "tape.html";

function currentFile() {
  const name = location.pathname.split("/").pop();
  return name && name.length && name !== "index.html" ? name : HOME;
}

export function renderNav(mountId = "appbar") {
  const mount = document.getElementById(mountId);
  if (!mount) return;
  const here = currentFile();

  let prevGroup = PAGES[0].group ?? null;
  const links = PAGES.map((p) => {
    const g = p.group ?? null;
    const sep = g !== prevGroup ? `<span class="appbar-sep" aria-hidden="true"></span>` : "";
    prevGroup = g;
    const on = p.file === here ? ' class="on"' : "";
    return `${sep}<a${on} href="${p.file}">${p.label}</a>`;
  }).join("");

  mount.innerHTML = `
    <a class="appbar-logo" href="${HOME}">
      <span class="bean">MACRO</span><span class="dot"></span><span class="rest">BEANS</span>
    </a>
    <nav class="appbar-menu">${links}</nav>`;
}

renderNav();
