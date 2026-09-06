"""최종 Appium 테스트 실패를 Jira Bug로 보고한다.

설정은 이 프로젝트의 config/jira_config.json만 사용한다.
토큰은 JIRA_TOKEN 환경변수로만 주입하며, 설정이 없으면 조용히 건너뛴다.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "jira_config.json"
STATE_FILE = ROOT / "state" / "pipeline.json"
TESTCASES_DIR = ROOT / "testcases"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[jira] 설정 읽기 실패 — 건너뜀: {exc}")
        return {}


def _adf_text(text: str) -> dict:
    return {"type": "text", "text": text}


def _paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [_adf_text(text)]}


def _heading(text: str) -> dict:
    return {"type": "heading", "attrs": {"level": 2},
            "content": [_adf_text(text)]}


def _bullet(items: list[str]) -> dict:
    return {"type": "bulletList", "content": [
        {"type": "listItem", "content": [_paragraph(item)]}
        for item in items
    ]}


def _relative_path(value: str) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / "reports" / path
    return path if path.exists() else None


def _tc_path(file_path: str) -> Path | None:
    match = re.search(r"tests/generated/[^/]+/([^/]+)/tc_(\d+)_", file_path)
    if not match:
        return None
    group, number = match.groups()
    candidates = sorted((TESTCASES_DIR / group).glob(f"tc_{number}_*.md"))
    return candidates[0] if candidates else None


def _tc_title(file_path: str) -> str:
    path = _tc_path(file_path)
    if not path:
        return Path(file_path).stem
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else path.stem


class JiraClient:
    def __init__(self, config: dict):
        token = os.environ.get(config.get("token_env", "JIRA_TOKEN"), "")
        if not token:
            raise ValueError("JIRA_TOKEN이 설정되지 않았습니다")
        email = config.get("email", "")
        if not email or "your-email" in email:
            raise ValueError("Jira email 설정이 필요합니다")
        encoded = base64.b64encode(f"{email}:{token}".encode()).decode()
        self.base = config["base_url"].rstrip("/") + "/rest/api/3"
        self.headers = {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def request(self, method: str, path: str, body=None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base + path, data=data, headers=self.headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise RuntimeError(f"Jira API {exc.code}: {detail}") from exc

    def attach(self, issue_key: str, path: Path) -> None:
        if not path.exists():
            return
        boundary = "----QANativeJiraUpload"
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        headers = dict(self.headers)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        headers["X-Atlassian-Token"] = "no-check"
        request = urllib.request.Request(
            f"{self.base}/issue/{issue_key}/attachments",
            data=body, headers=headers, method="POST",
        )
        with urllib.request.urlopen(request, timeout=30):
            pass


def _failure_description(failure: dict, platform: str, video: str) -> dict:
    file_path = failure.get("file", "")
    test_name = failure.get("test", "unknown")
    error = failure.get("error", "알 수 없는 오류")
    screenshot = _relative_path(failure.get("screenshot", ""))
    attachments = [str(p) for p in (screenshot, _relative_path(video)) if p]
    return {"type": "doc", "version": 1, "content": [
        _heading("기본 정보"),
        _bullet([
            f"플랫폼: {platform}",
            f"테스트: {test_name}",
            f"TC: {_tc_title(file_path)}",
            f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]),
        _heading("실패 내용"),
        {"type": "codeBlock", "attrs": {"language": "text"},
         "content": [_adf_text(error[:3000])]},
        _heading("첨부 파일"),
        _bullet(attachments or ["스크린샷/영상 없음"]),
    ]}


def create_issue(client: JiraClient, config: dict, failure: dict,
                 platform: str, video: str) -> str:
    file_path = failure.get("file", "")
    test_name = failure.get("test", "unknown")
    body = {"fields": {
        "project": {"key": config["project_key"]},
        "issuetype": {"id": config["issue_type_id"]},
        "summary": f"[QA 실패][{platform}] {_tc_title(file_path)}",
        "description": _failure_description(failure, platform, video),
    }}
    if config.get("version"):
        body["fields"]["versions"] = [{"name": config["version"]}]
    if config.get("epic_key"):
        body["fields"]["parent"] = {"key": config["epic_key"]}
    try:
        result = client.request("POST", "/issue", body)
    except RuntimeError as exc:
        if "parent" not in str(exc).lower():
            raise
        body["fields"].pop("parent", None)
        result = client.request("POST", "/issue", body)
    issue_key = result.get("key", "")
    if not issue_key:
        raise RuntimeError(f"Jira issue key가 응답되지 않았습니다: {result}")
    if config.get("auto_attach", True):
        for value in (failure.get("screenshot", ""), video):
            path = _relative_path(value)
            if path:
                client.attach(issue_key, path)
    return issue_key


def report_from_state(platform: str) -> list[str]:
    config = load_config()
    if not config.get("enabled", False):
        print("[jira] 비활성화 상태 — 건너뜀")
        return []
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("[jira] pipeline state 없음 — 건너뜀")
        return []
    failures = state.get("execute_results", {}).get("errors", [])
    if not failures:
        print("[jira] 최종 실패 항목 없음 — 건너뜀")
        return []
    try:
        client = JiraClient(config)
    except ValueError as exc:
        print(f"[jira] 설정 미완료 — 건너뜀: {exc}")
        return []
    video = state.get("last_fail_video", "")
    created = []
    for failure in failures:
        try:
            key = create_issue(client, config, failure, platform, video)
            created.append(key)
            print(f"[jira] 이슈 생성: {key}")
        except Exception as exc:
            print(f"[jira] 이슈 생성 실패 — 테스트 결과는 유지: {exc}")
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="최종 Appium 실패 Jira 보고")
    parser.add_argument("--platform", default="android", choices=["android", "ios"])
    args = parser.parse_args()
    report_from_state(args.platform)


if __name__ == "__main__":
    main()
