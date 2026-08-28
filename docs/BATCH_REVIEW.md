# Batch review from a spreadsheet

Nobody runs twelve commands to review twelve screens. They keep a sheet, and they
hand that sheet to someone else afterwards. `brush batch` takes the workbook a
reviewer already keeps, audits every row, and writes back what it found.

```bash
brush template --out cases.xlsx                        # a workbook to fill in
brush batch --sheet cases.xlsx --out results.xlsx      # audit every row
```

Or through the Makefile, against the 12-case evaluation set:

```bash
make batch        # -> out/brush_results.xlsx
```

---

## The input sheet

Fill in the yellow cells. Everything else is written by Brush.

| column | who fills it | what it holds |
|---|---|---|
| `ID` | you | any label for the row |
| `IMAGE/FIGMA` | you | path to a `design.spec.json`, **or** to a mockup image |
| `CODE` | you | path to the `.html` implementation |
| `CSS` | you | stylesheet(s), comma separated. Left blank, Brush looks for a `.css` beside the HTML |
| `EXPECTED` | you, optionally | the score *you* would give the row: `0`, `0.5` or `1` |
| `RESPUESTA BRUSH` | Brush | what was found, summarised |
| `BLOCKERS` / `MAJORS` / `MINORS` / `INFO` | Brush | counts by severity band |
| `CONFORMANCE` | Brush | `0` / `0.5` / `1` — does the code match the design |
| `POINTS` | Brush | `0` / `0.5` / `1` — was Brush right |
| `COMMENTS` | Brush | what drove the score and what to do first |

Header names are matched case-insensitively and accept Spanish aliases
(`CÓDIGO`, `PUNTOS`, `COMENTARIOS`, `ESPERADO`, `IMAGEN`), so an existing sheet
usually does not need renaming.

## The two scores, and why they are separate

This is the part that is easy to get wrong, so the workbook keeps them in
different columns with different meanings.

### CONFORMANCE — does the code match the design?

Brush's verdict on the artefact.

| score | condition |
|---|---|
| `1.0` | no blockers and no majors — ships as designed |
| `0.5` | no blockers, at least one major — partially conforms |
| `0.0` | at least one blocker — a WCAG AA failure, a removed state, or a target under 24px |

It is written into the cell as a **live formula**, not a stored number:

```excel
=IF(F2="","",IF(F2>0,0,IF(G2>0,0.5,1)))
```

So the rubric is visible in the sheet, and if a reviewer edits the counts the
score recalculates. A number Brush simply asserted would be unauditable.

### POINTS — was Brush right?

Agreement between Brush's `CONFORMANCE` and the `EXPECTED` score a human filled
in. This is the only column that says anything about Brush's accuracy.

| score | condition |
|---|---|
| `1.0` | exact agreement |
| `0.5` | one band apart (e.g. you said `1.0`, Brush said `0.5`) |
| `0.0` | two bands apart |

**With `EXPECTED` left blank, `POINTS` mirrors `CONFORMANCE` and measures
nothing** — and the Rubric tab says exactly that, in the workbook, in plain
words. A model that grades its own homework and reports the mark as an accuracy
figure is the failure this whole project argues against; the sheet should not
quietly commit it.

## Output tabs

| tab | contents |
|---|---|
| `Cases` | one row per screen, as above |
| `Findings` | one row per finding: component, property, spec value, code value, delta, unit, principles cited, suggested fix, evidence ids |
| `Summary` | counts and rates, all as formulas over the `Cases` tab |
| `Rubric` | what every score and severity band means, and which engine produced the run |

Every formula is Excel-2007-era (`COUNTIF`, `AVERAGE`, `IFERROR`, `IF`, `ABS`)
so the workbook opens and recalculates in LibreOffice, Excel and Sheets alike.
The shipped example recalculates with **0 errors across 38 formulas**.

## Result on the evaluation set

`EXPECTED` was derived from the severity band a human assigned to each injected
mutation in `eval/mutations.py` — never from Brush's output — using the same
rubric: any mutation banded `blocker` → `0.0`, else any `major` → `0.5`, else
`1.0`.

| | |
|---|---|
| cases | 12 |
| exact agreement | **12 / 12** |
| mean points | **1.00** |
| conforming `1.0` | 1 |
| partially conforming `0.5` | 6 |
| failing `0.0` | 5 |

Reproduce with `make batch`, then open `out/brush_results.xlsx`.

> One honest note on this number. Getting to 12/12 required correcting the
> *human* column twice, not the tool. The first pass of `EXPECTED` was written
> from memory against a stale case→mutation mapping and was wrong on four rows;
> the second was derived mechanically from the catalogue bands. Separately, a
> mutation hand-labelled `major` turned out to be a `blocker` because the
> lightened green also crossed WCAG AA. Agreement figures where the reference was
> revised during development are co-calibration, not a blind test, and should be
> read that way.

---

# Reading a mockup instead of a spec

The `IMAGE/FIGMA` column accepts a `.png` or `.jpg`. Brush does not measure from
pixels — it measures against a normalised specification — so an image has to
become a spec first, and that step is an **inference**, not an extraction.

The module makes that explicit rather than hiding it inside the audit:

```bash
export ANTHROPIC_API_KEY=...
brush batch --sheet cases.xlsx --out results.xlsx --provider anthropic
```

1. A vision model transcribes the mockup into a specification.
2. It is written beside the image as `<name>.draft.json`, carrying
   `"review_status": "unconfirmed"` and a note explaining what to check.
3. **Brush refuses to audit against it.** You either edit `review_status` to
   `confirmed`, or pass `--accept-drafted-spec` — in which case the run is
   labelled `PROVISIONAL` in the report and in the `COMMENTS` column.

The prompt instructs the model to **omit any property it cannot read** rather
than estimate it. An omitted property is audited as "not specified"; a guessed
one becomes a false finding with a measurement and a UX law attached to it, which
looks more credible than a real one. That asymmetry is why the refusal is the
default and the override is explicit.

`figma://` references need the REST adapter and a `FIGMA_TOKEN`; export the node
to `design.spec.json` instead — which is also what keeps the evaluation runnable
from a clean clone with no credentials.

---

# Does Brush need to be trained?

**No — and training it would make it worse.**

This comes up because "an AI that evaluates designs" sounds like a classifier, so
it sounds like it needs labelled examples. It is not one.

**Every number Brush reports is computed, not predicted.** CIEDE2000 colour
distance, WCAG relative-luminance contrast, the resolved CSS cascade with
specificity and inheritance, grid conformance, proximity ratios — these are
closed-form calculations with exact answers. A fine-tuned model would replace an
exact calculation with a learned approximation of it, and would be wrong in ways
that are much harder to notice, because the output would still look like a
number.

**What genuinely needs judgement is handled by a general-purpose model reading a
knowledge pack**, not by weights:

| decision | why a model | why not training |
|---|---|---|
| which DOM node implements `Button/Primary` | naming conventions vary per codebase | a new codebase would need new labels |
| is this deviation intentional | needs context the spec never captured | that is what the approvals ledger is for |
| what is the smallest correct fix | requires knowing the token layer exists | it is derivable from the measurement |

**The tuning surface is a JSON file, not a training run.** Every threshold and
severity clause lives in `src/brush/knowledge/ux_laws.json` — the just-noticeable
ΔE, the 4px grid base, the leading floor, all 22 clauses that map a measurement
to a band. Want the tool stricter about colour? Change `delta_e_obvious` from
`3.0` to `2.0`, re-run `make eval`, and read the effect on precision and recall
in the same table. That loop takes seconds, is fully reversible, and leaves a
diff a colleague can review. Fine-tuning offers none of those properties.

**So the spreadsheet is an evaluation harness, not a training set.** Its job is
to tell you when Brush is wrong. The workflow it supports is:

```
fill EXPECTED  →  make batch  →  read POINTS  →  edit ux_laws.json  →  make eval
```

Which is a tighter, cheaper and far more auditable loop than collecting labels
and retraining — and it is the loop that produced every improvement recorded in
`docs/CHANGELOG_IMPROVEMENT.md`.

The one place more data would genuinely help is the **mutation catalogue**:
19 defect types drawn from real drift patterns is a small sample of the ways an
implementation can diverge. Adding cases there widens the evaluation. That is
still not training — it is testing.
