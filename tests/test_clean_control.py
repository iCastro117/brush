"""
The control that matters most.

A detector that finds every injected defect but also invents findings on a
conforming file is worse than useless in review: it trains the team to skim, and
once they skim the real regressions go through with everything else. This test
asserts the floor -- on an implementation that matches the spec, the whole
pipeline emits nothing.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from brush.agents.orchestrator import run_audit  # noqa: E402
from brush.agents.provider import build_provider  # noqa: E402
from brush.analyze.compare import compare_nodes  # noqa: E402
from brush.extract.code import extract_code_nodes  # noqa: E402
from brush.extract.design import load_design  # noqa: E402
from brush.knowledge.retrieve import classify  # noqa: E402

CASES = os.path.join(ROOT, "eval", "cases")
DESIGN = os.path.join(CASES, "design.spec.json")
HTML = os.path.join(CASES, "checkout.html")
CSS = os.path.join(CASES, "checkout.css")


def test_classifier_fires_on_nothing_in_a_conforming_file() -> None:
    ds, design_nodes = load_design(DESIGN)
    code_nodes, _ = extract_code_nodes(HTML, [CSS], root_font_size=ds.root_font_size)
    code_by_key = {c.key(): c for c in code_nodes}
    fired, total = [], 0
    for d in design_nodes:
        c = code_by_key.get(d.key())
        if c is None:
            continue
        for m in compare_nodes(d, c, ds):
            total += 1
            v = classify(m, c)
            if v.is_finding:
                fired.append(f"{m.measurement_id} -> {v.severity} ({v.reason})")
    assert not fired, ("classifier produced findings on a conforming file:\n  "
                       + "\n  ".join(fired))
    print(f"  ok  0 findings across {total} measurements on the conforming file")


def test_full_pipeline_reports_nothing_on_a_conforming_file() -> None:
    rep = run_audit(DESIGN, HTML, [CSS], build_provider("offline"),
                    out_dir=os.path.join(ROOT, "out", "tests"),
                    ignore_annotations=True, run_id="test-clean")
    assert not rep.findings, (
        "pipeline reported findings on a conforming file: "
        + ", ".join(f"{f.node_key} {f.prop}" for f in rep.findings))
    assert rep.stats["measurements"] > 100, "suspiciously few measurements taken"
    print(f"  ok  pipeline emitted 0 findings from "
          f"{rep.stats['measurements']} measurements")


LABEL = "control checks"

if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, "out", "tests"), exist_ok=True)
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
