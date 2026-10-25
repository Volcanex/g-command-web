#!/usr/bin/env python3
"""Report native drift, or record a hand-ported screen as verified against the web."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.native import NATIVE_FILE, native_screens, source_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", metavar="SCREEN")
    parser.add_argument("--min-build", type=int)
    args = parser.parse_args()
    registry = json.loads(NATIVE_FILE.read_text())
    if args.min_build is not None and (not args.verify or args.min_build < 1):
        parser.error("--min-build requires --verify and a positive build number")
    if args.verify:
        if args.verify not in registry["screens"]:
            parser.error(f"unknown native screen: {args.verify}")
        screen = registry["screens"][args.verify]
        screen["verified"] = source_hash(screen["sources"])
        if args.min_build is not None:
            screen["min_build"] = args.min_build
        NATIVE_FILE.write_text(json.dumps(registry, indent=2) + "\n")
    stale = []
    current = native_screens(report=lambda message: (stale.append(message), print(message)))
    for name in current:
        print(f"native screen '{name}' is current")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
