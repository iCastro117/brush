"""
The tool surface.

Every tool here answers from the measurement index or the knowledge pack -- never
from the model's own recollection. That is the whole point: the agent's job is
judgement, and judgement needs facts it did not make up. Each call and each
result is written to the trajectory, so a reviewer can replay the exact evidence
a finding rests on.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from ..analyze import color as C
from ..analyze import geometry as G
from ..ir import DesignSystem, Measurement, StyleNode
from ..knowledge import retrieve as K
from ..memory.ledger import Ledger
from ..trace.trajectory import Trajectory


class ToolBox:
    def __init__(
        self,
        measurements: dict[str, Measurement],
        design_nodes: dict[str, StyleNode],
        code_nodes: dict[str, StyleNode],
        ds: DesignSystem,
        ledger: Ledger,
        traj: Optional[Trajectory] = None,
    ):
        self.m = measurements
        self.design = design_nodes
        self.code = code_nodes
        self.ds = ds
        self.ledger = ledger
        self.traj = traj
        self.call_count: dict[str, int] = {}

    # -- plumbing --------------------------------------------------------
    def call(self, agent: str, name: str, **kwargs) -> Any:
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            result = {"error": f"unknown tool '{name}'"}
        else:
            t0 = time.time()
            try:
                result = fn(**kwargs)
            except Exception as exc:  # tools must never crash the run
                result = {"error": f"{type(exc).__name__}: {exc}"}
            dt = (time.time() - t0) * 1000
        self.call_count[name] = self.call_count.get(name, 0) + 1
        if self.traj:
            cid = self.traj.record(agent, "tool_call", f"{name}({_short(kwargs)})",
                                   {"tool": name, "args": kwargs})
            preview = json.dumps(result, default=str)
            self.traj.record(agent, "tool_result",
                             f"{name} → {preview[:120]}{'…' if len(preview) > 120 else ''}",
                             {"tool": name, "result": result}, parent=cid,
                             duration_ms=round(dt, 2) if fn else None)
        return result

    # -- tools -----------------------------------------------------------
    def t_get_measurement(self, measurement_id: str) -> dict:
        m = self.m.get(measurement_id)
        if m is None:
            return {"error": "no such measurement", "measurement_id": measurement_id}
        return m.to_dict()

    def t_list_measurements(self, node_key: str, channel: Optional[str] = None,
                            only_out_of_tolerance: bool = True) -> dict:
        out = []
        for m in self.m.values():
            if m.node_key != node_key:
                continue
            if channel and m.channel != channel:
                continue
            if only_out_of_tolerance and m.within_tolerance:
                continue
            out.append({"measurement_id": m.measurement_id, "prop": m.prop,
                        "design": m.design_value, "code": m.code_value,
                        "delta": m.delta, "unit": m.delta_unit})
        return {"node_key": node_key, "count": len(out), "measurements": out}

    def t_list_nodes(self, side: str = "code") -> dict:
        src = self.code if side == "code" else self.design
        return {"side": side, "nodes": [
            {"key": k, "role": n.role, "selector": n.selector, "text": n.text_sample[:40]}
            for k, n in sorted(src.items())
        ]}

    def t_contrast(self, foreground: str, background: str,
                   font_px: float = 16.0, weight: float = 400.0) -> dict:
        fg, bg = C.parse_color(foreground), C.parse_color(background)
        if fg is None or bg is None:
            return {"error": "unparseable colour", "foreground": foreground,
                    "background": background}
        ratio = C.contrast_ratio(fg, bg)
        return {"ratio": round(ratio, 2),
                "level": C.wcag_level(ratio, font_px, weight),
                "aa_threshold": 3.0 if (font_px >= 24 or (font_px >= 18.66 and weight >= 700)) else 4.5,
                "method": "WCAG 2.1 relative luminance"}

    def t_delta_e(self, a: str, b: str) -> dict:
        ca, cb = C.parse_color(a), C.parse_color(b)
        if ca is None or cb is None:
            return {"error": "unparseable colour"}
        d = C.delta_e2000(ca, cb)
        return {"delta_e2000": round(d, 3), "a": ca.hex(), "b": cb.hex(),
                "jnd": K.thresholds()["delta_e_jnd"]["value"],
                "reading": ("imperceptible" if d < 1 else
                            "subtle" if d < 3 else
                            "obvious" if d < 5 else "different colour")}

    def t_nearest_color_token(self, value: str) -> dict:
        name, dist = C.nearest_token(value, self.ds.color)
        return {"value": value, "nearest_token": name,
                "token_value": self.ds.color.get(name) if name else None,
                "delta_e2000": round(dist, 3) if dist != float("inf") else None,
                "is_exact": dist < 0.5}

    def t_nearest_space_token(self, value: float) -> dict:
        name, dist = G.nearest_space_token(float(value), self.ds.space)
        return {"value": value, "nearest_token": name,
                "token_value": self.ds.space.get(name) if name else None,
                "delta_px": round(dist, 2) if dist != float("inf") else None}

    def t_grid_check(self, value: float) -> dict:
        v = float(value)
        return {"value": v, "grid_base": self.ds.grid_base,
                "on_grid": G.on_grid(v, self.ds.grid_base),
                "nearest_on_grid": G.nearest_grid(v, self.ds.grid_base)}

    def t_target_size(self, node_key: str) -> dict:
        n = self.code.get(node_key)
        if n is None:
            return {"error": "no such node"}
        h = n.props.get("min-height") or n.props.get("height")
        w = n.props.get("min-width") or n.props.get("width")
        return {"node_key": node_key, "height": h, "width": w,
                "wcag_min_px": 24, "comfortable_px": 44,
                "meets_wcag": h is None or float(h) >= 24,
                "comfortable": G.touch_target_ok(
                    float(w) if w else None, float(h) if h else None)}

    def t_lookup_principle(self, principle_id: str) -> dict:
        p = K.pack()
        for bucket in ("laws", "heuristics", "wcag"):
            if principle_id in p[bucket]:
                return {"id": principle_id, "bucket": bucket, **p[bucket][principle_id]}
        return {"error": "unknown principle id — only ids in the knowledge pack may be cited",
                "id": principle_id}

    def t_check_ledger(self, node_key: str, prop: str) -> dict:
        entry = self.ledger.lookup(node_key, prop)
        if entry is None:
            return {"approved_deviation": False}
        return {"approved_deviation": True, **entry}

    def t_proximity_check(self, inner_node: str, outer_node: str) -> dict:
        a, b = self.code.get(inner_node), self.code.get(outer_node)
        if a is None or b is None:
            return {"error": "node not found"}
        inner = a.props.get("margin-bottom") or a.props.get("padding-bottom")
        outer = b.props.get("margin-bottom") or b.props.get("padding-bottom")
        ratio = G.proximity_ratio(
            float(inner) if inner else None, float(outer) if outer else None)
        return {"inner_px": inner, "outer_px": outer,
                "ratio": round(ratio, 2) if ratio else None,
                "grouping_stable": ratio is not None and ratio >= 1.5,
                "law": "lux-proximity"}


def _short(kwargs: dict) -> str:
    bits = []
    for k, v in list(kwargs.items())[:3]:
        s = str(v)
        bits.append(f"{k}={s[:28]}{'…' if len(s) > 28 else ''}")
    return ", ".join(bits)


TOOL_SPECS = [
    {"name": "get_measurement", "args": ["measurement_id"],
     "desc": "Fetch one measurement by id. Returns design value, code value, delta, unit and the method used."},
    {"name": "list_measurements", "args": ["node_key", "channel?", "only_out_of_tolerance?"],
     "desc": "All measurements for a component, optionally filtered to one channel."},
    {"name": "list_nodes", "args": ["side"],
     "desc": "List design or code nodes with role, selector and sample text."},
    {"name": "contrast", "args": ["foreground", "background", "font_px?", "weight?"],
     "desc": "WCAG 2.1 contrast ratio and the level it meets for that text size."},
    {"name": "delta_e", "args": ["a", "b"],
     "desc": "CIEDE2000 perceptual distance between two colours."},
    {"name": "nearest_color_token", "args": ["value"],
     "desc": "Closest design-system colour token and its distance."},
    {"name": "nearest_space_token", "args": ["value"],
     "desc": "Closest spacing token in px."},
    {"name": "grid_check", "args": ["value"],
     "desc": "Whether a length lands on the base grid, and the nearest value that does."},
    {"name": "target_size", "args": ["node_key"],
     "desc": "Interactive target dimensions against WCAG 2.5.8 and the 44px comfort bar."},
    {"name": "lookup_principle", "args": ["principle_id"],
     "desc": "Read a UX law, Nielsen heuristic or WCAG criterion from the knowledge pack."},
    {"name": "check_ledger", "args": ["node_key", "prop"],
     "desc": "Whether a human has already approved this deviation as intentional."},
    {"name": "proximity_check", "args": ["inner_node", "outer_node"],
     "desc": "Gestalt grouping ratio between an inner and an outer spacing."},
]
