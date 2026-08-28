"""
Typography analysis.

Font size is the one property where equal-sized *errors* have unequal
consequences: 2px off a 12px caption is a 17% change; 2px off a 48px display is
4%. We therefore score type in ratio space, and separately check the two things
that actually damage reading: line-height falling under the leading floor, and
a font stack whose first family is not the one in the spec (a silent fallback
that changes metrics on every machine that lacks the font).
"""
from __future__ import annotations

import re
from typing import Optional

# Common modular scales. Detecting which one a system uses lets us say
# "this is half a step off" instead of "this is 2px off".
KNOWN_SCALES = {
    "minor-second": 1.067, "major-second": 1.125, "minor-third": 1.200,
    "major-third": 1.250, "perfect-fourth": 1.333, "augmented-fourth": 1.414,
    "perfect-fifth": 1.500, "golden": 1.618,
}

# Body copy under this leading gets measurably slower to read.
LEADING_FLOOR = 1.4
LEADING_CEILING = 1.9


def normalise_family(value: object) -> list[str]:
    if value is None:
        return []
    parts = re.split(r"\s*,\s*", str(value))
    out = []
    for p in parts:
        p = p.strip().strip("'\"").lower()
        if p:
            out.append(p)
    return out


def family_head(value: object) -> Optional[str]:
    fams = normalise_family(value)
    return fams[0] if fams else None


def family_mismatch(design: object, code: object) -> Optional[str]:
    """Return a short reason string when the *first* family differs."""
    d, c = family_head(design), family_head(code)
    if d is None or c is None:
        return None
    if d == c:
        return None
    return f"first family '{c}' does not match spec '{d}'"


def size_ratio(design_px: Optional[float], code_px: Optional[float]) -> Optional[float]:
    if not design_px or not code_px or design_px <= 0:
        return None
    return code_px / design_px


def scale_steps_off(
    design_px: Optional[float], code_px: Optional[float], ratio: float = 1.25
) -> Optional[float]:
    """How many steps of the modular scale separate the two sizes."""
    import math
    r = size_ratio(design_px, code_px)
    if r is None or r <= 0 or ratio <= 1:
        return None
    return math.log(r) / math.log(ratio)


def detect_scale(sizes: list[float]) -> tuple[Optional[str], float]:
    """Infer the modular scale a design system is built on."""
    vals = sorted({round(s, 2) for s in sizes if s})
    if len(vals) < 3:
        return None, 0.0
    ratios = [vals[i + 1] / vals[i] for i in range(len(vals) - 1) if vals[i] > 0]
    if not ratios:
        return None, 0.0
    avg = sum(ratios) / len(ratios)
    best, best_d = None, float("inf")
    for name, r in KNOWN_SCALES.items():
        d = abs(r - avg)
        if d < best_d:
            best, best_d = name, d
    return best, avg


def resolve_line_height(value: object, font_px: Optional[float]) -> Optional[float]:
    """Return line-height as a unitless ratio, whatever form it was written in."""
    if value is None or not font_px:
        return None
    s = str(value).strip().lower()
    if s in ("normal", "", "initial"):
        return 1.2
    try:
        if s.endswith("px"):
            return float(s[:-2]) / font_px
        if s.endswith("%"):
            return float(s[:-1]) / 100.0
        if s.endswith("rem"):
            return float(s[:-3]) * 16.0 / font_px
        if s.endswith("em"):
            return float(s[:-2])
        return float(s)
    except ValueError:
        return None


def weight_to_number(value: object) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().lower()
    named = {"thin": 100, "extralight": 200, "light": 300, "normal": 400,
             "regular": 400, "medium": 500, "semibold": 600, "bold": 700,
             "extrabold": 800, "black": 900, "heavy": 900}
    if s in named:
        return float(named[s])
    try:
        return float(s)
    except ValueError:
        return None


def measure_chars(width_px: Optional[float], font_px: Optional[float]) -> Optional[float]:
    """Approximate characters per line. Comfortable measure is 45-75."""
    if not width_px or not font_px:
        return None
    return width_px / (font_px * 0.5)
