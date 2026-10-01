from __future__ import annotations

import json
from pathlib import Path

import pytest

import _tc_credentials as creds

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_credentials_are_saved_masked_and_env_wins(fake_web, monkeypatch):
    status = creds.save("confluence", {"base_url": "https://yafit.atlassian.net/", "email": "qa.lead@yafit.com",
                                       "token": "secret-token"})
    assert status["confluence"] == {"configured": True, "base_url": "https://yafit.atlassian.net",
                                    "email_masked": "qa****@yafit.com", "deployment": "cloud"}
    assert "secret-token" not in json.dumps(creds.status())
    creds.save("confluence", {"email": "qa.lead@yafit.com", "token": ""})       # 빈 토큰 = 기존 유지
    assert creds.confluence()["token"] == "secret-token"
    assert creds.confluence_headers(creds.confluence())["Authorization"].startswith("Basic ")
    creds.save("confluence", {"base_url": "https://wiki.corp.example", "deployment": "dc"})
    assert creds.confluence_headers(creds.confluence())["Authorization"] == "Bearer secret-token"
    monkeypatch.setenv("CONFLUENCE_TOKEN", "from-env")
    assert creds.confluence()["token"] == "from-env"
    with pytest.raises(Exception):
        creds.save("confluence", {"base_url": "ftp://x"})
    assert creds.status()["figma"] == {"configured": False}


def test_credential_files_are_gitignored():
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "config/confluence_config.json" in ignored and "config/figma_config.json" in ignored
