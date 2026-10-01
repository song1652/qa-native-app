"""Confluence·Figma 자격증명 (PRD §7, 로드맵 C2). jira_reporter.py와 같은 방식.

- 파일: config/confluence_config.json, config/figma_config.json (gitignore 대상)
- 환경변수가 있으면 파일보다 우선: CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_TOKEN, FIGMA_TOKEN
- 화면·API에는 토큰을 절대 돌려주지 않는다 (status()는 마스킹 값만).
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import _paths
from _tc_library import LibraryError


def _file(kind: str) -> Path:
    return _paths.PROJECT_ROOT / "config" / f"{kind}_config.json"


def _read(kind: str) -> dict:
    path = _file(kind)
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def confluence() -> dict:
    data = _read("confluence")
    base = (os.environ.get("CONFLUENCE_BASE_URL") or data.get("base_url") or "").rstrip("/")
    return {
        "base_url": base,
        "email": os.environ.get("CONFLUENCE_EMAIL") or data.get("email", ""),
        "token": os.environ.get("CONFLUENCE_TOKEN") or data.get("token", ""),
        # cloud: email + API 토큰 Basic, dc: 개인 액세스 토큰 Bearer
        "deployment": data.get("deployment")
        or ("cloud" if (urlparse(base).hostname or "").endswith(".atlassian.net") else "dc"),
        "allow_private": bool(data.get("allow_private", False)),
    }


def figma() -> dict:
    return {"token": os.environ.get("FIGMA_TOKEN") or _read("figma").get("token", "")}


def confluence_headers(cfg: dict) -> dict[str, str]:
    if not (cfg["base_url"] and cfg["token"]):
        raise LibraryError("Confluence 연결이 설정되지 않았습니다", "CREDENTIALS_MISSING", 409)
    if cfg["deployment"] == "cloud":
        raw = f"{cfg['email']}:{cfg['token']}".encode("utf-8")
        return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii"), "Accept": "application/json"}
    return {"Authorization": f"Bearer {cfg['token']}", "Accept": "application/json"}


def figma_headers() -> dict[str, str]:
    token = figma()["token"]
    if not token:
        raise LibraryError("Figma 연결이 설정되지 않았습니다", "CREDENTIALS_MISSING", 409)
    return {"X-Figma-Token": token}


def _mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:2]}****@{domain}" if domain else ""


def status() -> dict:
    c, f = confluence(), figma()
    return {
        "confluence": {"configured": bool(c["base_url"] and c["token"]), "base_url": c["base_url"],
                       "email_masked": _mask_email(c["email"]), "deployment": c["deployment"]},
        "figma": {"configured": bool(f["token"])},
    }


def save(kind: str, fields: dict) -> dict:
    """PUT /api/tc-library/credentials/{kind}. 빈 토큰은 기존 값을 유지한다(다시 보여 주지 않으므로)."""
    if kind not in ("confluence", "figma"):
        raise LibraryError("알 수 없는 연결입니다", "INVALID_CREDENTIAL_KIND", 404)
    current = _read(kind)
    if kind == "confluence":
        base = str(fields.get("base_url", current.get("base_url", ""))).strip().rstrip("/")
        parsed = urlparse(base)
        if base and (parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.path not in ("", "/wiki")):
            raise LibraryError("base URL은 https://회사.atlassian.net 또는 https://confluence.회사.com 형식이어야 합니다", "INVALID_BASE_URL")
        current.update({"base_url": base, "email": str(fields.get("email", current.get("email", ""))).strip()})
        if fields.get("deployment") in ("cloud", "dc"):
            current["deployment"] = fields["deployment"]
        if "allow_private" in fields:
            current["allow_private"] = bool(fields["allow_private"])
    if str(fields.get("token", "")).strip():
        current["token"] = str(fields["token"]).strip()
    path = _file(kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return status()
