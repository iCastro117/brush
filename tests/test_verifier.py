"""
Adversarial tests for the verifier.

In `offline` mode the verifier's rejection rate is 0 by construction: the
offline policy derives severity from the same classifier the verifier
recomputes with, so there is nothing to disagree about. Reporting that 0 as
"the agent never hallucinates" would be meaningless.

The honest way to demonstrate the verifier is to attack it directly. Each test
below hands it a finding of the kind a language model actually produces when it
drifts -- a plausible citation to a measurement that does not exist, a number
recalled from earlier in the context instead of read from the tool, an
authoritative-sounding principle id that was never in the knowledge pack, a
severity inflated past what the policy supports -- and asserts that the finding
does not survive.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from brush.agents.verifier import verify  # noqa: E402
from brush.ir import Measurement, StyleNode  # noqa: E402
from brush.memory.ledger import Ledger  # noqa: E402
from brush.trace.trajectory import Trajectory  # noqa: E402

OUT = os.path.join(ROOT, "out", "tests")


def _fixture():
    node = StyleNode(node_id="Button/Primary", role="button", state="default",
                     props={"padding-left": 20.0, "min-height": 48.0},
                     parent_background="#FFFFFF")
    m = Measurement(
        node_key="Button/Primary@default", prop="padding-left", channel="geometry",
        design_value=24.0, code_value=20.0, delta=-4.0, delta_unit="px",
        within_tolerance=False, method="css cascade -> px",
        extra={"grid_applicable": True, "on_grid": True, "grid_base": 4.0},
    )
    index = {m.measurement_id: m}
    traj = Trajectory("test", os.path.join(OUT, "verifier.jsonl"))
    return node, index, traj, Ledger()


def _run(raw):
    node, index, traj, ledger = _fixture()
    rep, feedback = verify(raw, node, index, ledger, traj)
    traj.close()
    return rep, feedback


def test_fabricated_evidence_id_is_rejected() -> None:
    rep, fb = _run([{
        "prop": "padding-left", "severity": "major",
        "title": "Padding is wrong", "rationale": "It looks off.",
        "evidence": ["Button/Primary@default::padding-yellow"],
    }])
    assert not rep.accepted, "a finding citing a non-existent measurement was accepted"
    assert rep.rejected and "unknown measurement" in rep.rejected[0]["reason"]
    assert fb, "the agent was not told why its finding was dropped"
    print("  ok  fabricated evidence id rejected")


def test_no_evidence_is_rejected() -> None:
    rep, _ = _run([{"prop": "padding-left", "severity": "major",
                    "title": "Trust me", "evidence": []}])
    assert not rep.accepted, "a finding with no evidence at all was accepted"
    print("  ok  finding with no evidence rejected")


def test_number_recalled_from_memory_is_rejected() -> None:
    # The measurement says 20px. The finding asserts 18px -- the classic failure
    # where a model restates a number it saw earlier instead of reading the tool.
    rep, fb = _run([{
        "prop": "padding-left", "severity": "major", "code_value": 18.0,
        "title": "Padding shrank to 18px", "evidence": ["Button/Primary@default::padding-left"],
    }])
    assert not rep.accepted, "a finding contradicting its own measurement was accepted"
    assert "contradict" in rep.rejected[0]["reason"]
    print("  ok  asserted value contradicting the measurement rejected")


def test_invented_principle_id_is_stripped() -> None:
    rep, fb = _run([{
        "prop": "padding-left", "severity": "major",
        "title": "Padding is 4px under spec",
        "principles": ["lux-proximity", "lux-the-law-of-vibes", "nn-42"],
        "evidence": ["Button/Primary@default::padding-left"],
    }])
    assert rep.accepted, "a valid finding was dropped over one bad principle id"
    cited = rep.accepted[0].ux_laws
    assert "lux-the-law-of-vibes" not in cited and "nn-42" not in cited
    assert "lux-proximity" in cited, "the real principle was stripped too"
    assert any(c["field"] == "principles" for c in rep.corrected)
    print("  ok  invented principle ids stripped, real ones kept")


def test_inflated_severity_is_corrected() -> None:
    # A 4px padding delta on an interactive edge is `major` under the published
    # policy. The finding claims `blocker`.
    rep, fb = _run([{
        "prop": "padding-left", "severity": "blocker",
        "title": "Critical padding failure",
        "evidence": ["Button/Primary@default::padding-left"],
    }])
    assert rep.accepted, "the finding itself was valid and should survive"
    assert rep.accepted[0].severity == "major", \
        f"severity was not recomputed (got {rep.accepted[0].severity})"
    assert any(c["field"] == "severity" for c in rep.corrected)
    assert rep.accepted[0].verifier_note, "the correction was not recorded on the finding"
    print("  ok  inflated severity recomputed from the policy")


def test_duplicate_findings_are_collapsed() -> None:
    f = {"prop": "padding-left", "severity": "major", "title": "Padding off",
         "evidence": ["Button/Primary@default::padding-left"]}
    rep, _ = _run([f, dict(f, title="Padding off (again)")])
    assert len(rep.accepted) == 1, "the same property was reported twice"
    print("  ok  duplicate finding collapsed")


def test_within_tolerance_claim_is_rejected() -> None:
    node, index, traj, ledger = _fixture()
    m = index["Button/Primary@default::padding-left"]
    m.design_value, m.code_value, m.delta = 24.0, 24.0, 0.0
    rep, _ = verify([{"prop": "padding-left", "severity": "minor",
                      "title": "Something feels off here",
                      "evidence": ["Button/Primary@default::padding-left"]}],
                    node, index, ledger, traj)
    traj.close()
    assert not rep.accepted, "a finding on a conforming measurement was accepted"
    print("  ok  finding on an in-tolerance measurement rejected")


def test_human_approval_suppresses() -> None:
    node, index, traj, _ = _fixture()
    ledger = Ledger()
    ledger.approve("Button/Primary@default", "padding-left", 20.0,
                   "Compact variant signed off for the dense toolbar", "a.rivera")
    rep, _ = verify([{"prop": "padding-left", "severity": "major",
                      "title": "Padding is 4px under spec",
                      "evidence": ["Button/Primary@default::padding-left"]}],
                    node, index, ledger, traj)
    traj.close()
    assert not rep.accepted and rep.suppressed, "an approved deviation was still reported"
    print("  ok  approved deviation suppressed at the approved value")


LABEL = "adversarial cases"

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
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
