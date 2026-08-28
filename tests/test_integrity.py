"""
Integrity checks on the knowledge pack.

A clause id referenced in code but absent from the published policy would make
`clause()` return None and silently default the severity to `minor` -- a wrong
grade with no error and no trace. These tests make that failure loud.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from brush.knowledge import retrieve as K  # noqa: E402


def test_every_referenced_clause_exists() -> None:
    src = open(os.path.join(ROOT, "src", "brush", "knowledge", "retrieve.py"),
               encoding="utf-8").read()
    referenced = set(re.findall(r'v\("(c-[\w-]+)"', src))
    declared = {c["id"] for c in K.pack()["clauses"]}
    missing = referenced - declared
    assert not missing, f"clause ids used in code but absent from the policy: {sorted(missing)}"
    print(f"  ok  {len(referenced)} referenced clause ids all declared")


def test_no_unreachable_clauses() -> None:
    src = open(os.path.join(ROOT, "src", "brush", "knowledge", "retrieve.py"),
               encoding="utf-8").read()
    referenced = set(re.findall(r'v\("(c-[\w-]+)"', src))
    declared = {c["id"] for c in K.pack()["clauses"]}
    dead = declared - referenced
    assert not dead, f"clauses published but never reachable from the classifier: {sorted(dead)}"
    print("  ok  no dead clauses in the published policy")


def test_clause_principle_ids_are_real() -> None:
    valid = K.valid_law_ids()
    for c in K.pack()["clauses"]:
        for pid in c.get("laws", []) + c.get("heuristics", []) + c.get("wcag", []):
            assert pid in valid, f"clause {c['id']} cites unknown principle '{pid}'"
    print("  ok  every clause cites real principles")


def test_thirty_ux_laws_present() -> None:
    laws = K.pack()["laws"]
    assert len(laws) == 30, f"expected 30 Laws of UX entries, found {len(laws)}"
    assert len(K.pack()["heuristics"]) == 10, "expected Nielsen's 10 heuristics"
    print(f"  ok  {len(laws)} UX laws + {len(K.pack()['heuristics'])} heuristics loaded")


def test_pipeline_is_deterministic():
    """
    The same inputs must produce byte-identical findings.

    The project claims reproducibility, and with the offline provider that claim
    is checkable rather than aspirational: no sampling, no wall-clock in the
    output, no set iteration leaking into ordering. If this ever fails, a
    published number stopped meaning anything.
    """
    import hashlib
    import json
    import tempfile

    from brush.agents.orchestrator import run_audit
    from brush.agents.provider import build_provider

    design = os.path.join(ROOT, "eval", "cases", "design.spec.json")
    html = os.path.join(ROOT, "eval", "cases", "checkout.html")
    css = os.path.join(ROOT, "eval", "cases", "generated", "case_01.css")
    if not os.path.exists(css):
        print("  --  determinism skipped (run `make cases` first)")
        return

    digests = []
    for i in range(3):
        with tempfile.TemporaryDirectory() as tmp:
            rep = run_audit(design, html, [css], build_provider("offline"),
                            out_dir=tmp, ignore_annotations=True, run_id=f"det{i}")
        core = {
            "measurements": len(rep.measurements),
            "findings": [(f.node_key, f.prop, f.severity, f.delta, tuple(f.evidence))
                         for f in rep.findings],
        }
        digests.append(hashlib.sha256(
            json.dumps(core, sort_keys=True, default=str).encode()).hexdigest())

    assert len(set(digests)) == 1, (
        f"pipeline is not deterministic: {len(set(digests))} distinct results "
        f"across 3 identical runs"
    )
    print(f"  ok  3 identical runs, same {len(rep.findings)} findings "
          f"({digests[0][:12]}…)")


LABEL = "integrity checks"

if __name__ == "__main__":
    fails = skips = 0
    names = sorted(n for n in dict(globals()) if n.startswith("test_"))
    for name in names:
        try:
            globals()[name]()
        except AssertionError as exc:
            fails += 1
            print(f"  FAIL  {name}: {exc}")
        except ImportError as exc:
            # An optional dependency is missing. That is a skip, not a failure --
            # and it must never take the rest of the suite down with it.
            skips += 1
            print(f"  --    {name} skipped ({exc})")
        except Exception as exc:  # noqa: BLE001 - a crash is a failure, not a stop
            fails += 1
            print(f"  FAIL  {name}: unexpected {type(exc).__name__}: {exc}")
    note = f", {skips} skipped" if skips else ""
    print(f"\n{'FAILED' if fails else 'PASSED'} — {len(names) - skips} of "
          f"{len(names)} {LABEL}, {fails} failure(s){note}")
    sys.exit(1 if fails else 0)
