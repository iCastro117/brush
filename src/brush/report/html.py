"""
The reviewer-facing report — dashboard layout.

A fixed left sidebar navigates six sections: Dashboard, Root causes, Findings,
How this was verified, Step by step, and Packages. The last two exist because a
report travels: it gets forwarded to someone who has never installed the tool,
and the honest thing to hand them is the audit *and* the exact commands that
reproduce it, including what to type when the first command fails.

The logo slot loads `logo.png` from the same folder as the report; when the file
is absent a wordmark badge renders instead, so the page never shows a broken
image. Everything is self-contained — no CDN, no build step, works from file://.
"""
from __future__ import annotations

import html
import os
import platform
from datetime import datetime, timezone
from typing import Any

SEV_ORDER = ["blocker", "major", "minor", "info"]
SEV_LABEL = {"blocker": "Blocker", "major": "Major", "minor": "Minor", "info": "Info"}
SEV_PLURAL = {"blocker": "Blockers", "major": "Majors", "minor": "Minors", "info": "Info"}
CHANNEL_LABEL = {"color": "Color", "geometry": "Spacing & size",
                 "typography": "Type", "effect": "Effects"}


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


# ---------------------------------------------------------------------------
# CSS — kept as a plain string so braces need no escaping.
# ---------------------------------------------------------------------------
CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --bg:#F4F5FA;
  /* Glass surfaces sit on a violet-to-pink field. They are kept this opaque on
     purpose: this tool fails builds for WCAG contrast, so its own report has to
     clear AA. Every ink colour below was checked against the lightest point of
     the gradient seen through the panel. */
  --card:rgba(255,255,255,.72); --card-solid:#FFFFFF;
  --line:rgba(255,255,255,.55); --line-2:rgba(120,90,160,.13);
  --ink:#15121C; --ink-2:#413A52; --muted:#5E5670;
  --accent:#6D28D9; --accent-2:#7C3AED; --accent-soft:#F3EEFC; --accent-line:#E4D9FA;
  --ok:#16A34A; --ok-soft:#DCFCE7;
  --blocker:#DC2626; --blocker-soft:#FEE2E2;
  --major:#EA580C;  --major-soft:#FFEDD5;
  --minor:#CA8A04;  --minor-soft:#FEF9C3;
  --info:#2563EB;   --info-soft:#DBEAFE;
  --measure:#7C3AED; --measure-soft:#EDE9FE;
  --comp:#0891B2;   --comp-soft:#CFFAFE;
  --r:14px; --r-sm:10px;
  --shadow:0 1px 2px rgba(20,22,40,.05),0 8px 24px -12px rgba(20,22,40,.10);
  --sans:Inter,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,"Cascadia Code",Consolas,Menlo,monospace;
}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{margin:0;color:var(--ink);font-family:var(--sans);
  font-size:14.5px;line-height:1.55;position:relative;min-height:100vh}

/* The field. Fixed so it never scrolls out from under the glass, and painted
   with three soft radial pools rather than one linear ramp -- a ramp banding
   across 1400px reads as a gradient, pools read as light. */
body::before{content:"";position:fixed;inset:0;z-index:-2;
  background:
    radial-gradient(56% 46% at 10% 6%,  #B49CFC 0%, rgba(180,156,252,0) 62%),
    radial-gradient(54% 44% at 90% 2%,  #F98FCC 0%, rgba(249,143,204,0) 60%),
    radial-gradient(60% 54% at 80% 90%, #D488F0 0%, rgba(212,136,240,0) 62%),
    radial-gradient(52% 46% at 18% 94%, #93A6FC 0%, rgba(147,166,252,0) 60%),
    linear-gradient(150deg,#EFE7FF 0%,#FBE6F3 50%,#ECE5FF 100%);
  background-attachment:fixed}

/* Cursor layer. Pointer-events off so it never eats a click on the report. */
#liquid{position:fixed;inset:0;z-index:-1;pointer-events:none;
  filter:url(#goo) saturate(1.35);opacity:.8}
a{color:var(--accent);text-decoration:none}
code,.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}

/* ---------- shell ---------- */
.shell{display:grid;grid-template-columns:236px minmax(0,1fr);min-height:100vh}
.side{position:sticky;top:0;height:100vh;
  background:linear-gradient(180deg,rgba(255,255,255,.78),rgba(255,255,255,.62));
  -webkit-backdrop-filter:blur(22px) saturate(170%);
  backdrop-filter:blur(22px) saturate(170%);
  border-right:1px solid rgba(255,255,255,.6);display:flex;flex-direction:column;
  padding:22px 14px;gap:6px;box-shadow:1px 0 30px -18px rgba(76,29,149,.5)}
.main{padding:28px clamp(18px,3.4vw,44px) 72px;max-width:1220px;width:100%}

/* ---------- sidebar ---------- */
.brand{display:flex;align-items:center;gap:11px;padding:2px 8px 18px;
  border-bottom:1px solid var(--line-2);margin-bottom:14px}

/* The logo sits inside a thick glass lens that tilts toward the pointer. The
   tilt is small on purpose: enough to read as a physical object catching the
   light, not enough to make the wordmark hard to read while scrolling. */
.brand__lens{position:relative;width:46px;height:46px;flex:none;border-radius:15px;
  display:flex;align-items:center;justify-content:center;
  background:linear-gradient(150deg,rgba(255,255,255,.85),rgba(255,255,255,.35));
  border:1px solid rgba(255,255,255,.75);
  -webkit-backdrop-filter:blur(10px) saturate(180%);
  backdrop-filter:blur(10px) saturate(180%);
  box-shadow:0 6px 18px -8px rgba(76,29,149,.55),
             inset 0 1px 1px rgba(255,255,255,.9),
             inset 0 -6px 12px -8px rgba(109,40,217,.35);
  transform-style:preserve-3d;
  transition:transform .18s cubic-bezier(.2,.8,.3,1);
  will-change:transform}
/* Specular highlight; moves with the tilt via the same custom properties. */
.brand__lens::before{content:"";position:absolute;inset:0;border-radius:inherit;
  background:radial-gradient(60% 55% at calc(50% + var(--gx,0px) * 1.6)
    calc(28% + var(--gy,0px) * 1.6),rgba(255,255,255,.95),rgba(255,255,255,0) 70%);
  pointer-events:none}
.brand__lens img{width:30px;height:30px;object-fit:contain;display:block;
  filter:drop-shadow(0 1px 2px rgba(76,29,149,.35))}
.brand .mark{width:30px;height:30px;border-radius:9px;display:none;
  align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:15px;
  background:linear-gradient(140deg,var(--accent-2),#4C1D95)}
.brand b{font-size:19px;letter-spacing:.16em;font-weight:800}
.nav{display:flex;flex-direction:column;gap:2px}
.nav a{display:flex;align-items:center;gap:11px;padding:10px 12px;border-radius:11px;
  color:var(--ink-2);font-weight:550;font-size:13.8px;position:relative}
.nav a svg{width:18px;height:18px;flex:none;stroke:currentColor;fill:none;
  stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round;opacity:.85}
.nav a:hover{background:rgba(255,255,255,.75);color:var(--ink)}
.nav a.active{background:rgba(255,255,255,.9);color:var(--accent);
  box-shadow:0 2px 10px -4px rgba(109,40,217,.35)}
.nav a.active::before{content:"";position:absolute;left:-14px;top:9px;bottom:9px;
  width:3px;border-radius:3px;background:var(--accent)}
.side__foot{margin-top:auto;border-top:1px solid var(--line-2);padding:14px 8px 2px;
  font-size:12px;color:var(--muted)}
.side__foot b{display:block;color:var(--ink-2);font-weight:600}
.side__foot code{font-size:11px}

/* ---------- page head ---------- */
.phead{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:2px 0 20px}
.phead h1{font-size:24px;margin:0;letter-spacing:-.02em;font-weight:750}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:650;
  padding:4px 11px;border-radius:999px}
.pill--ok{background:rgba(220,252,231,.85);color:#14532D}
.phead .meta{width:100%;display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--muted);
  font-size:13px}

/* ---------- cards & layout ---------- */
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
  box-shadow:var(--shadow);
  -webkit-backdrop-filter:blur(18px) saturate(160%);
  backdrop-filter:blur(18px) saturate(160%)}
/* A single hairline of white along the top edge is what sells glass -- it reads
   as the lit rim of a thick pane. */
.card{position:relative}
.card::after{content:"";position:absolute;inset:0;border-radius:inherit;
  pointer-events:none;
  background:linear-gradient(180deg,rgba(255,255,255,.65),rgba(255,255,255,0) 38%);
  opacity:.55}
.sec{display:none;margin:8px 0 0}
.sec.view{display:block;animation:secIn .28s ease}
@keyframes secIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.sechead{padding:15px 20px;margin:0 0 14px}
.sechead h2{font-size:17px;letter-spacing:-.01em;margin:0 0 4px;font-weight:700}
.sechead .sub{color:var(--ink-2);font-size:13.5px;margin:0}

/* ---------- owner hero ---------- */
.owner{position:relative;z-index:20;display:flex;align-items:center;
  min-height:308px;padding:30px 500px 30px 30px;margin:0 0 16px;overflow:visible}
.owner__role{font-size:11px;letter-spacing:.15em;text-transform:uppercase;
  color:var(--accent);font-weight:750}
.owner__name{margin:7px 0 2px;font-size:31px;font-weight:800;letter-spacing:-.02em;
  background:linear-gradient(94deg,#6D28D9 10%,#DB2777 90%);
  -webkit-background-clip:text;background-clip:text;color:transparent}
.owner__event{margin:9px 0 13px;font-size:16.5px;font-weight:750;color:var(--ink)}
.owner__chips{display:flex;gap:9px;flex-wrap:wrap}
.chip-glass{display:inline-flex;align-items:center;padding:6px 15px;border-radius:999px;
  font-size:12.5px;font-weight:700;color:var(--accent);
  background:rgba(255,255,255,.55);border:1px solid rgba(255,255,255,.75);
  -webkit-backdrop-filter:blur(12px) saturate(160%);
  backdrop-filter:blur(12px) saturate(160%);
  box-shadow:0 4px 14px -8px rgba(109,40,217,.45),inset 0 1px 1px rgba(255,255,255,.9)}
.owner__art{position:absolute;right:6px;bottom:-4px;height:calc(100% + 100px);
  z-index:30;display:flex;align-items:flex-end;justify-content:flex-end;
  transition:transform .3s cubic-bezier(.2,.8,.3,1);will-change:transform;
  pointer-events:none}
.owner__art img{height:100%;width:auto;display:block;
  animation:heroFloat 6s ease-in-out infinite;
  filter:saturate(1.04) drop-shadow(0 22px 36px rgba(109,40,217,.30))}
@keyframes heroFloat{0%,100%{transform:translateY(0)}
  50%{transform:translateY(-9px)}}
@media (prefers-reduced-motion: reduce){.owner__art img{animation:none}}
.grid2{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:18px;align-items:start}

/* hero */
.hero{display:flex;gap:16px;margin:0 0 16px;
  background:linear-gradient(135deg,rgba(255,255,255,.80),rgba(253,242,250,.68));
  -webkit-backdrop-filter:blur(20px) saturate(165%);
  backdrop-filter:blur(20px) saturate(165%);
  border:1px solid rgba(255,255,255,.62);border-radius:var(--r);padding:20px 22px;
  box-shadow:var(--shadow)}
.hero__ic{width:44px;height:44px;flex:none;border-radius:13px;display:flex;
  align-items:center;justify-content:center;color:#fff;
  background:linear-gradient(140deg,var(--accent-2),#4C1D95);box-shadow:var(--shadow)}
.hero__ic svg{width:22px;height:22px;fill:currentColor}
.hero h3{margin:1px 0 6px;font-size:16.5px;font-weight:700}
.hero p{margin:0;color:var(--ink-2);font-size:13.5px;max-width:74ch}

/* meta strip */
.strip{display:flex;flex-wrap:wrap;margin-top:14px}
.strip>div{flex:1 1 150px;padding:13px 18px;border-right:1px solid var(--line-2);min-width:0}
.strip>div:last-child{border-right:0}
.strip dt{display:flex;align-items:center;gap:7px;font-size:10.5px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted);margin:0 0 5px;font-weight:650}
.strip dt svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:1.8}
.strip dd{margin:0;font-family:var(--mono);font-size:13.5px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}

/* stat cards */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));
  gap:12px;margin-top:16px}
.stat{padding:14px 16px;display:flex;flex-direction:column;gap:9px}
.stat .ic{width:34px;height:34px;border-radius:10px;display:flex;align-items:center;
  justify-content:center}
.stat .ic svg{width:17px;height:17px;stroke:currentColor;fill:none;stroke-width:2;
  stroke-linecap:round;stroke-linejoin:round}
.stat b{font-size:24px;line-height:1;letter-spacing:-.02em;font-family:var(--mono)}
.stat span{font-size:11px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--muted);font-weight:650}
.i-blocker{background:var(--blocker-soft);color:var(--blocker)}
.i-major{background:var(--major-soft);color:var(--major)}
.i-minor{background:var(--minor-soft);color:var(--minor)}
.i-info{background:var(--info-soft);color:var(--info)}
.i-measure{background:var(--measure-soft);color:var(--measure)}
.i-comp{background:var(--comp-soft);color:var(--comp)}

/* summary rail */
.rail .card{padding:18px}
.rail h4{margin:0 0 14px;font-size:14.5px;font-weight:700}
.donut{display:flex;gap:18px;align-items:center}
.donut__ring{width:128px;height:128px;border-radius:50%;flex:none;position:relative}
.donut__ring::after{content:"";position:absolute;inset:17px;
  background:rgba(255,255,255,.86);border-radius:50%;
  -webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px)}
.donut__num{position:absolute;inset:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;z-index:1}
.donut__num b{font-size:26px;font-family:var(--mono);letter-spacing:-.02em}
.donut__num span{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted);font-weight:650}
.legend{display:flex;flex-direction:column;gap:8px;font-size:13px;min-width:0}
.legend i{width:9px;height:9px;border-radius:3px;display:inline-block;margin-right:8px}
.legend .n{font-family:var(--mono);font-weight:650}
.legend .pc{color:var(--muted);margin-left:5px}
.kv{margin:16px 0 0;font-size:13px}
.kv div{display:flex;justify-content:space-between;gap:12px;padding:7px 0;
  border-bottom:1px solid var(--line-2)}
.kv div:last-child{border-bottom:0}
.kv dt{color:var(--muted)}
.kv dd{margin:0;font-weight:600;text-align:right}
.files{display:flex;flex-direction:column;gap:9px;margin-top:6px}
.file{display:flex;align-items:center;gap:11px;
  border:1px solid rgba(255,255,255,.6);background:rgba(255,255,255,.45);
  border-radius:var(--r-sm);padding:9px 12px}
.file .fic{width:30px;height:30px;border-radius:8px;flex:none;display:flex;
  align-items:center;justify-content:center;font-size:11px;font-weight:700}
.file b{font-size:13px;display:block}
.file span{font-size:11.5px;color:var(--muted)}
.actions{display:flex;flex-direction:column;gap:8px;margin-top:14px}
.btn{display:flex;align-items:center;justify-content:center;gap:8px;
  border:1px solid rgba(255,255,255,.65);border-radius:var(--r-sm);padding:9px 12px;
  color:var(--accent);font-weight:650;font-size:13px;
  background:rgba(255,255,255,.6);
  -webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);
  transition:transform .15s,background .15s}
.btn:hover{background:rgba(255,255,255,.85);transform:translateY(-1px)}
.btn svg{width:15px;height:15px;stroke:currentColor;fill:none;stroke-width:2;
  stroke-linecap:round;stroke-linejoin:round}

/* start here */
.start{margin-top:18px;padding:6px 18px}
.start h3{font-size:14.5px;margin:12px 0 6px}
.step{display:flex;gap:14px;align-items:flex-start;padding:13px 2px;
  border-bottom:1px solid var(--line-2)}
.step:last-child{border-bottom:0}
.step .no{width:26px;height:26px;flex:none;border-radius:50%;background:var(--accent);
  color:#fff;font-size:13px;font-weight:700;display:flex;align-items:center;
  justify-content:center;margin-top:1px}
.step b{font-weight:650;display:block}
.step span{font-size:12.5px;color:var(--muted)}

/* root causes */
.cause{padding:16px 18px;margin-bottom:12px}
.cause h3{margin:0 0 6px;font-size:14.8px;font-weight:650}
.cause p{margin:0;color:var(--ink-2);font-size:13.5px}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:11px}
.tag{font-family:var(--mono);font-size:11px;padding:3px 8px;border-radius:6px;
  background:rgba(255,255,255,.55);color:var(--ink-2);
  border:1px solid rgba(255,255,255,.6)}

/* findings */
.filters{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 14px}
.fbtn{border:1px solid rgba(255,255,255,.6);background:rgba(255,255,255,.62);
  -webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);
  border-radius:999px;padding:6px 14px;font-size:12.5px;font-weight:650;
  color:var(--ink-2);cursor:pointer;transition:transform .15s,background .15s}
.fbtn:hover{transform:translateY(-1px);background:rgba(255,255,255,.82)}
.fbtn .c{font-family:var(--mono);margin-left:5px;color:var(--muted)}
.fbtn.on{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
.f{margin-bottom:13px;overflow:hidden}
.f__head{display:flex;gap:13px;align-items:flex-start;padding:15px 18px 0}
.sev{font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;font-weight:750;
  padding:4px 10px;border-radius:999px;white-space:nowrap;margin-top:2px}
.sev--blocker{background:var(--blocker-soft);color:var(--blocker)}
.sev--major{background:var(--major-soft);color:var(--major)}
.sev--minor{background:var(--minor-soft);color:var(--minor)}
.sev--info{background:var(--info-soft);color:var(--info)}
.f__t{flex:1;min-width:0}
.f__t h3{margin:0;font-size:15px;font-weight:650}
.f__where{font-family:var(--mono);font-size:11.5px;color:var(--muted);margin-top:4px}
.f__id{font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.f__body{padding:12px 18px 17px}
.f__why{margin:0 0 12px;color:var(--ink-2);font-size:13.5px}
.fix{border-left:3px solid var(--accent);background:var(--accent-soft);
  border-radius:0 var(--r-sm) var(--r-sm) 0;padding:9px 13px;font-size:13.5px;margin:12px 0 0}
.fix b{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);
  display:block;margin-bottom:2px}
.laws{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}
.law{font-size:11.5px;padding:3px 9px;border-radius:6px;
  background:rgba(255,255,255,.55);border:1px solid rgba(255,255,255,.6);
  color:var(--ink-2)}
.ev{margin-top:11px;font-family:var(--mono);font-size:11px;color:var(--muted);
  word-break:break-all}
.ev b{color:var(--ink-2)}
.vnote{margin-top:9px;font-size:12.5px;color:var(--major);font-family:var(--mono)}

/* drift bar */
.drift{margin:13px 0 2px}
.drift__track{position:relative;height:30px;border-bottom:1px solid rgba(120,90,160,.25);
  background:repeating-linear-gradient(90deg,var(--line-2) 0 1px,transparent 1px 25%)}
.drift__span{position:absolute;bottom:0;height:9px;background:rgba(220,38,38,.12);
  border-left:1px solid rgba(220,38,38,.45);border-right:1px solid rgba(220,38,38,.45)}
.drift__tick{position:absolute;bottom:0;transform:translateX(-50%);text-align:center}
.drift__tick i{display:block;width:2px;height:20px;margin:0 auto;background:currentColor;
  border-radius:2px}
.drift__tick b{font-family:var(--mono);font-size:9.5px;letter-spacing:.09em;
  text-transform:uppercase;display:block;margin-bottom:2px}
.t-spec{color:var(--accent)} .t-code{color:var(--blocker)}
.drift__legend{display:flex;justify-content:space-between;font-size:12.5px;
  color:var(--muted);margin-top:6px}
.drift__delta{color:var(--blocker);font-weight:650}
.chips{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:13px 0 2px}
.chip{font-family:var(--mono);font-size:12.5px;padding:5px 10px;border-radius:8px;
  border:1px solid rgba(255,255,255,.6);background:rgba(255,255,255,.6)}
.chip--spec{border-left:3px solid var(--accent)}
.chip--code{border-left:3px solid var(--blocker)}
.sw{display:inline-block;width:11px;height:11px;border-radius:3px;
  border:1px solid rgba(0,0,0,.18);margin-right:7px;vertical-align:-1px}
.arrow{color:var(--muted)}

/* verified table */
.vtable{padding:6px 18px}
.vtable table{width:100%;border-collapse:collapse;font-size:13.5px}
.vtable td{padding:10px 2px;border-bottom:1px solid var(--line-2)}
.vtable tr:last-child td{border-bottom:0}
.vtable td:last-child{text-align:right;font-family:var(--mono);font-weight:650}

/* how-to (step by step + packages) */
.how{padding:4px 18px 10px}
.hstep{display:flex;gap:15px;padding:16px 0;border-bottom:1px solid var(--line-2)}
.hstep:last-child{border-bottom:0}
.hstep .no{width:28px;height:28px;flex:none;border-radius:9px;background:var(--accent-soft);
  color:var(--accent);font-weight:750;font-size:13px;display:flex;align-items:center;
  justify-content:center;margin-top:2px}
.hstep>div{flex:1;min-width:0}
.hstep h3{margin:0 0 4px;font-size:14.5px;font-weight:650}
.hstep p{margin:0 0 9px;color:var(--ink-2);font-size:13px}
pre.cmd{margin:8px 0;background:#171923;color:#E6E8F0;border-radius:var(--r-sm);
  padding:11px 14px;font-family:var(--mono);font-size:12.5px;line-height:1.65;
  overflow-x:auto;white-space:pre}
pre.cmd .c{color:#8B93AC}
.oslab{display:inline-block;font-size:10px;letter-spacing:.1em;text-transform:uppercase;
  font-weight:750;color:var(--muted);margin:6px 0 0}
.iferr{border:1px solid #FDE0C2;background:#FFF8F0;border-radius:var(--r-sm);
  padding:11px 14px;margin-top:10px;font-size:13px}
.iferr>b{display:flex;align-items:center;gap:7px;color:#B45309;font-size:12px;
  letter-spacing:.06em;text-transform:uppercase;margin-bottom:6px}
.iferr>b svg{width:14px;height:14px;flex:none;stroke:currentColor;fill:none;
  stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.iferr ul{margin:0;padding-left:18px}
.iferr li{margin:4px 0;color:var(--ink-2)}
.iferr code{background:#FFEEDC;border-radius:5px;padding:1px 6px;font-size:12px}

/* packages table */
.pkg{width:100%;border-collapse:collapse;font-size:13.5px}
.pkg th{text-align:left;font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--muted);padding:11px 10px;border-bottom:1px solid var(--line)}
.pkg td{padding:12px 10px;border-bottom:1px solid var(--line-2);vertical-align:top}
.pkg tr:last-child td{border-bottom:0}
.pkg .req{background:var(--accent-soft);color:var(--accent)}
.pkg .opt{background:var(--line-2);color:var(--ink-2)}
.pkg .pill{font-size:10.5px;padding:3px 9px}
.envnote{margin:14px 18px 16px;padding:11px 14px;border-radius:var(--r-sm);
  background:rgba(255,255,255,.5);border:1px solid rgba(255,255,255,.6);
  font-size:12.5px;color:var(--ink-2)}
.empty{padding:34px;text-align:center;color:var(--muted)}

footer{margin-top:44px;color:var(--muted);font-size:12px;display:flex;
  flex-wrap:wrap;gap:10px;justify-content:space-between}

@media (max-width:1060px){.grid2{grid-template-columns:1fr}.rail{order:-1}
  .owner{padding:24px 26px;min-height:0}
  .owner__art{position:static;height:230px;margin:0 auto 8px;justify-content:center}}
@media (max-width:840px){
  .shell{grid-template-columns:1fr}
  .side{position:static;height:auto;flex-direction:row;flex-wrap:wrap;align-items:center}
  .brand{border-bottom:0;padding-bottom:0;margin-bottom:0}
  .nav{flex-direction:row;flex-wrap:wrap}
  .nav a.active::before{display:none}
  .side__foot{display:none}
}
@media print{
  .side,.filters,.actions,#bubbles,.owner__art{display:none}
  .sec{display:block!important;margin:0 0 26px}
  .shell{grid-template-columns:1fr}
  body{background:#fff}
  .card{box-shadow:none}
}
"""

JS = """
/* ---- liquid trail following the cursor -------------------------------
   Original implementation, 2D canvas + an SVG gooey filter. No rims, no
   speculars, no discrete droplets: a chain of soft blobs eases after the
   pointer, and the goo filter (blur, then a hard alpha ramp) fuses them
   into one continuous streak that stretches on fast moves and pools when
   the pointer rests -- which is what liquid does. Kept dependency-free so
   the report still opens from file:// with no network.  */
(function(){
  var canvas = document.getElementById('liquid');
  if (!canvas || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    if (canvas) canvas.style.display = 'none';
    return;
  }
  var ctx = canvas.getContext('2d');
  if (!ctx) { canvas.style.display = 'none'; return; }

  var dpr = Math.min(window.devicePixelRatio || 1, 2);
  var W = 0, H = 0;
  function resize(){
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  window.addEventListener('resize', resize);

  var pointer = {x: W / 2, y: H / 2, has: false};
  window.addEventListener('pointermove', function(e){
    pointer.x = e.clientX; pointer.y = e.clientY; pointer.has = true;
  }, {passive: true});
  window.addEventListener('pointerleave', function(){ pointer.has = false; });

  // The chain: the head chases the pointer, every link chases the one before
  // it. Stiffer at the head, looser at the tail, so a flick stretches the
  // streak and a pause lets it pool back into a drop.
  var N = 16, chain = [];
  for (var i = 0; i < N; i++) chain.push({x: W / 2, y: H / 2});
  var presence = 0;   // fades the whole streak in and out smoothly

  function blob(x, y, r, hue, a){
    var g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0,  'hsla(' + hue + ',95%,72%,' + a + ')');
    g.addColorStop(.7, 'hsla(' + hue + ',90%,70%,' + (a * .85) + ')');
    g.addColorStop(1,  'hsla(' + hue + ',88%,68%,0)');
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(x, y, r, 0, 6.283); ctx.fill();
  }

  function frame(){
    ctx.clearRect(0, 0, W, H);
    presence += ((pointer.has ? 1 : 0) - presence) * 0.06;

    chain[0].x += (pointer.x - chain[0].x) * 0.30;
    chain[0].y += (pointer.y - chain[0].y) * 0.30;
    for (var i = 1; i < N; i++) {
      var k = 0.42 - i * 0.012;
      chain[i].x += (chain[i-1].x - chain[i].x) * k;
      chain[i].y += (chain[i-1].y - chain[i].y) * k;
    }

    if (presence > 0.02) {
      for (var i = N - 1; i >= 0; i--) {
        var t = i / (N - 1);
        var r = (30 - t * 21) * presence;         // 30px head -> 9px tail
        var hue = 268 + t * 56;                    // violet head -> pink tail
        blob(chain[i].x, chain[i].y, r, hue, 0.5 * presence * (1 - t * 0.45));
      }
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  // The logo lens still tilts toward the pointer.
  var lens = document.getElementById('lens');
  var art = document.getElementById('heroArt');
  if (lens) {
    window.addEventListener('pointermove', function(e){
      var b = lens.getBoundingClientRect();
      var dx = (e.clientX - (b.left + b.width / 2)) / window.innerWidth;
      var dy = (e.clientY - (b.top + b.height / 2)) / window.innerHeight;
      lens.style.transform = 'perspective(420px) rotateX(' +
        Math.max(-14, Math.min(14, -dy * 26)) + 'deg) rotateY(' +
        Math.max(-14, Math.min(14,  dx * 26)) + 'deg)';
      lens.style.setProperty('--gx', (dx * 9).toFixed(2) + 'px');
      lens.style.setProperty('--gy', (dy * 9).toFixed(2) + 'px');
      if (art) {
        // Page-centred coordinates: the lens uses its own centre, but the
        // floating art should answer to where the pointer is on screen.
        var ax = e.clientX / window.innerWidth - 0.5;
        var ay = e.clientY / window.innerHeight - 0.5;
        art.style.transform =
          'translate3d(' + (ax * 10).toFixed(1) + 'px,' +
          (ay * 7).toFixed(1) + 'px,0)';
      }
    }, {passive: true});
  }
})();

(function(){
  var links = document.querySelectorAll('.nav a[href^="#"]');
  /* Each section is its own page. Clicking the sidebar shows that section
     alone and returns to the top -- no scrolling across one long document. */
  function show(id){
    document.querySelectorAll('.sec').forEach(function(sec){
      sec.classList.toggle('view', sec.id === id);
    });
    links.forEach(function(a){
      a.classList.toggle('active', a.getAttribute('href') === '#' + id);
    });
    window.scrollTo(0, 0);
  }
  links.forEach(function(a){
    a.addEventListener('click', function(e){
      e.preventDefault();
      var id = a.getAttribute('href').slice(1);
      show(id);
      if (history.replaceState) history.replaceState(null, '', '#' + id);
    });
  });
  var initial = (location.hash || '#dashboard').slice(1);
  if (!document.getElementById(initial)) initial = 'dashboard';
  show(initial);

  var btns = document.querySelectorAll('.fbtn');
  btns.forEach(function(b){
    b.addEventListener('click', function(){
      btns.forEach(function(x){ x.classList.remove('on'); });
      b.classList.add('on');
      var want = b.getAttribute('data-sev');
      document.querySelectorAll('.f').forEach(function(card){
        card.style.display =
          (want === 'all' || card.getAttribute('data-sev') === want) ? '' : 'none';
      });
    });
  });
})();
"""

# Small inline icon set (stroke inherits currentColor).
IC = {
    "home": '<svg viewBox="0 0 24 24"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/></svg>',
    "target": '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/></svg>',
    "list": '<svg viewBox="0 0 24 24"><path d="M8 6h13M8 12h13M8 18h13"/><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01"/></svg>',
    "shield": '<svg viewBox="0 0 24 24"><path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="m9 12 2 2 4-4"/></svg>',
    "term": '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="m7 9 3 3-3 3M13 15h4"/></svg>',
    "box": '<svg viewBox="0 0 24 24"><path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/></svg>',
    "doc": '<svg viewBox="0 0 24 24"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/></svg>',
    "code": '<svg viewBox="0 0 24 24"><path d="m8 8-4 4 4 4M16 8l4 4-4 4"/></svg>',
    "cloud": '<svg viewBox="0 0 24 24"><path d="M7 18a4 4 0 1 1 .6-7.96A5.5 5.5 0 0 1 18.3 12 3.5 3.5 0 0 1 17.5 18z"/></svg>',
    "clock": '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    "dollar": '<svg viewBox="0 0 24 24"><path d="M12 2v20M16.5 6.5c-1-1.2-2.6-1.7-4.5-1.7-2.5 0-4.2 1.3-4.2 3.2 0 4.4 9 2.3 9 6.6 0 2-1.9 3.3-4.6 3.3-2.1 0-3.9-.7-4.9-2"/></svg>',
    "alert": '<svg viewBox="0 0 24 24"><path d="M12 3 2.5 20h19z"/><path d="M12 9.5V14M12 17h.01"/></svg>',
    "warn": '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7.5V13M12 16.5h.01"/></svg>',
    "info": '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5h.01"/></svg>',
    "ruler": '<svg viewBox="0 0 24 24"><rect x="2.5" y="8.5" width="19" height="7" rx="1.5" transform="rotate(-20 12 12)"/><path d="m8 13.6 1-2.6M12 12l1-2.6M16 10.5l1-2.6" transform="rotate(0)"/></svg>',
    "comp": '<svg viewBox="0 0 24 24"><rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1.5"/><rect x="13" y="3.5" width="7.5" height="7.5" rx="1.5"/><rect x="3.5" y="13" width="7.5" height="7.5" rx="1.5"/><rect x="13" y="13" width="7.5" height="7.5" rx="1.5"/></svg>',
    "dl": '<svg viewBox="0 0 24 24"><path d="M12 4v11m0 0 4-4m-4 4-4-4"/><path d="M4 19h16"/></svg>',
    "eye": '<svg viewBox="0 0 24 24"><path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="2.6"/></svg>',
    "spark": '<svg viewBox="0 0 24 24"><path d="M12 2.5 14 9l6.5 2L14 13l-2 6.5L10 13l-6.5-2L10 9z"/></svg>',
}


def _drift(design: Any, code: Any, unit: str, is_color: bool) -> str:
    if is_color:
        sw_d = f'<i class="sw" style="background:{_esc(design)}"></i>' if str(design).startswith(("#", "rgb", "hsl")) else ""
        sw_c = f'<i class="sw" style="background:{_esc(code)}"></i>' if str(code).startswith(("#", "rgb", "hsl")) else ""
        return (f'<div class="chips"><span class="chip chip--spec">{sw_d}{_esc(design)}</span>'
                f'<span class="arrow">→</span>'
                f'<span class="chip chip--code">{sw_c}{_esc(code)}</span></div>')
    try:
        d, c = float(design), float(code)
    except (TypeError, ValueError):
        return (f'<div class="chips"><span class="chip chip--spec">{_esc(design)}</span>'
                f'<span class="arrow">→</span>'
                f'<span class="chip chip--code">{_esc(code)}</span></div>')
    lo, hi = min(d, c), max(d, c)
    pad = max((hi - lo) * 0.9, abs(hi) * 0.12, 1e-6)
    a_lo, a_hi = lo - pad, hi + pad
    width = a_hi - a_lo or 1.0
    p_d, p_c = (d - a_lo) / width * 100, (c - a_lo) / width * 100
    left, right = min(p_d, p_c), max(p_d, p_c)
    delta = (_fmt(c - d, unit) if unit != "ratio"
             else _fmt((c / d - 1) if d else 0, "ratio"))
    axis_lo, axis_hi = (d, c) if p_d <= p_c else (c, d)
    return f"""<div class="drift">
  <div class="drift__track">
    <div class="drift__span" style="left:{left:.2f}%;width:{right - left:.2f}%"></div>
    <div class="drift__tick t-spec" style="left:{p_d:.2f}%"><b>spec</b><i></i></div>
    <div class="drift__tick t-code" style="left:{p_c:.2f}%"><b>code</b><i></i></div>
  </div>
  <div class="drift__legend"><span class="mono">{_fmt(axis_lo, unit if unit != 'ratio' else '')}</span>
  <span class="drift__delta mono">{delta}</span>
  <span class="mono">{_fmt(axis_hi, unit if unit != 'ratio' else '')}</span></div>
</div>"""


def _donut(by_sev: dict, total: int) -> str:
    colors = {"blocker": "var(--blocker)", "major": "var(--major)",
              "minor": "var(--minor)", "info": "var(--info)"}
    stops, acc = [], 0.0
    for k in SEV_ORDER:
        n = by_sev.get(k, 0)
        if not n or not total:
            continue
        share = n / total * 100
        stops.append(f"{colors[k]} {acc:.2f}% {acc + share:.2f}%")
        acc += share
    grad = f"conic-gradient({','.join(stops)})" if stops else "conic-gradient(var(--line) 0 100%)"
    legend = "".join(
        f'<div><i style="background:{colors[k]}"></i>'
        f'<span class="n">{by_sev.get(k, 0)}</span> {SEV_PLURAL[k]}'
        f'<span class="pc">({(by_sev.get(k, 0) / total * 100 if total else 0):.0f}%)</span></div>'
        for k in SEV_ORDER
    )
    return f"""<div class="donut">
  <div class="donut__ring" style="background:{grad}">
    <div class="donut__num"><b>{total}</b><span>Total</span></div>
  </div>
  <div class="legend">{legend}</div>
</div>"""


def _step_by_step() -> str:
    """The execution walkthrough, mirrored from the user manual, in English."""
    def step(n, title, intro, blocks, iferr=None):
        cmds = ""
        for oslabel, code in blocks:
            lab = f'<span class="oslab">{_esc(oslabel)}</span>' if oslabel else ""
            cmds += f'{lab}<pre class="cmd">{code}</pre>'
        err = ""
        if iferr:
            items = "".join(f"<li>{i}</li>" for i in iferr)
            err = (f'<div class="iferr"><b>{IC["alert"]} If it fails</b>'
                   f"<ul>{items}</ul></div>")
        return (f'<div class="hstep"><div class="no">{n}</div><div>'
                f"<h3>{_esc(title)}</h3><p>{intro}</p>{cmds}{err}</div></div>")

    s = ""
    s += step(1, "Check Python",
        "Brush needs Python 3.10 or newer. Nothing else for the core audit.",
        [("Windows PowerShell", "python --version"),
         ("macOS / Linux", "python3 --version")],
        ["<code>python3</code> is not recognized on Windows — that is normal. "
         "Use <code>python</code>, or try <code>py --version</code>.",
         "Typing <code>python</code> opens the Microsoft Store — disable the alias in "
         "<i>Settings → Apps → App execution aliases</i>, then install from python.org "
         "and tick <b>Add Python to PATH</b>.",
         "Neither works — install with <code>winget install Python.Python.3.12</code> "
         "and open a <b>new</b> terminal."])
    s += step(2, "Verify the install",
        "One command checks the interpreter, the package, the knowledge pack, the "
        "color engine and a full end-to-end audit. Six lines must say <b>ok</b>.",
        [("Windows PowerShell", "python run.py doctor"),
         ("macOS / Linux", "python3 run.py doctor")],
        ["Any <b>FAIL</b> line prints the exact command that fixes it — run that, "
         "then run doctor again.",
         "<code>No module named brush</code> — you are in the wrong folder. "
         "<code>cd</code> to the repo root (it contains <code>run.py</code>)."])
    s += step(3, "Generate the evaluation cases",
        "Builds 12 mutated stylesheets with known defects, seeded and deterministic.",
        [("", "python eval/mutations.py")])
    s += step(4, "Run the test suite",
        "27 tests across four files. All four must end in <b>PASSED</b>.",
        [("", "python tests/test_integrity.py\n"
              "python tests/test_verifier.py\n"
              "python tests/test_clean_control.py\n"
              "python tests/test_cli_errors.py")],
        ["<code>make: not recognized</code> — <code>make</code> does not exist on "
         "Windows; the plain commands above do the same thing."])
    s += step(5, "Run the evaluation",
        "Baseline vs Brush over the 12 cases. This prints the metrics table.",
        [("", "python eval/run_eval.py")])
    s += step(6, "Audit the hard case and open this report",
        "17 defects injected at once. Keep the command on <b>one line</b> — "
        "PowerShell does not accept <code>\\</code> as a line continuation.",
        [("Windows PowerShell",
          "python run.py audit --design eval/cases/design.spec.json "
          "--html eval/cases/checkout.html --css eval/cases/generated/case_01.css "
          "--out out --run-id demo\nstart out\\demo.report.html"),
         ("macOS / Linux",
          "python3 run.py audit --design eval/cases/design.spec.json \\\n"
          "  --html eval/cases/checkout.html \\\n"
          "  --css eval/cases/generated/case_01.css --out out --run-id demo\n"
          "open out/demo.report.html")],
        ["<code>… not found: …</code> with a suggestion — a typo in a path; Brush "
         "names the nearest real file.",
         "<code>no components could be paired</code> — the HTML has none of the "
         "elements the spec describes; check <code>selector_hint</code>."])
    s += step(7, "Audit the clean file — expect zero findings",
        "The control run. A correct detector reports nothing here; this is the "
        "proof there are no false positives.",
        [("", "python run.py audit --design eval/cases/design.spec.json "
              "--html eval/cases/checkout.html --css eval/cases/checkout.css "
              "--out out --run-id clean")])
    s += step(8, "Score the review workbook (Excel)",
        "Audits every row of the spreadsheet and writes the scored workbook back.",
        [("Windows PowerShell",
          "pip install openpyxl\n"
          "python run.py batch --sheet eval/cases/brush_cases.xlsx "
          "--base-dir . --out out\\results.xlsx\nstart out\\results.xlsx")],
        ["<code>spreadsheet mode needs openpyxl</code> — "
         "<code>pip install openpyxl</code> (only these two commands need it).",
         "<code>Defaulting to user installation…</code> is fine — pip installed it "
         "for your user account.",
         "<code>could not find the header row</code> — the first row needs "
         "<code>ID</code> plus <code>IMAGE/FIGMA</code> or <code>CODE</code>; "
         "<code>python run.py template --out cases.xlsx</code> writes a valid sheet."])
    return f'<div class="card how">{s}</div>'


def _packages(provider: str) -> str:
    rows = [
        ("Python", "3.10 or newer", "req", "Required",
         "The whole audit engine — CSS cascade, color math, agents, verifier — is "
         "standard library only.",
         "winget install Python.Python.3.12   # Windows\n"
         "brew install python@3.12            # macOS\n"
         "sudo apt install python3.12         # Ubuntu/Debian",
         "python --version"),
        ("openpyxl", "3.1 or newer", "opt", "Optional",
         "Only for spreadsheet mode: <code>batch</code> and <code>template</code>. "
         "Every other command runs without it.",
         "pip install openpyxl",
         "pip show openpyxl"),
        ("anthropic", "0.40 or newer", "opt", "Optional",
         "Only for live model runs (<code>--provider anthropic</code>) and for "
         "reading mockup images. The offline provider needs no key and no SDK.",
         "pip install anthropic\n"
         "$env:ANTHROPIC_API_KEY=\"sk-ant-...\"   # Windows PowerShell\n"
         "export ANTHROPIC_API_KEY=sk-ant-...    # macOS / Linux",
         "pip show anthropic"),
        ("git", "any recent", "opt", "Optional",
         "Only to clone the repository or publish it. The zip needs no git at all.",
         "winget install Git.Git              # Windows\n"
         "https://git-scm.com/downloads",
         "git --version"),
    ]
    body = ""
    for name, ver, cls, badge, why, install, verify in rows:
        body += (f"<tr><td><b>{_esc(name)}</b><br>"
                 f'<span class="mono" style="color:var(--muted);font-size:12px">{_esc(ver)}</span></td>'
                 f'<td><span class="pill {cls}">{badge}</span></td>'
                 f"<td>{why}</td>"
                 f'<td><pre class="cmd" style="margin:0">{_esc(install)}</pre></td>'
                 f'<td><code>{_esc(verify)}</code></td></tr>')

    try:
        import openpyxl  # noqa: PLC0415
        xl = f"openpyxl {openpyxl.__version__}"
    except ImportError:
        xl = "openpyxl not installed"
    env = (f"This report was generated with Python "
           f"{platform.python_version()} on {platform.system()} "
           f"{platform.machine()} · {xl} · engine <code>{_esc(provider)}</code>"
           + (" — a deterministic policy, not a language model"
              if provider == "offline" else ""))

    return f"""<div class="card" style="overflow:auto">
<table class="pkg">
<tr><th>Package</th><th></th><th>What it is for</th><th>Install</th><th>Verify</th></tr>
{body}
</table>
<div class="envnote">{env}. A one-command check of all of the above:
<code>python run.py doctor</code>.</div>
</div>"""


def write_html_report(report, path: str, design_path: str = "", code_path: str = "") -> str:
    s = report.stats
    summary = report.summary or {}
    by_sev = s.get("by_severity", {})
    provider = s.get("provider", "—")
    findings = sorted(
        report.findings,
        key=lambda f: (SEV_ORDER.index(f.severity) if f.severity in SEV_ORDER else 9,
                       f.node_key, f.prop),
    )
    total = len(findings)
    generated = datetime.now(timezone.utc).strftime("%B %d, %Y — %H:%M UTC")
    clean = s.get("paired_nodes", 0) - len({f.node_key for f in findings})
    audit_json = f"{report.run_id}.audit.json"
    traj_md = os.path.basename(report.trajectory_path).replace(".jsonl", ".md") \
        if report.trajectory_path else ""

    # ---- dashboard pieces ----------------------------------------------
    strip = ""
    for icon, label, value in [
        ("doc", "Specification", os.path.basename(design_path) or "—"),
        ("code", "Implementation", os.path.basename(code_path) or "—"),
        ("cloud", "Engine", provider),
        ("clock", "Runtime", f"{s.get('wall_seconds', 0)}s"),
        ("dollar", "Cost", f"${s.get('usage', {}).get('cost_usd', 0):.4f}"),
    ]:
        strip += (f"<div><dt>{IC[icon]} {label}</dt>"
                  f"<dd title=\"{_esc(value)}\">{_esc(value)}</dd></div>")

    stats_cards = ""
    for key, icon, label, val in [
        ("blocker", "alert", "Blockers", by_sev.get("blocker", 0)),
        ("major", "warn", "Majors", by_sev.get("major", 0)),
        ("minor", "warn", "Minors", by_sev.get("minor", 0)),
        ("info", "info", "Info", by_sev.get("info", 0)),
        ("measure", "ruler", "Measurements", s.get("measurements", 0)),
        ("comp", "comp", "Components", s.get("paired_nodes", 0)),
    ]:
        stats_cards += (f'<div class="card stat"><span class="ic i-{key}">{IC[icon]}</span>'
                        f"<b>{val}</b><span>{label}</span></div>")

    start = ""
    for i, fx in enumerate(summary.get("first_three_fixes", [])[:3], 1):
        start += (f'<div class="step"><div class="no">{i}</div><div>'
                  f"<b>{_esc(fx.get('change', ''))}</b>"
                  f"<span>{_esc(fx.get('why', ''))} · "
                  f'<span class="mono">{_esc(fx.get("finding_id", ""))}</span></span>'
                  f"</div></div>")
    start_card = (f'<div class="card start"><h3>Start here</h3>{start}</div>'
                  if start else "")

    tol_pct = 0
    if s.get("measurements"):
        tol_pct = round((s["measurements"] - s.get("out_of_tolerance", 0))
                        / s["measurements"] * 100)
    kv = "".join(
        f"<div><dt>{a}</dt><dd>{_esc(b)}</dd></div>"
        for a, b in [
            ("Run", report.run_id), ("Date", generated.split(" — ")[0]),
            ("Status", "Completed"),
            ("Measurements in tolerance", f"{tol_pct}%"),
            ("Total findings", total),
            ("Total measurements", s.get("measurements", 0)),
            ("Components audited", s.get("paired_nodes", 0)),
            ("Conforming components", max(clean, 0)),
            ("Tool calls", s.get("tool_calls_total", 0)),
            ("Analysis time", f"{s.get('wall_seconds', 0)} s"),
        ]
    )
    files = f"""<div class="files">
  <div class="file"><span class="fic" style="background:var(--accent-soft);color:var(--accent)">SPEC</span>
    <div><b>{_esc(os.path.basename(design_path) or '—')}</b><span>design source of truth</span></div></div>
  <div class="file"><span class="fic" style="background:var(--comp-soft);color:var(--comp)">&lt;/&gt;</span>
    <div><b>{_esc(os.path.basename(code_path) or '—')}</b><span>implementation under audit</span></div></div>
</div>"""
    rail = f"""<aside class="rail">
<div class="card">
  <h4>Comparison summary</h4>
  {_donut(by_sev, total)}
  <dl class="kv">{kv}</dl>
  <h4 style="margin-top:18px">Files compared</h4>
  {files}
  <div class="actions">
    <a class="btn" href="{_esc(audit_json)}">{IC['eye']} View full JSON</a>
    <a class="btn" href="{_esc(traj_md)}">{IC['dl']} Agent trajectory</a>
  </div>
</div>
</aside>"""

    # ---- root causes ----------------------------------------------------
    causes = ""
    for rc in summary.get("root_causes", [])[:6]:
        tags = "".join(f'<span class="tag">{_esc(i)}</span>'
                       for i in rc.get("finding_ids", [])[:10])
        causes += (f'<div class="card cause"><h3>{_esc(rc.get("cause", ""))}</h3>'
                   f'<p>{_esc(rc.get("single_change", ""))}</p>'
                   f'<div class="tags">{tags}</div></div>')
    if not causes:
        causes = ('<div class="card empty">No shared root causes — every finding '
                  "is independent.</div>")
    for extra_key, title, tmpl in [
        ("unmapped_components",
         "specified component(s) not found in the implementation",
         "The mapper declined to pair these rather than guess: {items}. "
         "They were not audited."),
        ("missing_states", "specified state(s) absent from the code",
         "The spec defines these states but the stylesheet never declares them: "
         "{items}. A missing focus ring surfaces here as an absent outline "
         "rather than a wrong value."),
    ]:
        vals = s.get(extra_key) or []
        if vals:
            items = ", ".join(v if isinstance(v, str)
                              else f"{v['component']} ({v['state']})" for v in vals)
            causes += (f'<div class="card cause"><h3>{len(vals)} {title}</h3>'
                       f"<p>{_esc(tmpl.format(items=items))}</p></div>")

    # ---- findings -------------------------------------------------------
    filters = '<button class="fbtn on" data-sev="all">All<span class="c">{}</span></button>'.format(total)
    for k in SEV_ORDER:
        filters += (f'<button class="fbtn" data-sev="{k}">{SEV_PLURAL[k]}'
                    f'<span class="c">{by_sev.get(k, 0)}</span></button>')

    fcards = ""
    for f in findings:
        laws = "".join(f'<span class="law">{_esc(l)}</span>' for l in f.ux_laws)
        ev = " ".join(f"<span>{_esc(e)}</span>" for e in f.evidence)
        note = f'<div class="vnote">{_esc(f.verifier_note)}</div>' if f.verifier_note else ""
        fix = (f'<div class="fix"><b>Fix</b>{_esc(f.suggested_fix)}</div>'
               if f.suggested_fix else "")
        fcards += f"""<article class="card f" data-sev="{f.severity}">
  <div class="f__head">
    <span class="sev sev--{f.severity}">{SEV_LABEL.get(f.severity, f.severity)}</span>
    <div class="f__t"><h3>{_esc(f.title)}</h3>
      <div class="f__where">{_esc(f.node_key)} · {_esc(f.prop)} · {CHANNEL_LABEL.get(f.channel, f.channel)}</div></div>
    <span class="f__id">{_esc(f.finding_id)}</span>
  </div>
  <div class="f__body">
    <p class="f__why">{_esc(f.rationale)}</p>
    {_drift(f.design_value, f.code_value, f.delta_unit, f.channel == "color")}
    {fix}
    <div class="laws">{laws}</div>
    <div class="ev"><b>evidence</b> {ev}</div>
    {note}
  </div>
</article>"""
    if not fcards:
        fcards = ('<div class="card empty">No verified deviations. Every measured '
                  "property matches the specification within tolerance.</div>")

    # ---- verified -------------------------------------------------------
    v = report.verification
    n_rej = v["rejected"] if isinstance(v["rejected"], int) else len(v["rejected"])
    n_cor = v["corrected"] if isinstance(v["corrected"], int) else len(v["corrected"])
    vrows = "".join(f"<tr><td>{_esc(a)}</td><td>{_esc(b)}</td></tr>" for a, b in [
        ("Findings proposed by the diagnostician", v.get("proposed", 0)),
        ("Accepted after independent recomputation", v.get("accepted", 0)),
        ("Rejected — unsupported by any measurement", n_rej),
        ("Severity corrected by the verifier", n_cor),
        ("Suppressed by a human-approved deviation", v.get("suppressed_by_ledger", 0)),
        ("Tool calls made to gather evidence", s.get("tool_calls_total", 0)),
        ("Trajectory steps recorded", s.get("trajectory_steps", 0)),
    ])

    hero_sub = summary.get(
        "what_is_fine",
        "Every value was measured from the resolved CSS cascade and the design "
        "specification, then recomputed independently before it was allowed into "
        "this report.")

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brush — Design Conformance Report · {_esc(report.run_id)}</title>
<style>{CSS}</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <filter id="goo"><feGaussianBlur in="SourceGraphic" stdDeviation="11" result="b"/>
  <feColorMatrix in="b" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 24 -11"/></filter>
</svg>
<canvas id="liquid" aria-hidden="true"></canvas>
<div class="shell">

<nav class="side">
  <div class="brand">
    <div class="brand__lens" id="lens">
      <img src="logo.png" alt="" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
      <span class="mark">B</span>
    </div>
    <b>BRUSH</b>
  </div>
  <div class="nav">
    <a class="active" href="#dashboard">{IC['home']} Dashboard</a>
    <a href="#root-causes">{IC['target']} Root causes</a>
    <a href="#findings">{IC['list']} Findings</a>
    <a href="#verified">{IC['shield']} How this was verified</a>
    <a href="#step-by-step">{IC['term']} Step by step</a>
    <a href="#packages">{IC['box']} Packages</a>
  </div>
  <div class="side__foot"><b>Run</b><code>{_esc(report.run_id)}</code>
    engine {_esc(provider)}</div>
</nav>

<main class="main">

<header class="phead">
  <h1>Report</h1>
  <div class="meta"><span>{generated}</span><span>engine: {_esc(provider)}</span>
  <span>{s.get('wall_seconds', 0)}s analysis</span></div>
</header>

<section class="sec" id="dashboard">
<div class="card owner">
  <div class="owner__txt">
    <div class="owner__role">UX/UI Designer · AI Trainer · Frontend Developer</div>
    <h2 class="owner__name">Isabella Castro Camacho</h2>
    <div class="owner__event">Frontier Engineering Challenge 2026</div>
    <div class="owner__chips">
      <span class="chip-glass">Hackathon</span>
      <span class="chip-glass">micro1</span>
    </div>
  </div>
  <div class="owner__art" id="heroArt">
    <img src="hero.png" alt="" onerror="this.parentNode.style.display='none'">
  </div>
</div>
<div class="grid2">
<div>
  <div class="hero">
    <div class="hero__ic">{IC['spark']}</div>
    <div>
      <h3>The implementation drifted from the design in {total} place{'' if total == 1 else 's'}.</h3>
      <p>{_esc(summary.get('headline', ''))}</p>
      <p style="margin-top:6px">{_esc(hero_sub)} Nothing here rests on a model's assertion.</p>
    </div>
  </div>
  <div class="card"><dl class="strip">{strip}</dl></div>
  <div class="stats">{stats_cards}</div>
  {start_card}
</div>
{rail}
</div>
</section>

<section class="sec" id="root-causes">
  <div class="card sechead">
    <h2>Root causes</h2>
    <p class="sub">Findings grouped by shared cause. Most drift is one wrong value
  repeated, so a single token-layer change usually clears a whole group.</p>
  </div>
  {causes}
</section>

<section class="sec" id="findings">
  <div class="card sechead">
    <h2>Findings</h2>
    <p class="sub">Every card cites the measurement ids it rests on; each was
  recomputed by the verifier before it reached this page.</p>
  </div>
  <div class="filters">{filters}</div>
  {fcards}
</section>

<section class="sec" id="verified">
  <div class="card sechead">
    <h2>How this was verified</h2>
    <p class="sub">The verifier is deterministic — it recomputes every asserted
  value and severity from the raw measurements and the published policy. A
  finding survives on evidence, never on the model's say-so.</p>
  </div>
  <div class="card vtable"><table>{vrows}</table></div>
</section>

<section class="sec" id="step-by-step">
  <div class="card sechead">
    <h2>Step by step</h2>
    <p class="sub">The exact commands that produced this report, in order — and
  what to type instead when a command fails. Windows PowerShell first; macOS
  and Linux variants where they differ.</p>
  </div>
  {_step_by_step()}
</section>

<section class="sec" id="packages">
  <div class="card sechead">
    <h2>Packages</h2>
    <p class="sub">Everything the tool can use, what each piece is for, and how to
  install and verify it. Only Python itself is required.</p>
  </div>
  {_packages(provider)}
</section>

</main>
</div>
<script>{JS}</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path
