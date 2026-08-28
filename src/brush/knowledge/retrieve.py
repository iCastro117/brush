"""
Knowledge retrieval + the deterministic severity classifier.

Two consumers, one function. The diagnostician agent reads `context_for()` to
reason with the same vocabulary a design-system reviewer would use. The verifier
calls `classify()` to recompute severity from the raw measurement and compare it
against what the agent claimed. Because both sides share this module, an agent
cannot quietly promote a 1px nudge to a blocker: the recomputation catches it.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

from ..ir import Measurement, StyleNode

_HERE = os.path.dirname(os.path.abspath(__file__))
_PACK_PATH = os.path.join(_HERE, "ux_laws.json")

INTERACTIVE_ROLES = {"button", "input", "link", "checkbox", "radio", "select", "tab"}
# Roles whose spacing draws a group boundary rather than just sitting inside one.
TEXT_ROLES = {"body", "heading", "label", "listitem", "alert", "status", "link", "button"}

SEVERITY_ORDER = {"info": 0, "minor": 1, "major": 2, "blocker": 3}


@lru_cache(maxsize=1)
def pack() -> dict:
    with open(_PACK_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def thresholds() -> dict:
    return pack()["perceptual_thresholds"]


def law(law_id: str) -> Optional[dict]:
    return pack()["laws"].get(law_id)


def valid_law_ids() -> set[str]:
    p = pack()
    return set(p["laws"]) | set(p["heuristics"]) | set(p["wcag"])


def clause(clause_id: str) -> Optional[dict]:
    for c in pack()["clauses"]:
        if c["id"] == clause_id:
            return c
    return None


@dataclass
class Verdict:
    """The deterministic classification of one measurement."""
    is_finding: bool
    clause_id: Optional[str]
    severity: str
    laws: list[str]
    heuristics: list[str]
    wcag: list[str]
    reason: str
    priority: float = 1.0


def _t(name: str) -> float:
    return float(thresholds()[name]["value"])


def classify(m: Measurement, node: StyleNode) -> Verdict:
    """
    Map a measurement to at most one clause. Order matters: accessibility
    failures are checked before aesthetic drift so that a colour change which
    also breaks contrast is reported as the blocker it is, not as a colour nit.
    """
    role = node.role
    prop = m.prop
    ch = m.channel
    d = m.delta
    ex = m.extra or {}

    def v(cid: str, reason: str, priority: float = 1.0) -> Verdict:
        c = clause(cid) or {}
        return Verdict(True, cid, c.get("severity", "minor"), list(c.get("laws", [])),
                       list(c.get("heuristics", [])), list(c.get("wcag", [])),
                       reason, priority)

    # ---- derived measurements ------------------------------------------
    if prop == "-derived-target-height":
        if ex.get("below_wcag_min"):
            return v("c-target-below-min",
                     f"{m.code_value}px interactive target is below the 24px WCAG minimum")
        if d is not None and d < 0 and (ex.get("below_comfortable") or abs(d) >= 4):
            return v("c-target-shrunk",
                     f"target height dropped {abs(d):.0f}px vs spec ({m.design_value} -> {m.code_value})")
        return Verdict(False, None, "info", [], [], [], "target size within spec")

    if prop == "-derived-grid-conformance":
        return v("c-offgrid", f"{int(d or 0)} spacing value(s) off the "
                              f"{ex.get('grid_base', 4):.0f}px base grid")

    if prop == "-derived-proximity-ratio":
        if ex.get("inverted"):
            return v("c-proximity-inversion",
                     f"grouping ratio fell to {m.code_value} (stable at "
                     f"{ex.get('threshold')}): the label no longer binds to its own field",
                     priority=1.5)
        return Verdict(False, None, "info", [], [], [], "grouping ratio stable")

    if prop == "-derived-padding-symmetry-x":
        return v("c-space-minor",
                 f"horizontal padding asymmetry of {m.code_value}px not present in the spec")

    # ---- a required state affordance that the code never declares ------
    # The spec asks for a focus ring; the stylesheet has no focus rule at all.
    # This must not degrade into "some property differs" -- an absent focus
    # indicator is a WCAG 2.4.7 failure and the policy calls it a blocker.
    if node.state == "focus" and prop in ("outline-width", "outline-style", "outline-color"):
        code_missing = m.code_value in (None, "none", "0", 0, "0px", "transparent")
        design_present = m.design_value not in (None, "none", "0", 0, "0px")
        if design_present and code_missing:
            return v("c-focus-removed",
                     f"spec defines {prop}={m.design_value} on focus; the implementation "
                     f"declares no focus rule at all", priority=1.8)

    # ---- a state the spec requires that the code never declares ---------
    # A deleted focus rule does not show up as a wrong value; it shows up as an
    # absent one. Reading that as "unresolved property" graded the single most
    # serious defect in the suite as info.
    if node.state in ("focus", "hover", "disabled") and prop.startswith("outline"):
        if m.code_value in (None, "", "none", 0, "0") and m.design_value not in (None, "", "none"):
            return v("c-focus-removed",
                     f"the spec defines a {node.state} outline ({m.design_value}) "
                     f"that the implementation never declares", priority=1.8)

    # ---- colour ---------------------------------------------------------
    if ch == "color":
        if prop == "color" and role in TEXT_ROLES and ex.get("wcag_level") == "fail":
            ratio = ex.get("contrast_ratio")
            return v("c-contrast-fail",
                     f"text contrast {ratio}:1 against {ex.get('contrast_backdrop')} fails WCAG AA",
                     priority=1.6)
        if prop in ("border-color", "outline-color"):
            nt = ex.get("nontext_contrast_ratio")
            if nt is not None and nt < 3.0 and (d is None or d > _t("delta_e_jnd")):
                return v("c-nontext-contrast-fail",
                         f"boundary contrast {nt}:1 is under the 3:1 non-text minimum")
        if d is None:
            return Verdict(False, None, "info", [], [], [], "colour not comparable")
        if m.within_tolerance and ex.get("is_token_value", True):
            return Verdict(False, None, "info", [], [], [], "matches spec within JND and uses a token")
        if d >= _t("delta_e_brand_break"):
            return v("c-color-brand-break", f"CIEDE2000 {d:.2f} reads as a different colour")
        if d >= _t("delta_e_obvious"):
            return v("c-color-obvious", f"CIEDE2000 {d:.2f} is above the ordinary-observer threshold")
        if d >= _t("delta_e_jnd"):
            return v("c-color-subtle", f"CIEDE2000 {d:.2f} is perceptible on close inspection")
        # Off-token only means something when there IS drift. A conforming
        # `transparent` or a literal that exactly equals its token is not a
        # defect at the computed-value layer; token *hygiene* is a source-level
        # check and is reported separately so the two never conflate.
        if d > 0.05 and not ex.get("is_token_value", True):
            return v("c-color-offtoken",
                     f"value is {d:.2f} deltaE from spec and does not resolve to a token")
        return Verdict(False, None, "info", [], [], [], "colour within tolerance")

    # ---- geometry -------------------------------------------------------
    if ch == "geometry":
        if d is None:
            return Verdict(False, None, "info", [], [], [], "length not comparable")
        ad = abs(d)
        if m.delta_unit == "bool":
            return (Verdict(False, None, "info", [], [], [], "identical")
                    if ad == 0 else v("c-space-minor", "non-numeric length differs from spec"))
        if ad <= 0.5:
            if ex.get("grid_applicable", False) and not ex.get("on_grid", True):
                return v("c-offgrid", f"{m.code_value}px is off the {ex.get('grid_base', 4):.0f}px grid")
            return Verdict(False, None, "info", [], [], [], "within tolerance")
        # A margin between a label and its control is a grouping edge just as
        # much as padding is -- that is the whole content of the Law of
        # Proximity, and treating margins as ungrouped under-graded every
        # collapsed label/field pair in the set.
        grouping = prop.startswith(
            ("padding-", "margin-", "gap", "row-gap", "column-gap")
        ) or role in INTERACTIVE_ROLES
        if role in INTERACTIVE_ROLES and prop in ("min-height", "height") \
                and isinstance(m.code_value, (int, float)) and m.code_value < 24:
            return v("c-target-below-min",
                     f"{m.code_value:g}px interactive target is below the 24px WCAG minimum",
                     priority=1.7)
        if prop == "border-radius":
            return v("c-radius-family", f"radius differs by {d:+.0f}px from the spec")
        if ad >= 4 and grouping:
            return v("c-space-major",
                     f"{prop} differs by {d:+.0f}px on a grouping or interactive edge")
        off_grid = ex.get("grid_applicable", False) and not ex.get("on_grid", True)
        if ad >= _t("spacing_perceptible_px"):
            # Magnitude decides the band. An off-grid flag is recorded in the
            # rationale but never escalates: we briefly let it promote 2px
            # deltas to major and it contradicted the perceptual floor the whole
            # model rests on (changelog I6).
            suffix = (f" and {m.code_value}px is off the "
                      f"{ex.get('grid_base', 4):.0f}px grid" if off_grid else "")
            return v("c-space-minor", f"{prop} differs by {d:+.0f}px{suffix}")
        suffix = (f"; {m.code_value}px is also off the "
                  f"{ex.get('grid_base', 4):.0f}px grid" if off_grid else "")
        return v("c-space-subpixel",
                 f"{prop} differs by {d:+.2f}px, below the perceptual floor{suffix}")

    # ---- typography -----------------------------------------------------
    if ch == "typography":
        if prop == "font-family":
            if m.within_tolerance:
                return Verdict(False, None, "info", [], [], [], "family matches")
            return v("c-family-fallback", ex.get("reason") or "font family differs from spec")
        if prop == "font-size":
            if d is None:
                return Verdict(False, None, "info", [], [], [], "size not comparable")
            ad = abs(d)
            if ad >= 0.12:
                return v("c-type-size-major",
                         f"font-size is {d * 100:+.1f}% off spec ({ex.get('delta_px', 0):+.0f}px)")
            if ad >= _t("type_size_ratio_notable"):
                return v("c-type-size-minor", f"font-size is {d * 100:+.1f}% off spec")
            return Verdict(False, None, "info", [], [], [], "size within tolerance")
        if prop == "font-weight":
            if d is None:
                return Verdict(False, None, "info", [], [], [], "weight not comparable")
            ad = abs(d)
            if ad >= 200:
                return v("c-weight-flatten", f"weight differs by {d:+.0f} ({ex.get('steps')} steps)")
            if ad >= 100:
                return v("c-weight-step", f"weight differs by one step ({m.design_value} -> {m.code_value})")
            return Verdict(False, None, "info", [], [], [], "weight matches")
        if prop == "line-height":
            if ex.get("below_leading_floor") and role in ("body", "listitem", "alert", "label"):
                return v("c-leading-floor",
                         f"line-height {m.code_value} is under the {ex.get('leading_floor')} reading floor")
            if d is not None and abs(d) > 0.02:
                return v("c-space-minor", f"line-height differs by {d:+.2f}")
            return Verdict(False, None, "info", [], [], [], "leading matches")
        if prop == "letter-spacing" and d is not None:
            ad = abs(d)
            if ad < 0.05:
                return Verdict(False, None, "info", [], [], [], "tracking matches")
            if ad < _t("spacing_perceptible_px"):
                return v("c-space-subpixel",
                         f"tracking differs by {d:+.2f}px, below the perceptual floor")
            return v("c-space-minor", f"tracking differs by {d:+.2f}px")
        if d is not None and abs(d) > 0.05:
            return v("c-space-minor", f"{prop} differs by {d:+.2f}")
        return Verdict(False, None, "info", [], [], [], "within tolerance")

    if d and abs(d) > 0:
        return v("c-unspecified-decoration", f"{prop} differs from spec")
    return Verdict(False, None, "info", [], [], [], "within tolerance")


def apply_modifiers(verdict: Verdict, node: StyleNode, flow_terminal: set[str]) -> float:
    """Priority multiplier. Moves ordering, never severity."""
    mods = pack()["weighting_modifiers"]
    p = verdict.priority
    if node.node_id in flow_terminal:
        p *= mods["terminal_action"]["factor"]
    if node.role in ("alert", "status") or "Error" in node.node_id:
        p *= mods["error_state"]["factor"]
    return round(p, 3)


def context_for(m: Measurement, node: StyleNode) -> dict[str, Any]:
    """
    The knowledge slice handed to the diagnostician for one measurement.
    Kept small on purpose: dumping the whole pack into every prompt was the
    first thing we tried and it measurably hurt precision (see changelog I2).
    """
    verdict = classify(m, node)
    ids = verdict.laws + verdict.heuristics + verdict.wcag
    p = pack()
    detail = {}
    for i in ids:
        if i in p["laws"]:
            detail[i] = {"name": p["laws"][i]["name"], "audit_use": p["laws"][i]["audit_use"]}
        elif i in p["heuristics"]:
            detail[i] = {"name": p["heuristics"][i]["name"], "audit_use": p["heuristics"][i]["audit_use"]}
        elif i in p["wcag"]:
            detail[i] = {"name": p["wcag"][i]["name"], "rule": p["wcag"][i]["rule"]}
    return {
        "candidate_clause": verdict.clause_id,
        "deterministic_severity": verdict.severity,
        "deterministic_reason": verdict.reason,
        "applicable_principles": detail,
        "severity_bands": p["severity_policy"]["bands"],
    }
