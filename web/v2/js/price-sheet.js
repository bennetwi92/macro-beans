// Price sheet page entry module.
// Renders the shared nav (side-effect import) and the options bar.
// The grid itself is not built yet — onChange is a placeholder hook.

import "./nav.js";
import { createOptionsBar } from "./options-bar.js";

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

createOptionsBar("optbar", {
  primary: [
    { type: "date", id: "ps-date", label: "DATE", value: todayISO() },
  ],
  onChange: (id, value) => {
    // Grid not built yet — this is where a date change will refilter the sheet.
    void id;
    void value;
  },
});
