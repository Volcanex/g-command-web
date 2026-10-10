#!/usr/bin/env python3
"""CLAUDE.md health check.

Two rules, failing either exits non-zero:

1. Every `code` span that looks like a real file path (has an extension
   or a trailing slash, isn't a URL or template placeholder) must
   resolve on disk. Stops stale references after a rename / delete.
2. Root CLAUDE.md is at most ROOT_DOC_LINE_CAP lines (default 400).
   Past that, sub-pages should absorb the detail.

Configuration: drop a JSON file at the project root called
`.check_docs.json` to customise:

    {
      "skip_dirs":         ["agents", "design-language"],
      "planned_paths":     ["scripts/run_audit.py"],
      "planned_prefixes":  ["scripts/integrations/"],
      "root_line_cap":     400
    }

`agents/`, `design-language/`, `node_modules/`, and the usual cache
directories are skipped automatically.

Run as part of CI; agents must run before opening a PR.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / ".check_docs.json"

_DEFAULT_CONFIG: dict = {
    "skip_dirs":        ["agents", "design-language"],
    "planned_paths":    [],
    "planned_prefixes": [],
    "root_line_cap":    400,
}

_PATH_RE = re.compile(r'`([a-zA-Z0-9_./\-]+/[a-zA-Z0-9_./\-]+)`')


def load_config() -> dict:
    cfg = dict(_DEFAULT_CONFIG)
    if CONFIG_FILE.is_file():
        try:
            user = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in user.items() if k in cfg})
        except json.JSONDecodeError as exc:
            print(f"warning: {CONFIG_FILE.name} parse failed: {exc}")
    return cfg


def find_claude_mds(skip_dirs: set[str]) -> list[Path]:
    auto_skips = {".pytest_cache", ".mypy_cache", "node_modules",
                  ".venv", "venv", "__pycache__", ".git",
                  "dist", "build", "output"}
    skips = auto_skips | set(skip_dirs)
    out = []
    for p in ROOT.rglob("CLAUDE.md"):
        if any(part in skips for part in p.parts):
            continue
        out.append(p)
    return sorted(out)


def looks_like_file_path(s: str) -> bool:
    """Heuristic: dotfiles, things-with-extensions, or trailing-slash dirs.
    Skips bare URL paths, route-likes, anything obviously not a file."""
    if s.startswith(("/", "http", "127.")):
        return False
    if "{" in s or "}" in s:
        return False
    last = s.rstrip("/").split("/")[-1]
    return s.endswith("/") or "." in last


def check_path_references(cfg: dict) -> list[str]:
    errors: list[str] = []
    skip_dirs = set(cfg["skip_dirs"])
    planned_paths = set(cfg["planned_paths"])
    planned_prefixes = tuple(cfg["planned_prefixes"])

    for doc in find_claude_mds(skip_dirs):
        text = doc.read_text(encoding="utf-8")
        for m in _PATH_RE.finditer(text):
            ref = m.group(1)
            if not looks_like_file_path(ref):
                continue
            if ref in planned_paths or (planned_prefixes and ref.startswith(planned_prefixes)):
                continue
            stripped = ref.rstrip("/")
            if (ROOT / stripped).exists():
                continue
            if (doc.parent / stripped).exists():
                continue
            errors.append(
                f"{doc.relative_to(ROOT)}: refers to `{ref}` which doesn't exist"
            )
    return errors


def check_root_size(cfg: dict) -> list[str]:
    cap = int(cfg["root_line_cap"])
    root_doc = ROOT / "CLAUDE.md"
    if not root_doc.is_file():
        return ["root CLAUDE.md missing"]
    n = sum(1 for _ in root_doc.read_text().splitlines())
    if n > cap:
        return [
            f"root CLAUDE.md is {n} lines (cap {cap}). "
            "Move detail into nested CLAUDE.md files."
        ]
    return []


def main() -> int:
    cfg = load_config()
    errors = check_path_references(cfg) + check_root_size(cfg)
    if errors:
        print("CLAUDE.md health check FAILED:\n")
        for e in errors:
            print(f"  ✗ {e}")
        print(f"\n{len(errors)} issue(s).")
        return 1
    n_docs = len(find_claude_mds(set(cfg["skip_dirs"])))
    print(f"CLAUDE.md health: OK ({n_docs} doc(s) checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
