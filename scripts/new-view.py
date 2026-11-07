#!/usr/bin/env python3
"""Scaffold a Preact view that keeps the view contract (pages/CLAUDE.md, "New views").

    python3 scripts/new-view.py <slug> --group <group> [--title "Title"] [--no-api]

Copies scripts/view-template/ into pages/<slug>/, filling __SLUG__, __TITLE__ and
__GROUP__. The template lives outside pages/, so it is never compiled or put on the rail.
The new view nests under <group> on the rail; then run `python3 compile.py`.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = Path(__file__).resolve().parent / "view-template"
PAGES = ROOT / "pages"


def groups() -> set[str]:
    out = set()
    for cfg in PAGES.glob("*/config.json"):
        c = json.loads(cfg.read_text())
        if c.get("tabs") and c.get("nav"):
            out.add(str(c["tabs"]))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--group", required=True, help="the rail group it nests under (tabs)")
    ap.add_argument("--title", help="defaults to the slug, capitalised")
    ap.add_argument("--no-api", action="store_true", help="skip api.py (the view then needs another data URL)")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[a-z][a-z0-9-]*", a.slug):
        sys.exit("slug: lower case letters, digits and hyphens, starting with a letter")
    known = groups()
    if a.group not in known:
        sys.exit(f"--group {a.group!r} is not a rail group; one of: {', '.join(sorted(known))}")
    dest = PAGES / a.slug
    if dest.exists():
        sys.exit(f"{dest} already exists")
    title = a.title or a.slug.replace("-", " ").capitalize()
    subs = {"__SLUG__": a.slug, "__TITLE__": title, "__GROUP__": a.group}
    dest.mkdir()
    for src in sorted(TEMPLATE.iterdir()):
        if a.no_api and src.name == "api.py":
            continue
        text = src.read_text()
        for k, v in subs.items():
            text = text.replace(k, json.dumps(v)[1:-1] if src.suffix == ".json" else v)
        (dest / src.name).write_text(text)
    print(f"pages/{a.slug}/ ({', '.join(sorted(p.name for p in dest.iterdir()))}); now: python3 compile.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
