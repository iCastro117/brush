# Solution video — 5:00

Screen recording with voiceover. Timings are cumulative.

---

## 0:00–0:35 · The problem, shown not told

**Screen.** Two greys side by side, large: `#767676` and `#8A8A8A`.

> "These are the same colour to you. One passes WCAG AA at 4.54 to 1. The other
> fails at 3.45. A design-systems engineer checking a release finds this by
> opening the design tool on one screen and DevTools on the other, and comparing
> by eye."

**Screen.** Run it live:

```bash
python -c "from brush.analyze.color import *; \
print(contrast_ratio(parse_color('#767676'), parse_color('#fff')))"
```

> "The eye is the wrong instrument. So is `diff` — these two blues differ by
> 0.375 ΔE, imperceptible, and a string comparison shouts about them exactly as
> loudly."

---

## 0:35–1:15 · The baseline, run for real

**Screen.** `python baseline/naive_diff.py --design ... --css case_01.css`

> "Here's what a competent team writes on a Friday. It resolves `var()`, expands
> shorthands, walks the class ladder. It's not a strawman — it finds 24 of the
> 31 defects in our hard case, with zero false positives."

**Screen.** Scroll the flat output.

> "Two problems. Everything has the same weight, so a reviewer triages by hand.
> And there are seven defects it structurally cannot see."

---

## 1:15–2:45 · One full execution

**Screen.** `make demo`, unedited.

```
229 measurements · 61 out of tolerance · 26 tool calls
41 verified findings (6 blocker, 19 major, 9 minor, 7 info)
verifier: 41 proposed → 41 accepted, 0 rejected, 0 corrected
0.034s
```

> "Six stages. Agents at three of them — mapping, judging, reporting. Everything
> a number can settle is settled by a number, before and after."

**Screen.** Open `out/demo.trajectory.md`. Scroll to a `tool_call` → `tool_result` pair.

> "The agent isn't allowed to do arithmetic. It asked for the contrast ratio and
> got 2.23 from the same engine the verifier uses. Every finding cites a
> measurement id."

**Screen.** Open `out/demo.report.html`. Point at a drift bar.

> "Spec and code on one axis, so you see the distance instead of subtracting two
> numbers. This one is the defect the baseline can't reach —"

**Screen.** The `-derived-proximity-ratio` finding.

> "— the label's margin and the field's margin are each individually reasonable.
> The *ratio* between them inverted, so the label now visually belongs to the
> field above it. No property is wrong. The relationship is."

---

## 2:45–3:30 · The comparison

**Screen.** `make eval`, then the aggregate table.

| | B1 | Brush |
|---|---|---|
| Recall | 0.781 | **1.000** |
| — plain properties | 0.932 | 1.000 |
| — derived relationships | **0.000** | 1.000 |
| Precision | 1.000 | 1.000 |
| FP on the clean control | 0 | 0 |

> "Twelve cases, ground truth derived by construction rather than hand-written.
> The honest read: the baseline is good at what it can see — 0.93. The whole
> remaining gap is the derived relationships, where it scores zero because a
> declaration-level diff has no way to express them."

> "And note the clean control. Zero false positives on a conforming file. An
> audit that cries wolf gets muted, and then it's worse than nothing."

---

## 3:30–4:15 · The changelog: one that worked, one we removed

> "The change that contributed most was giving the agent tools instead of letting
> it recall numbers. That's what makes verification possible at all."

**Screen.** `python tests/test_verifier.py`

> "Eight adversarial tests. Fabricated evidence ids, numbers recalled instead of
> read, invented principle ids, inflated severity — all caught."

**Screen.** The I2 row in the changelog.

> "The experiment we removed: batching all 200 measurements into one call to cut
> cost. Precision fell. The model started grouping unrelated components and
> citing whichever measurement id sat nearest in the prompt. Cost went back up.
> Correctness is the product."

**Screen.** Briefly, the I5 and I9 rows.

> "Two more reversals, both the same shape: our own evaluation punishing the
> detector for being right. That's the worst bug an eval can have, and we hit it
> twice."

---

## 4:15–5:00 · Failure mode and the hot take

**Screen.** The mapper stage in the architecture diagram.

> "The honest failure mode: if the mapper pairs the wrong element, everything
> downstream is confidently, verifiably wrong about a comparison that should
> never have happened. Every number correct, every citation resolving. The
> verifier is structurally blind to it — it sits above the measurement layer."

> "Which is the hot take. Verification is only as good as the layer beneath it,
> and everyone builds it one layer too high. Our verifier isn't clever; it just
> re-runs arithmetic the model was never allowed to do. So before designing the
> checker, find the earliest step whose output nothing downstream can verify, and
> spend the engineering there. For us that's mapping — and the fix wasn't a
> smarter checker. It was teaching the agent to abstain, and telling the user
> which components went unaudited."

**Screen.** The report's "not audited" panel. Hold.

---

## Recording notes

- Run `make cases` first so timings match.
- Use `--run-id demo` so paths on screen match the README.
- Do not cut the `make eval` run; it finishes in about a second.
- Show the clean control. It is the least dramatic and most important number.
