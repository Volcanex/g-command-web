"""Dash layout: where a panel page places its panels on a desktop window.

A page's `config.json` holds `layout`. The web compiles it into the dash
markup and placement CSS (`<!-- seed:dash-layout -->`), the manifest serves it
to the Mac app, and the page's panel order is its reading order. See
`core/panels/CLAUDE.md`, Layout.
"""
import html

WIDE = "(min-width: 901px) and (min-height: 561px)"


def items(layout):
    """Every item in reading order, each as a dict with `panel` or `row`."""
    for name in layout.get("top", []):
        yield _item(name)
    for column in layout.get("columns", []):
        for item in column.get("items", []):
            yield _item(item)


def panels(layout):
    names = []
    for item in items(layout):
        names += item["row"] if "row" in item else [item["panel"]]
    return names


def _item(item):
    return {"panel": item} if isinstance(item, str) else dict(item)


def normalise(layout):
    """The manifest form: every item an object, defaults left out."""
    return {
        "top": [_item(name) for name in layout.get("top", [])],
        "columns": [{
            "width": column.get("width", 1),
            "min": column.get("min", 0),
            "items": [_item(item) for item in column.get("items", [])],
        } for column in layout.get("columns", [])],
    }


def render(slug, layout):
    """The web dash: `.fd-dash` of `.fd-col` columns, `.fd-row` for panels
    side by side, then the page's placement CSS for wide windows."""
    cls = f"fd-{slug}"

    def panel(name, depth):
        return "  " * depth + f"<!-- seed:panel-{name} -->"

    lines = [f'<div class="fd-dash {html.escape(cls)}">']
    lines += [panel(name, 1) for name in layout.get("top", [])]
    for column in layout.get("columns", []):
        lines.append('  <div class="fd-col">')
        for item in map(_item, column.get("items", [])):
            if "row" in item:
                lines.append('    <div class="fd-row">')
                lines += [panel(name, 3) for name in item["row"]]
                lines.append("    </div>")
            else:
                lines.append(panel(item["panel"], 2))
        lines.append("  </div>")
    lines.append("</div>")

    columns = " ".join(f"minmax({column.get('min', 0)}{'px' if column.get('min') else ''}, {column.get('width', 1)}fr)"
                       for column in layout.get("columns", []))
    rules = [f".{cls} {{ grid-template-columns: {columns};"
             + (" grid-template-rows: auto minmax(0, 1fr); }" if layout.get("top") else " }")]
    rules += [f".{cls} > #fd-{name} {{ grid-column: 1 / -1; }}" for name in layout.get("top", [])]
    for column in layout.get("columns", []):
        for item in map(_item, column.get("items", [])):
            target = f".{cls} " + (f"#fd-{item['panel']}" if "panel" in item else ".fd-row:has(> #fd-" + item["row"][0] + ")")
            if item.get("fit"):
                rules.append(f"{target} {{ flex: 0 {1 if item.get('shrink') else 0} auto; }}")
            elif item.get("grow", 1) != 1:
                rules.append(f"{target} {{ flex: {item['grow']} 1 0; }}")
            if item.get("max"):
                rules.append(f"{target} {{ max-height: {item['max']}%; }}")
    lines.append("<style>")
    lines.append(f"@media {WIDE} {{")
    lines += ["  " + rule for rule in rules]
    lines.append("}")
    lines.append("</style>")
    return "\n".join(lines) + "\n"
