"""
Every way a person can hold this wrong.

These are regression tests for real failures found by feeding the CLI the
mistakes people actually make: a folder where a file was expected, a Makefile
where JSON was expected, an empty page, a spreadsheet with the wrong headers,
a rating typed as a word. Each one used to produce a Python traceback or --
worse -- a clean exit code on a run that audited nothing.

The rule they enforce: a problem the person can fix exits 2 with a sentence and
a suggested command. Only a genuine bug exits 1.
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from brush.cli import main  # noqa: E402

DESIGN = os.path.join(ROOT, "eval", "cases", "design.spec.json")
HTML = os.path.join(ROOT, "eval", "cases", "checkout.html")
CSS = os.path.join(ROOT, "eval", "cases", "checkout.css")
MAKEFILE = os.path.join(ROOT, "Makefile")
CASES_DIR = os.path.join(ROOT, "eval", "cases")
OUT = os.path.join(tempfile.gettempdir(), "brush-clitest")


def _run(argv: list[str]) -> tuple[int, str]:
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exc:      # argparse
            code = int(exc.code or 0)
    return code, out.getvalue() + err.getvalue()


def _audit(*extra: str) -> tuple[int, str]:
    return _run(["audit", "--design", DESIGN, "--html", HTML, "--css", CSS,
                 "--out", OUT, *extra])


def test_missing_file_is_a_user_error():
    code, text = _run(["audit", "--design", "nope.json", "--html", HTML,
                       "--css", CSS, "--out", OUT])
    assert code == 2, f"expected exit 2, got {code}"
    assert "not found" in text.lower()
    assert "Traceback" not in text
    print("  ok  missing file exits 2 with a sentence, not a traceback")


def test_typo_suggests_the_real_filename():
    code, text = _run(["audit", "--design", DESIGN + "x", "--html", HTML,
                       "--css", CSS, "--out", OUT])
    assert code == 2
    assert "did you mean" in text.lower(), text
    print("  ok  a mistyped path suggests the nearest real file")


def test_directory_where_a_file_belongs():
    code, text = _run(["audit", "--design", DESIGN, "--html", HTML,
                       "--css", CASES_DIR, "--out", OUT])
    assert code == 2
    assert "directory" in text.lower(), text
    print("  ok  a folder passed as --css is named as a folder")


def test_malformed_json_names_its_line():
    code, text = _run(["audit", "--design", MAKEFILE, "--html", HTML,
                       "--css", CSS, "--out", OUT])
    assert code == 2
    assert "not valid json" in text.lower() and "line" in text.lower(), text
    print("  ok  malformed JSON reports the line and the check command")


def test_corrupt_ledger_is_reported():
    code, text = _audit("--ledger", MAKEFILE)
    assert code == 2
    assert "ledger" in text.lower() and "json" in text.lower(), text
    print("  ok  an unreadable ledger is reported, not crashed on")


def test_replay_without_cassette():
    code, text = _audit("--provider", "replay")
    assert code == 2
    assert "cassette" in text.lower(), text
    print("  ok  replay without a cassette explains how to record one")


def test_unwritable_output_directory():
    """A path that cannot be a directory on any platform: a child of a real file.

    (This used to point at /proc, which does not exist on Windows -- the check
    then passed for the wrong reason, or failed outright.)
    """
    with tempfile.NamedTemporaryFile(suffix=".not-a-dir", delete=False) as fh:
        blocker = fh.name
    try:
        code, text = _audit("--out", os.path.join(blocker, "out"))
        assert code == 2, f"expected exit 2, got {code}"
        assert "output directory" in text.lower(), text
        assert "Traceback" not in text
    finally:
        os.unlink(blocker)
    print("  ok  an unwritable --out is caught before any work is done")


def test_auditing_nothing_is_never_success():
    """The worst of the bunch: an empty page used to exit 0 having audited zero
    components, which reads as a clean bill of health."""
    code, text = _run(["audit", "--design", DESIGN, "--html", os.devnull,
                       "--css", CSS, "--out", OUT])
    assert code != 0, "auditing nothing must not report success"
    assert "no components" in text.lower(), text
    print("  ok  a page with no matching components fails loudly")


def test_expected_column_accepts_words_and_rejects_nonsense():
    from brush.batch.excel import agreement_points, parse_expected

    assert parse_expected(1)[0] == 1.0
    assert parse_expected("0.5")[0] == 0.5
    assert parse_expected("parcial")[0] == 0.5
    assert parse_expected("sí")[0] == 1.0
    assert parse_expected("FAIL")[0] == 0.0
    value, note = parse_expected("muy bien")
    assert value is None and "not understood" in note
    value, note = parse_expected(0.7)
    assert value is None and "0, 0.5 or 1" in note
    assert agreement_points(0.5, "parcial") == 1.0
    assert agreement_points(1.0, "muy bien") is None
    print("  ok  EXPECTED accepts words, refuses nonsense, never reaches a formula")


def test_sheet_with_unrecognised_headers():
    from brush.batch.excel import SheetFormatError, read_jobs
    import tempfile

    try:
        from openpyxl import Workbook
    except ImportError:
        print("  --  sheet header test skipped (openpyxl not installed)")
        return

    wb = Workbook()
    wb.active.append(["foo", "bar"])
    wb.active.append([1, 2])
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as fh:
        path = fh.name
    wb.save(path)
    try:
        read_jobs(path)
        raise AssertionError("expected SheetFormatError")
    except SheetFormatError as exc:
        assert "header row" in str(exc)
    finally:
        os.unlink(path)
    print("  ok  an unrecognised header row is explained, not crashed on")


def test_scoring_logic_imports_without_openpyxl():
    """
    The scoring rules are arithmetic and must not need a spreadsheet library.

    Found the hard way: this suite crashed outright on a machine without
    openpyxl, because `brush.batch.excel` imported it at module scope. A test
    of pure arithmetic taking down the whole run over an optional dependency is
    the kind of failure that makes someone give up on the install.
    """
    import builtins
    import importlib

    real = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.split(".")[0] == "openpyxl":
            raise ImportError("No module named 'openpyxl'")
        return real(name, *args, **kwargs)

    for mod in [m for m in list(sys.modules) if m.startswith(("openpyxl", "brush.batch"))]:
        del sys.modules[mod]
    builtins.__import__ = blocked
    try:
        excel = importlib.import_module("brush.batch.excel")
        assert excel.parse_expected("parcial")[0] == 0.5
        assert excel.conformance_score({"blocker": 1}) == 0.0
        assert excel.agreement_points(0.5, 1) == 0.5
    finally:
        builtins.__import__ = real
        for mod in [m for m in list(sys.modules) if m.startswith("brush.batch")]:
            del sys.modules[mod]
    print("  ok  scoring logic imports and works with openpyxl absent")


def test_missing_openpyxl_is_a_clean_message():
    """Reaching spreadsheet mode without the dependency must name the install."""
    import builtins

    real = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.split(".")[0] == "openpyxl":
            raise ImportError("No module named 'openpyxl'")
        return real(name, *args, **kwargs)

    for mod in [m for m in list(sys.modules) if m.startswith(("openpyxl", "brush.batch"))]:
        del sys.modules[mod]
    builtins.__import__ = blocked
    try:
        code, text = _run(["batch", "--sheet", os.path.join(ROOT, "eval", "cases",
                                                            "brush_cases.xlsx"),
                           "--out", os.path.join(OUT, "x.xlsx")])
    finally:
        builtins.__import__ = real
        for mod in [m for m in list(sys.modules) if m.startswith("brush.batch")]:
            del sys.modules[mod]
    assert code == 2, f"expected exit 2, got {code}"
    assert "openpyxl" in text and "pip install" in text, text
    assert "Traceback" not in text
    print("  ok  missing openpyxl exits 2 naming the install command")


LABEL = "CLI error cases"

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    fails = skips = 0
    names = sorted(n for n in dict(globals()) if n.startswith("test_"))
    for name in names:
        try:
            globals()[name]()
        except AssertionError as exc:
            fails += 1
            print(f"  FAIL  {name}: {exc}")
        except ImportError as exc:
            # An optional dependency is missing. That is a skip, not a failure --
            # and it must never take the rest of the suite down with it.
            skips += 1
            print(f"  --    {name} skipped ({exc})")
        except Exception as exc:  # noqa: BLE001 - a crash is a failure, not a stop
            fails += 1
            print(f"  FAIL  {name}: unexpected {type(exc).__name__}: {exc}")
    note = f", {skips} skipped" if skips else ""
    print(f"\n{'FAILED' if fails else 'PASSED'} — {len(names) - skips} of "
          f"{len(names)} {LABEL}, {fails} failure(s){note}")
    sys.exit(1 if fails else 0)
