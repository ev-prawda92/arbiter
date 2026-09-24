"""Repository invariants a reviewer should be able to rely on."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _backend_version() -> str:
    text = (ROOT / "backend" / "app" / "version.py").read_text()
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def test_version_single_source():
    version = (ROOT / "VERSION").read_text().strip()
    package = json.loads((ROOT / "frontend" / "package.json").read_text())["version"]
    assert version == _backend_version() == package


def test_changelog_lists_current_release():
    major_minor = ".".join((ROOT / "VERSION").read_text().strip().split(".")[:2])
    assert f"v{major_minor}" in (ROOT / "CHANGELOG.md").read_text()


def test_no_hardcoded_product_version_in_api():
    main = (ROOT / "backend" / "app" / "main.py").read_text()
    assert '"0.27.0"' not in main


def test_runtime_policy_not_committed():
    ignore = (ROOT / ".gitignore").read_text()
    assert "backend/data/policy.json" in ignore


def _signer():
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from app.approval_control import ApprovalControlService

    return ApprovalControlService.__new__(ApprovalControlService)  # _sign needs no store


def test_production_signing_fails_closed(monkeypatch):
    import pytest

    monkeypatch.setenv("ARBITER_ENV", "production")
    monkeypatch.delenv("ARBITER_SETTLEMENT_SIGNING_SECRET", raising=False)
    with pytest.raises(ValueError, match="must be set in production"):
        _signer()._sign("abc")


def test_development_signing_is_never_production_eligible(monkeypatch):
    monkeypatch.setenv("ARBITER_ENV", "development")
    monkeypatch.delenv("ARBITER_SETTLEMENT_SIGNING_SECRET", raising=False)
    _sig, _key, mode, eligible = _signer()._sign("abc")
    assert mode == "local-development-hmac" and eligible is False


def test_production_signing_with_secret_is_eligible(monkeypatch):
    monkeypatch.setenv("ARBITER_ENV", "production")
    monkeypatch.setenv("ARBITER_SETTLEMENT_SIGNING_SECRET", "s3cret")
    sig, _key, mode, eligible = _signer()._sign("abc")
    assert sig.startswith("hmac-sha256:") and mode == "hmac-sha256" and eligible is True
