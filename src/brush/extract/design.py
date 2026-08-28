"""
Design source of truth -> IR.

The canonical input is a normalised `design.spec.json`. A Figma REST export is
converted into that shape by `adapters/figma.py` so the audit itself never
needs a Figma token -- which keeps the whole evaluation runnable from a clean
clone with no credentials (ground rule 08) and no private data (ground rule 07).
"""
from __future__ import annotations

import json
from typing import Any

from ..ir import DesignSystem, StyleNode, ALL_PROPS
from ..analyze.units import to_px
from ..analyze.typography import weight_to_number

NUMERIC_PROPS = {
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "gap", "row-gap", "column-gap", "width", "height", "min-height",
    "min-width", "border-radius", "border-width", "outline-width",
    "font-size", "letter-spacing",
}


def _expand_box(props: dict[str, Any]) -> dict[str, Any]:
    out = dict(props)
    for short in ("padding", "margin"):
        if short in out:
            v = str(out.pop(short)).split()
            sides = {1: lambda a: (a[0], a[0], a[0], a[0]),
                     2: lambda a: (a[0], a[1], a[0], a[1]),
                     3: lambda a: (a[0], a[1], a[2], a[1]),
                     4: lambda a: (a[0], a[1], a[2], a[3])}[min(len(v), 4)](v)
            for name, val in zip(("top", "right", "bottom", "left"), sides):
                out.setdefault(f"{short}-{name}", val)
    return out


def _resolve_token(value: Any, tokens: dict[str, Any]) -> Any:
    """`{color.brand.600}` -> the token's value."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    if s.startswith("{") and s.endswith("}"):
        path = s[1:-1].split(".")
        cur: Any = tokens
        for part in path:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return value
        return cur
    return value


def load_design(path: str) -> tuple[DesignSystem, list[StyleNode]]:
    with open(path, "r", encoding="utf-8") as fh:
        spec = json.load(fh)

    raw_tokens = spec.get("tokens", {})
    root_fs = float(spec.get("root_font_size", 16))

    ds = DesignSystem(
        color={k: str(v) for k, v in raw_tokens.get("color", {}).items()},
        space={k: float(to_px(v, root_fs) or 0) for k, v in raw_tokens.get("space", {}).items()},
        font_size={k: float(to_px(v, root_fs) or 0) for k, v in raw_tokens.get("font_size", {}).items()},
        font_weight={k: float(weight_to_number(v) or 400) for k, v in raw_tokens.get("font_weight", {}).items()},
        radius={k: float(to_px(v, root_fs) or 0) for k, v in raw_tokens.get("radius", {}).items()},
        grid_base=float(spec.get("grid_base", 4)),
        root_font_size=root_fs,
    )

    # Grouping intent lives in the design, not in the code, so it is declared
    # here and resolved into a derived measurement at compare time.
    groups = []
    for g in spec.get("groups", []):
        outer_px = to_px(_resolve_token(g["outer"].get("value"), raw_tokens), root_fs)
        groups.append({**g, "outer_px": outer_px})
    ds.groups = groups

    nodes: list[StyleNode] = []
    for comp in spec.get("components", []):
        name = comp["name"]
        role = comp.get("role", "generic")
        base = _expand_box(comp.get("props", {}))
        states: dict[str, dict] = {"default": base}
        for st, overlay in comp.get("states", {}).items():
            merged = dict(base)
            merged.update(_expand_box(overlay))
            states[st] = merged

        for state, props in states.items():
            resolved: dict[str, Any] = {}
            for prop, val in props.items():
                if prop not in ALL_PROPS:
                    continue
                val = _resolve_token(val, raw_tokens)
                if prop in NUMERIC_PROPS:
                    px = to_px(val, root_fs)
                    resolved[prop] = px if px is not None else val
                else:
                    resolved[prop] = val
            nodes.append(
                StyleNode(
                    node_id=name,
                    role=role,
                    state=state,
                    props=resolved,
                    source=path.split("/")[-1],
                    selector=comp.get("selector_hint", ""),
                    text_sample=comp.get("text", ""),
                    parent_background=_resolve_token(comp.get("on_background", "#ffffff"), raw_tokens),
                )
            )
    return ds, nodes
