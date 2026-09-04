// Shared top navigation for the v2 cockpit.
// macOS-menu-bar style: wordmark on the left, every page listed horizontally.
// One source of truth for the page list; each page includes this module and the
// bar renders itself with the current page marked active.

export const PAGES = [
  { label: "Price sheet", file: "price-sheet.html" },
  { label: "Scanner",     file: "scanner.html" },
  { label: "Chart",       file: "chart.html" },
  { label: "Reports",     file: "reports.html" },
  { label: "Simulator",   file: "simulator.html" },
  { label: "Trades",      file: "trades.html" },
  { label: "Positions",   file: "positions.html" },
  { label: "Portfolio",   file: "portfolio.html" },
  { label: "Requests",    file: "requests.html" },
  { label: "Instruments", file: "instruments.html" },
  { label: "Systems",     file: "systems.html" },
];

function currentFile() {
  const name = location.pathname.split("/").pop();
  return name && name.length ? name : "price-sheet.html";
}

export function renderNav(mountId = "appbar") {
  const mount = document.getElementById(mountId);
  if (!mount) return;
  const here = currentFile();

  const links = PAGES.map((p) => {
    const on = p.file === here ? ' class="on"' : "";
    return `<a${on} href="${p.file}">${p.label}</a>`;
  }).join("");

  mount.innerHTML = `
    <a class="appbar-logo" href="price-sheet.html">
      <span class="bean">MACRO</span><span class="dot"></span><span class="rest">BEANS</span>
    </a>
    <nav class="appbar-menu">${links}</nav>`;
}

renderNav();
