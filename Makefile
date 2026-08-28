.PHONY: help install demo clean-demo eval test cases approve-demo batch template all

PY ?= PYTHONPATH=src python3
DESIGN := eval/cases/design.spec.json
HTML   := eval/cases/checkout.html

help:
	@echo "  make install     install the package (editable)"
	@echo "  make cases       regenerate the seeded mutation set"
	@echo "  make demo        audit the hard case -> out/demo.report.html"
	@echo "  make clean-demo  audit the conforming file -> expect 0 findings"
	@echo "  make eval        full evaluation, baseline vs pipeline"
	@echo "  make test        27 tests: integrity, verifier, clean control, CLI errors"
	@echo "  make template    write a blank review workbook -> cases.xlsx"
	@echo "  make batch       score the 12-case workbook -> out/brush_results.xlsx"
	@echo "  make all         cases + test + eval + demo + batch"

install:
	$(PY) -m pip install -e .

cases:
	$(PY) eval/mutations.py --seed 20260828

demo:
	$(PY) -m brush.cli audit --design $(DESIGN) --html $(HTML) \
		--css eval/cases/generated/case_01.css --out out --run-id demo

clean-demo:
	$(PY) -m brush.cli audit --design $(DESIGN) --html $(HTML) \
		--css eval/cases/checkout.css --out out --run-id clean

approve-demo:
	$(PY) -m brush.cli approve --ledger out/ledger.json \
		--node "Button/Ghost@default" --prop min-height --value 28 \
		--reason "Compact toolbar variant, signed off 2026-08-20" --by "a.rivera"
	$(PY) -m brush.cli audit --design $(DESIGN) --html $(HTML) \
		--css eval/cases/generated/case_05.css --ledger out/ledger.json \
		--out out --run-id approved

template:
	$(PY) -m brush.cli template --out cases.xlsx

batch:
	$(PY) -m brush.cli batch --sheet eval/cases/brush_cases.xlsx \
		--base-dir . --out out/brush_results.xlsx

eval:
	$(PY) eval/run_eval.py

test:
	@$(PY) tests/test_integrity.py
	@$(PY) tests/test_verifier.py
	@$(PY) tests/test_clean_control.py
	@$(PY) tests/test_cli_errors.py
	@echo ""
	@echo "  ALL SUITES PASSED — 27 tests, 59 assertions, 4 files"
	@echo ""

all: cases test eval demo batch
