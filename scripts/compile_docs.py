#!/usr/bin/env python3
"""
Docs compiler: builds an auto-generated index of every CLAUDE.md in the
repo and splices it into the root CLAUDE.md between sentinel markers.

The root CLAUDE.md must contain:

    <!-- DOCS:START -->
    ...
    <!-- DOCS:END -->

Run after adding, removing, or renaming any CLAUDE.md. The index is the
single source of truth for "what docs exist in this repo". It replaces
scattered README.md / docs/ directories.

Usage: python3 scripts/compile_docs.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    "output", "venv", ".venv", "__pycache__", ".git",
    "node_modules", ".mypy_cache", ".pytest_cache", ".claude",
    "dist", "build",
}

START_MARKER = "<!-- DOCS:START -->"
END_MARKER = "<!-- DOCS:END -->"


def first_heading(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return path.parent.name


def discover() -> list[dict]:
    docs = []
    for md in sorted(PROJECT_ROOT.rglob("CLAUDE.md")):
        rel = md.relative_to(PROJECT_ROOT)
        if str(rel) == "CLAUDE.md":
            continue
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        docs.append({"path": str(rel), "heading": first_heading(md)})
    return docs


def table(docs: list[dict]) -> str:
    lines = ["| Path | Summary |", "|------|---------|"]
    for d in docs:
        lines.append(f"| `{d['path']}` | {d['heading']} |")
    return "\n".join(lines)


def main() -> None:
    root = PROJECT_ROOT / "CLAUDE.md"
    if not root.exists():
        raise SystemExit("ERROR: no root CLAUDE.md found")

    content = root.read_text(encoding="utf-8")
    if START_MARKER not in content or END_MARKER not in content:
        raise SystemExit(
            f"ERROR: root CLAUDE.md missing sentinels.\n"
            f"Add this block where you want the index:\n\n"
            f"{START_MARKER}\n{END_MARKER}"
        )

    docs = discover()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = table(docs) if docs else "_No subdirectory CLAUDE.md files yet._"
    block = f"{START_MARKER}\n{body}\n\n_Auto-compiled {timestamp}, {len(docs)} doc(s) found._\n{END_MARKER}"

    start = content.index(START_MARKER)
    end = content.index(END_MARKER) + len(END_MARKER)
    root.write_text(content[:start] + block + content[end:], encoding="utf-8")

    print(f"Indexed {len(docs)} CLAUDE.md file(s):")
    for d in docs:
        print(f"  {d['path']}: {d['heading']}")


if __name__ == "__main__":
    main()
