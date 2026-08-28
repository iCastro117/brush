"""
The verifier.

This is the component that makes the rest of the system trustworthy, and it is
deliberately not a model. It takes every finding the diagnostician proposed and
tries to break it against the measurement index:

  1. does every cited measurement id exist?
  2. do the values in the finding match the measurement they cite?
  3. does the severity match what the published policy computes from that
     measurement -- not what the finding asserts?
  4. is every cited principle id real?
  5. has a human already approved this exact deviation?

A finding that fails 1, 2 or 4 is dropped. A finding that fails 3 is corrected
and the agent is told why, which is what produces the retry rounds visible in
the trajectories. Nothing survives on the model's say-so.

The number this produces -- rejected findings as a share of proposed findings --
is the hallucination rate we report.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..ir import Finding, Measurement, StyleNode
from ..knowledge import retrieve as K
from ..memory.ledger import Ledger
from ..trace.trajectory import Trajectory

EPS = 0.01


@dataclass
class VerificationReport:
    accepted: list[Finding]
    rejected: list[dict]
    corrected: list[dict]
    suppressed: list[dict]

    @property
    def proposed(self) -> int:
        return len(self.accepted) + len(self.rejected) + len(self.suppressed)

    def stats(self) -> dict:
        p = self.proposed
        return {
            "proposed": p,
            "accepted": len(self.accepted),
            "rejected": len(self.rejected),
            "corrected": len(self.corrected),
            "suppressed_by_ledger": len(self.suppressed),
            "rejection_rate": round(len(self.rejected) / p, 4) if p else 0.0,
        }


def _values_agree(claimed: Any, measured: Any) -> bool:
    if claimed is None:
        return True
    try:
        return abs(float(claimed) - float(measured)) <= EPS
    except (TypeError, ValueError):
        return str(claimed).strip().lower() == str(measured).strip().lower()


def verify(
    raw_findings: list[dict],
    node: StyleNode,
    index: dict[str, Measurement],
    ledger: Ledger,
    traj: Trajectory,
    seq_start: int = 0,
) -> tuple[VerificationReport, list[str]]:
    """Returns (report, feedback_for_the_agent)."""
    agent = "verifier"
    accepted: list[Finding] = []
    rejected: list[dict] = []
    corrected: list[dict] = []
    suppressed: list[dict] = []
    feedback: list[str] = []
    valid_ids = K.valid_law_ids()
    seen_props: set[str] = set()
    seq = seq_start

    for raw in raw_findings:
        prop = raw.get("prop")
        evidence = [e for e in (raw.get("evidence") or []) if isinstance(e, str)]

        if not prop:
            rejected.append({"reason": "no property named", "raw": raw})
            continue

        if prop in seen_props:
            rejected.append({"prop": prop, "reason": "duplicate finding for this property"})
            feedback.append(f"You reported `{prop}` more than once. Report each property once.")
            continue

        # 1. evidence must exist
        missing = [e for e in evidence if e not in index]
        if not evidence or missing:
            rejected.append({"prop": prop,
                             "reason": "cites no valid measurement" if not evidence
                             else f"cites unknown measurement id(s): {missing}"})
            feedback.append(
                f"Finding on `{prop}` was discarded: it cited "
                f"{'no measurement' if not evidence else f'unknown ids {missing}'}. "
                f"Every finding must cite ids from the supplied measurements."
            )
            continue

        m = index[evidence[0]]

        # 2. claimed values must match the measurement
        if not _values_agree(raw.get("code_value"), m.code_value) or \
           not _values_agree(raw.get("design_value"), m.design_value):
            rejected.append({"prop": prop, "reason": "asserted values contradict the measurement",
                             "claimed": {"design": raw.get("design_value"),
                                         "code": raw.get("code_value")},
                             "measured": {"design": m.design_value, "code": m.code_value}})
            feedback.append(
                f"Finding on `{prop}` was discarded: you stated "
                f"{raw.get('code_value')} but the measurement says {m.code_value}. "
                f"Do not restate numbers from memory."
            )
            continue

        # 3. principle ids must be real
        principles = [p for p in (raw.get("principles") or []) if isinstance(p, str)]
        bad = [p for p in principles if p not in valid_ids]
        if bad:
            principles = [p for p in principles if p in valid_ids]
            feedback.append(
                f"Finding on `{prop}` cited principle id(s) that do not exist: {bad}. "
                f"They were stripped. Only cite ids from the knowledge slice."
            )
            corrected.append({"prop": prop, "field": "principles", "removed": bad})

        # 4. severity is recomputed, never trusted
        verdict = K.classify(m, node)
        claimed_sev = (raw.get("severity") or "").lower()
        note = ""
        if not verdict.is_finding:
            rejected.append({"prop": prop,
                             "reason": "recomputation finds this measurement within tolerance",
                             "measurement": m.measurement_id})
            feedback.append(
                f"Finding on `{prop}` was discarded: recomputing from "
                f"{m.measurement_id} puts it inside tolerance ({verdict.reason})."
            )
            continue
        if claimed_sev != verdict.severity:
            note = (f"severity corrected from '{claimed_sev or 'unset'}' to "
                    f"'{verdict.severity}' by recomputation of {m.measurement_id}")
            corrected.append({"prop": prop, "field": "severity",
                              "from": claimed_sev, "to": verdict.severity,
                              "clause": verdict.clause_id})
            feedback.append(
                f"Severity on `{prop}` was corrected to '{verdict.severity}' "
                f"(clause {verdict.clause_id}: {verdict.reason})."
            )

        # 5. human approvals
        sup = ledger.suppresses(node.key(), prop, m.code_value)
        if sup is not None:
            suppressed.append({"prop": prop, "approval_id": sup.approval_id,
                               "reason": sup.reason, "approved_by": sup.approved_by})
            traj.record(agent, "checkpoint",
                        f"{node.key()} `{prop}` suppressed by approval {sup.approval_id} "
                        f"({sup.approved_by}: {sup.reason})",
                        {"approval": sup.approval_id, "value": m.code_value})
            continue

        seq += 1
        seen_props.add(prop)
        if not principles:
            principles = verdict.laws + verdict.heuristics + verdict.wcag
        accepted.append(Finding(
            finding_id=f"DL-{seq:04d}",
            node_key=node.key(),
            prop=prop,
            channel=m.channel,
            title=raw.get("title") or f"{node.node_id}: {prop} does not match spec",
            severity=verdict.severity,
            design_value=m.design_value,
            code_value=m.code_value,
            delta=m.delta,
            delta_unit=m.delta_unit,
            ux_laws=principles,
            rationale=raw.get("rationale") or verdict.reason,
            suggested_fix=raw.get("suggested_fix") or "",
            evidence=evidence,
            confidence=float(raw.get("confidence") or 0.0),
            verified=True,
            verifier_note=note,
        ))

    report = VerificationReport(accepted, rejected, corrected, suppressed)
    traj.record(agent, "decision",
                f"{node.key()}: {len(accepted)} accepted, {len(rejected)} rejected, "
                f"{len(corrected)} corrected, {len(suppressed)} suppressed",
                report.stats())
    return report, feedback
