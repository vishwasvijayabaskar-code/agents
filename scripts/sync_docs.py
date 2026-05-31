#!/usr/bin/env python3
"""Sync root markdown into docs/ for mkdocs, rewriting cross-links.

Run: python3 scripts/sync_docs.py  (invoked by `make docs` + CI)
"""

from pathlib import Path

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"

# (root file -> docs filename)
PAGES = {
    "ARCHITECTURE.md": "architecture.md",
    "CONTRIBUTING.md": "contributing.md",
    "CONFIG.md": "config.md",
}

# Rewrite links to root files into their docs equivalents.
LINK_REWRITES = {
    "ARCHITECTURE.md": "architecture.md",
    "CONTRIBUTING.md": "contributing.md",
    "CONFIG.md": "config.md",
    "README.md": "index.md",
}


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    for src_name, dst_name in PAGES.items():
        src = ROOT / src_name
        if not src.exists():
            continue
        text = src.read_text()
        for old, new in LINK_REWRITES.items():
            text = text.replace(f"]({old})", f"]({new})")
        (DOCS / dst_name).write_text(text)
        print(f"synced {src_name} -> docs/{dst_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
