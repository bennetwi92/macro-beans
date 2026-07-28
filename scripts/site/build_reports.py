"""Build the v2 cockpit research library (Reports page).

Converts the markdown research notes under docs/ into HTML fragments at build
time (so the browser needs no markdown parser) and writes an index the Reports
page lists and filters.

Run:
    /usr/local/bin/python3 scripts/site/build_reports.py

Outputs:
    web/v2/data/reports.json            {built_at, reports:[{slug,title,category,summary,source,updated,words}]}
    web/v2/data/reports/<slug>.html     rendered HTML fragment per note

These are the owner's own trusted notes, so the rendered HTML is injected
as-is (no untrusted input to sanitise). Relative image links in a note won't
resolve on the site — text-first for now.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import markdown

# Make `src` importable (kept consistent with the other site builds; unused here
# but harmless and future-proof if a report ever needs registry data).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BuildTally, write_json  # noqa: E402

# Top-level docs/ subdirs to leave out of the public library.
# Directories under docs/ that must never reach the public site.
#   web_v2  -- internal build/design notes for the cockpit itself
#   private -- notes containing personal financial detail (contribution amounts,
#              day rates, account balances). The published companion notes carry
#              the same analysis expressed in percentages.
EXCLUDE_DIRS = {"web_v2", "private"}

# Nicer category names than a plain title-case of the directory.
CATEGORY_NAMES = {
    "event_studies": "Event Studies",
    "mean_reversion": "Mean Reversion",
    "portfolio": "Portfolio",
    "reference": "Reference",
    "vix_options": "VIX Options",
}

MD_EXTENSIONS = ["fenced_code", "tables", "sane_lists"]


def humanize(s: str) -> str:
    return s.replace("_", " ").replace("-", " ").strip().title()


def title_and_summary(text: str, fallback: str) -> tuple[str, str]:
    """First H1 as the title; first prose paragraph as the summary."""
    title = None
    summary = None
    for raw in text.splitlines():
        s = raw.strip()
        if title is None and s.startswith("# "):
            title = s[2:].strip()
            continue
        if title is not None and summary is None:
            if not s or s.startswith("#"):
                continue
            if s.startswith(("- ", "* ", "|", ">", "```", "![")):
                continue
            summary = s
            break
    if title is None:
        title = humanize(fallback)
    if summary:
        summary = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", summary)  # links -> text
        summary = re.sub(r"[*`_]", "", summary).strip()
        if len(summary) > 200:
            summary = summary[:197].rstrip() + "…"
    else:
        summary = ""
    return title, summary


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    docs_root = repo_root / "docs"
    out_dir = repo_root / "web" / "v2" / "data"
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    md_files = [
        p for p in sorted(docs_root.rglob("*.md"))
        if p.relative_to(docs_root).parts[0] not in EXCLUDE_DIRS
    ]
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tally = BuildTally(len(md_files))
    index = []

    for md_path in md_files:
        rel = md_path.relative_to(docs_root)
        top = rel.parts[0]
        slug = "-".join(rel.with_suffix("").parts)
        label = str(rel)
        print(f"  {label:<52s} ...", end=" ", flush=True)
        try:
            text = md_path.read_text(encoding="utf-8")
            title, summary = title_and_summary(text, rel.stem)
            html = markdown.markdown(text, extensions=MD_EXTENSIONS)
            (reports_dir / f"{slug}.html").write_text(html, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 — skip a bad file, keep the rest
            print(f"FAILED ({exc})")
            tally.record_failure(label, exc)
            continue
        updated = datetime.fromtimestamp(md_path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")
        index.append({
            "slug": slug,
            "title": title,
            "category": CATEGORY_NAMES.get(top, humanize(top)),
            "summary": summary,
            "source": str(rel),
            "updated": updated,
            "words": len(text.split()),
        })
        tally.record_ok()
        print(f"{len(text.split()):>5d} words  ->  {slug}.html")

    write_json(out_dir / "reports.json", {"built_at": built_at, "reports": index})
    print(f"\nWrote {len(index)} reports + reports.json")
    print(f"Built at {built_at}")

    sys.exit(tally.report_and_exit_code())


if __name__ == "__main__":
    main()
