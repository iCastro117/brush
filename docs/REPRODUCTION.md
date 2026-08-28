# Reproduction guide

Written for someone starting from an empty directory with nothing installed.

## 0. What you need

| | |
|---|---|
| Python | 3.10 or newer (developed on 3.12.3) |
| OS | Linux, macOS or WSL |
| Disk | < 5 MB |
| Network | Only to clone and to `pip install -e .` |
| API key | **Not required** for any result in the README |
| Runtime | Full suite in under 10 seconds |
| Cost | $0.00 offline |

There is no browser, no headless Chromium, no database and no framework. The runtime imports only the Python standard library.

## 1. Set up

```bash
git clone <repo-url> brush
cd brush
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[all]"
```

Verify:

```bash
brush doctor
```

That checks the interpreter, the package, the knowledge pack, the colour engine
and a full end-to-end audit, and prints the exact command to fix anything it
finds. All six required lines must read `ok`; the three optional ones below the
gap are features you may not need.

**If `pip install` failed for any reason**, skip it entirely — the audit engine
has no third-party dependencies:

```bash
python3 run.py doctor
```

Every command in this guide works with `python3 run.py` substituted for `brush`.
Four installation routes and a symptom-to-fix table are in
[`MANUAL.md`](MANUAL.md).

## 2. Data

All inputs are synthetic and live in the repo. Nothing is downloaded and no private data is used.

| File | What it is |
|---|---|
| `eval/cases/design.spec.json` | "Meridian Checkout DS" — 14 colour tokens, 8 spacing, 7 sizes, 4 weights, 4 radii, 12 components, 1 declared grouping |
| `eval/cases/checkout.html` | The implemented markup |
| `eval/cases/checkout.css` | The **conforming** stylesheet — audits to 0 findings |
| `eval/cases/generated/` | 12 mutated stylesheets + `cases.json` with ground truth |

Regenerate the mutated cases (deterministic, seeded):

```bash
python eval/mutations.py --seed 20260828
```

Expected: `generated 12 cases in eval/cases/generated`, with `case_00` the clean control (0 mutations) and `case_01` the hard case (17 mutations).

## 3. Run the solution

```bash
python -m brush.cli audit \
  --design eval/cases/design.spec.json \
  --html   eval/cases/checkout.html \
  --css    eval/cases/generated/case_01.css \
  --out    out --run-id demo
```

Expected output:

```
  Brush — run demo  [provider: offline]
  229 measurements · 61 out of tolerance · 26 tool calls
  41 verified findings  (6 blocker, 19 major, 9 minor, 7 info)
  verifier: 41 proposed → 41 accepted, 0 rejected, 0 corrected
  0.034s · $0.3434

  6 accessibility blocker(s) and 19 visible deviation(s): Button/Primary: outline-color does not match spec.
```

Three files land in `out/`:

| File | What it is |
|---|---|
| `demo.report.html` | The reviewer-facing report — **open this one** |
| `demo.audit.json` | Every finding, measurement id and stat, machine-readable |
| `demo.trajectory.md` / `.jsonl` | Every agent step, tool call and tool response |

Sanity check — the conforming stylesheet must report nothing:

```bash
python -m brush.cli audit \
  --design eval/cases/design.spec.json --html eval/cases/checkout.html \
  --css eval/cases/checkout.css --out out --run-id clean
# → 226 measurements · 20 out of tolerance · 0 verified findings
```

Note the 20 "out of tolerance" against 0 findings: the measurement layer flags
anything that is not numerically identical, and the classifier then correctly
rejects every one of them (a 1px border is not off-grid, `transparent` is not an
off-token colour, and so on). That gap is the false-positive filter doing its job.

## 4. Run the baselines

**B1 — script baseline** (no key, always available):

```bash
python baseline/naive_diff.py \
  --design eval/cases/design.spec.json \
  --css eval/cases/generated/case_01.css
# → naive_diff: 24 differences in ~0.008s
```

**B2 — single-prompt LLM baseline** (needs a key):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pip install -e ".[live]"
python baseline/single_prompt.py \
  --design eval/cases/design.spec.json \
  --css eval/cases/generated/case_01.css \
  --out eval/results/b2_case01.json
```

## 5. Reproduce every number in the README

```bash
python eval/run_eval.py
```

Runs all 12 cases through both B1 and the pipeline, derives ground truth, and writes `eval/results/eval_offline.json`. Takes about 1 second. Expected aggregate:

```
  metric                             baseline     pipeline        Δ
  defects found (TP)                       82          105      +23
  defects missed (FN)                      23            0      -23
  spurious (FP)                             0            0       +0
  precision                             1.000        1.000    +0.0p
  recall                                0.781        1.000   +21.9p
  F1                                    0.877        1.000   +12.3p
    · recall, plain properties          0.932        1.000    +6.8p
    · recall, derived relations         0.000        1.000  +100.0p
  catalogue recall (independent)        0.961        1.000    +3.9p
  severity accuracy                       n/a        1.000
  false positives on clean case             0            0
```

These figures are byte-reproducible: the offline provider is deterministic and the case set is seeded.

## 6. Run the tests

```bash
python tests/test_integrity.py       # 4 — knowledge pack ↔ code consistency
python tests/test_verifier.py        # 8 — adversarial attacks on the verifier
python tests/test_clean_control.py   # 2 — zero findings on a conforming file
```

All 14 must pass. `test_verifier.py` is the one to read: in offline mode the verifier's rejection rate is 0 by construction, so it is demonstrated by attacking it directly with the failure modes a real model produces.

## 7. Human approval loop (ground rules 04 and 05)

No finding is ever dismissed on the agent's own authority. A reviewer records an intentional deviation:

```bash
python -m brush.cli approve --ledger out/ledger.json \
  --node "Button/Ghost@default" --prop min-height --value 28 \
  --reason "Compact toolbar variant, signed off 2026-08-20" --by "a.rivera"

python -m brush.cli audit --design eval/cases/design.spec.json \
  --html eval/cases/checkout.html --css eval/cases/generated/case_05.css \
  --ledger out/ledger.json --out out --run-id approved
```

The finding is suppressed and the suppression is recorded in the trajectory as a `checkpoint` step.

**The property that makes this safe:** the approval is scoped to the *value*, not the property name. Approving `min-height = 28` does not suppress a later drift to `20`. Verify:

```bash
python -c "
import sys; sys.path.insert(0,'src')
from brush.memory.ledger import Ledger
l = Ledger(); l.approve('Button/Ghost@default','min-height',28,'demo','you')
print('28 suppressed:', bool(l.suppresses('Button/Ghost@default','min-height',28)))
print('20 suppressed:', bool(l.suppresses('Button/Ghost@default','min-height',20)))
"
# 28 suppressed: True
# 20 suppressed: False
```

## 8. Run against a live model

Everything above uses `--provider offline`, a deterministic scripted policy that is **not a language model**. It exercises the full architecture with no credentials. To run the real thing:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pip install -e ".[live]"

python -m brush.cli audit \
  --design eval/cases/design.spec.json --html eval/cases/checkout.html \
  --css eval/cases/generated/case_01.css \
  --provider anthropic --cassette out/case01.cassette.json \
  --out out --run-id live
```

Recording is automatic. Anyone can then replay your exact run with no key and no network:

```bash
python -m brush.cli audit ... --provider replay --cassette out/case01.cassette.json
```

Full live evaluation:

```bash
python eval/run_eval.py --provider anthropic --cassette out/eval.cassette.json
```

Approximate cost: ~40 model calls per case × 12 cases. On Sonnet pricing, roughly **$1.50–$3.00** for the full sweep, and 4–8 minutes of wall clock.

### Live results table — intentionally empty

| Metric | B1 script | B2 single prompt | Brush (anthropic) |
|---|---|---|---|
| Recall | 0.781 | _not run_ | _not run_ |
| Precision | 1.000 | _not run_ | _not run_ |
| Severity accuracy before verification | n/a | _not run_ | _not run_ |
| Verifier rejection rate | n/a | n/a | _not run_ |
| Cost per case | $0.00 | _not run_ | _not run_ |

These rows are blank because no one has run them yet. They are not estimated. Running section 8 fills them from `eval/results/eval_anthropic.json`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `provider=anthropic needs ANTHROPIC_API_KEY` | key not exported | `export ANTHROPIC_API_KEY=...` |
| `cassette miss (…)` | a prompt changed since recording | re-record with `--provider anthropic` |
| `no cassette at …` | replaying before recording | run section 8 first |
| Numbers differ from the README | case set regenerated with another seed | `python eval/mutations.py --seed 20260828` |
| `ModuleNotFoundError: brush` | package not installed | `pip install -e .` from the repo root |

## Versions this was verified on

```
Python 3.12.3 · Ubuntu 24.04 · no third-party runtime dependencies
anthropic>=0.40 (optional, live mode only)
```
