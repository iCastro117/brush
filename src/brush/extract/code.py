"""Implemented frontend -> IR."""
from __future__ import annotations

import os

from ..ir import StyleNode, ALL_PROPS
from ..analyze.units import to_px
from .css_engine import (
    Element, apply_cascade, parse_css, parse_html, resolve_backgrounds,
)

NUMERIC_PROPS = {
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "gap", "row-gap", "column-gap", "width", "height", "min-height",
    "min-width", "border-radius", "border-width", "outline-width",
    "font-size", "letter-spacing",
}


def extract_code_nodes(
    html_path: str,
    css_paths: list[str] | None = None,
    root_font_size: float = 16.0,
    include_unannotated: bool = False,
    ignore_annotations: bool = False,
) -> tuple[list[StyleNode], Element]:
    """
    Parse HTML+CSS and return one StyleNode per component element.

    `data-ds-component` is the happy path, but most real codebases have no such
    annotation, so `include_unannotated` also emits every class-bearing element
    as a mapping candidate for the mapper agent. `ignore_annotations` drops the
    attributes entirely -- that is the harder configuration we evaluate under,
    because it is the one a team adopting the tool actually starts from.
    """
    with open(html_path, "r", encoding="utf-8") as fh:
        html_src = fh.read()
    root, inline_styles = parse_html(html_src)

    css_text = ""
    for p in (css_paths or []):
        with open(p, "r", encoding="utf-8") as fh:
            css_text += fh.read() + "\n"
    css_text += "\n".join(inline_styles)

    rules, variables = parse_css(css_text)
    apply_cascade(root, rules, variables, root_font_size)
    resolve_backgrounds(root)

    nodes: list[StyleNode] = []
    for el in root.walk():
        annotated = el.component if not ignore_annotations else None
        if not annotated:
            if not include_unannotated:
                continue
            if not el.classes or el.tag in ("html", "body", "head"):
                continue
        # A state node is only meaningful when the cascade actually produced a
        # different result for it. Emitting identical hover/focus twins would
        # inflate every count downstream and hide the states that do differ.
        state_pairs = [("default", el.computed)]
        for st, comp in sorted(el.computed_states.items()):
            if comp != el.computed:
                state_pairs.append((st, comp))

        for state, computed in state_pairs:
            props: dict[str, object] = {}
            for prop in ALL_PROPS:
                raw = computed.get(prop)
                if raw is None:
                    continue
                if prop in NUMERIC_PROPS:
                    parent_fs = to_px(computed.get("font-size"), root_font_size) or root_font_size
                    px = to_px(raw, root_font_size, parent_fs)
                    props[prop] = px if px is not None else raw
                else:
                    props[prop] = raw
            nodes.append(
                StyleNode(
                    node_id=annotated or el.selector_path(),
                    role=el.role,
                    state=state,
                    props=props,
                    source=os.path.basename(html_path),
                    selector=el.selector_path(),
                    text_sample=el.text.strip()[:80],
                    parent_background=computed.get("-dl-effective-background"),
                )
            )
            nodes[-1].props["-dl-annotated"] = bool(annotated)
    return nodes, root
