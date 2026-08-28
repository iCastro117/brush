# Brush — user manual

Everything you need to run Brush, in order, with a way out of each place it can
go wrong.

**If you only read one thing:** run `python3 run.py doctor` (`python run.py
doctor` on Windows). It checks the install and names the exact command that fixes
whatever it finds.

---

## Windows in sixty seconds

Windows has no `python3` command, so the first thing you type fails. That is
normal and nothing is broken. The full path, start to finish, in PowerShell:

```powershell
python --version                    # if this fails, try:  py --version
python run.py doctor                # six lines must say "ok"

python eval/mutations.py            # generate the defect cases
python tests/test_integrity.py      # \
python tests/test_verifier.py       #  |  four suites, all must say PASSED
python tests/test_clean_control.py  #  |
python tests/test_cli_errors.py     # /
python eval/run_eval.py             # the results table from the README

python run.py audit --design eval/cases/design.spec.json --html eval/cases/checkout.html --css eval/cases/generated/case_01.css --out out --run-id demo
start out\demo.report.html          # opens the report
```

Three rules for the rest of this manual on Windows: use **`python`** wherever it
says `python3`, ignore every **`make`** command (the plain equivalent is always
given next to it), and keep long commands on **one line** — PowerShell does not
understand `\` as a line continuation.

Details and every failure case: [section 1](#1-before-you-start) and
[section 11](#11-troubleshooting).

---

## Contents

1. [Before you start](#1-before-you-start)
2. [Install — four routes](#2-install--four-routes)
3. [Verify it works](#3-verify-it-works)
4. [Your first audit](#4-your-first-audit)
5. [Reading the report](#5-reading-the-report)
6. [Auditing your own project](#6-auditing-your-own-project)
7. [Reviewing many screens from a spreadsheet](#7-reviewing-many-screens-from-a-spreadsheet)
8. [Approving intentional deviations](#8-approving-intentional-deviations)
9. [Running with a live model](#9-running-with-a-live-model)
10. [Reproducing the published numbers](#10-reproducing-the-published-numbers)
11. [Troubleshooting](#11-troubleshooting)
12. [Command reference](#12-command-reference)

---

## 1. Before you start

**You need:** Python 3.10 or newer. Nothing else.

The audit engine has no third-party dependencies — the CSS cascade resolver, the
colour maths and the agent loop are all standard library. Two optional packages
unlock two optional features, and you can skip both.

Check what you have:

```bash
python3 --version
```

> ### On Windows, `python3` does not exist
>
> This is the first thing almost every Windows user hits, and it looks alarming:
>
> ```
> python3 : El término 'python3' no se reconoce como nombre de un cmdlet…
> CommandNotFoundError
> ```
>
> Nothing is broken. Windows simply does not create a `python3` command. Find
> yours by trying these two, in this order:
>
> ```powershell
> python --version
> py --version
> ```
>
> Whichever one prints a version number — `Python 3.12.4`, `Python 3.14.4` —
> **is your command**. Use it everywhere this manual says `python3`.
>
> | you got | your command is |
> |---|---|
> | `python --version` → a version | `python` |
> | `py --version` → a version | `py` |
> | both fail | Python is not installed — see the table below |
>
> **If typing `python` opens the Microsoft Store**, that is a placeholder alias
> Windows ships by default, not Python. Turn it off in *Settings → Apps →
> Advanced app settings → App execution aliases*, and switch off both entries
> named `python.exe` and `python3.exe`. Then install Python properly.
>
> **The rest of this manual works identically on Windows**, with three
> substitutions that are called out again wherever they matter:
>
> | this manual writes | on Windows PowerShell use |
> |---|---|
> | `python3 run.py …` | `python run.py …` |
> | `make demo` | the plain command — see [section 4](#4-your-first-audit); `make` is not installed on Windows |
> | `\` to continue a long line | keep it on **one line** (PowerShell uses a backtick `` ` ``, which is easy to mistype) |
> | `open file.html` | `start file.html` |
> | `export VAR=value` | `$env:VAR="value"` |

<details>
<summary><b>If no Python is installed, or it prints 3.9 or older</b></summary>

| system | what to do |
|---|---|
| Windows | `winget install Python.Python.3.12` — then **close the terminal and open a new one**. Or download from [python.org](https://www.python.org/downloads/) and **tick "Add Python to PATH"** on the first installer screen. Missing that tick is the single most common cause of `command not found` |
| macOS | `brew install python@3.12`, then use `python3.12` in place of `python3` |
| Ubuntu / Debian | `sudo apt update && sudo apt install python3.12 python3.12-venv` |
| Fedora / RHEL | `sudo dnf install python3.12` |
| No admin rights | Download a standalone build from [python-build-standalone](https://github.com/astral-sh/python-build-standalone/releases) and unpack it in your home folder |

Several versions can coexist. If `python3` is old but `python3.12` exists, use
`python3.12` everywhere in this manual.
</details>

**Get the code:**

```bash
git clone <repository-url>
cd brush
```

Or unzip `brush.zip` and `cd` into the folder it creates. Every command below is
run from the repository root — the folder containing `README.md` and `Makefile`.
Confirm you are in the right place:

```bash
ls          # PowerShell understands ls too; cmd.exe needs dir
```

You should see `README.md`, `Makefile`, `run.py`, `src`, `docs`, `eval`. If you
see a single folder called `brush` instead, you are one level too high — `cd
brush` and look again.

---

## 2. Install — four routes

**Try Route A. If anything fails, Route B always works.** They are ordered from
tidiest to most bulletproof, not from best to worst.

### Route A — virtual environment (recommended)

A venv keeps Brush's packages away from your system Python. This is the normal
way to install Python software.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[all]"
```

You should now have a `brush` command:

```bash
brush version
```

<details>
<summary><b>What <code>-e ".[all]"</code> means</b></summary>

- `-e` installs in *editable* mode: the package points at your source folder, so
  edits to `ux_laws.json` take effect immediately without reinstalling.
- `[all]` pulls both optional extras. Narrower choices:
  - `pip install -e .` — audit engine only, zero dependencies
  - `pip install -e ".[sheets]"` — adds `openpyxl` for `brush batch`
  - `pip install -e ".[live]"` — adds the `anthropic` SDK for live model runs
</details>

### Route B — no install at all (always works)

If `pip` or `venv` gives you any trouble, skip both. `run.py` puts the source on
the path and runs the same CLI.

```bash
python3 run.py doctor
python3 run.py audit --design eval/cases/design.spec.json \
    --html eval/cases/checkout.html \
    --css eval/cases/generated/case_01.css
```

Anywhere this manual says `brush`, you can say `python3 run.py` instead. This
route needs no network, no admin rights and no packages. It is the one to use on
a locked-down machine, and it is how the graders can run the project in under a
minute.

For spreadsheet mode on this route you still need openpyxl:
`pip install --user openpyxl`.

### Route C — pipx (isolated, global command)

If you want `brush` available everywhere without touching your system Python:

```bash
pipx install -e ".[all]"
```

Install pipx first with `python3 -m pip install --user pipx` if you do not have
it.

### Route D — Docker (nothing installed on your machine)

```bash
docker run --rm -it -v "$PWD":/app -w /app python:3.12-slim \
    bash -c "pip install -e '.[all]' -q && brush doctor"
```

Useful when your machine's Python is a lost cause, or to prove reproducibility on
a clean image.

---

## 3. Verify it works

```bash
brush doctor          # or: python3 run.py doctor
```

You should see:

```
  Brush — installation check

  ok    Python 3.10 or newer           found 3.12.3 on Linux
  ok    brush package importable       /path/to/brush/src/brush
  ok    knowledge pack loads           30 laws, 10 heuristics, 5 WCAG criteria, 22 clauses
  ok    colour engine correct          #767676 on white = 4.54:1 (expected 4.54)
  ok    sample files present           /path/to/brush
  ok    end-to-end audit runs          226 measurements, 0 findings on the conforming file (expected 0)

  ok    spreadsheet mode (optional)    openpyxl 3.1.5
  --    live model mode (optional)     anthropic SDK not installed
  --    ANTHROPIC_API_KEY (optional)   not set — the offline provider needs no key
```

The first six lines must say `ok`. The three below the gap are optional — `--`
there means a feature you are not using yet, not a problem.

**Any `FAIL` prints the exact command that fixes it.** If you would rather see
the whole picture, [section 11](#11-troubleshooting) has a table of every failure
and its cause.

Then run the test suite:

```bash
make test
```

Without `make`, run the four files in turn:

```powershell
python tests/test_integrity.py
python tests/test_verifier.py
python tests/test_clean_control.py
python tests/test_cli_errors.py
```

Four files, 25 tests, 53 assertions: repository integrity, eight adversarial attacks
on the verifier, and the clean-control audit that must produce zero findings.
All three must print `PASSED`.

---

## 4. Your first audit

The repository ships with a design system (*Meridian Checkout*) and an
implementation of it. `eval/cases/checkout.css` conforms; the generated cases
under `eval/cases/generated/` have known defects injected.

**Step 1 — generate the defect cases** (once, after cloning):

```bash
make cases
```

> **No `make`?** It is not installed on Windows and is optional everywhere else.
> Every `make` target in this manual is a shortcut for one or two plain commands,
> and both forms are given side by side from here on. The equivalent here is:
>
> ```powershell
> python run.py --version    # sanity check, optional
> python eval/mutations.py
> ```

**Step 2 — audit the conforming file.** This should find nothing.

Keep it on one line — PowerShell does not accept `\` as a line continuation:

```powershell
python run.py audit --design eval/cases/design.spec.json --html eval/cases/checkout.html --css eval/cases/checkout.css --out out --run-id clean
```

On macOS or Linux you can split it for readability:

```bash
python3 run.py audit \
  --design eval/cases/design.spec.json \
  --html   eval/cases/checkout.html \
  --css    eval/cases/checkout.css \
  --out    out --run-id clean
```

```
  Brush — run clean  [provider: offline]
  226 measurements · 0 out of tolerance · 0 tool calls
  0 verified findings
```

If this reports findings, something is wrong — see
[section 11](#11-troubleshooting).

**Step 3 — audit the hard case**, 17 defects injected at once:

```bash
make demo
```

Without `make`, one line:

```powershell
python run.py audit --design eval/cases/design.spec.json --html eval/cases/checkout.html --css eval/cases/generated/case_01.css --out out --run-id demo
```

```
  Brush — run demo  [provider: offline]
  229 measurements · 61 out of tolerance · 26 tool calls
  41 verified findings  (6 blocker, 19 major, 9 minor, 7 info)
  verifier: 41 proposed → 41 accepted, 0 rejected, 0 corrected
```

Three files land in `out/`:

| file | what it is |
|---|---|
| `demo.report.html` | the report a reviewer reads — **open this one** |
| `demo.audit.json` | every finding and measurement, machine-readable |
| `demo.trajectory.md` | what each agent did, tool call by tool call |

Open the report:

```powershell
start out\demo.report.html         # Windows
```

```bash
open out/demo.report.html          # macOS
xdg-open out/demo.report.html      # Linux
```

In VS Code you can also right-click `out/demo.report.html` in the explorer and
choose **Open with Live Preview**, or just double-click it in your file manager.

---

## 5. Reading the report

The report is ordered so you can stop reading at any point and still have acted
on the most important thing.

**Headline** — one sentence, worst problem first.

**Start here** — the three fixes with the best consequence-to-effort ratio.

**Root causes** — findings grouped by shared cause. A design system's drift is
usually one wrong value repeated, not forty independent mistakes, so this section
is where the leverage is: one token change often clears a dozen rows.

**Findings** — one card each, sorted by severity:

| band | meaning |
|---|---|
| **Blocker** | Fails WCAG AA, removes a state the user needs, or drops a target under 24px |
| **Major** | Visible to an ordinary user and changes meaning or hierarchy |
| **Minor** | Perceptible on close inspection, does not change meaning |
| **Info** | Below perception but off-spec — an off-token literal, a sub-pixel nudge |

Each card carries a **drift bar** putting the spec value and the code value on
one axis, so you see the distance rather than doing the subtraction; the UX
principles the deviation violates; the smallest fix; and the **evidence ids** —
`Button/Primary@default::padding-left` — which you can look up in the JSON. Every
number was recomputed by the verifier before it was allowed into the report.

**How this was verified** — how many findings the agent proposed, how many
survived recomputation, how many had their severity corrected.

---

## 6. Auditing your own project

Brush needs two things: a specification and an implementation.

### Step 1 — write a specification

Copy `eval/cases/design.spec.json` and edit it. The shape:

```json
{
  "root_font_size": 16,
  "grid_base": 4,
  "tokens": {
    "color":       { "brand-600": "#1F6FEB", "ink-900": "#0F1115" },
    "space":       { "space-2": "8px", "space-6": "24px" },
    "font_size":   { "fs-body": "16px" },
    "font_weight": { "fw-semibold": 600 },
    "radius":      { "radius-md": "8px" }
  },
  "components": [
    {
      "name": "Button/Primary",
      "role": "button",
      "selector_hint": "button.btn.btn--primary",
      "text": "Place order",
      "on_background": "{color.surface-000}",
      "props": {
        "padding": "12px 24px",
        "background-color": "{color.brand-600}",
        "font-size": "{font_size.fs-body}",
        "min-height": "48px"
      },
      "states": {
        "focus": { "outline-width": "2px", "outline-style": "solid",
                   "outline-color": "{color.brand-600}" }
      }
    }
  ]
}
```

Notes that save time:

- `{color.brand-600}` references a token. Use references, not literals — that is
  how Brush knows a hard-coded hex is off-token.
- `role` drives the accessibility rules. `button`, `input`, `link` and `select`
  get target-size checks; `body`, `label`, `alert` get contrast and leading
  checks.
- `states` is where focus rings live. If you specify a focus state and the
  stylesheet has no focus rule, Brush reports the **absence** as a blocker —
  which no value-by-value comparison can do.
- Omit anything you do not want audited. An omitted property is "not specified",
  not "must be zero".

### Step 2 — point Brush at your files

```bash
brush audit \
  --design path/to/your.spec.json \
  --html   path/to/page.html \
  --css    path/to/styles.css path/to/components.css \
  --out    out
```

Multiple stylesheets are fine — they cascade in the order you list them.

### Step 3 — component mapping

By default Brush ignores annotations and lets the mapper agent pair
`Button/Primary` with the element implementing it, using `selector_hint` and the
element's role and text. If it cannot decide, it says "no match" and skips the
component rather than guessing — an unmapped component is listed in the report.

To make mapping exact, add `data-ds-component` attributes to your HTML and pass
`--use-annotations`:

```html
<button class="btn btn--primary" data-ds-component="Button/Primary">Place order</button>
```

```bash
brush audit ... --use-annotations
```

<details>
<summary><b>What the CSS engine does and does not support</b></summary>

**Supported:** class, id, element and attribute selectors; descendant and child
combinators; specificity and source order; inheritance; `var()` with fallbacks;
`padding`/`margin`/`border`/`outline`/`gap`/`border-radius` shorthands; `px`,
`rem`, `em`, `pt`, `ch` units; `:hover`, `:focus`, `:focus-visible`, `:disabled`
captured as separate states.

**Not supported:** layout. Brush never computes used widths from flow, so
percentage lengths stay unresolved rather than guessed — a wrong number is worse
than no number. `@media` blocks are skipped; the base viewport is audited.
CSS-in-JS and Tailwind need to be compiled to plain CSS first
(`npx tailwindcss -i in.css -o out.css`), then pass the output.
</details>

---

## 7. Reviewing many screens from a spreadsheet

**Step 1 — create a workbook:**

```bash
brush template --out cases.xlsx
```

```powershell
pip install openpyxl                       # once — spreadsheet mode needs it
python run.py template --out cases.xlsx
```

**Step 2 — fill in the yellow cells.** One row per screen:

| column | what to put |
|---|---|
| `ID` | any label |
| `IMAGE/FIGMA` | path to a `design.spec.json`, or to a mockup image |
| `CODE` | path to the `.html` |
| `CSS` | stylesheet(s), comma separated. Blank = look for a `.css` beside the HTML |
| `EXPECTED` | *optional*: the score you would give the row — `0`, `0.5` or `1` |

Paths are relative to the spreadsheet's folder, or pass `--base-dir`.

**Step 3 — run it:**

```bash
brush batch --sheet cases.xlsx --out results.xlsx
```

```powershell
python run.py batch --sheet cases.xlsx --out results.xlsx
```

**Step 4 — open `results.xlsx`.** Four tabs: `Cases`, `Findings`, `Summary`,
`Rubric`.

Two scores come back, and keeping them apart is the whole point:

- **`CONFORMANCE`** — *does the code match the design?*
  `1.0` no blockers and no majors · `0.5` no blockers but at least one major ·
  `0.0` at least one blocker. It is a live Excel formula, so the rubric is
  visible and the sheet recalculates if you edit the counts.
- **`POINTS`** — *was Brush right?* Agreement against the `EXPECTED` score **you**
  filled in. `1.0` exact · `0.5` one band apart · `0.0` two bands apart.

**With `EXPECTED` blank, `POINTS` just mirrors `CONFORMANCE` and measures
nothing** — the Rubric tab says so in the workbook. A model reporting its own
verdict as an accuracy figure is the failure this project argues against.

Try it on the shipped 12-case set:

```bash
make batch     # -> out/brush_results.xlsx, 12/12 exact agreement
```

```powershell
python run.py batch --sheet eval/cases/brush_cases.xlsx --base-dir . --out out/brush_results.xlsx
start out\brush_results.xlsx
```

Full detail, including **why no training is required**:
[`docs/BATCH_REVIEW.md`](BATCH_REVIEW.md).

---

## 8. Approving intentional deviations

Not every deviation is a defect. When one is deliberate, record it — otherwise it
is reported on every commit until the team mutes the tool, and a muted tool is
worse than no tool.

```bash
brush approve --ledger out/ledger.json \
  --node "Button/Ghost@default" --prop min-height --value 28 \
  --reason "Compact toolbar variant signed off by design 2026-08-14" \
  --by "a.rivera"
```

Then pass the ledger on later runs:

```bash
brush audit ... --ledger out/ledger.json
```

**An approval is scoped to the value it was granted for.** Approving a 28px ghost
button suppresses that finding; if the value later drifts to 20px the approval no
longer covers it and the finding comes back. That is what stops the ledger
becoming a permanent blindfold.

List what has been approved:

```bash
brush ledger --ledger out/ledger.json
```

Approvals expire after 180 days by default (`--expires`), so nobody inherits a
decision made by someone who left two years ago.

---

## 9. Running with a live model

Everything so far used the `offline` provider — a deterministic policy that is
**not a language model**. It exists so the whole project runs with no API key.
To use real Claude:

```bash
pip install anthropic                    # or: pip install -e ".[live]"
export ANTHROPIC_API_KEY=sk-ant-...

brush audit \
  --design eval/cases/design.spec.json \
  --html   eval/cases/checkout.html \
  --css    eval/cases/generated/case_01.css \
  --provider anthropic \
  --cassette out/cassette.json \
  --out out --run-id live
```

On Windows PowerShell — note `$env:` rather than `export`, and one line:

```powershell
pip install anthropic
$env:ANTHROPIC_API_KEY="sk-ant-..."
python run.py audit --design eval/cases/design.spec.json --html eval/cases/checkout.html --css eval/cases/generated/case_01.css --provider anthropic --cassette out/cassette.json --out out --run-id live
```

The variable only lasts for that terminal window. To keep it, use
`setx ANTHROPIC_API_KEY "sk-ant-..."` once, then **open a new terminal**.

`--cassette` records every request and response. Once recorded, anyone can replay
your exact run with no key and no network:

```bash
brush audit ... --provider replay --cassette out/cassette.json
```

That is how a reviewer reproduces live figures **exactly** rather than
approximately.

**Reading a mockup image.** With a live provider, the `IMAGE/FIGMA` column
accepts a `.png` or `.jpg`. A vision model drafts a specification from it and
writes `<name>.draft.json` marked `review_status: unconfirmed`. **Brush refuses
to audit against it** until you confirm it, or pass `--accept-drafted-spec` — in
which case the run is labelled `PROVISIONAL`. A mis-read mockup turns every
downstream measurement into a confident, well-evidenced fiction, so the refusal
is the default.

---

## 10. Reproducing the published numbers

```bash
make cases       # regenerate the mutation set, seed 20260828
make test        # 25 tests, 53 assertions, across 4 files
make eval        # baseline vs Brush over 12 cases
```

`make eval` takes under a second and prints the table from the README. Results
land in `eval/results/eval_offline.json` with a `provenance` block recording the
provider, the seed and the timestamp.

For live figures:

```bash
python3 eval/run_eval.py --provider anthropic --cassette out/eval-cassette.json
```

Methodology, and an honest account of what these numbers do and do not prove:
[`docs/REPRODUCTION.md`](REPRODUCTION.md).

---

## 11. Troubleshooting

**Start here:** `brush doctor` (or `python3 run.py doctor`). It names the fix for
whatever it finds. The table below covers the rest.

### Install and startup

| What you see | Why | Fix |
|---|---|---|
| **Windows:** `python3 : El término 'python3' no se reconoce…` / `python3: command not found` | Windows has no `python3` command | Use `python` instead. Try `python --version`, then `py --version`; whichever answers is your command |
| **Windows:** `py : El término 'py' no se reconoce…` | The Python launcher was not installed | Not a problem if `python` works. If neither works, `winget install Python.Python.3.12` and open a **new** terminal |
| **Windows:** typing `python` opens the Microsoft Store | A default Windows alias, not Python | *Settings → Apps → Advanced app settings → App execution aliases* → switch off `python.exe` and `python3.exe`. Then install Python properly |
| **Windows:** `make : El término 'make' no se reconoce…` | `make` is not part of Windows | Every `make` target has a plain-command equivalent in this manual. You never need `make` |
| **Windows:** a long command fails after the first line | PowerShell does not accept `\` as a line continuation | Put the whole command on one line |
| `command not found: brush` | Not installed, or the venv is not active | `source .venv/bin/activate`, or just use `python3 run.py` (`python run.py` on Windows) |
| Doctor says `Ready. Try: brush audit …` but `brush` is not found | `brush` only exists after `pip install -e .` | Use `python run.py audit …`. Doctor prints the form matching how you launched it, so if it still says `brush`, you did install it and the venv is simply inactive |
| `No module named brush` | Running from the wrong folder, or not installed | `cd` to the repo root and use `python3 run.py`, or `PYTHONPATH=src python3 -m brush.cli` |
| `error: externally-managed-environment` | Debian/Ubuntu blocks pip on system Python | Use a venv (Route A). Or `pip install --user -e .`. Never use `--break-system-packages` on a machine you care about |
| `No module named venv` | `python3-venv` not installed | `sudo apt install python3-venv`, or skip to Route B |
| `pip: command not found` | pip missing | `python3 -m ensurepip --upgrade`, or Route B |
| `SSL: CERTIFICATE_VERIFY_FAILED` on pip | Corporate proxy | Route B needs no network at all |
| `Brush needs Python 3.10 or newer` | Old interpreter | Use `python3.12 run.py ...`. See [section 1](#1-before-you-start) |
| `ModuleNotFoundError: openpyxl` | Only affects `brush batch` | `pip install openpyxl`. Everything else works without it |
| `Permission denied` writing to `out/` | Read-only folder | `--out ~/brush-out`, or `chmod u+w out` |
| `cannot create the output directory` | `--out` points somewhere unwritable | Checked before any work runs, so nothing is wasted. Use `--out ~/brush-out` |

### Running an audit

| What you see | Why | Fix |
|---|---|---|
| `design specification not found: …` | Wrong path | Paths are relative to where you ran the command. Brush suggests the nearest real filename |
| `no components could be paired, so nothing was audited` | The HTML has none of the elements the spec describes | Exits non-zero on purpose — auditing nothing must never look like a pass. Check `selector_hint`, or add `data-ds-component` and pass `--use-annotations` |
| `is a directory, not a file` | A folder was passed where a file belongs | Pass the file itself |
| `is not valid JSON … (line N)` | Malformed spec or ledger | The line number is in the message; check with `python3 -m json.tool` |
| A component listed as **not found in the implementation** | The mapper abstained rather than guess | Add a `selector_hint`, or annotate the element. This is deliberate — a wrong pairing produces a page of fictional findings |
| Findings on a file you believe is correct | Usually the spec is stale, not the code | This is Brush's main failure mode. Check the evidence ids against reality before changing code |
| `line 1 column 1 (char 0)` reading the spec | Malformed JSON | `python3 -m json.tool your.spec.json` points at the line |
| Percentages reported as `—` | Layout is not computed | Expected. Brush never guesses a used width. Specify lengths in `px` or `rem` |
| `@media` rules seem ignored | Only the base viewport is audited | Expected. Run separate audits against separate stylesheets if you need breakpoints |
| `cassette miss (…)` | Prompts changed since recording | Re-record with `--provider anthropic`, or use `--provider offline` |
| `provider=anthropic needs ANTHROPIC_API_KEY` | Key not exported | `export ANTHROPIC_API_KEY=sk-ant-...` in the *same* shell |

### Spreadsheet mode

| What you see | Why | Fix |
|---|---|---|
| `could not find the header row` | Header names unrecognised | First row needs `ID` plus `IMAGE/FIGMA` or `CODE`. Spanish names work. `brush template` gives a valid sheet |
| `implementation not found: …` | Relative paths resolved from the sheet's folder | Pass `--base-dir .` to resolve from the repo root instead |
| `POINTS` all `1.0` and it looks too good | `EXPECTED` is blank, so POINTS mirrors CONFORMANCE | Fill in `EXPECTED` yourself. See the Rubric tab |
| An `EXPECTED` cell is empty but you typed something | The value was not a score | Use `0`, `0.5` or `1`. Words work too: `sí`/`yes`/`ok`, `parcial`/`partial`, `no`/`fail`. Anything else is kept as a cell note instead of breaking the formula |
| `could not find the header row` names your columns | Header not recognised | The first row needs `ID` plus `IMAGE/FIGMA` or `CODE` |
| Formula cells look empty in pandas | openpyxl writes formulas without cached values | Open once in Excel/LibreOffice to recalculate, or read with `data_only=False` |
| `drafted a specification at ….draft.json` | A mockup was read but not confirmed | Review the draft, set `review_status` to `confirmed`, re-run. Or `--accept-drafted-spec` |

### Still stuck

```bash
BRUSH_DEBUG=1 brush audit ...     # full traceback instead of a summary
```

---

## 12. Command reference

```
brush doctor                  check the install, name the fix for anything broken
brush version                 versions of brush and python

brush audit                   audit one implementation against one specification
  --design PATH               design.spec.json                        [required]
  --html PATH                 the implementation                      [required]
  --css PATH [PATH ...]       stylesheet(s), cascaded in order        [required]
  --out DIR                   where reports go                        [out]
  --run-id NAME               names the output files                  [random]
  --ledger PATH               approved deviations to honour
  --provider {offline,anthropic,replay}                               [offline]
  --model NAME                                            [claude-sonnet-4-6]
  --cassette PATH             record with anthropic, replay with replay
  --use-annotations           trust data-ds-component instead of the mapper

brush batch                   audit every row of a spreadsheet
  --sheet PATH                input .xlsx                             [required]
  --out PATH                  scored workbook                    [results.xlsx]
  --base-dir DIR              root for relative paths        [the sheet's folder]
  --accept-drafted-spec       audit against an unconfirmed drafted spec
  (also takes --provider, --model, --cassette, --ledger)

brush template --out PATH     write a blank review workbook

brush approve                 record an intentional deviation
  --ledger PATH --node KEY --prop NAME --value V --reason TEXT --by WHO
  --tolerance F               how far the value may move            [0.5]
  --expires DAYS                                                    [180]

brush ledger --ledger PATH    list approved deviations
```

**Make targets**

```
make cases        regenerate the seeded mutation set
make test         27 tests: integrity, verifier, clean control, CLI errors
make eval         baseline vs Brush over 12 cases
make demo         audit the hard case -> out/demo.report.html
make clean-demo   audit the conforming file -> expect 0 findings
make batch        score the 12-case workbook
make all          cases + test + eval + demo + batch
```

**Environment**

```
ANTHROPIC_API_KEY    required only for --provider anthropic
BRUSH_DEBUG=1        print full tracebacks instead of summaries
PY                   override the interpreter: make eval PY=python3.12
```
