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

function buildField(f, emit) {
  const isSeg = f.type === "seg";
  const wrap = document.createElement(isSeg ? "div" : "label");
  wrap.className = "opt-field" + (isSeg ? " opt-field-seg" : "");

  if (f.label) {
    const label = document.createElement("span");
    label.className = "opt-label";
    label.textContent = f.label;
    wrap.appendChild(label);
  }

  // Segmented control: a row of buttons, exactly one active.
  if (isSeg) {
    const seg = document.createElement("div");
    seg.className = "opt-seg";
    if (f.id) seg.id = f.id;
    let current = f.value;
    for (const o of f.options || []) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "opt-seg-btn" + (o.value === f.value ? " on" : "");
      b.dataset.value = o.value;
      b.textContent = o.label;
      b.addEventListener("click", () => {
        if (current === o.value) return;
        current = o.value;
        seg.querySelectorAll(".opt-seg-btn").forEach((x) =>
          x.classList.toggle("on", x.dataset.value === current)
        );
        emit(f.id, current);
      });
      seg.appendChild(b);
    }
    wrap.appendChild(seg);
    return { wrap, input: seg };
  }

  // Inputs: date / search / text. ('search' is a text input the page wires a
  // datalist onto for type-ahead.)
  const input = document.createElement("input");
  input.type = f.type === "date" ? "date" : "text";
  input.className = "opt-input" + (f.type === "search" ? " opt-search" : "");
  if (f.type === "search") input.setAttribute("autocomplete", "off");
  if (f.id) input.id = f.id;
  if (f.value != null) input.value = f.value;
  if (f.placeholder) input.placeholder = f.placeholder;
  input.addEventListener("change", () => emit(f.id, input.value));
  wrap.appendChild(input);
  return { wrap, input };
}

export function createOptionsBar(mount, { primary = [], extra = [], onChange } = {}) {
  const el = typeof mount === "string" ? document.getElementById(mount) : mount;
  if (!el) return null;

  el.classList.add("optbar");
  el.innerHTML = "";
  const fields = {};
  const emit = (id, value) => onChange?.(id, value, fields);

  const addField = (f, row) => {
    const { wrap, input } = buildField(f, emit);
    if (f.id) fields[f.id] = input;
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
