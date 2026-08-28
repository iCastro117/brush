"""Length normalisation. Everything becomes float pixels or None."""
from __future__ import annotations

import re
from typing import Optional

_LEN_RE = re.compile(r"^(-?\d*\.?\d+)\s*(px|rem|em|pt|%|vh|vw|ch)?$", re.I)
KEYWORD_LENGTHS = {"none": 0.0, "0": 0.0, "auto": None, "normal": None, "initial": None}


def to_px(
    value: object,
    root_font_size: float = 16.0,
    parent_font_size: Optional[float] = None,
    percent_basis: Optional[float] = None,
) -> Optional[float]:
    """
    Convert a CSS length to pixels.

    `em` resolves against `parent_font_size` (the element's own font-size for
    non-font properties, per CSS spec, which the caller supplies).
    Percentages only resolve when a basis is given; otherwise we return None
    rather than guessing, because a wrong number is worse than no number.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    if not s:
        return None
    if s in KEYWORD_LENGTHS:
        return KEYWORD_LENGTHS[s]
    m = _LEN_RE.match(s)
    if not m:
        return None
    num = float(m.group(1))
    unit = (m.group(2) or "px").lower()
    if unit == "px":
        return num
    if unit == "pt":
        return num * 96.0 / 72.0
    if unit == "rem":
        return num * root_font_size
    if unit == "em":
        base = parent_font_size if parent_font_size is not None else root_font_size
        return num * base
    if unit == "ch":
        base = parent_font_size if parent_font_size is not None else root_font_size
        return num * base * 0.5  # approximation, flagged in method string
    if unit == "%":
        return None if percent_basis is None else num / 100.0 * percent_basis
    return None


def fmt_px(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.0f}px" if abs(v - round(v)) < 1e-6 else f"{v:.2f}px"
