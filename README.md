# Brush

**An agentic auditor that finds where a frontend implementation drifted from its design specification — and proves every claim it makes.**

Built for the micro1 Agentic Workflows Hackathon, 2026.

---

## Who has this problem

The design-systems engineer on a team that ships a component library and a product on top of it.

Their specific job: before a release, confirm that what shipped still matches the design system. Spacing, colour, type, radii, borders, component states. Today that means opening the design tool on one screen and DevTools on the other and comparing values by eye, component by component, state by state.

## What makes it worth solving

Three things make eyeballing the wrong instrument, and all three are measurable:

**The eye is the wrong instrument for colour.** `#767676` on white is 4.54:1 and passes WCAG AA. `#8A8A8A` on white is 3.45:1 and fails. They are two greys that no reviewer distinguishes on a screen, and one of them is an accessibility bug. Meanwhile `#1F6FEB` and `#2070EC` differ by 0.375 ΔE — literally imperceptible — and a string comparison flags them as loudly as it flags a broken contrast ratio. Neither eyes nor `diff` sort these correctly. CIEDE2000 and a relative-luminance calculation do.

**The defects that matter most are relationships, not values.** A label's margin and a field's margin can each be individually reasonable while the *ratio* between them inverts, at which point the label visually attaches to the field above it. A button's height and its padding can each be plausible while the resulting tap target lands under the WCAG minimum. No property-by-property comparison sees any of this, because no single property is wrong.

**An audit that cries wolf gets muted, and then it is worse than nothing.** Report the same twelve intentional deviations on every commit and the team learns to skim within a week — and once they skim, the real regressions go through with everything else.

## What Brush does

Six stages. Agents sit at exactly three of them — the three where the answer is a judgement rather than a calculation.

| # | Stage | Who | What happens |
|---|-------|-----|--------------|
| 1 | Extract | deterministic | Design spec and the resolved CSS cascade become one intermediate representation |
| 2 | Map | **agent** | Pair `Button/Primary` with `.btn.btn--primary`; abstain rather than guess |
| 3 | Measure | deterministic | Every property, in a perceptual unit: px, CIEDE2000, ratio, weight steps |
| 4 | Diagnose | **agent + tools** | Is it a defect, which principle does it violate, what is the smallest fix |
| 5 | Verify | deterministic | Recompute everything the agent asserted; drop or correct what fails |
| 6 | Report | **agent** | Group by root cause, rank by consequence, write for the engineer who must fix it |

Everything a number can settle is settled by a number, before and after the model. That split is why the verifier can afford to be strict: it never argues with the model about arithmetic, only about relevance.

Findings are graded against a published policy built from **Jon Yablonski's 30 Laws of UX**, **Jakob Nielsen's 10 usability heuristics**, and **five WCAG 2.1/2.2 success criteria** — 30 laws, 10 heuristics, 22 severity clauses, all in [`src/brush/knowledge/ux_laws.json`](src/brush/knowledge/ux_laws.json). The agent may only cite principle ids that exist in that file; the verifier strips any it invents. See [`docs/UX_LAWS.md`](docs/UX_LAWS.md).

## Quickstart

```bash
git clone <repo> && cd brush
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"

brush doctor       # check the install; names the fix for anything broken
make demo          # audit the hard case, write an HTML report
make eval          # reproduce every number in this README
make test          # 27 tests: integrity, verifier, clean control, CLI errors
make batch         # score a 12-row review workbook -> out/brush_results.xlsx
```

**If `pip` or `venv` gives you trouble, skip both.** The audit engine has no
third-party dependencies, so this works on a bare Python 3.10+ with nothing
installed:

```bash
python3 run.py doctor
python3 run.py audit --design eval/cases/design.spec.json \
    --html eval/cases/checkout.html --css eval/cases/generated/case_01.css
```

No API key needed for any of the above.

📖 **Step-by-step user manual, with four installation routes and a
symptom-to-fix troubleshooting table: [`docs/MANUAL.md`](docs/MANUAL.md).**
Methodology and evaluation design: [`docs/REPRODUCTION.md`](docs/REPRODUCTION.md).

### Reviewing from a spreadsheet

Nobody runs twelve commands to review twelve screens. `brush batch` takes the
sheet a reviewer already keeps, audits every row, and writes back what it found.

```bash
brush template --out cases.xlsx                      # a workbook to fill in
brush batch --sheet cases.xlsx --out results.xlsx    # audit every row
```

You fill in `ID`, `IMAGE/FIGMA`, `CODE` and — optionally — `EXPECTED`. Brush
fills in the rest. Two scores come back, and keeping them apart is the point:

- **`CONFORMANCE`** — *does the code match the design?* `1.0` no blockers and no
  majors · `0.5` no blockers but at least one major · `0.0` at least one blocker.
  Written as a live Excel formula so the rubric is visible and the sheet
  recalculates if you edit the counts.
- **`POINTS`** — *was Brush right?* Agreement against the `EXPECTED` score **you**
  filled in. `1.0` exact · `0.5` one band apart · `0.0` two bands apart. With
  `EXPECTED` blank it mirrors `CONFORMANCE` and measures nothing — and the
  workbook's Rubric tab says so, because a model reporting its own verdict as an
  accuracy figure is the failure this project argues against.

On the 12-case set, with `EXPECTED` derived from the human-assigned severity band
of each injected mutation: **12/12 exact agreement**. The `IMAGE/FIGMA` column
also accepts a mockup image, which a vision model transcribes into a draft
specification that **a human must confirm before Brush will audit against it**.

Details, including why **no training is required** and what to tune instead:
[`docs/BATCH_REVIEW.md`](docs/BATCH_REVIEW.md).

---

## Measured improvement

12 cases, seed `20260828`, 105 ground-truth defect entries. Case 00 is a **clean control**; case 01 is the **hard case** — 17 defects injected at once.

Ground truth is derived by construction, not hand-written: resolve the conforming stylesheet, resolve the mutated one, and any measurement whose code-side value changed *is* a defect. Both detectors are scored against the identical set.

| Metric | B1 · script baseline | Brush | Change |
|---|---|---|---|
| Defects found (of 105) | 82 | **105** | +23 |
| Defects missed | 23 | **0** | −23 |
| Spurious findings | 0 | **0** | — |
| Precision | 1.000 | **1.000** | — |
| Recall | 0.781 | **1.000** | **+21.9 pp** |
| F1 | 0.877 | **1.000** | +12.3 pp |
| — recall on plain properties | 0.932 | 1.000 | +6.8 pp |
| — recall on derived relationships | 0.000 | 1.000 | +100 pp |
| Catalogue recall *(independent)* | 0.961 | **1.000** | +3.9 pp |
| Severity accuracy | n/a | 1.000 | — |
| False positives on the clean control | 0 | **0** | — |
| Findings emitted (review burden) | 82 | 105 | +23 |
| Wall clock, 12 cases | 0.06 s | 0.32 s | +0.26 s |

**Where the gain actually comes from.** The baseline is good at what it can see — 0.932 recall on plain property comparisons. The entire remaining gap is structural: it scores **0.000** on derived relationships, because a declaration-level diff has no way to express "this tap target is under 24px" or "this label no longer binds to its field". That is the capability the pipeline adds, and disaggregating it matters more than the headline number.

**On the hard case (case_01, 17 simultaneous defects):** the baseline finds 24 of 31; Brush finds 31 of 31 in 0.031s using 26 tool calls, and ranks them 6 blocker / 19 major / 9 minor / 7 info instead of returning a flat list.

### Read these numbers with three caveats

1. **They were produced by the `offline` provider, which is not a language model.** It is a deterministic scripted policy that exercises the full architecture — tool loop, verification, retries, trajectories — without credentials. Figures labelled `offline` measure *the architecture's* contribution, isolated from the model's. Live figures need `--provider anthropic` and an API key; the command is in `docs/REPRODUCTION.md` and the results table there is explicitly empty until someone runs it.
2. **Derived ground truth shares an extraction layer with the pipeline**, so recall against it cannot fall below what the extractor can represent. The independent check is *catalogue recall* — scored against bands a human wrote down before any detector existed — which is 0.961 → 1.000.
3. **Severity accuracy of 1.000 in offline mode measures policy self-consistency, not model skill**, because the offline policy derives severity from the same classifier the verifier recomputes with. In offline mode the verifier's rejection rate is 0 *by construction*, which is why the verifier is demonstrated by [8 adversarial tests](tests/test_verifier.py) instead of by that number.

**B2 (single-prompt LLM baseline)** is implemented in [`baseline/single_prompt.py`](baseline/single_prompt.py) and shares the harness, but requires an API key, so its row is absent rather than estimated.

---

## Improvement changelog

| Stage | What we tried and why | Evidence | Decision |
|---|---|---|---|
| **Baseline** | B1: resolve `var()`, expand shorthands, walk the class ladder, compare declared values | recall **0.781**, 0 FP | Kept as the comparison. Deliberately a strong baseline — a strawman would prove nothing |
| **I1** | Wrote a CSS cascade resolver instead of driving a headless browser, so results are exact and deterministic | 226 measurements, **0 FP** on the conforming file | Kept. Also removed a 130 MB download and a per-run cold start from the eval loop |
| **I2** | Batched all ~200 measurements into one diagnosis call to cut cost | precision fell: the model grouped unrelated components and cited whichever measurement id sat nearest in the prompt | **Removed.** Diagnosis is per component. Cost rose; correctness is the product |
| **I3** | Added the tool layer so the agent fetches contrast, ΔE, grid and target facts instead of recalling them | 26 tool calls on the hard case; every finding cites a measurement id | Kept. This is what makes the verifier's job possible |
| **I4** | Found a silent key mismatch: findings were keyed by CSS selector while evidence and ledger lookups were keyed by design component | Approvals silently failed to suppress | **Fixed** with a merged audit node — design identity, code reality |
| **I5** | Replaced hand-written ground truth with GT derived from the measurement engine | Hand-written GT omitted cascade side effects (mutating `.btn` also changes `Button/Secondary`) and **scored the correct detector as wrong** | **Kept.** Penalising correct behaviour is the worst failure an eval can have |
| **I6** | Let an off-grid flag escalate a 2px spacing delta from `minor` to `major` | Contradicted the published perceptual floor; graded a 1px trim as major | **Reverted.** Magnitude decides the band; off-grid is carried in the rationale |
| **I7** | Tightened "is this a token value" from 0.5 ΔE to 0.05 | At 0.5 a hand-picked `#2070EC` counted *as* `brand-600` and the finding vanished | Kept. Recovered the entire `color_near` defect class |
| **I8** | Added an integrity test asserting no clause is referenced-but-undeclared or declared-but-unreachable | Caught `c-proximity-inversion` published but never reachable | **Implemented the check properly** and added mutation M19 to exercise it |
| **I9** | Restricted the "must be outside tolerance" GT rule to derived relationships only | The blanket rule excluded M03 — a real off-token defect below the perceptual floor | Kept, narrowed. Perceptual tolerance ≠ conformance tolerance |
| **Final** | 6 stages, 3 agents, 12 tools, 22 severity clauses, 27 tests | recall **1.000**, precision **1.000**, **0 FP** on clean | Main contribution: the measure→judge→recompute split |

Full detail with commands and outputs: [`docs/CHANGELOG_IMPROVEMENT.md`](docs/CHANGELOG_IMPROVEMENT.md).

---

## The main failure mode

**The tool is confidently wrong when the mapper pairs the wrong element.**

Everything downstream is conditional on stage 2. Pair `Button/Primary` to `.btn--secondary` and the pipeline will produce a page of perfectly measured, perfectly verified, perfectly cited findings about a comparison that should never have happened. The verifier cannot catch it: every number *is* correct, every evidence id *does* resolve. The error is upstream of everything verification can see.

Three mitigations, and none of them is a fix: the mapper is instructed that `null` is a better answer than a plausible guess; a proposed code node that does not exist is rejected outright and logged; and unmapped components are surfaced in the report as "not audited" rather than passed over silently. On the evaluation set the mapper abstains rather than mispairs. On a codebase with two similarly-named button variants, I would expect it to fail, and the report would look exactly as confident as a correct one.

## Hot take

**Verification is only as good as the layer beneath it, and everyone is building it one layer too high.**

The instinct with an unreliable agent is to add a checker on the output. We did, and it works: 8 adversarial tests show it catching fabricated evidence ids, numbers recalled instead of read, invented principle ids, and inflated severities. But every one of those catches is possible *only because a deterministic engine had already produced the ground truth to check against*. The verifier is not clever. It re-runs arithmetic the model was never allowed to do in the first place.

The corollary is the uncomfortable part. Our worst failure mode — mapping the wrong component — sits *above* the measurement layer, and the verifier is structurally blind to it. Adding a second verifier would not help; it would check the same measurements just as successfully.

So the lesson we would carry into the next agent: **before designing the verification, find the earliest step whose output nothing downstream can check, and spend the engineering there instead.** In this system that step is component mapping, and the honest mitigation was not a smarter checker — it was teaching the agent to abstain, and telling the user plainly which components went unaudited.

---

## Deliverables

| # | Deliverable | Where |
|---|---|---|
| 1 | Solution code + improvement changelog | this repo · [`docs/CHANGELOG_IMPROVEMENT.md`](docs/CHANGELOG_IMPROVEMENT.md) |
| 2 | Reproduction guide | [`docs/REPRODUCTION.md`](docs/REPRODUCTION.md) · step-by-step manual: [`docs/MANUAL.md`](docs/MANUAL.md) |
| 3 | Solution video (≤5 min) | [`docs/VIDEO_SCRIPT.md`](docs/VIDEO_SCRIPT.md) |
| 4 | Agent trajectories | `out/*.trajectory.md` and `.jsonl` · one per agent, per run |

Supporting: [`docs/MANUAL.md`](docs/MANUAL.md) · [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`docs/BATCH_REVIEW.md`](docs/BATCH_REVIEW.md) · [`docs/UX_LAWS.md`](docs/UX_LAWS.md) · [`docs/SEVERITY_DERIVATION.md`](docs/SEVERITY_DERIVATION.md)

## What existed before this competition

Nothing. Every file here was written for this hackathon. No framework is vendored; the runtime depends only on the Python 3.10+ standard library, and `anthropic` is an optional extra needed solely for live-model mode. All evaluation data is synthetic and generated by [`eval/mutations.py`](eval/mutations.py) from a design system written for this project.

## Licence

MIT.
