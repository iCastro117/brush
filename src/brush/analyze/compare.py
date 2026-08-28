"""
Measurement generation.

This module answers exactly one question per property: how far apart are the
design value and the code value, in a unit that means something perceptually.
It never decides whether a difference matters. That separation is deliberate --
it is what lets the verifier recompute any agent claim from first principles.
"""
from __future__ import annotations

from typing import Optional

from ..ir import CHANNEL_OF, Measurement, StyleNode, DesignSystem
from . import color as C
from . import geometry as G
from . import typography as T

# Below these, we record the measurement but mark it within tolerance.
TOL_PX = 0.5
TOL_DELTA_E = 0.5
TOL_RATIO = 0.01


def _num(v: object) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace("px", ""))
    except (ValueError, AttributeError):
        return None


def compare_nodes(
    design: StyleNode,
    code: StyleNode,
    ds: DesignSystem,
) -> list[Measurement]:
    """Produce one Measurement per property present on either side."""
    out: list[Measurement] = []
    key = design.key()
    props = sorted(set(design.props) | set(code.props))

    d_fs = _num(design.props.get("font-size")) or ds.root_font_size
    c_fs = _num(code.props.get("font-size")) or ds.root_font_size

    for prop in props:
        channel = CHANNEL_OF.get(prop)
        if channel is None:
            continue
        dv = design.props.get(prop)
        cv = code.props.get(prop)

        if channel == "color":
            out.append(_color_measurement(key, prop, dv, cv, design, code, ds))
        elif channel == "geometry":
            out.append(_geometry_measurement(key, prop, dv, cv, ds))
        elif channel == "typography":
            out.append(_typography_measurement(key, prop, dv, cv, d_fs, c_fs))
        else:
            same = str(dv).strip().lower() == str(cv).strip().lower()
            out.append(Measurement(
                key, prop, channel, dv, cv,
                delta=0.0 if same else 1.0, delta_unit="bool",
                within_tolerance=same, method="normalised string equality",
            ))

    out.extend(_derived_measurements(key, design, code, ds, d_fs, c_fs))
    return out


def _color_measurement(key, prop, dv, cv, design, code, ds) -> Measurement:
    dc, cc = C.parse_color(dv), C.parse_color(cv)
    extra: dict = {}

    if dc is None or cc is None:
        missing = cv is None or (dv is not None and cc is None)
        return Measurement(
            key, prop, "color", dv, cv,
            delta=None if not missing else 1.0, delta_unit="bool",
            within_tolerance=(str(dv).lower() == str(cv).lower()),
            method="unparseable on one side; string comparison only",
            extra={"parse_failed": True},
        )

    de = C.delta_e2000(dc, cc)
    token_name, token_dist = C.nearest_token(cv, ds.color)
    extra["nearest_token"] = token_name
    extra["nearest_token_delta_e"] = round(token_dist, 3)
    # Identity, not proximity. A value 0.4 deltaE from brand-600 is invisible to
    # a user AND is not brand-600 -- those are two different questions and the
    # answer to the second one is what keeps the token layer honest.
    extra["is_token_value"] = any(
        cc.hex() == (C.parse_color(hv).hex() if C.parse_color(hv) else None)
        for hv in ds.color.values()
    )
    extra["token_proximity_only"] = (not extra["is_token_value"]) and token_dist < 1.0
    extra["design_hex"] = dc.hex()
    extra["code_hex"] = cc.hex()

    # Contrast is only meaningful for foreground text against its backdrop.
    if prop == "color" and code.parent_background:
        bg = C.parse_color(code.parent_background)
        own_bg = C.parse_color(code.props.get("background-color"))
        if own_bg is not None and own_bg.a > 0:
            bg = own_bg
        if bg is not None:
            fs = _num(code.props.get("font-size")) or 16.0
            wt = T.weight_to_number(code.props.get("font-weight")) or 400.0
            ratio = C.contrast_ratio(cc, bg)
            extra["contrast_ratio"] = round(ratio, 2)
            extra["contrast_backdrop"] = bg.hex()
            extra["wcag_level"] = C.wcag_level(ratio, fs, wt)
            if dc is not None:
                extra["design_contrast_ratio"] = round(C.contrast_ratio(dc, bg), 2)
    if prop in ("border-color", "outline-color") and code.parent_background:
        bg = C.parse_color(code.parent_background)
        if bg is not None:
            extra["nontext_contrast_ratio"] = round(C.contrast_ratio(cc, bg), 2)

    return Measurement(
        key, prop, "color", dv, cv,
        delta=round(de, 4), delta_unit="deltaE",
        within_tolerance=de <= TOL_DELTA_E,
        method="sRGB -> CIELAB (D65) -> CIEDE2000",
        extra=extra,
    )


def _geometry_measurement(key, prop, dv, cv, ds) -> Measurement:
    dn, cn = _num(dv), _num(cv)
    if dn is None or cn is None:
        same = str(dv).strip().lower() == str(cv).strip().lower()
        return Measurement(
            key, prop, "geometry", dv, cv,
            delta=None if dv is None or cv is None else (0.0 if same else 1.0),
            delta_unit="bool", within_tolerance=same,
            method="non-numeric length; string comparison",
            extra={"unresolved": True},
        )
    delta = cn - dn
    token, tok_d = G.nearest_space_token(cn, ds.space)
    # The base grid governs *spacing*. Hairline borders and pill radii are not
    # spacing and are never expected to land on it -- checking them there
    # produced a false positive on every conforming 1px border we tested.
    grid_relevant = prop.startswith(("padding-", "margin-", "gap", "row-gap", "column-gap"))
    extra = {
        "grid_applicable": grid_relevant,
        "on_grid": G.on_grid(cn, ds.grid_base) if grid_relevant else True,
        "nearest_grid": G.nearest_grid(cn, ds.grid_base),
        "grid_base": ds.grid_base,
        "nearest_space_token": token,
        "nearest_space_token_delta": round(tok_d, 3) if tok_d != float("inf") else None,
    }
    return Measurement(
        key, prop, "geometry", dn, cn,
        delta=round(delta, 3), delta_unit="px",
        within_tolerance=abs(delta) <= TOL_PX,
        method="css cascade -> px (rem@root, em@parent)",
        extra=extra,
    )


def _typography_measurement(key, prop, dv, cv, d_fs, c_fs) -> Measurement:
    if prop == "font-family":
        reason = T.family_mismatch(dv, cv)
        return Measurement(
            key, prop, "typography", dv, cv,
            delta=0.0 if reason is None else 1.0, delta_unit="bool",
            within_tolerance=reason is None,
            method="first-family comparison after quote/case normalisation",
            extra={"reason": reason,
                   "design_head": T.family_head(dv),
                   "code_head": T.family_head(cv)},
        )

    if prop == "font-weight":
        dn, cn = T.weight_to_number(dv), T.weight_to_number(cv)
        if dn is None or cn is None:
            return Measurement(key, prop, "typography", dv, cv, None, "bool",
                               str(dv) == str(cv), "unresolved weight")
        return Measurement(
            key, prop, "typography", dn, cn,
            delta=round(cn - dn, 3), delta_unit="weight",
            within_tolerance=abs(cn - dn) < 1,
            method="keyword -> numeric weight",
            extra={"steps": round((cn - dn) / 100.0, 2)},
        )

    if prop == "font-size":
        dn, cn = _num(dv), _num(cv)
        if dn is None or cn is None:
            return Measurement(key, prop, "typography", dv, cv, None, "bool",
                               str(dv) == str(cv), "unresolved size")
        ratio = T.size_ratio(dn, cn) or 1.0
        return Measurement(
            key, prop, "typography", dn, cn,
            delta=round(ratio - 1.0, 5), delta_unit="ratio",
            within_tolerance=abs(ratio - 1.0) <= TOL_RATIO,
            method="px ratio (code/design); ratio space, not absolute px",
            extra={"delta_px": round(cn - dn, 2),
                   "scale_steps": round(T.scale_steps_off(dn, cn) or 0.0, 3)},
        )

    if prop == "line-height":
        dr = T.resolve_line_height(dv, d_fs)
        cr = T.resolve_line_height(cv, c_fs)
        if dr is None or cr is None:
            return Measurement(key, prop, "typography", dv, cv, None, "bool",
                               str(dv) == str(cv), "unresolved line-height")
        return Measurement(
            key, prop, "typography", round(dr, 4), round(cr, 4),
            delta=round(cr - dr, 4), delta_unit="ratio",
            within_tolerance=abs(cr - dr) <= 0.02,
            method="normalised to unitless ratio against own font-size",
            extra={"below_leading_floor": cr < T.LEADING_FLOOR,
                   "leading_floor": T.LEADING_FLOOR},
        )

    if prop == "letter-spacing":
        dn, cn = _num(dv) or 0.0, _num(cv) or 0.0
        return Measurement(
            key, prop, "typography", dn, cn,
            delta=round(cn - dn, 3), delta_unit="px",
            within_tolerance=abs(cn - dn) <= 0.05,
            method="css cascade -> px",
        )

    same = str(dv).strip().lower() == str(cv).strip().lower()
    return Measurement(key, prop, "typography", dv, cv,
                       0.0 if same else 1.0, "bool", same, "string equality")


def _derived_measurements(key, design, code, ds, d_fs, c_fs) -> list[Measurement]:
    """
    Facts that are not a single property diff but a relationship between them.
    These are where the UX laws bite hardest and where a naive property-by-
    property diff sees nothing wrong.
    """
    out: list[Measurement] = []

    # 1. Interactive target size (Fitts's Law / WCAG 2.5.8)
    if code.role in ("button", "input", "link", "checkbox", "radio", "select"):
        d_h = _num(design.props.get("min-height")) or _num(design.props.get("height"))
        c_h = _num(code.props.get("min-height")) or _num(code.props.get("height"))
        if d_h is not None or c_h is not None:
            out.append(Measurement(
                key, "-derived-target-height", "geometry", d_h, c_h,
                delta=None if (d_h is None or c_h is None) else round(c_h - d_h, 2),
                delta_unit="px",
                within_tolerance=(c_h is not None and c_h >= 44.0),
                method="min-height or height of an interactive role",
                extra={"wcag_min": 24, "comfortable": 44,
                       "below_wcag_min": c_h is not None and c_h < 24,
                       "below_comfortable": c_h is not None and c_h < 44},
            ))

    # 2. Horizontal padding symmetry -- asymmetry that the spec did not ask for
    d_sym = G.symmetry_break(design.props, "x")
    c_sym = G.symmetry_break(code.props, "x")
    if d_sym is not None and c_sym is not None and abs(c_sym - d_sym) > TOL_PX:
        out.append(Measurement(
            key, "-derived-padding-symmetry-x", "geometry", d_sym, c_sym,
            delta=round(c_sym - d_sym, 2), delta_unit="px",
            within_tolerance=False,
            method="abs(padding-left - padding-right), design vs code",
        ))

    # 3. Gestalt grouping ratio (Law of Proximity).
    #    This is the case a property-by-property diff structurally cannot see:
    #    every individual value can sit inside tolerance while the RELATIONSHIP
    #    between two of them inverts, and the label silently reassigns itself to
    #    the field above.
    for g in getattr(ds, "groups", []):
        if g.get("inner", {}).get("component") != design.node_id:
            continue
        prop = g["inner"]["prop"]
        inner_code = _num(code.props.get(prop))
        inner_design = _num(design.props.get(prop))
        outer = g.get("outer_px")
        if inner_code is None or not outer:
            continue
        r_code = G.proximity_ratio(inner_code, outer)
        r_design = G.proximity_ratio(inner_design, outer) if inner_design else None
        out.append(Measurement(
            key, "-derived-proximity-ratio", "geometry",
            round(r_design, 3) if r_design else None,
            round(r_code, 3) if r_code else None,
            delta=round(r_code - r_design, 3) if (r_code and r_design) else None,
            delta_unit="ratio",
            within_tolerance=r_code is not None and r_code >= 1.5,
            method=f"outer separation {outer:g}px / inner {prop}; stable at >= 1.5",
            extra={"group": g.get("name"), "inner_px": inner_code,
                   "outer_px": outer, "threshold": 1.5,
                   "inverted": r_code is not None and r_code < 1.5},
        ))

    # 4. Off-grid audit over every resolved spacing value
    off_grid = {}
    for prop, val in code.props.items():
        if prop.startswith(("padding-", "margin-", "gap", "row-gap", "column-gap")):
            n = _num(val)
            if n is not None and n != 0 and not G.on_grid(n, ds.grid_base):
                off_grid[prop] = n
    if off_grid:
        out.append(Measurement(
            key, "-derived-grid-conformance", "geometry",
            f"multiples of {ds.grid_base:.0f}px", off_grid,
            delta=float(len(off_grid)), delta_unit="count",
            within_tolerance=False,
            method=f"value % {ds.grid_base:.0f} != 0 across spacing properties",
            extra={"grid_base": ds.grid_base,
                   "suggested": {k: G.nearest_grid(v, ds.grid_base) for k, v in off_grid.items()}},
        ))

    return out


def index_measurements(ms: list[Measurement]) -> dict[str, Measurement]:
    return {m.measurement_id: m for m in ms}
