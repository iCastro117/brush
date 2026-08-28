"""
The diagnostician.

Given measurements that are already known to be numerically out of tolerance,
this agent decides the three things a number cannot decide on its own:

  1. Is this a defect, or an intentional deviation the spec did not capture?
  2. Which principle does it violate, and therefore how much does it cost?
  3. What is the smallest correct fix -- and is that fix at the token layer?

It is deliberately not allowed to do arithmetic from memory. Anything numeric it
wants to assert, it must fetch through a tool, and every finding must cite the
measurement ids it rests on. The verifier enforces both.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ..ir import Measurement, StyleNode
from ..knowledge import retrieve as K
from ..trace.trajectory import Trajectory
from .provider import Provider
from .tools import TOOL_SPECS, ToolBox

SYSTEM = """You are a senior design-systems engineer auditing an implementation against its specification.

You receive measurements that have ALREADY been computed by a deterministic engine. You must not recompute or estimate any number yourself. If you need a fact, call a tool.

Your job is judgement, not arithmetic:
- decide whether each out-of-tolerance measurement is a real defect
- assign exactly one severity band and name the clause you matched
- cite the principles that make it matter, using ONLY ids present in the supplied knowledge slice
- state the smallest correct fix, preferring a design-token change over a per-component override

Rules you must follow:
- Every finding MUST list the measurement ids it rests on in `evidence`. A finding with no evidence is discarded.
- Never invent a principle id. Ids not in the knowledge pack are rejected.
- Never report a property twice for the same component.
- If an approved deviation covers a measurement, do not report it.
- Write `rationale` for a working engineer: what a user experiences, not a restatement of the numbers.

Reply with ONLY a JSON object, no prose and no code fences. Two shapes are valid:
{"tool_calls": [{"name": "...", "args": {...}}]}   -- to gather more facts first
{"findings": [{...}]}                               -- your final answer for this component

Finding shape:
{"prop": str, "severity": "blocker|major|minor|info", "clause_id": str,
 "title": str, "rationale": str, "suggested_fix": str,
 "principles": [str], "evidence": [str], "confidence": 0.0-1.0}
"""


def build_task(node: StyleNode, measurements: list[Measurement],
               ledger_hits: dict[str, dict], round_no: int,
               tool_results: Optional[list[dict]] = None,
               verifier_feedback: Optional[list[str]] = None) -> dict:
    items = []
    for m in measurements:
        ctx = K.context_for(m, node)
        items.append({
            "measurement_id": m.measurement_id,
            "prop": m.prop,
            "channel": m.channel,
            "design_value": m.design_value,
            "code_value": m.code_value,
            "delta": m.delta,
            "unit": m.delta_unit,
            "method": m.method,
            "detail": m.extra,
            "knowledge": ctx,
        })
    task: dict[str, Any] = {
        "task": "diagnose",
        "round": round_no,
        "component": {
            "node_key": node.key(), "id": node.node_id, "role": node.role,
            "state": node.state, "selector": node.selector,
            "text_sample": node.text_sample,
            "backdrop": node.parent_background,
        },
        "measurements": items,
        "approved_deviations": ledger_hits,
        "available_tools": TOOL_SPECS,
    }
    if tool_results:
        task["tool_results"] = tool_results
    if verifier_feedback:
        task["verifier_feedback"] = verifier_feedback
    return task


def _parse(text: str) -> dict:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(t[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {"findings": [], "_parse_error": True, "_raw": t[:400]}


def diagnose_component(
    node: StyleNode,
    measurements: list[Measurement],
    provider: Provider,
    tools: ToolBox,
    traj: Trajectory,
    max_rounds: int = 3,
    verifier_feedback: Optional[list[str]] = None,
) -> tuple[list[dict], dict]:
    """Run the tool loop for one component. Returns (raw findings, usage)."""
    agent = "diagnostician"
    ledger_hits = {}
    for m in measurements:
        hit = tools.ledger.lookup(node.key(), m.prop)
        if hit:
            ledger_hits[m.prop] = hit

    traj.record(agent, "instruction",
                f"Adjudicate {len(measurements)} out-of-tolerance measurement(s) on {node.key()}",
                {"node_key": node.key(), "role": node.role,
                 "props": [m.prop for m in measurements],
                 "approved_deviations": list(ledger_hits)})

    tool_results: list[dict] = []
    usage = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0,
             "latency_ms": 0.0}

    for rnd in range(1, max_rounds + 1):
        task = build_task(node, measurements, ledger_hits, rnd,
                          tool_results or None, verifier_feedback)
        comp = provider.complete(SYSTEM, json.dumps(task), max_tokens=2000)
        usage["input_tokens"] += comp.input_tokens
        usage["output_tokens"] += comp.output_tokens
        usage["cost_usd"] += comp.cost_usd
        usage["latency_ms"] += comp.latency_ms
        usage["calls"] += 1

        parsed = _parse(comp.text)

        if parsed.get("_parse_error"):
            traj.record(agent, "error", "model reply was not valid JSON; retrying",
                        {"raw_preview": parsed.get("_raw", "")[:200]})
            verifier_feedback = ["Your previous reply was not valid JSON. "
                                 "Reply with a single JSON object and nothing else."]
            continue

        calls = parsed.get("tool_calls") or []
        if calls:
            traj.record(agent, "thought",
                        f"round {rnd}: needs {len(calls)} more fact(s) before deciding",
                        {"requested": [c.get("name") for c in calls]})
            for c in calls[:8]:
                name = c.get("name", "")
                args = c.get("args", {}) or {}
                res = tools.call(agent, name, **args)
                tool_results.append({"name": name, "args": args, "result": res})
            continue

        findings = parsed.get("findings", [])
        traj.record(agent, "decision",
                    f"round {rnd}: proposed {len(findings)} finding(s) for {node.key()}",
                    {"props": [f.get("prop") for f in findings],
                     "severities": [f.get("severity") for f in findings]})
        return findings, usage

    traj.record(agent, "error",
                f"exhausted {max_rounds} rounds on {node.key()} without a final answer", {})
    return [], usage


# ---------------------------------------------------------------------------
# Offline policy
# ---------------------------------------------------------------------------
FIX_TEMPLATES = {
    "geometry": "Set `{prop}` to {design} (token `{token}`) instead of {code}.",
    "color": "Replace the literal {code} with the `{token}` token ({design}).",
    "typography": "Restore `{prop}` to {design} from the type scale.",
    "effect": "Restore `{prop}` to {design} as specified.",
}


def offline_diagnose(payload: dict) -> dict:
    """
    Deterministic stand-in for the diagnostician. Not a language model.

    It applies the published severity policy directly and asks one tool question
    per colour finding, so the tool loop, the evidence trail and the trajectory
    are exercised exactly as they are in a live run.
    """
    node_key = payload["component"]["node_key"]
    approved = payload.get("approved_deviations", {})
    already_asked = {tr["name"] + str(tr["args"]) for tr in payload.get("tool_results", [])}

    # Round 1: corroborate anything whose severity depends on a threshold the
    # measurement alone does not carry -- contrast levels, target minimums and
    # grid conformance. This is the same discipline the live agent is held to:
    # do not assert a threshold you have not looked up.
    if not payload.get("tool_results"):
        wanted = []
        for item in payload["measurements"]:
            detail = item.get("detail") or {}
            if item["prop"] == "color" and "contrast_ratio" in detail:
                wanted.append({"name": "contrast", "args": {
                    "foreground": str(item["code_value"]),
                    "background": str(detail.get("contrast_backdrop", "#ffffff")),
                }})
            elif item["prop"] in ("border-color", "outline-color"):
                wanted.append({"name": "nearest_color_token",
                               "args": {"value": str(item["code_value"])}})
            elif item["prop"] == "-derived-target-height":
                wanted.append({"name": "target_size", "args": {"node_key": node_key}})
            elif item["channel"] == "geometry" and isinstance(item["code_value"], (int, float)):
                wanted.append({"name": "grid_check", "args": {"value": item["code_value"]}})
        deduped = []
        for w in wanted:
            sig = w["name"] + str(w["args"])
            if sig not in already_asked and sig not in {d["name"] + str(d["args"]) for d in deduped}:
                deduped.append(w)
        if deduped:
            return {"tool_calls": deduped[:8]}

    findings = []
    seen: set[str] = set()

    for item in payload["measurements"]:
        prop = item["prop"]
        if prop in seen or prop in approved:
            continue
        k = item["knowledge"]
        clause_id = k.get("candidate_clause")
        if not clause_id:
            continue
        seen.add(prop)
        principles = [pid for pid in k.get("applicable_principles", {})]
        detail = item.get("detail") or {}
        token = detail.get("nearest_token") or detail.get("nearest_space_token") or "—"
        tmpl = FIX_TEMPLATES.get(item["channel"], "Restore `{prop}` to {design}.")
        fix = tmpl.format(prop=prop, design=item["design_value"],
                          code=item["code_value"], token=token)
        findings.append({
            "prop": prop,
            "severity": k["deterministic_severity"],
            "clause_id": clause_id,
            "title": _title(node_key, prop, item),
            "rationale": k["deterministic_reason"],
            "suggested_fix": fix,
            "principles": principles,
            "evidence": [item["measurement_id"]],
            "confidence": 0.9,
        })
    return {"findings": findings}


def _title(node_key: str, prop: str, item: dict) -> str:
    comp = node_key.split("@")[0]
    unit = item.get("unit")
    d = item.get("delta")
    if prop.startswith("-derived-"):
        pretty = prop.replace("-derived-", "").replace("-", " ")
        return f"{comp}: {pretty} off spec"
    if unit == "px" and isinstance(d, (int, float)):
        return f"{comp}: {prop} is {d:+.0f}px off spec"
    if unit == "deltaE" and isinstance(d, (int, float)):
        return f"{comp}: {prop} drifts {d:.1f} ΔE from the token"
    if unit == "ratio" and isinstance(d, (int, float)):
        return f"{comp}: {prop} is {d * 100:+.0f}% off spec"
    if unit == "weight" and isinstance(d, (int, float)):
        return f"{comp}: {prop} differs by {d:+.0f}"
    return f"{comp}: {prop} does not match spec"
