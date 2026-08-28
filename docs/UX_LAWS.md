# The knowledge pack

`src/brush/knowledge/ux_laws.json` is the file that turns a numeric
difference into a judgement about consequence. It holds **30 Laws of UX**
(Jon Yablonski), **10 usability heuristics** (Jakob Nielsen), **5 WCAG 2.1/2.2
success criteria**, a set of **perceptual thresholds**, and **22 severity
clauses** that bind them to measurements.

Two rules govern its use, and both are enforced in code:

1. **The agent may only cite ids that exist in this file.** The verifier strips
   anything else — `tests/test_verifier.py::test_invented_principle_id_is_stripped`
   proves it. A model that invents an authoritative-sounding principle gets that
   citation removed while its valid citations survive.
2. **No clause may be published-but-unreachable or referenced-but-undeclared.**
   `tests/test_integrity.py` fails the build otherwise. This caught a real case:
   `c-proximity-inversion` was documented and cited in the README while no code
   path could reach it.

## Perceptual thresholds

These are the numbers that make severity defensible rather than felt.

| Threshold | Value | Why it is the boundary |
|---|---|---|
| `delta_e_jnd` | **1.0** CIEDE2000 | Just-noticeable difference for a trained observer |
| `delta_e_obvious` | **3.0** | Where an ordinary user notices two non-adjacent colours differ |
| `delta_e_brand_break` | **5.0** | Reads as a different colour; breaks Law of Similarity grouping |
| `spacing_floor_px` | **1.0** | Below reliable perception, still breaks grid rhythm |
| `spacing_perceptible_px` | **2.0** | Where spacing error becomes visible in a repeated element |
| `type_size_ratio_notable` | **6%** | Below this, size drift is invisible in isolation |
| `leading_floor` | **1.4** | Below this, body copy measurably slows reading |
| `measure` | **45–75 ch** | Comfortable line length |
| target size | **24px** min, **44px** comfortable | WCAG 2.5.8 and the practical comfort bar |

## How a law becomes a severity

The retrieval function `context_for()` hands the agent only the slice relevant to
one measurement — never the whole file. Dumping the full pack into every prompt
was the first thing we tried and it measurably hurt precision (changelog I2).

Worked example — `Input/HelpText` colour drifts to `#A8AEB8`:

```
measurement   Input/HelpText@default::color
              design #6B7280 · code #A8AEB8 · ΔE 8.4
              method sRGB → CIELAB (D65) → CIEDE2000
              extra  contrast_ratio 2.23 · backdrop #FFFFFF · wcag_level fail

clause        c-contrast-fail   (checked before the ΔE clauses)
severity      blocker
laws          lux-active-user-paradox, lux-selective-attention
heuristics    nn-9, nn-10
wcag          wcag-1.4.3
```

Ordering matters: accessibility failures are checked **before** aesthetic drift,
so a colour change that also breaks contrast is reported as the blocker it is
rather than as a colour nit.

## The 30 Laws of UX, and what each one audits

Not every law drives a severity clause. Several bound the design of the *tool*
rather than grading the interface, and they are marked `meta`.

| Law | What it audits here |
|---|---|
| Aesthetic-Usability Effect | Accumulated minor drift lowers perceived usability; justifies grading compound drift |
| Choice Overload | Implementation adding variants the system never defined |
| Chunking | Spacing tokens draw the chunks; wrong gaps dissolve boundaries |
| Cognitive Bias | Semantic colour that contradicts the element's real role |
| Cognitive Load | Inconsistent spacing/type forces re-parsing on every encounter |
| Doherty Threshold | Transition duration drift; missing focus feedback |
| **Fitts's Law** | Interactive height, padding, hit area. Drives `-derived-target-height` |
| Flow | Missing or inconsistent focus states break keyboard flow |
| Goal-Gradient | The terminal action of a flow is the costliest to get wrong |
| Hick's Law | Secondary actions that read as primary |
| Jakob's Law | Conventions the spec encoded — blue links, focus rings, field heights |
| Law of Common Region | Card padding, border and radius draw the region |
| **Law of Proximity** | Inner-to-outer spacing ratio. Drives `-derived-proximity-ratio` |
| Law of Prägnanz | Radius drift across siblings breaks the shape family |
| **Law of Similarity** | The core argument against off-token colours |
| **Law of Uniform Connectedness** | The spacing grid. Drives `-derived-grid-conformance` |
| Mental Model | Variants carry meaning; a ghost styled as primary contradicts it |
| Miller's Law | Bounds how many visual treatments a system can carry |
| Occam's Razor | Hard-coded values duplicating an existing token |
| Paradox of the Active User | Help and error text must survive on visual weight alone |
| Pareto Principle | Ranks remediation: one token fix clears a long tail |
| Parkinson's Law | `meta` — argues for constraining the audit surface |
| Peak-End Rule | Weights defects on final steps and error states higher |
| Postel's Law | `meta` — accept messy CSS, emit strict verified findings |
| Selective Attention | Colour and weight survive filtering; drift there costs more |
| Serial Position Effect | First and last items in a repeated group weighted higher |
| Tesler's Law | `meta` — ambiguity resolved in the tool or dumped on the reviewer |
| Von Restorff Effect | Drift that steals the primary action's isolation |
| Working Memory | Error text separated from its field by wrong margins |
| Zeigarnik Effect | `meta` — half-migrated components are the ones users notice |

## Nielsen's heuristics

`nn-4 Consistency and standards` is the heuristic this entire tool exists to
enforce; every off-token value cites it. The other nine attach where they apply —
`nn-1` to focus and status states, `nn-5` to under-sized targets, `nn-9` and
`nn-10` to error and help text legibility.

## WCAG criteria

| ID | Criterion | Enforced as |
|---|---|---|
| `wcag-1.4.3` | Contrast (Minimum) AA | 4.5:1 normal, 3:1 large — computed, not estimated |
| `wcag-1.4.6` | Contrast (Enhanced) AAA | Reported, never a blocker |
| `wcag-1.4.11` | Non-text Contrast | 3:1 for borders, focus rings, state indicators |
| `wcag-2.4.7` | Focus Visible | A missing focus state is a blocker, not a style nit |
| `wcag-2.5.8` | Target Size (Minimum) | 24×24 CSS px |

## Extending it

Adding a clause requires three things, and the tests enforce all three: an entry
in `clauses` citing only existing principle ids, a reachable branch in
`knowledge/retrieve.py::classify()`, and a mutation in `eval/mutations.py` that
exercises it with a band derived in `SEVERITY_DERIVATION.md`.
