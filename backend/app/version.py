"""Arbiter product version: the single source of truth.

Keep in sync with the repository-root VERSION file and frontend/package.json;
``make check`` (tests/test_repo_consistency.py) fails if they drift. Module- and
schema-level versions elsewhere (e.g. BENCHMARK_VERSION, operations_intelligence
VERSION) version their own data formats and are intentionally independent.
"""

__version__ = "0.38.0"
