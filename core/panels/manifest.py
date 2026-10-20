import json
from collections import defaultdict
from pathlib import Path

from core.panels import PANELS, layout


def build_manifest(pages_dir):
    configs = []
    for page in sorted(Path(pages_dir).iterdir()):
        if not page.is_dir() or page.name.startswith("_"):
            continue
        path = page / "config.json"
        if not path.is_file():
            continue
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        config.setdefault("slug", page.name)
        configs.append(config)
    sections = defaultdict(list)
    groups = defaultdict(list)
    for config in configs:
        if config.get("nav"):
            sections[config.get("nav_section") or config.get("title", "Other")].append(config)
        if config.get("tabs"):
            groups[str(config["tabs"])].append(config)

    def entry(config, tab=False):
        slug = config.get("slug", "")
        label = (config.get("tab_label") if tab else None) or config.get("nav_label") or config.get("title", slug)
        result = {"slug": slug, "label": label}
        if not tab:
            result["icon"] = config.get("nav_icon", "circle")
        if "layout" in config:
            result["panels"] = layout.panels(config["layout"])
            result["layout"] = layout.normalise(config["layout"])
        elif "panels" in config:
            result["panels"] = list(config["panels"])
        if not tab and config.get("tabs"):
            result["tabs"] = [entry(member, True) for member in sorted(groups[str(config["tabs"])], key=lambda c: c.get("order", 999))]
        return result

    ordered = sorted(sections, key=lambda name: min(config.get("order", 999) for config in sections[name]))
    return {"v": 1, "name": "G-Command",
            "sections": [{"title": name, "entries": [entry(config) for config in sorted(sections[name], key=lambda c: c.get("order", 999))]} for name in ordered],
            "panels": {name: {"title": spec[0], "icon": spec[1]} for name, spec in PANELS.items()}}
