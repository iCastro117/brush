"""
Intermediate Representation (IR).

Both sides of the audit -- the design source of truth and the implemented
frontend -- are normalised into the same shape before anything is compared.
Every downstream claim in Brush must point at a `Measurement` in this
module. If a claim cannot cite one, the verifier drops it.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# Properties we normalise and compare. Grouped by the perceptual channel they
# act on, because severity rules differ per channel.
GEOMETRY_PROPS = (
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "gap", "row-gap", "column-gap",
    "width", "height", "min-height", "min-width",
    "border-radius", "border-width",
)
COLOR_PROPS = ("color", "background-color", "border-color", "outline-color")
TYPO_PROPS = (
    "font-family", "font-size", "font-weight",
    "line-height", "letter-spacing", "text-transform",
)
EFFECT_PROPS = ("box-shadow", "opacity", "outline-width", "outline-style")

ALL_PROPS = GEOMETRY_PROPS + COLOR_PROPS + TYPO_PROPS + EFFECT_PROPS

CHANNEL_OF: dict[str, str] = {}
for _p in GEOMETRY_PROPS:
    CHANNEL_OF[_p] = "geometry"
for _p in COLOR_PROPS:
    CHANNEL_OF[_p] = "color"
for _p in TYPO_PROPS:
    CHANNEL_OF[_p] = "typography"
for _p in EFFECT_PROPS:
    CHANNEL_OF[_p] = "effect"


@dataclass
class StyleNode:
    """One component (or component state) with fully resolved styles."""

    node_id: str                      # stable id, e.g. "Button/Primary"
    role: str = "generic"             # button, input, card, heading, body...
    state: str = "default"            # default | hover | focus | disabled
    props: dict[str, Any] = field(default_factory=dict)
    source: str = ""                  # file the node came from
    selector: str = ""                # css selector or design path
    text_sample: str = ""             # visible text, used for contrast checks
    parent_background: Optional[str] = None

    def key(self) -> str:
        return f"{self.node_id}@{self.state}"


@dataclass
class DesignSystem:
    """Token dictionaries lifted from the design source."""

    color: dict[str, str] = field(default_factory=dict)
    space: dict[str, float] = field(default_factory=dict)
    font_size: dict[str, float] = field(default_factory=dict)
    font_weight: dict[str, float] = field(default_factory=dict)
    radius: dict[str, float] = field(default_factory=dict)
    grid_base: float = 4.0
    root_font_size: float = 16.0
    groups: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Measurement:
    """
    A single reproducible fact -- the atom of evidence.
    `method` records HOW the number was obtained so a reader can re-derive it.
    """

    node_key: str
    prop: str
    channel: str
    design_value: Any
    code_value: Any
    delta: Optional[float] = None      # numeric distance; unit depends on channel
    delta_unit: str = ""               # px | deltaE | ratio | steps | bool
    within_tolerance: bool = True
    method: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def measurement_id(self) -> str:
        return f"{self.node_key}::{self.prop}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["measurement_id"] = self.measurement_id
        return d


@dataclass
class Finding:
    """
    An adjudicated discrepancy. Proposed by the diagnostician, then checked by
    the verifier. `evidence` MUST contain valid measurement ids.
    """

    finding_id: str
    node_key: str
    prop: str
    channel: str
    title: str
    severity: str                      # blocker | major | minor | info
    design_value: Any = None
    code_value: Any = None
    delta: Optional[float] = None
    delta_unit: str = ""
    ux_laws: list[str] = field(default_factory=list)
    rationale: str = ""
    suggested_fix: str = ""
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    verified: bool = False
    verifier_note: str = ""
    suppressed_by: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AuditResult:
    component: str
    findings: list[Finding] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "findings": [f.to_dict() for f in self.findings],
            "measurements": [m.to_dict() for m in self.measurements],
            "stats": self.stats,
        }
