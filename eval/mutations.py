"""
Seeded defect injection.

The hardest part of evaluating a design-drift detector is knowing the right
answer. Hand-labelling a real codebase is slow and the labels are arguable.
So we invert it: start from an implementation that provably matches the spec
(0 findings, verified in `test_clean_baseline`), then inject defects whose
identity, location and expected severity band are known by construction.

Every mutation is a single, surgical edit to one declaration inside one rule.
That gives an unambiguous ground-truth tuple:

    (component, property, expected_band, mutation_id)

and it means precision/recall are computed against facts, not opinions.

The mutations are drawn from real design-drift patterns: a designer's value
retyped from memory, a token replaced by the literal it happened to equal at
the time, a focus ring deleted during a refactor, a font stack whose first
family was never installed.
"""
from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass, asdict
from typing import Optional


# `expected_band` is assigned by reading the published severity policy in
# `src/brush/knowledge/ux_laws.json` against the measured value of each
# mutation -- not by observing what the detector outputs. The derivation for
# every entry is written out in `docs/SEVERITY_DERIVATION.md` so a judge can
# check the assignment independently of the code.


@dataclass
class Mutation:
    mutation_id: str
    kind: str
    component: str
    css_rule: str
    prop: str
    original: str
    mutated: str
    expected_band: str          # blocker | major | minor | info
    expected_props: list[str]   # IR properties a correct detector should flag
    narrative: str              # how this happens in real life


# ---------------------------------------------------------------------------
# CSS surgery
# ---------------------------------------------------------------------------
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))
from brush.extract.css_engine import find_block as _find_block  # noqa: E402


def read_decl(css: str, selector: str, prop: str) -> Optional[str]:
    span = _find_block(css, selector)
    if not span:
        return None
    body = css[span[0]:span[1]]
    m = re.search(rf"(?<![\w-]){re.escape(prop)}\s*:\s*([^;]+);", body)
    return m.group(1).strip() if m else None


def set_decl(css: str, selector: str, prop: str, value: str) -> str:
    span = _find_block(css, selector)
    if not span:
        raise KeyError(f"selector not found: {selector}")
    start, end = span
    body = css[start:end]
    pat = re.compile(rf"((?<![\w-]){re.escape(prop)}\s*:\s*)([^;]+)(;)")
    if pat.search(body):
        new_body = pat.sub(lambda m: m.group(1) + value + m.group(3), body, count=1)
    else:
        new_body = body.rstrip() + f"\n  {prop}: {value};\n"
    return css[:start] + new_body + css[end:]


def drop_decl(css: str, selector: str, prop: str) -> str:
    span = _find_block(css, selector)
    if not span:
        raise KeyError(f"selector not found: {selector}")
    start, end = span
    body = css[start:end]
    new_body = re.sub(rf"(?<![\w-]){re.escape(prop)}\s*:\s*[^;]+;\s*", "", body, count=1)
    return css[:start] + new_body + css[end:]


def drop_rule(css: str, selector: str) -> str:
    pattern = re.compile(r"(^|\})(\s*)" + re.escape(selector) + r"\s*\{[^}]*\}", re.M)
    return pattern.sub(lambda m: m.group(1), css, count=1)


# ---------------------------------------------------------------------------
# The mutation catalogue
# ---------------------------------------------------------------------------
def catalogue() -> list[Mutation]:
    """
    Every entry is a real drift pattern. `expected_band` is derived from the
    published severity policy in `ux_laws.json`, not from what our detector
    happens to output -- otherwise the evaluation would be marking its own work.
    """
    return [
        Mutation(
            "M01", "space_nudge", "Button/Primary", ".btn--primary", "padding",
            "12px 24px", "12px 20px", "major",
            ["padding-right", "padding-left"],
            "Someone eyeballed the button in a browser and shaved the sides to fit a longer label.",
        ),
        Mutation(
            "M02", "space_offgrid", "Card/Summary", ".summary", "padding",
            "var(--space-6)", "22px", "minor",
            ["padding-top", "padding-right", "padding-bottom", "padding-left", "-derived-grid-conformance"],
            "Token replaced by a literal during a merge conflict; 22px is off the 4px grid entirely.",
        ),
        Mutation(
            "M03", "color_near", "Button/Primary", ".btn--primary", "background-color",
            "var(--brand-600)", "#2070EC", "info",
            ["background-color"],
            "Brand blue pasted from a screenshot colour-picker. Visually identical, but no longer a token.",
        ),
        Mutation(
            "M04", "color_drift", "Badge/Success", ".badge--success", "color",
            "var(--success-600)", "#2E9E63", "blocker",
            ["color"],
            # Originally banded 'major' by hand as a plain colour drift. The tool
            # disagreed, and the tool was right: the spec green sits at 4.72:1 on
            # surface-050 and the lightened one falls to 3.19:1, so this crosses
            # WCAG AA rather than merely looking different. Band corrected.
            "Success green lightened 'to look friendlier'. It also crosses the AA line, "
            "which is precisely what nobody notices by eye.",
        ),
        Mutation(
            "M05", "color_contrast", "Input/HelpText", ".field__help", "color",
            "var(--ink-500)", "#A8AEB8", "blocker",
            ["color"],
            "Help text greyed down for visual calm. Drops to 2.3:1 and fails WCAG AA.",
        ),
        Mutation(
            "M06", "type_size", "Card/Title", ".summary__title", "font-size",
            "24px", "21px", "major",
            ["font-size"],
            "Heading nudged down to stop a two-line wrap on a narrow viewport.",
        ),
        Mutation(
            "M07", "weight_flatten", "Button/Primary", ".btn", "font-weight",
            "600", "400", "major",
            ["font-weight"],
            "Weight reset when the base .btn rule was rewritten; the variant never re-declared it.",
        ),
        Mutation(
            "M08", "family_fallback", "Input/Text", ".field__input", "font-family",
            "var(--font-sans)", "Helvetica, Arial, sans-serif", "major",
            ["font-family"],
            "Field styled in isolation by a contractor who did not know the token existed.",
        ),
        Mutation(
            "M09", "leading_crush", "List/Row", ".summary__row", "line-height",
            "1.5", "1.2", "major",
            ["line-height"],
            "Leading tightened to fit more rows above the fold.",
        ),
        Mutation(
            "M10", "radius_drift", "Input/Text", ".field__input", "border-radius",
            "var(--radius-md)", "4px", "minor",
            ["border-radius"],
            "Wrong radius token picked from autocomplete; sm instead of md.",
        ),
        Mutation(
            "M11", "focus_removed", "Button/Primary", ".btn--primary:focus-visible", "__RULE__",
            "outline: 2px solid var(--brand-600);", "(rule deleted)", "blocker",
            ["outline-width", "outline-style"],
            "Focus ring deleted to silence a designer's 'ugly blue box' complaint.",
        ),
        Mutation(
            "M12", "target_shrink", "Button/Ghost", ".btn--ghost", "min-height",
            "44px", "28px", "major",
            ["min-height", "-derived-target-height"],
            "Ghost button compacted for a dense toolbar. Still above the WCAG floor, but hard to hit.",
        ),
        Mutation(
            "M13", "target_below_min", "Button/Ghost", ".btn--ghost", "min-height",
            "44px", "20px", "blocker",
            ["min-height", "-derived-target-height"],
            "Same compaction taken one step further; now under the 24px WCAG 2.5.8 minimum.",
        ),
        Mutation(
            "M14", "proximity_collapse", "Input/Label", ".field__label", "margin-bottom",
            "var(--space-2)", "2px", "major",
            ["margin-bottom"],
            "Label pulled tight against its field, collapsing the grouping the spec relies on.",
        ),
        Mutation(
            "M15", "border_contrast", "Input/Text", ".field__input", "border",
            "1px solid var(--ink-300)", "1px solid #E8EAEE", "blocker",
            ["border-color"],
            "Field border lightened for a cleaner look. Boundary drops under the 3:1 non-text minimum.",
        ),
        Mutation(
            "M16", "space_subpixel", "Alert/Danger", ".alert--danger", "padding",
            "16px", "15px", "info",
            ["padding-top", "padding-right", "padding-bottom", "padding-left"],
            "A 1px trim that no one will see but which breaks grid rhythm across the page.",
        ),
        Mutation(
            "M19", "proximity_inversion", "Input/Label", ".field__label", "margin-bottom",
            "var(--space-2)", "28px", "major",
            ["margin-bottom", "-derived-proximity-ratio"],
            "Label pushed away from its field to 'give it room'. The gap below the label "
            "now exceeds the 24px gap between fields, so the label reads as belonging to "
            "the field above it. Every individual value still looks reasonable in isolation.",
        ),
        Mutation(
            "M17", "letter_spacing", "Card/Title", ".summary__title", "letter-spacing",
            "-0.4px", "0px", "info",
            ["letter-spacing"],
            "Optical tracking dropped when the heading style was copied from a generic template.",
        ),
        Mutation(
            "M18", "color_semantic_swap", "Alert/Danger", ".alert--danger", "background-color",
            "var(--danger-050)", "#FFF8E1", "major",
            ["background-color"],
            "Danger alert given a warning-amber background; the semantic role no longer matches the colour.",
        ),
    ]


# ---------------------------------------------------------------------------
# Case generation
# ---------------------------------------------------------------------------
def apply_mutation(css: str, mut: Mutation) -> str:
    if mut.kind == "focus_removed":
        return drop_rule(css, mut.css_rule)
    if mut.prop == "__RULE__":
        return drop_rule(css, mut.css_rule)
    return set_decl(css, mut.css_rule, mut.prop, mut.mutated)


def build_cases(
    clean_css_path: str,
    out_dir: str,
    seed: int = 20260828,
    n_cases: int = 12,
    per_case: tuple[int, int] = (2, 4),
) -> list[dict]:
    """
    Generate `n_cases` mutated stylesheets plus their ground truth.

    Case 0 is always the untouched stylesheet -- the specificity control. A
    detector that scores well on defects but invents findings on a clean file
    is useless in review, and this case is the only one that catches that.
    Case 1 is always the full catalogue applied at once: the hard case.
    """
    rng = random.Random(seed)
    with open(clean_css_path, "r", encoding="utf-8") as fh:
        clean = fh.read()
    os.makedirs(out_dir, exist_ok=True)
    cat = catalogue()

    # Mutations that touch the same declaration cannot coexist in one case.
    def conflict(a: Mutation, b: Mutation) -> bool:
        return a.css_rule == b.css_rule and a.prop == b.prop

    cases: list[dict] = []

    def emit(idx: int, muts: list[Mutation], label: str) -> None:
        css = clean
        for m in muts:
            css = apply_mutation(css, m)
        name = f"case_{idx:02d}"
        path = os.path.join(out_dir, f"{name}.css")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"/* {name} — {label} — generated by eval/mutations.py, seed={seed} */\n")
            fh.write(css)
        cases.append({
            "case_id": name,
            "label": label,
            "css_path": path,
            "mutations": [asdict(m) for m in muts],
            "ground_truth": [
                {"component": m.component, "prop": p, "expected_band": m.expected_band,
                 "mutation_id": m.mutation_id, "kind": m.kind}
                for m in muts for p in m.expected_props
            ],
        })

    emit(0, [], "clean control — a correct detector reports nothing here")
    non_conflicting: list[Mutation] = []
    for m in cat:
        if not any(conflict(m, x) for x in non_conflicting):
            non_conflicting.append(m)
    emit(1, non_conflicting, "everything at once — the hard case")

    for i in range(2, n_cases):
        k = rng.randint(*per_case)
        picked: list[Mutation] = []
        pool = cat[:]
        rng.shuffle(pool)
        for m in pool:
            if len(picked) >= k:
                break
            if not any(conflict(m, x) for x in picked):
                picked.append(m)
        kinds = ", ".join(sorted({m.kind for m in picked}))
        emit(i, picked, f"{len(picked)} defects: {kinds}")

    manifest = os.path.join(out_dir, "cases.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"seed": seed, "n_cases": len(cases), "cases": cases}, fh, indent=2)
    return cases


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Generate the mutated evaluation set.")
    ap.add_argument("--css", default="eval/cases/checkout.css")
    ap.add_argument("--out", default="eval/cases/generated")
    ap.add_argument("--seed", type=int, default=20260828)
    ap.add_argument("--n", type=int, default=12)
    a = ap.parse_args()
    cs = build_cases(a.css, a.out, a.seed, a.n)
    print(f"generated {len(cs)} cases in {a.out}")
    for c in cs:
        print(f"  {c['case_id']}: {len(c['mutations'])} mutations, "
              f"{len(c['ground_truth'])} ground-truth entries — {c['label']}")
