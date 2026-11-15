PYTHON ?= .venv/bin/python

.PHONY: test test-coverage lint format-check typecheck check

test:
	$(PYTHON) -m pytest

test-coverage:
	$(PYTHON) -m pytest --cov --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check .

format-check:
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy

check: lint format-check typecheck
