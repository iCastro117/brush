"""
Spacing and box-model analysis.

The design-system question is never "are these two numbers equal?" but
"is this difference something a user's visual system will register, and does
it break the grouping the layout depends on?" Two rules encode that:

  * grid conformance -- a spacing value off the 4/8pt base is a smell even when
    it is close to the spec, because it breaks the rhythm every other component
    is tuned to (Law of Uniform Connectedness).
  * proximity ratio -- when inner padding approaches outer margin, the visual
    grouping collapses (Law of Proximity). A 2px error matters far more here
    than the same 2px on an isolated edge.
"""
from __future__ import annotations

from typing import Optional

# Below this, a spacing difference is not reliably perceivable on a standard
# display at normal viewing distance. Sourced from the 1px rendering floor plus
# a margin for sub-pixel rounding across engines.
PERCEPTUAL_FLOOR_PX = 1.0


def on_grid(value: Optional[float], base: float = 4.0, tol: float = 0.01) -> bool:
    if value is None:
        return True
    if base <= 0:
        return True
    r = value / base
    return abs(r - round(r)) < tol


def grid_steps_off(value: Optional[float], base: float = 4.0) -> float:
    if value is None or base <= 0:
        return 0.0
    r = value / base
    return abs(r - round(r))


def nearest_grid(value: Optional[float], base: float = 4.0) -> Optional[float]:
    if value is None:
        return None
    return round(value / base) * base


def nearest_space_token(
    value: Optional[float], tokens: dict[str, float]
) -> tuple[Optional[str], float]:
    if value is None or not tokens:
        return None, float("inf")
    best, best_d = None, float("inf")
    for name, tv in tokens.items():
        d = abs(float(tv) - value)
        if d < best_d:
            best, best_d = name, d
    return best, best_d


def proximity_ratio(inner: Optional[float], outer: Optional[float]) -> Optional[float]:
    """
    outer / inner. Gestalt grouping is stable above ~1.5; below ~1.0 the element
    reads as belonging to its neighbour rather than to its own container.
    """
    if not inner or not outer or inner <= 0:
        return None
    return outer / inner


def touch_target_ok(width: Optional[float], height: Optional[float]) -> Optional[bool]:
    """WCAG 2.2 target size (minimum) is 24x24 CSS px; 44x44 is the comfort bar."""
    if width is None and height is None:
        return None
    w = width if width is not None else 999.0
    h = height if height is not None else 999.0
    return w >= 44.0 and h >= 44.0


def symmetry_break(props: dict, axis: str = "x") -> Optional[float]:
    """Absolute px difference between opposing paddings on one axis."""
    pair = ("padding-left", "padding-right") if axis == "x" else ("padding-top", "padding-bottom")
    a, b = props.get(pair[0]), props.get(pair[1])
    if a is None or b is None:
        return None
    try:
        return abs(float(a) - float(b))
    except (TypeError, ValueError):
        return None
