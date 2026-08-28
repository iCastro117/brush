"""
The mapper.

Before anything can be compared, each design component has to be paired with the
element that implements it. In a codebase with `data-ds-component` annotations
this is a dictionary lookup. In every codebase we have actually seen, it is not:
the design calls it `Button/Primary`, the code calls it `.btn.btn--primary`, and
somewhere there is a `.cta` that is really the same component under a name
nobody updated.

That is a semantic judgement over naming conventions, which is exactly the kind
of work a model is good at and a string matcher is not. So the deterministic
layer proposes candidates with a cheap lexical score, and the agent decides --
and is allowed to answer "no match", which matters more than it sounds: a wrong
pairing produces a page of confident, entirely fictional findings.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from ..ir import StyleNode
from ..trace.trajectory import Trajectory
from .provider import Provider

SYSTEM = """You pair design-system components with the DOM elements that implement them.

For each design component you are given candidate code nodes with their selector, semantic role and sample text, plus a lexical similarity score computed beforehand.

Judge by naming convention, role and text -- not by the score alone. `Button/Primary` and `.btn.btn--primary` are the same component under two naming systems. `Button/Primary` and `.btn.btn--secondary` are not, however close the strings look.

Answer "null" when no candidate is the same component. A wrong pairing produces a page of confident findings about an element that was never meant to match, which is worse than reporting nothing.

Reply with ONLY a JSON object, no prose, no code fences:
{"mappings": [{"design": "<design node_id>", "code": "<code node_id or null>", "confidence": 0.0-1.0, "why": "<one short clause>"}]}
"""

_ROLE_EQUIV = {
    "button": {"button", "link"}, "input": {"input", "textbox"},
    "heading": {"heading", "h1", "h2", "h3"}, "body": {"body", "p", "generic"},
    "label": {"label"}, "card": {"card", "section", "generic", "div"},
    "listitem": {"listitem", "li"}, "alert": {"alert", "div", "generic"},
    "status": {"status", "span", "generic"},
}


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", s.lower()) if t and len(t) > 1}


def lexical_score(design: StyleNode, code: StyleNode) -> float:
    """Cheap prior. Deliberately weak -- it proposes, the agent disposes."""
    dt = _tokens(design.node_id) | _tokens(design.selector)
    ct = _tokens(code.node_id) | _tokens(code.selector)
    if not dt or not ct:
        return 0.0
    jaccard = len(dt & ct) / len(dt | ct)
    role_bonus = 0.25 if code.role in _ROLE_EQUIV.get(design.role, {design.role}) else 0.0
    text_bonus = 0.0
    if design.text_sample and code.text_sample:
        a, b = _tokens(design.text_sample), _tokens(code.text_sample)
        if a and b:
            text_bonus = 0.25 * len(a & b) / len(a | b)
    return round(min(1.0, jaccard + role_bonus + text_bonus), 4)


def candidates(design: StyleNode, code_nodes: list[StyleNode], top_k: int = 5) -> list[dict]:
    scored = [
        {"code_node": c.node_id, "selector": c.selector, "role": c.role,
         "text": c.text_sample[:40], "score": lexical_score(design, c)}
        for c in code_nodes if c.state == "default"
    ]
    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]


def map_components(
    design_nodes: list[StyleNode],
    code_nodes: list[StyleNode],
    provider: Provider,
    traj: Trajectory,
    batch_size: int = 6,
) -> tuple[dict[str, Optional[str]], dict]:
    agent = "mapper"
    design_default = [d for d in design_nodes if d.state == "default"]
    code_by_id = {c.node_id: c for c in code_nodes if c.state == "default"}

    mappings: dict[str, Optional[str]] = {}
    usage = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0, "latency_ms": 0.0}

    # Exact annotation match needs no model.
    unresolved = []
    for d in design_default:
        if d.node_id in code_by_id:
            mappings[d.node_id] = d.node_id
        else:
            unresolved.append(d)

    traj.record(agent, "instruction",
                f"{len(mappings)} component(s) matched by annotation; "
                f"{len(unresolved)} need semantic mapping",
                {"resolved_by_annotation": sorted(mappings),
                 "unresolved": [d.node_id for d in unresolved]})

    for i in range(0, len(unresolved), batch_size):
        batch = unresolved[i:i + batch_size]
        task = {
            "task": "map",
            "components": [{
                "design": d.node_id, "role": d.role,
                "selector_hint": d.selector, "text": d.text_sample[:40],
                "candidates": candidates(d, code_nodes),
            } for d in batch],
        }
        comp = provider.complete(SYSTEM, json.dumps(task), max_tokens=1200)
        usage["input_tokens"] += comp.input_tokens
        usage["output_tokens"] += comp.output_tokens
        usage["cost_usd"] += comp.cost_usd
        usage["latency_ms"] += comp.latency_ms
        usage["calls"] += 1

        text = comp.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            traj.record(agent, "error", "mapper reply was not valid JSON; batch left unmapped",
                        {"preview": text[:200]})
            for d in batch:
                mappings[d.node_id] = None
            continue

        for entry in parsed.get("mappings", []):
            dkey = entry.get("design")
            ckey = entry.get("code")
            if ckey is not None and ckey not in code_by_id:
                traj.record(agent, "error",
                            f"proposed code node '{ckey}' does not exist; treating as no match",
                            {"design": dkey, "proposed": ckey})
                ckey = None
            mappings[dkey] = ckey
            traj.record(agent, "decision",
                        f"{dkey} → {ckey or 'no match'} "
                        f"(confidence {entry.get('confidence', 0)})",
                        {"why": entry.get("why", "")})

    matched = sum(1 for v in mappings.values() if v)
    traj.record(agent, "decision",
                f"mapping complete: {matched}/{len(design_default)} components paired",
                {"unmatched": [k for k, v in mappings.items() if not v]})
    return mappings, usage


def offline_map(payload: dict) -> dict:
    """
    Deterministic stand-in. Takes the top lexical candidate when it clears a
    margin over the runner-up, and abstains otherwise -- the same abstention
    behaviour we ask the model for, so the two modes stay comparable.
    """
    out = []
    for comp in payload.get("components", []):
        cands = comp.get("candidates", [])
        if not cands:
            out.append({"design": comp["design"], "code": None, "confidence": 0.0,
                        "why": "no candidates"})
            continue
        best = cands[0]
        runner = cands[1]["score"] if len(cands) > 1 else 0.0
        margin = best["score"] - runner
        if best["score"] >= 0.45 and margin >= 0.05:
            out.append({"design": comp["design"], "code": best["code_node"],
                        "confidence": round(min(0.95, best["score"]), 2),
                        "why": f"top lexical match, {margin:.2f} clear of runner-up"})
        else:
            out.append({"design": comp["design"], "code": None,
                        "confidence": round(best["score"], 2),
                        "why": f"ambiguous: best {best['score']:.2f}, margin {margin:.2f}"})
    return {"mappings": out}
