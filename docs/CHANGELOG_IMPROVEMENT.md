# Improvement changelog

Every entry is an experiment we actually ran, with the evidence that decided it.
Three of them were removed or reverted; those are the interesting ones.

Unless stated otherwise, evidence comes from `python eval/run_eval.py`
(12 cases, seed `20260828`, 105 ground-truth entries, `offline` provider).

---

## Baseline — B1, the script a team writes on a Friday

**Tried.** Compare declared CSS values against the specification. Resolve `var()`
from `:root`, expand `padding`/`margin`/`border` shorthands, normalise hex case,
walk the `.btn` → `.btn--primary` class ladder, compare numerically where both
sides are plain lengths.

**Why.** This is the honest version of "the manual process people use today". We
deliberately made it competent — a strawman baseline proves nothing, and this one
scores 0.932 recall on the properties it can actually see.

**Evidence.** Recall **0.781**, precision **1.000**, 0 false positives on the
clean control, 0.06s across 12 cases.

**Decision.** Kept as the comparison for every later entry.

---

## I1 — Resolve the CSS cascade instead of driving a browser

**Tried.** A cascade resolver in pure Python — selector matching with real
specificity, inheritance, `var()` with fallbacks, shorthand expansion, and
`:hover`/`:focus`/`:disabled` captured as separate style sets — rather than
Playwright and `getComputedStyle`.

**Why.** A headless browser gives the truth, but it also puts a 130 MB download,
a per-run cold start and a source of nondeterminism (font availability, GPU
rasterisation) inside the evaluation loop. A conformance audit needs the
*declared computed values*, and those can be resolved exactly.

**Evidence.** 226 measurements on the conforming file, **0 false positives**.
Full 12-case sweep runs in 0.32s with no browser.

**Decision.** Kept. The boundary is explicit: the resolver does not compute
layout, so percentage lengths stay unresolved rather than guessed.

---

## I2 — Batching the whole page into one diagnosis call — REMOVED

**Tried.** Send all ~200 measurements to the diagnostician in a single call to
cut token cost.

**Why.** Obvious cost win, and the measurements are independent facts.

**Evidence.** Precision dropped. With 200 measurements in context the model began
grouping unrelated components into one finding and citing whichever measurement
id happened to sit nearest in the prompt — evidence that resolved, attached to
the wrong component.

**Decision. Removed.** Diagnosis runs per component. Cost rose; correctness is
the product. This is also what made the per-component trajectories readable.

---

## I3 — Give the agent tools instead of letting it recall numbers

**Tried.** 12 tools — `get_measurement`, `contrast`, `delta_e`,
`nearest_color_token`, `grid_check`, `target_size`, `proximity_check`,
`lookup_principle`, `check_ledger` and others — with a loop of up to 3 rounds.

**Why.** Any number the model states from memory is unverifiable. Any number it
fetches is checkable against the same source the verifier uses.

**Evidence.** 26 tool calls on the hard case. Every accepted finding cites at
least one resolvable measurement id; findings that cite none are rejected
(`tests/test_verifier.py::test_no_evidence_is_rejected`).

**Decision.** Kept. This is the precondition that makes verification possible at
all — see the hot take in the README.

---

## I4 — Silent key mismatch between evidence and memory

**Tried.** Nothing; this was a bug found while wiring the approval ledger.

**Why it happened.** Measurements were keyed by the *design* component
(`Button/Primary@default`) while findings carried the *code* node's identity
(`button.btn.btn--primary@default`). Both were internally consistent, so nothing
raised an error.

**Evidence.** Approvals recorded against `Button/Ghost@default` never suppressed
anything, and finding titles read as CSS selectors rather than component names.

**Decision.** Fixed with a merged audit node that carries the **design identity**
(so keys match evidence and the ledger, and titles are recognisable) and the
**code reality** (role, resolved props, backdrop).

---

## I5 — Hand-written ground truth — REPLACED

**Tried.** List the expected findings next to each mutation in the catalogue.

**Why it failed.** Within an hour: mutating `font-weight` on the base `.btn` rule
also changes `Button/Secondary`, which inherits it. The hand-written list did not
say so, so the *baseline* — which correctly reported `Button/Secondary` — was
scored as producing a false positive.

**Evidence.** `Button/Secondary font-weight 600 → 400` appeared in the baseline's
output and in no ground-truth list.

**Decision. Replaced** with ground truth derived by construction: resolve the
clean stylesheet, resolve the mutated one, and any measurement whose code-side
value changed *is* a defect. Exact, complete, covers cascade side effects and
derived measurements for free. **Penalising a detector for being right is the
worst failure an evaluation can have.**

The hand-written catalogue survives as *catalogue recall* — a second,
non-circular check that asks only "did the tool say anything about the component
and property this mutation touched", scored identically for both detectors.

---

## I6 — Letting off-grid escalate severity — REVERTED

**Tried.** A clause `c-offgrid-grouping` making an off-grid spacing value `major`
when it sits on a grouping or interactive edge.

**Why.** A 22px padding breaks the rhythm every other component is tuned to,
which felt worse than a plain 2px nudge.

**Evidence.** It graded a **1px** trim on an alert as `major`, directly
contradicting the perceptual floor the entire severity model is built on. The
published policy puts a 2–4px delta in `minor` and anything under 2px in `info`.

**Decision. Reverted.** Magnitude decides the band; the off-grid fact is carried
in the rationale text instead. The clause was then unreachable, and
`tests/test_integrity.py::test_no_unreachable_clauses` failed until it was
deleted from the published policy — dead policy in a published document is worse
than no policy.

---

## I7 — "Is this a token value" tightened from 0.5 ΔE to 0.05

**Tried.** Treat a colour as a token match when it lands within 0.5 CIEDE2000 of
one.

**Why it failed.** `#2070EC` sits 0.375 ΔE from `brand-600`, so it counted *as*
`brand-600` and the entire `color_near` defect class vanished silently.

**Evidence.** `Button/Primary background-color` was the pipeline's only false
negative in three consecutive runs.

**Decision.** Tightened to 0.05. "Is a token" has to mean an equality, not a
neighbourhood. Perceptual tolerance and conformance tolerance are different
things, and conflating them cost us a whole defect class.

---

## I8 — Integrity tests on the knowledge pack

**Tried.** Assert that every clause id used in the classifier is declared in the
published policy, and that every declared clause is reachable.

**Why.** A clause referenced but undeclared makes `clause()` return `None` and
silently defaults the severity to `minor` — a wrong grade with no error and no
trace.

**Evidence.** The test immediately caught `c-proximity-inversion`: published,
documented, cited in the README as a headline capability, and never reachable
from any code path.

**Decision.** Rather than delete it, we **implemented it properly** — grouping
intent is now declared in the design spec, resolved into a
`-derived-proximity-ratio` measurement, and exercised by a new mutation M19
(label margin pushed to 28px, exceeding the 24px gap between fields, so the label
visually reattaches to the field above). Ground-truth entries rose from 78 to 105.

---

## I9 — "Must be outside tolerance" ground-truth rule, narrowed

**Tried.** After adding M19, tighten the ground-truth definition so a defect is a
change that leaves the measurement outside tolerance.

**Why.** The grouping ratio moved from 3.0 to 12.0 under a different mutation —
a large change in the *safe* direction — and the blanket "any change is a defect"
rule scored the pipeline as having missed a defect for correctly staying silent.
The same failure as I5.

**Evidence.** The blanket fix then excluded M03, a real off-token colour defect
that sits below the perceptual floor, turning a correct finding into a false
positive for both detectors.

**Decision.** Kept but narrowed to **derived relationship measurements only**,
which are the only directional ones. Plain property changes are always defects,
because an off-token literal is off-spec even when imperceptible.

---

## Final

6 stages · 3 agents · 12 tools · 30 UX laws + 10 heuristics + 5 WCAG criteria ·
---

## I9 — Hardening pass: what happens when someone holds it wrong

**What we tried and why.** Every number above was produced by us, on our machine,
with correct inputs. Before shipping we fed the CLI the mistakes a grader would
actually make: a folder where a file belongs, a `Makefile` where JSON belongs, an
empty page, a spreadsheet with unrecognised headers, an unwritable `--out`, and a
rating typed as the word "muy bien".

**Evidence.** Six of nine produced a Python traceback. Two were worse:

| input | before | why it mattered |
|---|---|---|
| an empty HTML page | **exit 0**, "0 findings" | auditing nothing read as a clean bill of health |
| `EXPECTED` typed as a word | workbook shipped with `#VALUE!` | the delivered artefact was broken, silently |
| `openpyxl` not installed | **every** command failed | a dependency for a feature you were not using |

**Decision.** Kept, and fixed all three classes:

* `openpyxl` became a lazy import, so a missing spreadsheet dependency can only
  break the spreadsheet commands.
* Inputs are validated before any work runs — file vs directory, JSON parses,
  output directory writable — and a mistyped path suggests the nearest real
  filename via `difflib`.
* A run that paired zero components now exits non-zero. This is the one that
  worried us most: every other failure was loud, and that one was quiet.
* `EXPECTED` is coerced by `parse_expected()`, which accepts `0` / `0.5` / `1`
  and the words people actually type (`sí`, `parcial`, `fail`); anything else is
  preserved as a cell note and never reaches the formula.
* Added `brush doctor`, which checks the interpreter, the package, the knowledge
  pack, the colour engine and a full end-to-end audit, and names the fix for
  whatever it finds. Added `run.py` so the tool runs with no install at all.

**What it taught us.** The failure modes we had instrumented were all in the
*agent* — hallucinated evidence, inflated severity — because that is where we
expected to be wrong. The failures that would actually have cost us a grader were
in the *first thirty seconds*: install, paths, permissions. A verifier that
catches a fabricated measurement id is worth nothing if `pip install` fails and
the person never gets to run it.

`tests/test_cli_errors.py` pins all ten cases so they cannot regress.

22 severity clauses · 27 tests.

| | B1 | Brush |
|---|---|---|
| Recall | 0.781 | **1.000** |
| — plain properties | 0.932 | 1.000 |
| — derived relationships | 0.000 | 1.000 |
| Precision | 1.000 | 1.000 |
| False positives on clean | 0 | 0 |

**The main contribution is the split, not any single component:** every number is
computed by a deterministic engine before the model sees it and recomputed after
the model speaks, so the agent is confined to the judgement calls — mapping,
relevance, and how to phrase the fix — and cannot move a number without being
caught.

**The second contribution is what that split cannot cover.** The mapper sits
above the measurement layer, so nothing downstream can check it. Three of the
nine entries above are reversals, and the two that hurt most (I5, I9) were both
the evaluation punishing the detector for behaving correctly.
