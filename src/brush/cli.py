"""Brush command line."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .agents.orchestrator import run_audit
from .agents.provider import build_provider
from .memory.ledger import Ledger
from .report.html import write_html_report
from .trace.trajectory import Trajectory, load_trajectory


class UserError(Exception):
    """A problem the person can fix, reported as a sentence not a traceback."""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


def require_file(path: str, what: str, hint: str = "") -> str:
    if not path:
        raise UserError(f"no {what} given", hint=hint)
    if os.path.isdir(path):
        raise UserError(
            f"{what} is a directory, not a file: {path}",
            hint=f"pass the file itself, e.g. {os.path.join(path, 'styles.css')}",
        )
    if not os.path.exists(path):
        near = _nearby(path)
        # A near match beats a generic hint: most bad paths are typos, and
        # naming the real file is more useful than restating the rule.
        raise UserError(
            f"{what} not found: {path}",
            hint=(f"did you mean {near} ?" if near else
                  hint or "paths are relative to where you ran the command"),
        )
    return path


def require_writable_dir(path: str, what: str = "output directory") -> str:
    """
    Check we can actually write here before doing any work.

    Discovering an unwritable output folder after a full audit wastes the run and
    surfaces as whichever low-level error happened to fire first.
    """
    try:
        os.makedirs(path, exist_ok=True)
    except PermissionError as exc:
        raise UserError(f"cannot create the {what}: {path} (permission denied)",
                        hint="try --out ~/brush-out") from exc
    except (OSError, FileNotFoundError) as exc:
        raise UserError(f"cannot create the {what}: {path} ({exc.strerror or exc})",
                        hint="try --out ~/brush-out") from exc
    if not os.access(path, os.W_OK):
        raise UserError(f"the {what} is not writable: {path}",
                        hint="try --out ~/brush-out")
    return path


def _nearby(path: str) -> str:
    """Suggest a real file with a similar name -- most bad paths are typos."""
    import difflib
    folder = os.path.dirname(path) or "."
    if not os.path.isdir(folder):
        return ""
    matches = difflib.get_close_matches(os.path.basename(path), os.listdir(folder), 1, 0.6)
    return os.path.join(folder, matches[0]) if matches else ""


def _check_json(path: str, what: str) -> None:
    """Parse-check a JSON input up front so a syntax error names its own line."""
    import json as _json
    try:
        with open(path, "r", encoding="utf-8") as fh:
            _json.load(fh)
    except _json.JSONDecodeError as exc:
        raise UserError(
            f"{what} is not valid JSON: {path}  (line {exc.lineno}, column {exc.colno}: {exc.msg})",
            hint=f"check it with: python3 -m json.tool {path}",
        ) from exc
    except UnicodeDecodeError as exc:
        raise UserError(f"{what} is not a UTF-8 text file: {path}",
                        hint="is this actually a JSON file?") from exc


def _provider_or_error(kind: str, cassette, model):
    try:
        return build_provider(kind, cassette, model)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        hints = {
            "replay": "record one first: --provider anthropic --cassette out/cassette.json",
            "anthropic": "export ANTHROPIC_API_KEY=sk-ant-...  and  pip install anthropic",
        }
        raise UserError(str(exc), hint=hints.get(kind, "")) from exc


def cmd_audit(a) -> int:
    require_file(a.design, "design specification",
                 hint="try eval/cases/design.spec.json to see it working")
    require_file(a.html, "HTML implementation")
    for c in a.css:
        require_file(c, "stylesheet")
    require_writable_dir(a.out)
    _check_json(a.design, "design specification")
    if a.ledger and os.path.exists(a.ledger):
        _check_json(a.ledger, "ledger")
    provider = _provider_or_error(a.provider, a.cassette, a.model)
    rep = run_audit(
        design_path=a.design, html_path=a.html, css_paths=a.css,
        provider=provider, out_dir=a.out, ledger_path=a.ledger,
        ignore_annotations=not a.use_annotations, run_id=a.run_id,
    )
    os.makedirs(a.out, exist_ok=True)
    json_path = os.path.join(a.out, f"{rep.run_id}.audit.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(rep.to_dict(), fh, indent=2, default=str)

    html_path = os.path.join(a.out, f"{rep.run_id}.report.html")
    write_html_report(rep, html_path, design_path=a.design, code_path=a.html)

    md_path = os.path.join(a.out, f"{rep.run_id}.trajectory.md")
    steps = load_trajectory(rep.trajectory_path)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(_trajectory_md(rep.run_id, steps))

    s = rep.stats
    if s["paired_nodes"] == 0:
        raise UserError(
            "no components could be paired, so nothing was audited",
            hint=("check that the HTML actually contains the elements the spec "
                  "describes, that `selector_hint` matches your selectors, or add "
                  "data-ds-component attributes and pass --use-annotations"),
        )
    print(f"\n  Brush — run {rep.run_id}  [provider: {s['provider']}]")
    print(f"  {s['measurements']} measurements · {s['out_of_tolerance']} out of tolerance "
          f"· {s['tool_calls_total']} tool calls")
    print(f"  {s['findings']} verified findings  {_sev_line(s['by_severity'])}")
    print(f"  verifier: {rep.verification['proposed']} proposed → "
          f"{rep.verification['accepted']} accepted, "
          f"{rep.verification['rejected'] if isinstance(rep.verification['rejected'], int) else len(rep.verification['rejected'])} rejected, "
          f"{rep.verification['corrected'] if isinstance(rep.verification['corrected'], int) else len(rep.verification['corrected'])} corrected")
    print(f"  {s['wall_seconds']}s · ${s['usage']['cost_usd']:.4f}")
    print(f"\n  {rep.summary.get('headline', '')}\n")
    print(f"  report      {html_path}")
    print(f"  findings    {json_path}")
    print(f"  trajectory  {md_path}\n")
    return 0


def _sev_line(by_sev: dict) -> str:
    order = ["blocker", "major", "minor", "info"]
    bits = [f"{by_sev[k]} {k}" for k in order if by_sev.get(k)]
    return "(" + ", ".join(bits) + ")" if bits else ""


def _trajectory_md(run_id: str, steps: list[dict]) -> str:
    t = Trajectory.__new__(Trajectory)
    t.run_id = run_id
    t.steps = []
    from .trace.trajectory import Step
    meta = next((s for s in steps if s.get("type") == "run_meta"), {})
    for s in steps:
        if s.get("type") != "step":
            continue
        t.steps.append(Step(s["step_id"], s["agent"], s["kind"], s["summary"],
                            s.get("payload", {}), s.get("ts", 0),
                            s.get("parent"), s.get("duration_ms")))
    header = (f"_provider: `{meta.get('provider')}` · model: `{meta.get('model')}` · "
              f"annotations ignored: `{meta.get('ignore_annotations')}`_\n")
    body = t.to_markdown(f"Brush trajectory — {run_id}")
    return body.replace("\n\n", "\n\n" + header + "\n", 1)


def _load_sheets():
    """
    Import the spreadsheet layer only when it is actually used.

    openpyxl is the one third-party package the tool needs, and it is needed by
    exactly two commands. Importing it at module scope meant a missing openpyxl
    broke `brush audit` too -- a dependency for a feature you were not using.
    """
    try:
        from .batch.excel import read_jobs, run_job, write_template, write_workbook
    except ImportError as exc:
        raise UserError(
            "spreadsheet mode needs openpyxl, which is not installed",
            hint="pip install openpyxl     (or: pip install -e '.[sheets]')",
        ) from exc
    return read_jobs, run_job, write_template, write_workbook


def cmd_batch(a) -> int:
    """Audit every row of a spreadsheet and write the scored workbook back."""
    read_jobs, run_job, _, write_workbook = _load_sheets()
    from .batch.excel import MissingDependencyError, SheetFormatError
    require_file(a.sheet, "spreadsheet",
                 hint="run `brush template --out cases.xlsx` to create one")
    require_writable_dir(a.out_dir, "batch output directory")
    require_writable_dir(os.path.dirname(os.path.abspath(a.out)) or ".",
                         "folder for the results workbook")
    provider = _provider_or_error(a.provider, a.cassette, a.model)
    try:
        jobs, _ = read_jobs(a.sheet)
    except MissingDependencyError as exc:
        raise UserError(str(exc),
                        hint="pip install openpyxl     (or: pip install -e '.[sheets]')") from exc
    except SheetFormatError as exc:
        raise UserError(str(exc),
                        hint="run `brush template --out cases.xlsx` for a valid sheet") from exc
    if not jobs:
        print("no rows found in the sheet")
        return 1
    base = a.base_dir or os.path.dirname(os.path.abspath(a.sheet))

    print(f"\n  Brush — batch of {len(jobs)} case(s)  [provider: {provider.name}]\n")
    results = []
    for job in jobs:
        res = run_job(job, provider, base, a.out_dir, a.ledger, a.accept_drafted_spec)
        results.append(res)
        if res.ok:
            mark = {1.0: "conforms", 0.5: "partial ", 0.0: "fails   "}[res.conformance]
            print(f"  {res.case_id:<16} {mark}  {res.conformance:.1f}   {res.response}")
        else:
            print(f"  {res.case_id:<16} skipped         {res.error[:70]}")

    out = write_workbook(results, a.out, jobs, provider.name)
    ok = [r for r in results if r.ok]
    scored = [r for r in ok if r.conformance is not None]
    mean = sum(r.conformance for r in scored) / len(scored) if scored else 0.0
    print(f"\n  {len(ok)}/{len(results)} audited · mean conformance {mean:.2f}")
    print(f"  {sum(r.counts.get('blocker', 0) for r in ok)} blocker(s), "
          f"{sum(r.counts.get('major', 0) for r in ok)} major deviation(s)")
    print(f"\n  workbook    {out}\n")
    return 0


def cmd_template(a) -> int:
    _, _, write_template, _ = _load_sheets()
    from .batch.excel import MissingDependencyError
    try:
        path = write_template(a.out)
    except MissingDependencyError as exc:
        raise UserError(str(exc),
                        hint="pip install openpyxl     (or: pip install -e '.[sheets]')") from exc
    print(f"template written to {path}")
    print("  fill the yellow cells, then: brush batch --sheet "
          f"{os.path.basename(path)} --out results.xlsx")
    return 0


def cmd_doctor(a) -> int:
    """
    Self-check the installation.

    Every failure line names the exact command that fixes it, because the person
    reading this output is already stuck and does not want a diagnosis, they want
    the next thing to type.
    """
    import platform

    rows: list[tuple[str, bool, str, str]] = []

    def check(name: str, ok: bool, detail: str = "", fix: str = "") -> None:
        rows.append((name, ok, detail, fix))

    # --- interpreter -----------------------------------------------------
    v = sys.version_info
    check("Python 3.10 or newer", v >= (3, 10),
          f"found {v.major}.{v.minor}.{v.micro} on {platform.system()}",
          "install Python 3.10+ from python.org, then recreate the venv")

    # --- the package itself ----------------------------------------------
    try:
        import brush as _b
        where = os.path.dirname(os.path.abspath(_b.__file__))
        check("brush package importable", True, where)
    except ImportError as exc:
        check("brush package importable", False, str(exc),
              ("run from the repo root with: python run.py doctor" if os.name == "nt"
               else "run from the repo root with: python3 run.py doctor"))
        where = ""

    # --- knowledge pack ---------------------------------------------------
    try:
        from .knowledge import retrieve as K
        pack = K.pack()
        n = (len(pack["laws"]), len(pack["heuristics"]),
             len(pack["wcag"]), len(pack["clauses"]))
        ok = n[0] >= 30 and n[1] >= 10 and n[3] >= 20
        check("knowledge pack loads", ok,
              f"{n[0]} laws, {n[1]} heuristics, {n[2]} WCAG criteria, {n[3]} clauses",
              "reinstall: pip install -e .   (the JSON ships as package data)")
    except Exception as exc:
        check("knowledge pack loads", False, str(exc)[:80],
              "reinstall: pip install -e .")

    # --- deterministic core ------------------------------------------------
    try:
        from .analyze.color import contrast_ratio, parse_color
        r = contrast_ratio(parse_color("#767676"), parse_color("#ffffff"))
        ok = abs(r - 4.54) < 0.02
        check("colour engine correct", ok, f"#767676 on white = {r:.2f}:1 (expected 4.54)",
              "this is a bug — please report it")
    except Exception as exc:
        check("colour engine correct", False, str(exc)[:80], "reinstall the package")

    # --- sample data -------------------------------------------------------
    root = _repo_root()
    samples = {
        "design spec": os.path.join(root, "eval", "cases", "design.spec.json"),
        "sample HTML": os.path.join(root, "eval", "cases", "checkout.html"),
        "sample CSS": os.path.join(root, "eval", "cases", "checkout.css"),
    }
    missing = [k for k, v in samples.items() if not os.path.exists(v)]
    check("sample files present", not missing,
          root if not missing else f"missing: {', '.join(missing)}",
          "run doctor from the repository root, not from an installed copy")

    # --- end-to-end self test ---------------------------------------------
    if not missing:
        try:
            from .agents.orchestrator import run_audit
            from .agents.provider import build_provider
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                rep = run_audit(samples["design spec"], samples["sample HTML"],
                                [samples["sample CSS"]], build_provider("offline"),
                                out_dir=tmp, ignore_annotations=True, run_id="doctor")
            ok = len(rep.findings) == 0 and rep.stats["measurements"] > 200
            check("end-to-end audit runs", ok,
                  f"{rep.stats['measurements']} measurements, "
                  f"{len(rep.findings)} findings on the conforming file (expected 0)",
                  "this is a bug — re-run with BRUSH_DEBUG=1 and report the traceback")
        except Exception as exc:
            check("end-to-end audit runs", False, f"{type(exc).__name__}: {exc}"[:90],
                  "re-run with BRUSH_DEBUG=1 for the traceback")

    # --- optional extras ---------------------------------------------------
    try:
        import openpyxl
        check("spreadsheet mode (optional)", True, f"openpyxl {openpyxl.__version__}")
    except ImportError:
        check("spreadsheet mode (optional)", False, "openpyxl not installed",
              "pip install openpyxl     — only needed for `brush batch`")

    try:
        import anthropic
        check("live model mode (optional)", True,
              f"anthropic SDK {getattr(anthropic, '__version__', 'installed')}")
    except ImportError:
        check("live model mode (optional)", False, "anthropic SDK not installed",
              "pip install anthropic    — only needed for --provider anthropic")

    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    check("ANTHROPIC_API_KEY (optional)", has_key,
          "set" if has_key else "not set — the offline provider needs no key",
          ("$env:ANTHROPIC_API_KEY=\"sk-ant-...\"" if os.name == "nt"
           else "export ANTHROPIC_API_KEY=sk-ant-...")
          + "   — only for live runs")

    # --- report ------------------------------------------------------------
    required = rows[:6]
    optional = rows[6:]
    print("\n  Brush — installation check\n")
    width = max(len(r[0]) for r in rows) + 2
    for name, ok, detail, _ in required:
        _print_row("ok  " if ok else "FAIL", name, detail, width)
    print()
    for name, ok, detail, _ in optional:
        _print_row("ok  " if ok else "--  ", name, detail, width)

    failures = [r for r in required if not r[1]]
    if failures:
        print("\n  Fix these first:\n")
        for name, _, _, fix in failures:
            _print_fix(name, fix)
        return 1

    skipped = [r for r in optional if not r[1]]
    if skipped:
        print("\n  Optional features not available (everything else works):\n")
        for name, _, _, fix in skipped:
            _print_fix(name, fix)
    else:
        print()
    print("  Ready. Try:\n")
    for i, line in enumerate(_example_command()):
        print(f"    {line}" if i == 0 else f"        {line}")
    print()
    return 0


def _launcher() -> str:
    """
    How this person actually invoked us.

    Suggesting `brush …` to someone running `python run.py …` sends them to a
    command that does not exist yet, which is a rough thing to hit immediately
    after a screen of green ticks.
    """
    argv0 = os.path.basename(sys.argv[0] or "")
    if argv0.startswith("brush"):
        return "brush"
    exe = "python" if os.name == "nt" else "python3"
    if argv0 == "run.py":
        return f"{exe} run.py"
    return f"{exe} -m brush.cli"


def _example_command() -> list[str]:
    """
    A copy-pasteable command, split across lines only when it will not fit.

    A line longer than the window gets wrapped by the terminal, and a wrapped
    line loses the space it broke on when it is copied back out -- which is how
    `--design ... --html ...` reaches the clipboard as `--design ...--html`.
    So: one line when it fits, otherwise one flag per line, joined by whichever
    continuation character this shell understands.
    """
    parts = [
        f"{_launcher()} audit",
        "--design eval/cases/design.spec.json",
        "--html   eval/cases/checkout.html",
        "--css    eval/cases/generated/case_01.css",
    ]
    single = " ".join(parts)
    if 4 + len(single) <= _term_width():
        return [single]
    cont = _continuation()
    return [part + (f" {cont}" if part is not parts[-1] else "")
            for part in parts]


def _continuation() -> str:
    """The character that carries a command onto the next line, per shell."""
    if os.name != "nt":
        return "\\"
    # PowerShell always exports PSModulePath; cmd.exe on its own does not.
    return "`" if os.environ.get("PSModulePath") else "^"


def _term_width() -> int:
    """
    Usable columns -- one short of the real width.

    Writing into the very last column wraps on a Windows console, so that column
    is left empty on purpose.
    """
    import shutil
    return max(48, shutil.get_terminal_size(fallback=(80, 24)).columns - 1)


def _print_row(mark: str, name: str, detail: str, width: int) -> None:
    """One doctor line, folded by us rather than wrapped by the terminal."""
    import textwrap
    cols = _term_width()
    line = f"  {mark}  {name:<{width}} {detail}"
    if len(line) <= cols:
        print(line)
        return
    print(f"  {mark}  {name}")
    for chunk in textwrap.wrap(detail, max(24, cols - 10)) or [""]:
        print(f"          {chunk}")


def _print_fix(name: str, fix: str) -> None:
    """A remedy, indented under the check it belongs to."""
    import textwrap
    cols = _term_width()
    print(f"    {name}")
    for i, chunk in enumerate(textwrap.wrap(fix, max(24, cols - 8)) or [""]):
        print(f"      {'\u2192 ' if i == 0 else '  '}{chunk}")
    print()


def _repo_root() -> str:
    """The repository root when running from a checkout; cwd otherwise."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.dirname(os.path.dirname(here))
    if os.path.isdir(os.path.join(candidate, "eval", "cases")):
        return candidate
    return os.getcwd()


def cmd_version(a) -> int:
    import platform
    try:
        from importlib.metadata import version
        v = version("brush")
    except Exception:
        v = "1.0.0 (not installed as a package)"
    print(f"brush {v}")
    print(f"python {platform.python_version()} on {platform.system()} "
          f"{platform.machine()}")
    return 0


def cmd_approve(a) -> int:
    ledger = Ledger(a.ledger)
    ap = ledger.approve(a.node, a.prop, a.value, a.reason, a.by,
                        tolerance=a.tolerance, expires_after_days=a.expires)
    ledger.save(a.ledger)
    print(f"recorded {ap.approval_id}: {a.node} `{a.prop}` = {a.value}")
    print(f"  approved by {a.by}: {a.reason}")
    print(f"  suppressed while the measured value stays within ±{a.tolerance}; "
          f"expires in {a.expires} days")
    return 0


def cmd_ledger(a) -> int:
    ledger = Ledger(a.ledger)
    if not ledger.approvals:
        print("no approved deviations recorded")
        return 0
    for ap in ledger.approvals:
        flag = " (expired)" if ap.expired() else ""
        print(f"{ap.approval_id}{flag}  {ap.node_key} `{ap.prop}` = {ap.approved_code_value}")
        print(f"    {ap.approved_by}: {ap.reason}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="brush",
        description="Audit a frontend implementation against its design specification.")
    sub = p.add_subparsers(dest="cmd", required=True)

    au = sub.add_parser("audit", help="run a conformance audit")
    au.add_argument("--design", required=True, help="design.spec.json")
    au.add_argument("--html", required=True)
    au.add_argument("--css", nargs="+", required=True)
    au.add_argument("--out", default="out")
    au.add_argument("--provider", default="offline", choices=["anthropic", "replay", "offline"])
    au.add_argument("--model", default="claude-sonnet-4-6")
    au.add_argument("--cassette", default=None)
    au.add_argument("--ledger", default=None)
    au.add_argument("--run-id", default=None)
    au.add_argument("--use-annotations", action="store_true",
                    help="trust data-ds-component instead of making the mapper earn it")
    au.set_defaults(func=cmd_audit)

    ba = sub.add_parser("batch", help="audit every row of a spreadsheet")
    ba.add_argument("--sheet", required=True, help="input .xlsx")
    ba.add_argument("--out", default="results.xlsx")
    ba.add_argument("--out-dir", default="out/batch")
    ba.add_argument("--base-dir", default=None,
                    help="root for relative paths (default: the sheet's folder)")
    ba.add_argument("--provider", default="offline",
                    choices=["anthropic", "replay", "offline"])
    ba.add_argument("--model", default="claude-sonnet-4-6")
    ba.add_argument("--cassette", default=None)
    ba.add_argument("--ledger", default=None)
    ba.add_argument("--accept-drafted-spec", action="store_true",
                    help="audit against a spec drafted from a mockup that no human "
                         "has confirmed; every finding is marked provisional")
    ba.set_defaults(func=cmd_batch)

    tp = sub.add_parser("template", help="write a starting workbook to fill in")
    tp.add_argument("--out", default="cases.xlsx")
    tp.set_defaults(func=cmd_template)

    dc = sub.add_parser("doctor", help="check the installation and say what to fix")
    dc.set_defaults(func=cmd_doctor)

    vs = sub.add_parser("version", help="print versions")
    vs.set_defaults(func=cmd_version)

    ap = sub.add_parser("approve", help="record an intentional deviation")
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--node", required=True, help="e.g. 'Button/Ghost@default'")
    ap.add_argument("--prop", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--by", required=True)
    ap.add_argument("--tolerance", type=float, default=0.5)
    ap.add_argument("--expires", type=int, default=180)
    ap.set_defaults(func=cmd_approve)

    lg = sub.add_parser("ledger", help="list approved deviations")
    lg.add_argument("--ledger", required=True)
    lg.set_defaults(func=cmd_ledger)

    a = p.parse_args(argv)
    try:
        return a.func(a)
    except UserError as exc:
        print(f"\n  {exc}", file=sys.stderr)
        if exc.hint:
            print(f"  → {exc.hint}", file=sys.stderr)
        print(file=sys.stderr)
        return 2
    except PermissionError as exc:
        print(f"\n  permission denied: {exc.filename or exc}", file=sys.stderr)
        print("  → choose a writable location, e.g. --out ~/brush-out\n", file=sys.stderr)
        return 2
    except IsADirectoryError as exc:
        print(f"\n  that path is a directory: {exc.filename or exc}", file=sys.stderr)
        print("  → pass a file, not a folder\n", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"\n  file not found: {exc.filename or exc}", file=sys.stderr)
        print("  → check the path, or run `brush doctor` to verify the install\n",
              file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n  cancelled\n", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\n  unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("  → run `brush doctor` to check the install. If that passes, this is a "
              "bug —\n    re-run with BRUSH_DEBUG=1 for the full traceback.\n",
              file=sys.stderr)
        if os.environ.get("BRUSH_DEBUG"):
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
