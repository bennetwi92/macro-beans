// Shared options bar for v2 cockpit pages.
//
// An expandable form that starts as a single compact row of controls. Pages
// pass a list of `primary` fields (always visible) and optional `extra` fields
// (revealed by an expand toggle that only appears when extras exist). Each page
// owns its own field set; this component only renders and wires them.
//
// Usage:
//   createOptionsBar('optbar', {
//     primary: [{ type:'date', id:'ps-date', label:'DATE', value:'2026-06-26' }],
//     onChange: (id, value, fields) => { ... },
//   });
//
// Returns { el, fields } where `fields` maps id -> the input element.

function buildField(f) {
  const wrap = document.createElement("label");
  wrap.className = "opt-field";

  const label = document.createElement("span");
  label.className = "opt-label";
  label.textContent = f.label ?? "";
  wrap.appendChild(label);

  let input;
  switch (f.type) {
    case "date":
      input = document.createElement("input");
      input.type = "date";
      break;
    default: // 'text' and unknown types fall back to a text input
      input = document.createElement("input");
      input.type = "text";
  }
  input.className = "opt-input";
  if (f.id) input.id = f.id;
  if (f.value != null) input.value = f.value;
  if (f.placeholder) input.placeholder = f.placeholder;
  wrap.appendChild(input);

  return { wrap, input };
}

export function createOptionsBar(mount, { primary = [], extra = [], onChange } = {}) {
  const el = typeof mount === "string" ? document.getElementById(mount) : mount;
  if (!el) return null;

  el.classList.add("optbar");
  el.innerHTML = "";
  const fields = {};

  const addField = (f, row) => {
    const { wrap, input } = buildField(f);
    if (f.id) fields[f.id] = input;
    input.addEventListener("change", () => onChange?.(f.id, input.value, fields));
    row.appendChild(wrap);
  };

  const primaryRow = document.createElement("div");
  primaryRow.className = "optbar-row";
  primary.forEach((f) => addField(f, primaryRow));
  el.appendChild(primaryRow);

  // Expand mechanism — only surfaced when a page supplies extra controls.
  if (extra.length) {
    const extraRow = document.createElement("div");
    extraRow.className = "optbar-row optbar-extra";
    extraRow.hidden = true;
    extra.forEach((f) => addField(f, extraRow));

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "opt-expand";
    btn.setAttribute("aria-expanded", "false");
    btn.title = "More options";
    btn.textContent = "···";
    btn.addEventListener("click", () => {
      const open = extraRow.hidden;
      extraRow.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
      btn.classList.toggle("on", open);
    });

    primaryRow.appendChild(btn);
    el.appendChild(extraRow);
  }

  return { el, fields };
}
