"""
The orchestrator.

Six stages, and the ordering is the design:

  1. extract    deterministic. Both sides into one IR.
  2. map        agent. Pair design components with the elements implementing them.
  3. measure    deterministic. Every property, in a perceptual unit.
  4. diagnose   agent, per component, with tools. Judgement only.
  5. verify     deterministic. Recompute everything the agent asserted.
  6. report     agent. Group by root cause and rank by consequence.

Agents sit only at 2, 4 and 6 -- the three places where the answer is a
judgement rather than a calculation. Everything a number can settle is settled
by a number, before and after. That split is why the verifier can be strict:
it never has to argue with the model about arithmetic, only about relevance.

Stage 4 runs per component rather than over the whole page. Batching everything
into one call was our first design and it cost precision badly (changelog I2):
with 200 measurements in context the model started grouping unrelated
components and citing whichever measurement id was nearest in the prompt.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from ..analyze.compare import compare_nodes, index_measurements
from ..extract.code import extract_code_nodes
from ..extract.design import load_design
from ..ir import Finding, Measurement, StyleNode
from ..knowledge import retrieve as K
from ..memory.ledger import Ledger
from ..trace.trajectory import Trajectory
from . import diagnostician as DX
from . import mapper as MP
from . import reporter as RP
from . import verifier as VF
from .provider import OfflineProvider, Provider
from .tools import ToolBox


@dataclass
class AuditReport:
    run_id: str
    findings: list[Finding] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    mappings: dict = field(default_factory=dict)
    verification: dict = field(default_factory=dict)
    trajectory_path: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "summary": self.summary,
            "stats": self.stats,
            "mappings": self.mappings,
            "verification": self.verification,
            "findings": [f.to_dict() for f in self.findings],
            "measurement_count": len(self.measurements),
            "trajectory": self.trajectory_path,
        }


def wire_offline(provider: Provider) -> None:
    """Register the deterministic handlers when running without a model."""
    if isinstance(provider, OfflineProvider):
        provider.register("map", MP.offline_map)
        provider.register("diagnose", DX.offline_diagnose)
        provider.register("report", RP.offline_report)


def run_audit(
    design_path: str,
    html_path: str,
    css_paths: list[str],
    provider: Provider,
    out_dir: str = "out",
    ledger_path: Optional[str] = None,
    ignore_annotations: bool = True,
    max_rounds: int = 3,
    run_id: Optional[str] = None,
) -> AuditReport:
    t_start = time.time()
    run_id = run_id or f"dl-{uuid.uuid4().hex[:8]}"
    os.makedirs(out_dir, exist_ok=True)
    traj_path = os.path.join(out_dir, f"{run_id}.trajectory.jsonl")
    traj = Trajectory(run_id, traj_path, {
        "tool": "brush", "provider": provider.name,
        "model": getattr(provider, "model", "n/a"),
        "design": design_path, "html": html_path, "css": css_paths,
        "ignore_annotations": ignore_annotations,
    })
    wire_offline(provider)

    usage_total = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                   "calls": 0, "latency_ms": 0.0}

    def add_usage(u: dict) -> None:
        for k in usage_total:
            usage_total[k] += u.get(k, 0)

    # ---- 1. extract ----------------------------------------------------
    t0 = time.time()
    ds, design_nodes = load_design(design_path)
    code_nodes, _ = extract_code_nodes(
        html_path, css_paths, root_font_size=ds.root_font_size,
        include_unannotated=True, ignore_annotations=ignore_annotations,
    )
    traj.record("extractor", "decision",
                f"{len(design_nodes)} design node(s), {len(code_nodes)} code node(s) "
                f"resolved from {len(css_paths)} stylesheet(s)",
                {"tokens": {"color": len(ds.color), "space": len(ds.space),
                            "font_size": len(ds.font_size), "radius": len(ds.radius)},
                 "grid_base": ds.grid_base, "root_font_size": ds.root_font_size},
                duration_ms=round((time.time() - t0) * 1000, 2))

    ledger = Ledger(ledger_path)
    if ledger.approvals:
        traj.record("memory", "instruction",
                    f"loaded {len(ledger.approvals)} approved deviation(s) from the ledger",
                    ledger.stats())

    # ---- 2. map --------------------------------------------------------
    mappings, u = MP.map_components(design_nodes, code_nodes, provider, traj)
    add_usage(u)

    code_by_key = {c.key(): c for c in code_nodes}

    # ---- 3. measure ----------------------------------------------------
    t0 = time.time()
    all_measurements: list[Measurement] = []
    pairs: list[tuple[StyleNode, StyleNode]] = []
    missing_states: list[dict] = []

    for d in design_nodes:
        code_id = mappings.get(d.node_id)
        if not code_id:
            continue
        c = code_by_key.get(f"{code_id}@{d.state}")
        if c is None:
            if d.state != "default":
                # A state the spec requires that the implementation never defines.
                # This is how a deleted focus ring is caught: not as a wrong value,
                # but as an absent one.
                missing_states.append({"component": d.node_id, "state": d.state})
                base = code_by_key.get(f"{code_id}@default")
                if base is not None:
                    c = StyleNode(node_id=code_id, role=base.role, state=d.state,
                                  props=dict(base.props), source=base.source,
                                  selector=base.selector, text_sample=base.text_sample,
                                  parent_background=base.parent_background)
                else:
                    continue
            else:
                continue
        # The node handed to the agents carries the DESIGN identity (so findings
        # are named for the component a human recognises, and so their key matches
        # the measurement ids) but the CODE reality (role, props, backdrop).
        # Keeping these on separate objects was the source of a silent key
        # mismatch between evidence ids and ledger lookups -- see changelog I4.
        audit_node = StyleNode(
            node_id=d.node_id, role=c.role, state=d.state, props=dict(c.props),
            source=c.source, selector=c.selector, text_sample=c.text_sample,
            parent_background=c.parent_background,
        )
        pairs.append((d, audit_node))
        all_measurements.extend(compare_nodes(d, c, ds))

    index = index_measurements(all_measurements)
    # What reaches the agent is decided by the classifier, not by numeric
    # tolerance. Tolerance answers "would a user see this?"; the classifier also
    # asks "is this still a token?". Using tolerance as a pre-filter silently
    # dropped every off-token colour that happened to be imperceptible -- which
    # is exactly the drift a design system exists to prevent (changelog I5).
    node_lookup = {d.key(): c for d, c in pairs}
    out_of_tol = [
        m for m in all_measurements
        if (not m.within_tolerance)
        or (m.node_key in node_lookup and K.classify(m, node_lookup[m.node_key]).is_finding)
    ]
    traj.record("comparator", "decision",
                f"{len(all_measurements)} measurement(s) across {len(pairs)} paired node(s); "
                f"{len(out_of_tol)} outside tolerance",
                {"missing_states": missing_states,
                 "channels": _count_by(all_measurements, "channel")},
                duration_ms=round((time.time() - t0) * 1000, 2))

    if missing_states:
        traj.record("comparator", "checkpoint",
                    f"{len(missing_states)} specified state(s) absent from the implementation",
                    {"states": missing_states})

    tools = ToolBox(index, {d.key(): d for d in design_nodes},
                    {c.key(): c for c in code_nodes}, ds, ledger, traj)

    # ---- 4 + 5. diagnose, then verify, with one feedback round ---------
    accepted: list[Finding] = []
    ver_stats = {"proposed": 0, "accepted": 0, "rejected": 0,
                 "corrected": 0, "suppressed_by_ledger": 0}
    rejected_detail: list[dict] = []
    corrected_detail: list[dict] = []
    seq = 0

    by_node: dict[str, list[Measurement]] = {}
    for m in out_of_tol:
        by_node.setdefault(m.node_key, []).append(m)

    for d, c in pairs:
        node_ms = by_node.get(d.key(), [])
        if not node_ms:
            continue
        raw, u = DX.diagnose_component(c, node_ms, provider, tools, traj, max_rounds)
        add_usage(u)
        report, feedback = VF.verify(raw, c, index, ledger, traj, seq_start=seq)

        # One corrective round. The agent is told exactly what failed and why.
        if feedback and report.rejected:
            traj.record("verifier", "retry",
                        f"returning {len(feedback)} correction(s) to the diagnostician "
                        f"for {d.key()}",
                        {"feedback": feedback[:6]})
            raw2, u2 = DX.diagnose_component(c, node_ms, provider, tools, traj,
                                             max_rounds, verifier_feedback=feedback)
            add_usage(u2)
            report2, _ = VF.verify(raw2, c, index, ledger, traj, seq_start=seq)
            if len(report2.accepted) > len(report.accepted):
                traj.record("verifier", "decision",
                            f"retry improved {d.key()}: "
                            f"{len(report.accepted)} → {len(report2.accepted)} accepted", {})
                report = report2

        seq += len(report.accepted)
        accepted.extend(report.accepted)
        s = report.stats()
        for k in ver_stats:
            ver_stats[k] += s.get(k, 0)
        rejected_detail.extend(report.rejected)
        corrected_detail.extend(report.corrected)

    # ---- 6. report -----------------------------------------------------
    clean_components = len(pairs) - len({f.node_key for f in accepted})
    summary, u = RP.summarise(accepted, provider, traj, len(pairs), max(clean_components, 0))
    add_usage(u)

    wall = time.time() - t_start
    stats = {
        "provider": provider.name,
        "model": getattr(provider, "model", "n/a"),
        "design_nodes": len(design_nodes),
        "code_nodes": len(code_nodes),
        "paired_nodes": len(pairs),
        "unmapped_components": [k for k, v in mappings.items() if not v],
        "measurements": len(all_measurements),
        "out_of_tolerance": len(out_of_tol),
        "findings": len(accepted),
        "by_severity": RP._by_severity(accepted),
        "missing_states": missing_states,
        "tool_calls": dict(tools.call_count),
        "tool_calls_total": sum(tools.call_count.values()),
        "trajectory_steps": len(traj.steps),
        "wall_seconds": round(wall, 3),
        "usage": {**usage_total, "cost_usd": round(usage_total["cost_usd"], 6)},
    }
    ver_stats["rejection_rate"] = (
        round(ver_stats["rejected"] / ver_stats["proposed"], 4)
        if ver_stats["proposed"] else 0.0
    )
    traj.close(stats)

    return AuditReport(
        run_id=run_id, findings=accepted, measurements=all_measurements,
        summary=summary, stats=stats, mappings=mappings,
        verification={**ver_stats, "rejected": rejected_detail,
                      "corrected": corrected_detail},
        trajectory_path=traj_path,
    )


def _count_by(items: list[Measurement], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for i in items:
        k = getattr(i, attr)
        out[k] = out.get(k, 0) + 1
    return out
