# Arbiter developer commands. Run `make check` before every commit.
PY ?= python3

.PHONY: install lint format test gates build check run

install:
	$(PY) -m pip install -r backend/requirements-dev.txt
	cd frontend && npm ci

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff format .

test:
	$(PY) -m pytest

build:
	cd frontend && npm run build

gates: build
	PYTHON=$(PY) scripts/run_gates.sh

check: lint test gates

run: build
	./start.sh
