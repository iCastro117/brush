# Architecture

## The organising principle

Everything a number can settle is settled by a number — before and after the
model speaks. Agents are confined to the three questions arithmetic cannot
answer.

```
  ┌── deterministic ──┐   ┌─ agent ─┐   ┌── deterministic ──┐   ┌─ agent ─┐
  │ 1  extract        │ → │ 2  map  │ → │ 3  measure        │ → │ 4 judge │
  └───────────────────┘   └─────────┘   └───────────────────┘   └────┬────┘
                                                                     ↓
                          ┌─ agent ──┐   ┌── deterministic ──┐       │
                          │ 6 report │ ← │ 5  verify         │ ←─────┘
                          └──────────┘   └───────────────────┘  ↑ retry with
                                                                  feedback
```

The verifier can afford to be strict precisely because it never argues with the
model about arithmetic — only about relevance.

## Stage by stage

### 1. Extract — `extract/`

`design.py` turns `design.spec.json` into `StyleNode`s, resolving `{color.brand-600}`
token references and expanding box shorthands.

`css_engine.py` is a CSS cascade resolver in ~430 lines of stdlib Python:

| Implemented | Deliberately not |
|---|---|
| Selector matching: tag, class, id, descendant, child | Layout. No used widths, no flow |
| Real specificity `(id, class, type)` + source order | `@media` variants (base viewport only) |
| Inheritance for inherited properties | Sibling combinators `+` `~` |
| `var()` with fallbacks, recursive, depth-capped | `calc()` |
| Shorthand expansion: padding, margin, border, outline, gap | Percentages, which stay **unresolved rather than guessed** |
| `:hover`, `:focus`, `:focus-visible`, `:disabled` as separate style sets | Cascade layers, `@container` |

**Why not Playwright.** A browser gives the truth and also gives a 130 MB
download, a per-run cold start, and nondeterminism (font availability, GPU
rasterisation) inside the evaluation loop. A conformance audit needs declared
computed values, not a rasterised bitmap. The trade is stated so a reader can
judge it: the resolver is exact within its scope and silent outside it. A
Playwright adapter would slot in at this boundary without touching stages 2–6.

### 2. Map — `agents/mapper.py`

Pairs `Button/Primary` with `.btn.btn--primary`. A cheap Jaccard + role + text
score proposes the top 5 candidates; the agent decides and may answer `null`.

This is the system's **most dangerous stage** — see the failure mode in the
README. A proposed code node that does not exist is rejected and logged;
unmapped components are surfaced in the report as "not audited".

### 3. Measure — `analyze/`

| Module | Answers |
|---|---|
| `color.py` | sRGB → CIELAB (D65) → CIEDE2000; WCAG 2.1 relative luminance and contrast; nearest colour token |
| `units.py` | px, rem, em, pt, ch → float px; `%` returns `None` rather than a guess |
| `geometry.py` | Grid conformance, nearest spacing token, proximity ratio, target size |
| `typography.py` | Modular-scale detection, line-height normalised to a unitless ratio, weight keywords → numbers, first-family comparison |
| `compare.py` | Emits `Measurement` objects — the atoms of evidence |

Each `Measurement` records `method`, the string describing how the number was
obtained, so any reader can re-derive it.

**Derived measurements** are where a property-by-property diff is structurally
blind:

- `-derived-target-height` — Fitts's Law / WCAG 2.5.8
- `-derived-proximity-ratio` — Law of Proximity; grouping intent declared in the design spec's `groups` block
- `-derived-grid-conformance` — Law of Uniform Connectedness
- `-derived-padding-symmetry-x` — asymmetry the spec never asked for

The baseline scores **0.000** recall on this family. That is not a tuning gap; a
declaration-level diff has no way to express these facts.

### 4. Judge — `agents/diagnostician.py`

Per component, never per page (changelog I2). Receives measurements already known
to be out of tolerance, plus a small knowledge slice per measurement. Loops up to
3 rounds, calling tools from `agents/tools.py`.

The agent is told plainly: do not recompute or estimate any number; if you need a
fact, call a tool; every finding must cite measurement ids.

### 5. Verify — `agents/verifier.py`

Not a model. Five checks:

1. Every cited measurement id exists → else **drop**
2. Asserted values match the measurement → else **drop**
3. Severity **recomputed** from the published policy → **correct** and tell the agent
4. Principle ids exist in the knowledge pack → **strip** the invented ones
5. A human approval covers this exact value → **suppress** and record a checkpoint

Failures 1, 2 and 4 generate feedback and one corrective round. The retry is
visible in the trajectory as a `retry` step.

**In `offline` mode the rejection rate is 0 by construction**, because the offline
policy derives severity from the same classifier. The verifier is therefore
demonstrated by 8 adversarial tests in `tests/test_verifier.py`, not by that
number.

### 6. Report — `agents/reporter.py`, `report/html.py`

Groups findings by root cause, surfaces token-layer clusters (Pareto: one token
change usually clears a long tail), and ranks by consequence.

## Memory — `memory/ledger.py`

The approval ledger is the agent's memory across runs, and the human checkpoint
required by ground rules 04 and 05.

**The property that makes it safe: an approval is scoped to the value, not the
property name.** Approving `Button/Ghost min-height = 28` does not suppress a
later drift to `20`. Without that scoping, one approval becomes a permanent
blindfold on a property.

## Trajectories — `trace/trajectory.py`

JSONL, one line per step, streamed to disk. Step kinds: `instruction`,
`thought`, `tool_call`, `tool_result`, `decision`, `retry`, `checkpoint`,
`error`. Rendered to Markdown by the CLI.

A trajectory records the four things that make an agent step auditable: what the
agent was told, what it asked for, what the tool actually returned, and what it
did with the answer — including the times it was told it was wrong.

## Providers — `agents/provider.py`

| Mode | What it is | Needs |
|---|---|---|
| `anthropic` | Real Claude via the Messages API. Records a cassette automatically | API key |
| `replay` | Byte-identical replay of a recorded run, keyed by prompt hash | a cassette |
| `offline` | Deterministic scripted policy — **not a language model** | nothing |

`offline` exists so the architecture can be exercised and measured separately
from the model. Every figure it produces is labelled `offline` in the results
file and in the README.

## File map

```
src/brush/
  ir.py                     StyleNode · DesignSystem · Measurement · Finding
  cli.py                    audit | approve | ledger
  extract/                  design.py · code.py · css_engine.py
  analyze/                  color.py · units.py · geometry.py · typography.py · compare.py
  knowledge/                ux_laws.json (30 laws + 10 heuristics + 22 clauses) · retrieve.py
  agents/                   provider.py · tools.py · mapper.py · diagnostician.py
                            verifier.py · reporter.py · orchestrator.py
  memory/ledger.py          approvals scoped to values
  trace/trajectory.py       JSONL + Markdown rendering
  report/html.py            the reviewer-facing report
baseline/                   naive_diff.py (B1) · single_prompt.py (B2)
eval/                       mutations.py · run_eval.py · cases/
tests/                      integrity · adversarial verifier · clean control
```

## Report design

The report is a design artefact as much as a code one, so the choices are stated:
the page is set on the same 4px grid the tool audits against, drawn faintly in
the background; numbers are monospaced and always carry a unit and a sign; and
the signature element is a **drift bar** that plots the spec value and the code
value on one shared axis, so the reader sees the distance instead of reading two
numbers and subtracting them. Severity colours are functional, not decorative.
Responsive, printable, keyboard-focusable, and honours `prefers-reduced-motion`.
