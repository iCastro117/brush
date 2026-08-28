"""
The reporter.

The audit is worthless if the output is a wall of 40 equally-weighted rows. A
reviewer has a budget, and the job of this agent is to spend it well: group the
verified findings by root cause, put the accessibility blockers where they will
be read first, and say plainly which single token change clears the longest tail
of findings.

That last part is the Pareto move and it is usually the whole story -- most
drift in a design system is one wrong value repeated, not forty independent
mistakes.
"""
from __future__ import annotations

import json
from collections import defaultdict

from ..ir import Finding
from ..trace.trajectory import Trajectory
from .provider import Provider

SYSTEM = """You write the summary of a design-system conformance audit for the engineer who has to fix it.

You are given verified findings. Every number in them has already been checked; do not restate numbers you were not given and do not soften or dramatise them.

Produce:
- `headline`: one sentence stating what is wrong with this implementation, most consequential thing first.
- `root_causes`: groups of findings that share one cause, each with the single change that clears the group.
- `first_three_fixes`: the three changes with the best consequence-to-effort ratio, in order.
- `what_is_fine`: one short sentence acknowledging what conforms, so the reader can trust the rest.

Write like an engineer briefing a colleague. No filler, no "it's worth noting", no restating the brief. Sentence case. Reply with ONLY a JSON object, no prose and no code fences.
"""

SEV_RANK = {"blocker": 0, "major": 1, "minor": 2, "info": 3}


def summarise(findings: list[Finding], provider: Provider, traj: Trajectory,
              component_count: int, clean_count: int) -> tuple[dict, dict]:
    agent = "reporter"
    traj.record(agent, "instruction",
                f"Summarise {len(findings)} verified finding(s) across {component_count} components",
                {"by_severity": _by_severity(findings)})

    payload = {
        "task": "report",
        "component_count": component_count,
        "conforming_components": clean_count,
        "by_severity": _by_severity(findings),
        "findings": [{
            "id": f.finding_id, "component": f.node_key, "prop": f.prop,
            "severity": f.severity, "channel": f.channel, "title": f.title,
            "design": f.design_value, "code": f.code_value,
            "delta": f.delta, "unit": f.delta_unit,
            "principles": f.ux_laws, "fix": f.suggested_fix,
        } for f in sorted(findings, key=lambda x: SEV_RANK.get(x.severity, 9))],
        "token_clusters": token_clusters(findings),
    }
    comp = provider.complete(SYSTEM, json.dumps(payload), max_tokens=1800)
    usage = {"input_tokens": comp.input_tokens, "output_tokens": comp.output_tokens,
             "cost_usd": comp.cost_usd, "calls": 1, "latency_ms": comp.latency_ms}

    text = comp.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        traj.record(agent, "error", "reporter reply was not valid JSON; using deterministic summary", {})
        out = offline_report(payload)
    traj.record(agent, "decision", "summary written",
                {"headline": out.get("headline", "")[:160],
                 "root_cause_groups": len(out.get("root_causes", []))})
    return out, usage


def _by_severity(findings: list[Finding]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for f in findings:
        out[f.severity] += 1
    return dict(out)


def token_clusters(findings: list[Finding]) -> list[dict]:
    """Findings that share a channel and a design value: one token fix clears them all."""
    groups: dict[tuple, list[Finding]] = defaultdict(list)
    for f in findings:
        groups[(f.channel, str(f.design_value), f.prop.split("-")[0])].append(f)
    out = []
    for (channel, design_value, family), fs in groups.items():
        if len(fs) < 2:
            continue
        out.append({
            "channel": channel, "expected_value": design_value, "property_family": family,
            "finding_ids": [f.finding_id for f in fs],
            "components": sorted({f.node_key.split("@")[0] for f in fs}),
            "count": len(fs),
        })
    out.sort(key=lambda g: -g["count"])
    return out


def offline_report(payload: dict) -> dict:
    """Deterministic summary. Same structure, no model."""
    fs = payload["findings"]
    blockers = [f for f in fs if f["severity"] == "blocker"]
    majors = [f for f in fs if f["severity"] == "major"]

    if blockers:
        headline = (f"{len(blockers)} accessibility blocker(s) and {len(majors)} visible "
                    f"deviation(s): {blockers[0]['title']}.")
    elif majors:
        headline = (f"{len(majors)} visible deviation(s) from the spec, led by "
                    f"{majors[0]['title']}.")
    elif fs:
        headline = f"{len(fs)} minor deviation(s); nothing a user would notice in isolation."
    else:
        headline = "Implementation matches the specification on every measured property."

    roots = []
    for cl in payload.get("token_clusters", [])[:5]:
        roots.append({
            "cause": f"{cl['property_family']} ({cl['channel']}) drifted from {cl['expected_value']} "
                     f"in {len(cl['components'])} component(s)",
            "finding_ids": cl["finding_ids"],
            "single_change": f"Restore the token value {cl['expected_value']} at the token layer "
                             f"rather than patching {cl['count']} call sites.",
        })
    for f in blockers:
        roots.append({"cause": f["title"], "finding_ids": [f["id"]],
                      "single_change": f["fix"]})

    ordered = blockers + majors
    return {
        "headline": headline,
        "root_causes": roots[:6],
        "first_three_fixes": [
            {"finding_id": f["id"], "change": f["fix"], "why": f"{f['severity']} — {f['title']}"}
            for f in ordered[:3]
        ],
        "what_is_fine": (f"{payload['conforming_components']} of {payload['component_count']} "
                         f"components match the spec on every measured property."),
        "_generated_by": "deterministic offline summariser",
    }
