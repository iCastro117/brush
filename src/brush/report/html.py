"""
The reviewer-facing report.

Design note, since this file is a design artefact as much as a code one: the
page is set on the same 4px grid the tool audits against, drawn faintly in the
background, and every measurement is shown on a shared axis so the reader sees
the distance rather than reading two numbers and subtracting them. Numbers are
monospaced and always carry their unit and sign. Nothing here is decorative --
the grid is the subject, and the drift bar is the finding.
"""
from __future__ import annotations

import html
import os
from datetime import datetime, timezone
from typing import Any

SEV_ORDER = ["blocker", "major", "minor", "info"]
SEV_LABEL = {
    "blocker": "Blocker", "major": "Major", "minor": "Minor", "info": "Info",
}
CHANNEL_LABEL = {
    "color": "Colour", "geometry": "Spacing & size",
    "typography": "Type", "effect": "Effects",
}


def _esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def _fmt(v: Any, unit: str = "") -> str:
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        if unit == "px":
            return f"{v:g}px"
        if unit == "ratio":
            return f"{v:+.1%}"
        if unit == "deltaE":
            return f"{v:.2f} ΔE"
        return f"{v:g}"
    return str(v)


def _drift_bar(design: Any, code: Any, unit: str) -> str:
    """
    The signature element: spec and code plotted on one axis.

    Two numbers in a table make a reader do the subtraction. A shared axis makes
    the distance the thing you see first, which is the whole point of the report.
    """
    try:
        d, c = float(design), float(code)
    except (TypeError, ValueError):
        return (f'<div class="drift drift--cat">'
                f'<span class="chip chip--spec">{_esc(design)}</span>'
                f'<span class="drift__arrow">→</span>'
                f'<span class="chip chip--code">{_esc(code)}</span></div>')

    lo, hi = min(d, c), max(d, c)
    span = hi - lo
    pad = max(span * 0.9, abs(hi) * 0.12, 1e-6)
    axis_lo, axis_hi = lo - pad, hi + pad
    width = axis_hi - axis_lo or 1.0
    p_d = (d - axis_lo) / width * 100
    p_c = (c - axis_lo) / width * 100
    left, right = min(p_d, p_c), max(p_d, p_c)

    return f"""<div class="drift">
  <div class="drift__track">
    <div class="drift__span" style="left:{left:.2f}%;width:{right - left:.2f}%"></div>
    <div class="drift__tick drift__tick--spec" style="left:{p_d:.2f}%"><i></i><b>spec</b></div>
    <div class="drift__tick drift__tick--code" style="left:{p_c:.2f}%"><i></i><b>code</b></div>
  </div>
  <div class="drift__legend">
    <span class="mono">{_fmt(d, unit if unit != 'ratio' else '')}</span>
    <span class="drift__delta mono">{_fmt(c - d, unit) if unit != 'ratio' else _fmt(c / d - 1 if d else 0, 'ratio')}</span>
    <span class="mono">{_fmt(c, unit if unit != 'ratio' else '')}</span>
  </div>
</div>"""


def _swatch(v: Any) -> str:
    s = str(v or "")
    if s.startswith("#") or s.startswith("rgb") or s.startswith("hsl"):
        return f'<i class="sw" style="background:{_esc(s)}"></i>'
    return ""


CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --paper:#FBFBFD; --ink:#14161A; --ink-2:#4C525C; --ink-3:#858B95;
  --rule:#E2E5EA; --rule-2:#F0F2F5;
  --instrument:#1B3A6B;
  --blocker:#B3261E; --major:#B26B00; --minor:#4C525C; --info:#858B95;
  --spec:#1B3A6B; --code:#B3261E;
  --grid:rgba(27,58,107,.055);
  --mono:ui-monospace,"SF Mono",SFMono-Regular,"JetBrains Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Inter,Helvetica,Arial,sans-serif;
}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
  font-size:15px;line-height:1.6;
  /* The 4px grid the tool audits against, drawn at 1/8 strength. */
  background-image:linear-gradient(var(--grid) 1px,transparent 1px),
                   linear-gradient(90deg,var(--grid) 1px,transparent 1px);
  background-size:32px 32px;
}
.wrap{max-width:940px;margin:0 auto;padding:48px 24px 96px}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}

/* masthead */
.mast{border-top:3px solid var(--ink);padding-top:16px;margin-bottom:40px}
.mast__row{display:flex;flex-wrap:wrap;gap:16px;align-items:baseline;justify-content:space-between}
.mast__id{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3)}
.mast h1{font-size:clamp(28px,5vw,42px);line-height:1.1;letter-spacing:-.022em;margin:12px 0 0;font-weight:640}
.mast__sub{color:var(--ink-2);margin:12px 0 0;max-width:62ch}
.mast__meta{display:flex;flex-wrap:wrap;gap:0;margin-top:28px;border:1px solid var(--rule);background:#fff}
.mast__meta div{flex:1 1 130px;padding:12px 16px;border-right:1px solid var(--rule)}
.mast__meta div:last-child{border-right:0}
.mast__meta dt{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);margin:0 0 4px}
.mast__meta dd{margin:0;font-family:var(--mono);font-size:14px}

/* headline */
.headline{border-left:3px solid var(--instrument);padding:4px 0 4px 20px;margin:40px 0 8px;
  font-size:19px;line-height:1.45;letter-spacing:-.01em}
.fine{color:var(--ink-2);font-size:14px;padding-left:23px;margin:0 0 40px}

/* score strip */
.tally{display:flex;border:1px solid var(--rule);background:#fff;margin:0 0 44px}
.tally div{flex:1;padding:16px;border-right:1px solid var(--rule);text-align:left}
.tally div:last-child{border-right:0}
.tally b{display:block;font-family:var(--mono);font-size:26px;line-height:1;letter-spacing:-.02em}
.tally span{display:block;font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);margin-top:8px}
.tally .t-blocker b{color:var(--blocker)} .tally .t-major b{color:var(--major)}

h2.sec{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);
  margin:56px 0 16px;padding-bottom:8px;border-bottom:1px solid var(--rule);font-weight:600}

/* root causes */
.cause{border:1px solid var(--rule);background:#fff;padding:18px 20px;margin-bottom:12px}
.cause h3{margin:0 0 8px;font-size:15.5px;font-weight:600;letter-spacing:-.005em}
.cause p{margin:0;color:var(--ink-2);font-size:14px}
.cause .ids{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px}
.tag{font-family:var(--mono);font-size:11px;padding:2px 7px;border:1px solid var(--rule);color:var(--ink-2);background:var(--rule-2)}

/* findings */
.f{border:1px solid var(--rule);background:#fff;margin-bottom:14px}
.f__bar{height:3px}
.f--blocker .f__bar{background:var(--blocker)} .f--major .f__bar{background:var(--major)}
.f--minor .f__bar{background:var(--minor)} .f--info .f__bar{background:var(--info)}
.f__head{display:flex;gap:14px;align-items:flex-start;padding:16px 20px 0}
.f__sev{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;
  padding:3px 8px;border:1px solid currentColor;white-space:nowrap;margin-top:2px}
.f--blocker .f__sev{color:var(--blocker)} .f--major .f__sev{color:var(--major)}
.f--minor .f__sev{color:var(--minor)} .f--info .f__sev{color:var(--info)}
.f__title{flex:1;min-width:0}
.f__title h3{margin:0;font-size:16px;font-weight:600;letter-spacing:-.008em}
.f__where{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);margin-top:4px}
.f__id{font-family:var(--mono);font-size:11px;color:var(--ink-3)}
.f__body{padding:14px 20px 18px}
.f__why{margin:0 0 14px;color:var(--ink-2);font-size:14.5px}
.f__fix{border-left:2px solid var(--instrument);padding:2px 0 2px 14px;font-size:14px;margin:14px 0 0}
.f__fix b{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);display:block;margin-bottom:3px;font-weight:600}
.laws{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.law{font-size:11.5px;padding:3px 9px;background:var(--rule-2);border:1px solid var(--rule);color:var(--ink-2)}
.ev{margin-top:12px;font-family:var(--mono);font-size:11px;color:var(--ink-3);word-break:break-all}
.ev b{color:var(--ink-2);font-weight:600}
.note{margin-top:10px;font-size:12.5px;color:var(--major);font-family:var(--mono)}

/* drift bar — the signature */
.drift{margin:16px 0 4px}
.drift__track{position:relative;height:30px;border-bottom:1px solid var(--rule);
  background-image:repeating-linear-gradient(90deg,var(--rule-2) 0 1px,transparent 1px 25%)}
.drift__span{position:absolute;bottom:0;height:9px;background:rgba(179,38,30,.13);
  border-left:1px solid rgba(179,38,30,.4);border-right:1px solid rgba(179,38,30,.4)}
.drift__tick{position:absolute;bottom:0;transform:translateX(-50%);text-align:center}
.drift__tick i{display:block;width:1px;height:22px;margin:0 auto;background:currentColor}
.drift__tick b{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;
  display:block;margin-bottom:2px;font-weight:500}
.drift__tick--spec{color:var(--spec)} .drift__tick--code{color:var(--code)}
.drift__legend{display:flex;justify-content:space-between;font-size:12.5px;color:var(--ink-3);margin-top:7px}
.drift__delta{color:var(--code);font-weight:600}
.drift--cat{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.chip{font-family:var(--mono);font-size:12.5px;padding:4px 9px;border:1px solid var(--rule);background:var(--rule-2)}
.chip--spec{border-left:2px solid var(--spec)} .chip--code{border-left:2px solid var(--code)}
.drift__arrow{color:var(--ink-3)}
.sw{display:inline-block;width:10px;height:10px;border:1px solid rgba(0,0,0,.2);margin-right:6px;vertical-align:-1px}

/* verification + footer */
.verif{border:1px solid var(--rule);background:#fff;padding:18px 20px}
.verif table{width:100%;border-collapse:collapse;font-size:14px}
.verif td{padding:7px 0;border-bottom:1px solid var(--rule-2)}
.verif td:last-child{text-align:right;font-family:var(--mono)}
.verif tr:last-child td{border-bottom:0}
.empty{border:1px solid var(--rule);background:#fff;padding:32px 20px;text-align:center;color:var(--ink-2)}
footer{margin-top:64px;padding-top:20px;border-top:1px solid var(--rule);
  font-size:12.5px;color:var(--ink-3);display:flex;flex-wrap:wrap;gap:12px;justify-content:space-between}
a{color:var(--instrument)}
@media (max-width:620px){
  .wrap{padding:32px 16px 64px}
  .tally{flex-wrap:wrap}.tally div{flex:1 1 50%;border-bottom:1px solid var(--rule)}
  .mast__meta div{flex:1 1 50%;border-bottom:1px solid var(--rule)}
  .f__head{flex-wrap:wrap}
}
@media print{body{background:#fff}.wrap{max-width:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""


def write_html_report(report, path: str, design_path: str = "", code_path: str = "") -> str:
    s = report.stats
    summary = report.summary or {}
    by_sev = s.get("by_severity", {})
    findings = sorted(
        report.findings,
        key=lambda f: (SEV_ORDER.index(f.severity) if f.severity in SEV_ORDER else 9,
                       f.node_key, f.prop),
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    tally = "".join(
        f'<div class="t-{k}"><b>{by_sev.get(k, 0)}</b><span>{SEV_LABEL[k]}</span></div>'
        for k in SEV_ORDER
    )
    tally += (f'<div><b>{s.get("measurements", 0)}</b><span>Measurements</span></div>'
              f'<div><b>{s.get("paired_nodes", 0)}</b><span>Components</span></div>')

    causes = ""
    for rc in summary.get("root_causes", [])[:6]:
        ids = "".join(f'<span class="tag">{_esc(i)}</span>'
                      for i in rc.get("finding_ids", [])[:10])
        causes += (f'<div class="cause"><h3>{_esc(rc.get("cause", ""))}</h3>'
                   f'<p>{_esc(rc.get("single_change", ""))}</p>'
                   f'<div class="ids">{ids}</div></div>')
    if not causes:
        causes = '<div class="empty">No shared root causes — every finding is independent.</div>'

    fixes = ""
    for i, fx in enumerate(summary.get("first_three_fixes", [])[:3], 1):
        fixes += (f'<div class="cause"><h3>{i}. {_esc(fx.get("change", ""))}</h3>'
                  f'<p>{_esc(fx.get("why", ""))} · <span class="mono">'
                  f'{_esc(fx.get("finding_id", ""))}</span></p></div>')

    body = ""
    for f in findings:
        laws = "".join(f'<span class="law">{_esc(l)}</span>' for l in f.ux_laws)
        ev = " ".join(f'<span>{_esc(e)}</span>' for e in f.evidence)
        note = f'<div class="note">{_esc(f.verifier_note)}</div>' if f.verifier_note else ""
        sw_d = _swatch(f.design_value) if f.channel == "color" else ""
        sw_c = _swatch(f.code_value) if f.channel == "color" else ""
        drift = _drift_bar(f.design_value, f.code_value, f.delta_unit)
        if f.channel == "color" and (sw_d or sw_c):
            drift = (f'<div class="drift drift--cat">'
                     f'<span class="chip chip--spec">{sw_d}{_esc(f.design_value)}</span>'
                     f'<span class="drift__arrow">→</span>'
                     f'<span class="chip chip--code">{sw_c}{_esc(f.code_value)}</span>'
                     f'<span class="drift__delta mono">{_fmt(f.delta, f.delta_unit)}</span></div>')
        fix = ""
        if f.suggested_fix:
            fix = f'<p class="f__fix"><b>Fix</b>{_esc(f.suggested_fix)}</p>'
        body += f"""<article class="f f--{f.severity}">
  <div class="f__bar"></div>
  <div class="f__head">
    <span class="f__sev">{SEV_LABEL.get(f.severity, f.severity)}</span>
    <div class="f__title">
      <h3>{_esc(f.title)}</h3>
      <div class="f__where">{_esc(f.node_key)} · {_esc(f.prop)} · {CHANNEL_LABEL.get(f.channel, f.channel)}</div>
    </div>
    <span class="f__id">{_esc(f.finding_id)}</span>
  </div>
  <div class="f__body">
    <p class="f__why">{_esc(f.rationale)}</p>
    {drift}
    {fix}
    <div class="laws">{laws}</div>
    <div class="ev"><b>evidence</b> {ev}</div>
    {note}
  </div>
</article>"""
    if not body:
        body = ('<div class="empty">No verified deviations. Every measured property '
                'matches the specification within tolerance.</div>')

    v = report.verification
    n_rej = v["rejected"] if isinstance(v["rejected"], int) else len(v["rejected"])
    n_cor = v["corrected"] if isinstance(v["corrected"], int) else len(v["corrected"])
    verif_rows = [
        ("Findings proposed by the diagnostician", v.get("proposed", 0)),
        ("Accepted after recomputation", v.get("accepted", 0)),
        ("Rejected — unsupported by any measurement", n_rej),
        ("Severity corrected by the verifier", n_cor),
        ("Suppressed by an approved deviation", v.get("suppressed_by_ledger", 0)),
        ("Tool calls made to gather evidence", s.get("tool_calls_total", 0)),
        ("Trajectory steps recorded", s.get("trajectory_steps", 0)),
    ]
    verif = "".join(f"<tr><td>{_esc(a)}</td><td>{_esc(b)}</td></tr>" for a, b in verif_rows)

    unmapped = s.get("unmapped_components") or []
    unmapped_note = ""
    if unmapped:
        unmapped_note = (
            f'<div class="cause"><h3>{len(unmapped)} specified component(s) not found '
            f'in the implementation</h3><p>The mapper declined to pair these rather than '
            f'guess: {_esc(", ".join(unmapped))}. They were not audited.</p></div>')

    missing = s.get("missing_states") or []
    missing_note = ""
    if missing:
        items = ", ".join(f"{m['component']} ({m['state']})" for m in missing)
        missing_note = (
            f'<div class="cause"><h3>{len(missing)} specified state(s) absent from the code</h3>'
            f'<p>The spec defines these states but the stylesheet never declares them: '
            f'{_esc(items)}. They are audited against the default state, so a missing focus '
            f'ring surfaces as an absent outline rather than a wrong value.</p></div>')

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Design conformance — {_esc(report.run_id)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<header class="mast">
  <div class="mast__row">
    <span class="mast__id">Brush · design-system conformance</span>
    <span class="mast__id">{_esc(report.run_id)}</span>
  </div>
  <h1>The implementation drifted from the spec in {len(findings)} place{'' if len(findings) == 1 else 's'}.</h1>
  <p class="mast__sub">Every value below was measured from the resolved CSS cascade and
  the design specification, then recomputed independently before it was allowed into this
  report. Nothing here rests on a model's assertion.</p>
  <dl class="mast__meta">
    <div><dt>Specification</dt><dd>{_esc(os.path.basename(design_path) or '—')}</dd></div>
    <div><dt>Implementation</dt><dd>{_esc(os.path.basename(code_path) or '—')}</dd></div>
    <div><dt>Engine</dt><dd>{_esc(s.get('provider', '—'))}</dd></div>
    <div><dt>Runtime</dt><dd>{_esc(s.get('wall_seconds', 0))}s</dd></div>
    <div><dt>Cost</dt><dd>${s.get('usage', {}).get('cost_usd', 0):.4f}</dd></div>
  </dl>
</header>

<p class="headline">{_esc(summary.get('headline', ''))}</p>
<p class="fine">{_esc(summary.get('what_is_fine', ''))}</p>

<div class="tally">{tally}</div>

<h2 class="sec">Start here</h2>
{fixes or '<div class="empty">Nothing to fix.</div>'}

<h2 class="sec">Root causes</h2>
{causes}
{unmapped_note}
{missing_note}

<h2 class="sec">Findings</h2>
{body}

<h2 class="sec">How this was verified</h2>
<div class="verif"><table>{verif}</table></div>

<footer>
  <span>Generated {generated} · run {_esc(report.run_id)} · engine {_esc(s.get('provider', ''))}</span>
  <span>Trajectory: {_esc(os.path.basename(report.trajectory_path))}</span>
</footer>

</div>
</body>
</html>"""

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path
