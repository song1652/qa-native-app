#!/usr/bin/env python3
"""테스트용 가짜 claude CLI. 실제 CLI처럼 stdin 프롬프트를 받고 --output-format json 결과를 낸다.

FAKE_CLAUDE_MODE: ok(기본) · bad(구조 오류 1 + 모호 표현 1) · error(종료 코드 1) · slow(10초 대기) · empty(0건)
FAKE_CLAUDE_ARGS: 받은 인자를 이 경로에 JSON으로 적는다 (보안 옵션 확인용)
"""
import json
import os
import re
import sys
import time

args = sys.argv[1:]
if os.environ.get("FAKE_CLAUDE_ARGS"):
    with open(os.environ["FAKE_CLAUDE_ARGS"], "w", encoding="utf-8") as fh:
        json.dump({"args": args, "cwd": os.getcwd()}, fh, ensure_ascii=False)
prompt = sys.stdin.read()
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
if mode == "error":
    print("boom", file=sys.stderr)
    sys.exit(1)
if mode == "slow":
    time.sleep(10)
refs = re.findall(r"^- (\S+#§\d+)", prompt, re.M)
blocks = dict(re.findall(r'<source ref="([^"]+)"[^>]*>\n(.*?)\n</source>', prompt, re.S))
cases = []
if mode != "empty":
    for ref in refs[:2]:
        first = next((line for line in blocks.get(ref, "").splitlines() if line.strip()), "")
        cases.append({"feature": f"{first[:10]} 확인", "precondition": "", "steps": ["1. 앱 실행", "혜택 탭 선택"],
                      "expected": "안내 팝업이 노출된다.", "bullets": ["내일부터 참여할 수 있어요"],
                      "priority": "P1", "auto": "Y-app", "source_ref": ref, "source_quote": first})
if mode == "bad":
    cases.append({"feature": "출처 없음", "steps": ["a"], "expected": "b", "priority": "P1",
                  "source_ref": "file:nope#§9", "source_quote": ""})
    cases.append({"feature": "모호", "steps": ["a"], "expected": "정상 동작한다.", "priority": "P2",
                  "source_ref": refs[0], "source_quote": "없는 문장"})
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.0123,
                  "result": json.dumps({"cases": cases}, ensure_ascii=False),
                  "structured_output": {"cases": cases}}, ensure_ascii=False))
