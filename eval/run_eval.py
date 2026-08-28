"""
The evaluation harness.

Ground truth is derived, not hand-written. Our first version listed the expected
findings alongside each mutation, and it was wrong within an hour: mutating
`font-weight` on the base `.btn` rule also changes `Button/Secondary`, which
inherits it. The hand-written list did not say so, so a detector that correctly
reported Button/Secondary was scored as producing a false positive. Penalising
the better detector for being right is the worst failure an evaluation can have.

So the harness computes ground truth by construction instead:

  1. resolve the clean stylesheet into measurements against the spec
  2. resolve the mutated stylesheet the same way
  3. any measurement whose code-side value changed between the two IS a defect

That definition is exact, complete, includes cascade side effects the author did
not anticipate, and covers derived measurements (target size, grid conformance)
for free. The mutation catalogue is kept as a sanity check on coverage, not as
the source of truth.

Metrics reported, per case and in aggregate:
  precision, recall, F1        over (component, property) pairs
  false positives on clean     the control case, weighted separately
  severity accuracy            share of true positives given the right band
  review burden                findings a human must read to reach full recall
  runtime, cost                wall clock and USD per component
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

from brush.agents.orchestrator import run_audit  # noqa: E402
from brush.agents.provider import build_provider  # noqa: E402
from brush.analyze.compare import compare_nodes  # noqa: E402
from brush.extract.code import extract_code_nodes  # noqa: E402
from brush.extract.design import load_design  # noqa: E402
from baseline import naive_diff  # noqa: E402

SEV_RANK = {"info": 0, "minor": 1, "major": 2, "blocker": 3}


# ---------------------------------------------------------------------------
# Ground truth by construction
# ---------------------------------------------------------------------------
def measurement_map(design_path: str, html_path: str, css_path: str) -> dict[str, Any]:
    """Measurement id -> (code value, within_tolerance) for one stylesheet."""
    ds, design_nodes = load_design(design_path)
    code_nodes, _ = extract_code_nodes(
        html_path, [css_path], root_font_size=ds.root_font_size,
        include_unannotated=True, ignore_annotations=False,
    )
    code_by_key = {c.key(): c for c in code_nodes}
    out: dict[str, Any] = {}
    for d in design_nodes:
        c = code_by_key.get(d.key())
        if c is None:
            base = code_by_key.get(f"{d.node_id}@default")
            if base is None:
                continue
            from brush.ir import StyleNode
            c = StyleNode(node_id=d.node_id, role=base.role, state=d.state,
                          props=dict(base.props), source=base.source,
                          selector=base.selector, text_sample=base.text_sample,
                          parent_background=base.parent_background)
        for m in compare_nodes(d, c, ds):
            out[m.measurement_id] = (m.code_value, m.within_tolerance)
    return out


def derive_ground_truth(design_path: str, html_path: str,
                        clean_css: str, mutated_css: str) -> set[tuple[str, str]]:
    """Every (component, property) the mutation actually changed on the code side."""
    before = measurement_map(design_path, html_path, clean_css)
    after = measurement_map(design_path, html_path, mutated_css)
    gt: set[tuple[str, str]] = set()
    for mid, (val, within_tolerance) in after.items():
        # A measurement present only after the mutation exists *because* of it --
        # derived checks like grid conformance are emitted only when they have
        # something to say, so absence-then-presence is itself the defect.
        changed = _changed(before[mid][0], val) if mid in before else True
        # A change to a plain property is always a defect: an off-token literal
        # is off-spec even when the drift is below the perceptual floor, which
        # is exactly the class of bug this tool exists to surface.
        #
        # Derived RELATIONSHIP measurements are different, because they are
        # directional. A grouping ratio can move a long way in the safe
        # direction, and counting that as a defect scored the detector as having
        # missed something for correctly staying silent -- the same failure that
        # made us stop hand-writing ground truth (changelog I5). So for those,
        # and only those, the change must also leave the measurement outside
        # tolerance.
        _, prop_name = mid.split("::", 1)
        directional = prop_name.startswith("-derived-")
        if changed and (within_tolerance is False or not directional):
            node_key, prop = mid.split("::", 1)
            gt.add((node_key.split("@")[0], prop))
    return gt


def _changed(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return False
    try:
        return abs(float(a) - float(b)) > 0.001
    except (TypeError, ValueError):
        return str(a).strip().lower() != str(b).strip().lower()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def score(emitted: set[tuple[str, str]], gt: set[tuple[str, str]]) -> dict:
    tp = len(emitted & gt)
    fp = len(emitted - gt)
    fn = len(gt - emitted)
    precision = tp / (tp + fp) if (tp + fp) else (1.0 if not gt else 0.0)
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    # Split the score by measurement family. Derived relationships (target size,
    # grid conformance, grouping ratio) are facts about how properties relate to
    # each other, and a declaration-level diff structurally cannot emit them. A
    # judge should be able to see how much of the gap is "measured the same
    # things better" and how much is "measured things the other tool cannot".
    plain_gt = {k for k in gt if not k[1].startswith("-derived-")}
    deriv_gt = gt - plain_gt
    plain_em = {k for k in emitted if not k[1].startswith("-derived-")}
    deriv_em = emitted - plain_em
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4),
            "plain": {"gt": len(plain_gt), "tp": len(plain_em & plain_gt)},
            "derived": {"gt": len(deriv_gt), "tp": len(deriv_em & deriv_gt)},
            "missed": sorted(gt - emitted)[:12],
            "spurious": sorted(emitted - gt)[:12]}


def catalogue_recall(findings, mutations) -> dict:
    """
    A second, non-circular recall check.

    Ground truth derived from the measurement engine shares an extraction layer
    with the pipeline, so recall against it cannot fall below what the extractor
    can see. This check instead asks the question a human wrote down before any
    code ran: for each injected mutation, did the tool say anything at all about
    the component and property the mutation touched? The baseline is scored the
    same way, so the comparison stays like for like.
    """
    emitted = {(f.node_key.split("@")[0], f.prop) if hasattr(f, "node_key")
               else (f["component"], f["prop"]) for f in findings}
    caught, missed = 0, []
    for mu in mutations:
        want = {(mu["component"], p) for p in mu["expected_props"]}
        if emitted & want:
            caught += 1
        else:
            missed.append(mu["mutation_id"])
    total = len(mutations)
    return {"mutations": total, "caught": caught,
            "recall": round(caught / total, 4) if total else None,
            "missed_mutation_ids": missed}


def severity_accuracy(findings, mutations) -> dict:
    """
    Checked only against bands a human assigned from the published policy, so the
    tool is never scored against its own classifier.
    """
    expected: dict[tuple[str, str], str] = {}
    for mu in mutations:
        for p in mu["expected_props"]:
            expected[(mu["component"], p)] = mu["expected_band"]
    hits = total = 0
    off_by = []
    for f in findings:
        k = (f.node_key.split("@")[0], f.prop)
        if k not in expected:
            continue
        total += 1
        if f.severity == expected[k]:
            hits += 1
        else:
            off_by.append({"component": k[0], "prop": k[1],
                           "expected": expected[k], "got": f.severity})
    return {"checked": total, "correct": hits,
            "accuracy": round(hits / total, 4) if total else None,
            "mismatches": off_by[:8]}


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------
def run_pipeline(design, html, css, provider_kind, cassette, out_dir, run_id, ledger=None):
    provider = build_provider(provider_kind, cassette)
    rep = run_audit(design, html, [css], provider, out_dir=out_dir,
                    ledger_path=ledger, ignore_annotations=True, run_id=run_id)
    emitted = {(f.node_key.split("@")[0], f.prop) for f in rep.findings}
    return rep, emitted


def run_baseline(design, css):
    res = naive_diff.run(design, [css])
    emitted = {(f["component"], f["prop"]) for f in res["findings"]}
    return res, emitted


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--design", default=os.path.join(HERE, "cases", "design.spec.json"))
    ap.add_argument("--html", default=os.path.join(HERE, "cases", "checkout.html"))
    ap.add_argument("--clean-css", default=os.path.join(HERE, "cases", "checkout.css"))
    ap.add_argument("--cases", default=os.path.join(HERE, "cases", "generated", "cases.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    ap.add_argument("--provider", default="offline", choices=["anthropic", "replay", "offline"])
    ap.add_argument("--cassette", default=None)
    a = ap.parse_args(argv)

    with open(a.cases, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    os.makedirs(a.out, exist_ok=True)
    runs_dir = os.path.join(a.out, "runs")

    rows = []
    t_all = time.time()
    for case in manifest["cases"]:
        cid = case["case_id"]
        css = case["css_path"]
        if not os.path.isabs(css):
            css = os.path.join(ROOT, css)
        gt = derive_ground_truth(a.design, a.html, a.clean_css, css)

        t0 = time.time()
        b_res, b_emitted = run_baseline(a.design, css)
        b_time = time.time() - t0

        rep, p_emitted = run_pipeline(a.design, a.html, css, a.provider,
                                      a.cassette, runs_dir, f"eval-{cid}")

        row = {
            "case_id": cid,
            "label": case["label"],
            "mutation_count": len(case["mutations"]),
            "ground_truth_size": len(gt),
            "baseline": {**score(b_emitted, gt),
                         "catalogue": catalogue_recall(b_res["findings"], case["mutations"]),
                         "emitted": len(b_emitted),
                         "wall_seconds": round(b_time, 4),
                         "cost_usd": 0.0,
                         "severity": None},
            "pipeline": {**score(p_emitted, gt),
                         "catalogue": catalogue_recall(rep.findings, case["mutations"]),
                         "emitted": len(p_emitted),
                         "high_severity": sum(v for k, v in rep.stats["by_severity"].items()
                                              if k in ("blocker", "major")),
                         "wall_seconds": rep.stats["wall_seconds"],
                         "cost_usd": round(rep.stats["usage"]["cost_usd"], 6),
                         "severity": severity_accuracy(rep.findings, case["mutations"]),
                         "by_severity": rep.stats["by_severity"],
                         "verification": {k: v for k, v in rep.verification.items()
                                          if isinstance(v, (int, float))},
                         "tool_calls": rep.stats["tool_calls_total"],
                         "trajectory": os.path.basename(rep.trajectory_path)},
        }
        rows.append(row)
        print(f"{cid:9} gt={len(gt):3}  "
              f"baseline P={row['baseline']['precision']:.2f} R={row['baseline']['recall']:.2f} "
              f"F1={row['baseline']['f1']:.2f}   "
              f"pipeline P={row['pipeline']['precision']:.2f} R={row['pipeline']['recall']:.2f} "
              f"F1={row['pipeline']['f1']:.2f}")

    agg = aggregate(rows)
    out = {
        "provenance": {
            "provider": a.provider,
            "note": ("Figures produced with the deterministic offline policy. It is not a "
                     "language model; see docs/REPRODUCTION.md. Re-run with "
                     "--provider anthropic for live model figures."
                     if a.provider == "offline" else
                     f"Figures produced with provider={a.provider}."),
            "seed": manifest.get("seed"),
            "cases": len(rows),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_wall_seconds": round(time.time() - t_all, 2),
        },
        "aggregate": agg,
        "cases": rows,
    }
    path = os.path.join(a.out, f"eval_{a.provider}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)

    print_summary(agg, a.provider)
    print(f"\nwritten to {path}")
    return 0


def aggregate(rows: list[dict]) -> dict:
    defect = [r for r in rows if r["ground_truth_size"] > 0]
    control = [r for r in rows if r["ground_truth_size"] == 0]

    def pooled(side: str) -> dict:
        tp = sum(r[side]["tp"] for r in defect)
        fp = sum(r[side]["fp"] for r in defect)
        fn = sum(r[side]["fn"] for r in defect)
        p = tp / (tp + fp) if (tp + fp) else 0.0
        rc = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * p * rc / (p + rc) if (p + rc) else 0.0
        p_gt = sum(r[side]["plain"]["gt"] for r in defect)
        p_tp = sum(r[side]["plain"]["tp"] for r in defect)
        d_gt = sum(r[side]["derived"]["gt"] for r in defect)
        d_tp = sum(r[side]["derived"]["tp"] for r in defect)
        return {
            "plain_recall": round(p_tp / p_gt, 4) if p_gt else None,
            "plain_gt": p_gt, "plain_tp": p_tp,
            "derived_recall": round(d_tp / d_gt, 4) if d_gt else None,
            "derived_gt": d_gt, "derived_tp": d_tp,
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(p, 4), "recall": round(rc, 4), "f1": round(f1, 4),
            "macro_f1": round(statistics.mean([r[side]["f1"] for r in defect]), 4),
            "review_burden": sum(r[side]["emitted"] for r in defect),
            "false_positives_on_clean": sum(r[side]["fp"] for r in control),
            "wall_seconds": round(sum(r[side]["wall_seconds"] for r in rows), 3),
            "cost_usd": round(sum(r[side]["cost_usd"] for r in rows), 6),
            "catalogue_mutations": sum(r[side]["catalogue"]["mutations"] for r in defect),
            "catalogue_caught": sum(r[side]["catalogue"]["caught"] for r in defect),
            "catalogue_recall": round(
                sum(r[side]["catalogue"]["caught"] for r in defect)
                / max(sum(r[side]["catalogue"]["mutations"] for r in defect), 1), 4),
        }

    b, p = pooled("baseline"), pooled("pipeline")
    sev_checked = sum(r["pipeline"]["severity"]["checked"] for r in defect)
    sev_correct = sum(r["pipeline"]["severity"]["correct"] for r in defect)
    return {
        "baseline": b,
        "pipeline": {**p, "severity_accuracy":
                     round(sev_correct / sev_checked, 4) if sev_checked else None,
                     "severity_checked": sev_checked},
        "delta": {
            "recall_points": round((p["recall"] - b["recall"]) * 100, 1),
            "precision_points": round((p["precision"] - b["precision"]) * 100, 1),
            "f1_points": round((p["f1"] - b["f1"]) * 100, 1),
            "defects_found_additional": p["tp"] - b["tp"],
        },
    }


def print_summary(agg: dict, provider: str) -> None:
    b, p, d = agg["baseline"], agg["pipeline"], agg["delta"]
    print("\n" + "─" * 66)
    print(f"  AGGREGATE over defect cases          provider: {provider}")
    print("─" * 66)
    print(f"  {'metric':<30}{'baseline':>13}{'pipeline':>13}{'Δ':>9}")
    print(f"  {'-' * 62}")
    print(f"  {'defects found (TP)':<30}{b['tp']:>13}{p['tp']:>13}{p['tp'] - b['tp']:>+9}")
    print(f"  {'defects missed (FN)':<30}{b['fn']:>13}{p['fn']:>13}{p['fn'] - b['fn']:>+9}")
    print(f"  {'spurious (FP)':<30}{b['fp']:>13}{p['fp']:>13}{p['fp'] - b['fp']:>+9}")
    print(f"  {'precision':<30}{b['precision']:>13.3f}{p['precision']:>13.3f}"
          f"{d['precision_points']:>+8.1f}p")
    print(f"  {'recall':<30}{b['recall']:>13.3f}{p['recall']:>13.3f}"
          f"{d['recall_points']:>+8.1f}p")
    print(f"  {'F1':<30}{b['f1']:>13.3f}{p['f1']:>13.3f}{d['f1_points']:>+8.1f}p")
    print(f"  {'  · recall, plain properties':<30}{b['plain_recall']:>13.3f}"
          f"{p['plain_recall']:>13.3f}"
          f"{(p['plain_recall'] - b['plain_recall']) * 100:>+8.1f}p")
    print(f"  {'  · recall, derived relations':<30}{b['derived_recall']:>13.3f}"
          f"{p['derived_recall']:>13.3f}"
          f"{(p['derived_recall'] - b['derived_recall']) * 100:>+8.1f}p")
    print(f"  {'catalogue recall (independent)':<30}{b['catalogue_recall']:>13.3f}"
          f"{p['catalogue_recall']:>13.3f}"
          f"{(p['catalogue_recall'] - b['catalogue_recall']) * 100:>+8.1f}p")
    sa = p.get("severity_accuracy")
    print(f"  {'severity accuracy':<30}{'n/a':>13}"
          f"{(f'{sa:.3f}' if sa is not None else 'n/a'):>13}")
    print(f"  {'false positives on clean case':<30}{b['false_positives_on_clean']:>13}"
          f"{p['false_positives_on_clean']:>13}")
    print(f"  {'review burden (rows to read)':<30}{b['review_burden']:>13}{p['review_burden']:>13}")
    print(f"  {'wall seconds (all cases)':<30}{b['wall_seconds']:>13.2f}{p['wall_seconds']:>13.2f}")
    print(f"  {'cost USD (all cases)':<30}{b['cost_usd']:>13.4f}{p['cost_usd']:>13.4f}")
    print("─" * 66)


if __name__ == "__main__":
    sys.exit(main())
