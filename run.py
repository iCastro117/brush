#!/usr/bin/env python3
"""
Zero-install entry point.

`pip install -e .` is the tidy way to run Brush, but it is also the step most
likely to fail on a locked-down machine: no venv module, an externally-managed
Python, a proxy in front of PyPI. None of that should stand between a reviewer
and the result, so this script puts `src/` on the path and hands straight over to
the CLI.

    python3 run.py doctor
    python3 run.py audit --design eval/cases/design.spec.json \
        --html eval/cases/checkout.html --css eval/cases/generated/case_01.css

The audit engine has no third-party dependencies, so this works on a bare Python
3.10+ with nothing installed at all.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

if sys.version_info < (3, 10):
    sys.exit(
        f"Brush needs Python 3.10 or newer; this is {sys.version_info.major}."
        f"{sys.version_info.minor}.\n"
        "Try `python3.11 run.py ...` or `python3.12 run.py ...` if one is installed."
    )

from brush.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
