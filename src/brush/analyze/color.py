"""
Colour maths.

Why not just compare hex strings? Because `#1F6FEB` vs `#2070EC` are different
strings and the same colour to a human eye, while `#767676` vs `#8A8A8A` are
"close" strings and the difference between passing and failing WCAG AA on white.
String equality is the wrong instrument. We compare in CIELAB with CIEDE2000,
which is built to track *perceived* difference, and we score legibility with the
WCAG 2.1 relative-luminance contrast ratio.

Everything here is stdlib-only and deterministic.
"""
from __future__ import annotations

import math
import re
from typing import Optional

# Subset of CSS named colours that actually turn up in design systems.
NAMED = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000",
    "blue": "#0000ff", "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0",
    "transparent": "#00000000", "currentcolor": None, "inherit": None,
    "orange": "#ffa500", "yellow": "#ffff00", "purple": "#800080",
    "navy": "#000080", "teal": "#008080", "lime": "#00ff00", "maroon": "#800000",
}

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3,8})$")
_FUNC_RE = re.compile(r"^(rgba?|hsla?)\s*\(([^)]*)\)$", re.I)


class Color:
    """An sRGB colour with straight (non-premultiplied) alpha."""

    __slots__ = ("r", "g", "b", "a", "raw")

    def __init__(self, r: float, g: float, b: float, a: float = 1.0, raw: str = ""):
        self.r, self.g, self.b, self.a = r, g, b, a
        self.raw = raw

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Color({self.hex()}, a={self.a:.2f})"

    def hex(self) -> str:
        return "#{:02x}{:02x}{:02x}".format(
            int(round(self.r * 255)), int(round(self.g * 255)), int(round(self.b * 255))
        )

    def over(self, backdrop: "Color") -> "Color":
        """Composite self over an opaque backdrop (source-over)."""
        if self.a >= 1.0:
            return Color(self.r, self.g, self.b, 1.0, self.raw)
        a = self.a
        return Color(
            self.r * a + backdrop.r * (1 - a),
            self.g * a + backdrop.g * (1 - a),
            self.b * a + backdrop.b * (1 - a),
            1.0,
            self.raw,
        )


def parse_color(value: object) -> Optional[Color]:
    """Parse hex / rgb() / rgba() / hsl() / named. Returns None if unparseable."""
    if value is None:
        return None
    if isinstance(value, Color):
        return value
    s = str(value).strip().lower()
    if not s:
        return None
    if s in NAMED:
        mapped = NAMED[s]
        if mapped is None:
            return None
        s = mapped

    m = _HEX_RE.match(s)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        elif len(h) == 4:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            return Color(int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, 1.0, s)
        if len(h) == 8:
            return Color(
                int(h[0:2], 16) / 255, int(h[2:4], 16) / 255,
                int(h[4:6], 16) / 255, int(h[6:8], 16) / 255, s,
            )
        return None

    m = _FUNC_RE.match(s)
    if m:
        fn = m.group(1).lower()
        parts = [p.strip() for p in re.split(r"[,\s/]+", m.group(2)) if p.strip()]
        try:
            if fn.startswith("rgb"):
                vals = []
                for p in parts[:3]:
                    vals.append(float(p[:-1]) / 100 if p.endswith("%") else float(p) / 255)
                alpha = 1.0
                if len(parts) > 3:
                    ap = parts[3]
                    alpha = float(ap[:-1]) / 100 if ap.endswith("%") else float(ap)
                return Color(*vals, alpha, s)
            # hsl
            h = float(parts[0].replace("deg", "")) % 360 / 360.0
            sat = float(parts[1].rstrip("%")) / 100
            lig = float(parts[2].rstrip("%")) / 100
            alpha = 1.0
            if len(parts) > 3:
                ap = parts[3]
                alpha = float(ap[:-1]) / 100 if ap.endswith("%") else float(ap)
            r, g, b = _hsl_to_rgb(h, sat, lig)
            return Color(r, g, b, alpha, s)
        except (ValueError, TypeError, IndexError):
            return None
    return None


def _hsl_to_rgb(h: float, s: float, ll: float) -> tuple[float, float, float]:
    if s == 0:
        return ll, ll, ll

    def hue2rgb(p, q, t):
        t = t % 1.0
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = ll * (1 + s) if ll < 0.5 else ll + s - ll * s
    p = 2 * ll - q
    return hue2rgb(p, q, h + 1 / 3), hue2rgb(p, q, h), hue2rgb(p, q, h - 1 / 3)


# --------------------------------------------------------------------------
# CIELAB + CIEDE2000
# --------------------------------------------------------------------------
def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def to_xyz(c: Color) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(c.r), _srgb_to_linear(c.g), _srgb_to_linear(c.b))
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    return x, y, z


def to_lab(c: Color) -> tuple[float, float, float]:
    x, y, z = to_xyz(c)
    # D65 reference white
    xn, yn, zn = 0.95047, 1.0, 1.08883
    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t) + (16 / 116)
    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e2000(c1: Color, c2: Color) -> float:
    """CIEDE2000. ~1.0 is the just-noticeable difference for a trained eye."""
    l1, a1, b1 = to_lab(c1)
    l2, a2, b2 = to_lab(c2)
    avg_l = (l1 + l2) / 2
    c1_ = math.hypot(a1, b1)
    c2_ = math.hypot(a2, b2)
    avg_c = (c1_ + c2_) / 2
    g = 0.5 * (1 - math.sqrt(avg_c ** 7 / (avg_c ** 7 + 25 ** 7))) if avg_c > 0 else 0.0
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    avg_cp = (c1p + c2p) / 2
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0.0

    dlp = l2 - l1
    dcp = c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2)

    if c1p * c2p == 0:
        avg_hp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        avg_hp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        avg_hp = (h1p + h2p + 360) / 2
    else:
        avg_hp = (h1p + h2p - 360) / 2

    t = (1 - 0.17 * math.cos(math.radians(avg_hp - 30))
         + 0.24 * math.cos(math.radians(2 * avg_hp))
         + 0.32 * math.cos(math.radians(3 * avg_hp + 6))
         - 0.20 * math.cos(math.radians(4 * avg_hp - 63)))
    d_theta = 30 * math.exp(-(((avg_hp - 275) / 25) ** 2))
    rc = 2 * math.sqrt(avg_cp ** 7 / (avg_cp ** 7 + 25 ** 7)) if avg_cp > 0 else 0.0
    sl = 1 + (0.015 * (avg_l - 50) ** 2) / math.sqrt(20 + (avg_l - 50) ** 2)
    sc = 1 + 0.045 * avg_cp
    sh = 1 + 0.015 * avg_cp * t
    rt = -math.sin(math.radians(2 * d_theta)) * rc
    return math.sqrt(
        (dlp / sl) ** 2 + (dcp / sc) ** 2 + (dHp / sh) ** 2
        + rt * (dcp / sc) * (dHp / sh)
    )


# --------------------------------------------------------------------------
# WCAG 2.1 contrast
# --------------------------------------------------------------------------
def relative_luminance(c: Color) -> float:
    r, g, b = (_srgb_to_linear(c.r), _srgb_to_linear(c.g), _srgb_to_linear(c.b))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: Color, bg: Color) -> float:
    fg_solid = fg.over(bg)
    l1, l2 = relative_luminance(fg_solid), relative_luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def wcag_level(ratio: float, font_px: float, weight: float) -> str:
    """Return the highest WCAG level this pairing satisfies for its text size."""
    large = font_px >= 24 or (font_px >= 18.66 and weight >= 700)
    if large:
        if ratio >= 4.5:
            return "AAA"
        return "AA" if ratio >= 3.0 else "fail"
    if ratio >= 7.0:
        return "AAA"
    return "AA" if ratio >= 4.5 else "fail"


def nearest_token(value: str, tokens: dict[str, str]) -> tuple[Optional[str], float]:
    """Closest named colour token to `value`, with its CIEDE2000 distance."""
    c = parse_color(value)
    if c is None or not tokens:
        return None, float("inf")
    best, best_d = None, float("inf")
    for name, hexv in tokens.items():
        tc = parse_color(hexv)
        if tc is None:
            continue
        d = delta_e2000(c, tc)
        if d < best_d:
            best, best_d = name, d
    return best, best_d
