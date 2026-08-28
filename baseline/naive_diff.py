"""
Baseline B1 — the script a competent team writes on a Friday afternoon.

This is the honest version of "the manual process people use today". It is not a
strawman: it resolves `var()` against `:root`, expands the box shorthands,
normalises hex case and units, and compares numerically wherever both sides are
plain lengths. Anyone who has maintained a design system has written something
close to this, and it catches a real share of drift.

What it cannot do is the point of the comparison:

  * it reads declarations, not the resolved cascade, so a value inherited from a
    base class or overridden by specificity is invisible to it
  * it compares colours as strings, so `#2070EC` and `#1F6FEB` are simply
    "different" -- it cannot tell an imperceptible token slip from a brand break,
    and it cannot see a contrast failure at all
  * it can only compare declarations that exist, so a deleted focus rule reads as
    "nothing to compare" rather than as a missing state
  * it has no concept of a relationship between properties, so target size,
    grid conformance and grouping ratios are outside its reach
  * every difference it finds carries the same weight, so the output is a flat
    list that a reviewer has to triage by hand

Run it exactly like the real tool so the comparison is like for like.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from brush.extract.css_engine import (  # noqa: E402
    expand_shorthand, find_block, parse_css, parse_decls, resolve_vars,
)
from brush.extract.design import load_design  # noqa: E402
from brush.analyze.units import to_px  # noqa: E402

NUMERIC = {
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "gap", "row-gap", "column-gap", "width", "height", "min-height",
    "min-width", "border-radius", "border-width", "outline-width",
    "font-size", "letter-spacing",
}
COMPARED = NUMERIC | {
    "color", "background-color", "border-color", "outline-color",
    "font-family", "font-weight", "line-height", "text-transform", "outline-style",
}


def _norm(v: str) -> str:
    v = str(v).strip().lower().rstrip(";")
    v = re.sub(r"\s+", " ", v)
    if re.fullmatch(r"#[0-9a-f]{3}", v):
        v = "#" + "".join(c * 2 for c in v[1:])
    return v


def _selector_variants(hint: str) -> list[str]:
    """
    `button.btn.btn--primary` is how the spec names it; `.btn` and `.btn--primary`
    is how the stylesheet writes it. A competent script tries the whole ladder and
    merges base-to-modifier, which is the manual reading a person would do.
    """
    classes = re.findall(r"\.([\w-]+)", hint)
    tag = re.match(r"^([a-zA-Z][\w-]*)", hint)
    out = []
    if tag:
        out.append(tag.group(1))
    for c in classes:
        out.append(f".{c}")
    out.append(hint)
    if tag and classes:
        out.append(tag.group(1) + "." + classes[-1])
    seen, ordered = set(), []
    for sel in out:
        if sel not in seen:
            seen.add(sel)
            ordered.append(sel)
    return ordered


def declared_props(css: str, selector: str, variables: dict) -> dict:
    """
    Declarations for a component, merged base-class first then modifiers.
    This mirrors specificity crudely: later (more specific) selectors win.
    """
    out: dict[str, str] = {}
    for sel in _selector_variants(selector):
        span = find_block(css, sel)
        if not span:
            continue
        decls = parse_decls(css[span[0]:span[1]])
        for prop, raw in decls.items():
            if prop.startswith("--"):
                continue
            for k, v in expand_shorthand(prop, resolve_vars(raw, variables)).items():
                out[k] = v
    return out


def run(design_path: str, css_paths: list[str]) -> dict:
    t0 = time.time()
    ds, design_nodes = load_design(design_path)
    css = ""
    for p in css_paths:
        with open(p, "r", encoding="utf-8") as fh:
            css += fh.read() + "\n"
    _, variables = parse_css(css)

    findings = []
    for d in design_nodes:
        if d.state != "default":
            continue
        sel = d.selector
        if not sel:
            continue
        # The baseline is given the selector hint from the spec, so it is not
        # penalised on component mapping -- only on what it can measure.
        got = declared_props(css, sel, variables)
        if not got:
            continue
        for prop, want in sorted(d.props.items()):
            if prop not in COMPARED or prop not in got:
                continue
            have = got[prop]
            if prop in NUMERIC:
                a = to_px(want, ds.root_font_size)
                b = to_px(have, ds.root_font_size)
                if a is None or b is None:
                    differs = _norm(str(want)) != _norm(have)
                else:
                    differs = abs(a - b) > 0.01
            else:
                differs = _norm(str(want)) != _norm(have)
            if differs:
                findings.append({
                    "component": d.node_id, "prop": prop,
                    "expected": want, "actual": have,
                    "note": "declared value differs from specification",
                })

    return {
        "baseline": "naive_diff",
        "findings": findings,
        "stats": {
            "findings": len(findings),
            "wall_seconds": round(time.time() - t0, 4),
            "cost_usd": 0.0,
            "severity_available": False,
            "components_checked": len({d.node_id for d in design_nodes if d.state == "default"}),
        },
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--design", required=True)
    ap.add_argument("--css", nargs="+", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(a.design, a.css)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2, default=str)
    try:
        print(f"naive_diff: {res['stats']['findings']} differences "
              f"in {res['stats']['wall_seconds']}s")
        for f in res["findings"][:12]:
            print(f"  {f['component']:22} {f['prop']:18} {f['expected']} → {f['actual']}")
    except BrokenPipeError:
        pass  # piping into `head` is a normal way to run this
