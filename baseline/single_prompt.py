"""
Baseline B2 — one prompt, both artefacts, "list the discrepancies".

This is the other reasonable starting point from the brief: a single direct
prompt with basic instructions. The design spec and the stylesheet are pasted
in and the model is asked to find the drift. No measurement engine, no tools, no
verification -- exactly the setup most people try first, and the one our
pipeline has to beat to justify its existence.

It shares the eval harness, the cases and the output schema with B1 and with the
pipeline, so the comparison stays like for like.

Requires ANTHROPIC_API_KEY. Figures from this baseline are absent from the
offline results file for that reason, and the README says so rather than
quietly leaving a gap.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from brush.agents.provider import build_provider  # noqa: E402

SYSTEM = """You audit a frontend implementation against its design specification.

You are given the design specification as JSON and the implemented stylesheet as CSS. Find every place the implementation deviates from the specification: spacing, colour, typography, radii, borders, states and component sizing.

Reply with ONLY a JSON object, no prose and no code fences:
{"findings": [{"component": "<component name from the spec>", "prop": "<css property>", "expected": "<spec value>", "actual": "<code value>", "severity": "blocker|major|minor|info", "why": "<one sentence>"}]}
"""


def run(design_path: str, css_paths: list[str], provider_kind: str = "anthropic",
        cassette: str | None = None) -> dict:
    t0 = time.time()
    with open(design_path, "r", encoding="utf-8") as fh:
        design = fh.read()
    css = ""
    for p in css_paths:
        with open(p, "r", encoding="utf-8") as fh:
            css += fh.read() + "\n"

    provider = build_provider(provider_kind, cassette)
    user = (f"DESIGN SPECIFICATION\n{design}\n\n"
            f"IMPLEMENTED STYLESHEET\n{css}\n\n"
            f"List every deviation.")
    comp = provider.complete(SYSTEM, user, max_tokens=4000)

    text = comp.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(text)
        findings = parsed.get("findings", [])
    except json.JSONDecodeError:
        findings = []

    return {
        "baseline": "single_prompt",
        "findings": findings,
        "stats": {
            "findings": len(findings),
            "wall_seconds": round(time.time() - t0, 4),
            "cost_usd": round(comp.cost_usd, 6),
            "input_tokens": comp.input_tokens,
            "output_tokens": comp.output_tokens,
            "severity_available": True,
            "provider": provider.name,
            "model": comp.model,
        },
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--design", required=True)
    ap.add_argument("--css", nargs="+", required=True)
    ap.add_argument("--provider", default="anthropic", choices=["anthropic", "replay"])
    ap.add_argument("--cassette", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(a.design, a.css, a.provider, a.cassette)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2, default=str)
    print(f"single_prompt: {res['stats']['findings']} findings "
          f"in {res['stats']['wall_seconds']}s, ${res['stats']['cost_usd']:.4f}")
