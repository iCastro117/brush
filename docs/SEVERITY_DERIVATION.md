# Severity derivation

`expected_band` in `eval/mutations.py` is the ground truth against which severity
accuracy is scored. If those bands were chosen by watching what the tool outputs,
the metric would be meaningless. They are derived instead from the **published
severity policy** in `src/brush/knowledge/ux_laws.json` applied to the
**measured value** of each mutation.

Every measurement below is reproducible:

```bash
python -c "
import sys; sys.path.insert(0,'src')
from brush.analyze.color import parse_color, delta_e2000, contrast_ratio, wcag_level
a,b = parse_color('#1B7F4B'), parse_color('#2E9E63')
print(round(delta_e2000(a,b),2), round(contrast_ratio(b,parse_color('#F7F8FA')),2))
"
```

## The policy bands

| Band | Rule (quoted from the policy) |
|---|---|
| `blocker` | Fails a WCAG AA criterion, or removes a state the user needs, or drops an interactive target below 24px |
| `major` | Visible and changes meaning: ΔE ≥ 3.0, spacing ≥ 4px on an interactive or grouping edge, font-size ratio ≥ 12%, weight delta ≥ 200, or a proximity inversion |
| `minor` | Perceptible on close inspection, meaning unchanged: ΔE 1.0–3.0, spacing 2–4px, font-size 6–12%, one weight step |
| `info` | Below perception but off-spec: ΔE < 1.0, spacing < 2px, off-token literals |

## Derivations

| ID | Change | Measured | Rule matched | Band |
|---|---|---|---|---|
| M01 | Button padding 24 → 20px | −4px, interactive edge | spacing ≥ 4px | `major` |
| M02 | Card padding 24 → 22px | −2px | spacing 2–4px | `minor` |
| M03 | `#1F6FEB` → `#2070EC` | **ΔE 0.375** | ΔE < 1.0, off-token | `info` |
| M04 | `#1B7F4B` → `#2E9E63` | **ΔE 11.03**; contrast **3.19:1** on `#F7F8FA` at 12px/600 (AA needs 4.5) | fails WCAG AA | `blocker` |
| M05 | Help text → `#A8AEB8` | contrast **2.23:1** on white (needs 4.5) | fails WCAG AA | `blocker` |
| M06 | Title 24 → 21px | ratio **−12.5%** | ≥ 12% | `major` |
| M07 | Weight 600 → 400 | delta **200** | ≥ 200 | `major` |
| M08 | Family → Helvetica | first family differs | `c-family-fallback` | `major` |
| M09 | Line-height 1.5 → 1.2 | below the **1.4** reading floor | `c-leading-floor` | `major` |
| M10 | Radius 8 → 4px | −4px radius | `c-radius-family` | `minor` |
| M11 | Focus rule deleted | state absent in code | removes a needed state | `blocker` |
| M12 | Ghost height 44 → 28px | −16px, above the 24px floor | target shrunk ≥ 4px | `major` |
| M13 | Ghost height 44 → 20px | **below 24px** | WCAG 2.5.8 | `blocker` |
| M14 | Label margin 8 → 2px | −6px on a grouping edge | spacing ≥ 4px | `major` |
| M15 | Input border → `#E8EAEE` | contrast **1.20:1** (non-text needs 3.0) | fails WCAG 1.4.11 | `blocker` |
| M16 | Alert padding 16 → 15px | −1px | spacing < 2px | `info` |
| M17 | Tracking −0.4 → 0px | 0.4px | spacing < 2px | `info` |
| M18 | Alert bg → `#FFF8E1` | **ΔE 13.17** | ΔE ≥ 5.0 | `major` |
| M19 | Label margin 8 → 28px | ratio **0.86**, below the 1.5 grouping floor | proximity inversion | `major` |

## Two bands we got wrong first

**M02** was assigned `major` on the reasoning that an off-grid 22px breaks page
rhythm. The policy puts a 2px delta in `minor`, and when we changed the
*classifier* to agree with the band rather than the band to agree with the
policy, it started grading a 1px trim as `major` (changelog I6). The band was
wrong, not the policy.

**M04** was assigned `major` on ΔE alone. Computing the contrast showed the
mutated green fails AA on the badge's own background, which the policy grades
`blocker` regardless of ΔE. The lesson generalises: a colour change has to be
checked against *both* the perceptual rule and the accessibility rule, and the
more severe one wins.
