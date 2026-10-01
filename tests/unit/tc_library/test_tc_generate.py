from __future__ import annotations

import json
import threading
import time

import pytest

import _tc_generate as gen
import _tc_library as lib
import _tc_sources as src
from _tc_template import analyze_workbook
from _tc_xlsx_import import import_workbook
from tests.unit.tc_library.source_fixtures import PRD_MD

SUITE = "야핏무브"
TARGET = {"sheet": "혜택", "path": ["혜택 탭", "상단 배너"]}


@pytest.fixture
def seeded(library_dir, template_xlsx):
    profiles = analyze_workbook(template_xlsx)
    cases = import_workbook(template_xlsx, profiles, ["혜택", "홈"], {"혜택": "BEN", "홈": "HOME"})
    lib.save_template(SUITE, template_xlsx, profiles)
    lib.import_cases(SUITE, ["혜택", "홈"], cases, "tester")
    bundle = src.new_bundle()
    src.add_file(bundle, "prd.md", PRD_MD.encode())
    return bundle


def test_command_is_restricted_and_never_skips_permissions(fake_claude):
    cmd = gen.claude_command()
    for flag in ("--restricted", "--strict-mcp-config", "--no-session-persistence", "--json-schema"):
        assert flag in cmd
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert not any("dangerously" in part for part in cmd)


def test_app_target_platform_is_saved_in_job_prompt_and_draft(seeded, fake_claude):
    target = {**TARGET, "platforms": ["ios"]}
    job = gen.create_job(SUITE, bundle_id=seeded, target=target, profile="기본")
    assert job["target"]["platforms"] == ["ios"]
    gen.run_job(job["job_id"])
    cases = lib.filter_cases(lib.load_cases(SUITE), {"job": job["job_id"]})
    assert cases and all(c["platforms"] == ["ios"] for c in cases)
    from _tc_prompt import build_prompt
    prompt = build_prompt(chunk=[{"ref": "file:x", "title": "x", "section": "x", "text": "x"}],
                          target=target, profile={"name": "기본", "rules": [], "banned_phrases": [], "expected_endings": []}, examples=[])
    assert "iOS" in prompt and "And :" in prompt


def test_missing_claude_is_a_clear_error(library_dir, monkeypatch):
    monkeypatch.delenv("TCS_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(gen.shutil, "which", lambda _: None)
    with pytest.raises(gen.JobError) as exc:
        gen.claude_command()
    assert (exc.value.code, exc.value.status) == ("CLAUDE_NOT_FOUND", 503)


def test_job_adds_valid_drafts_in_target_branch(seeded, fake_claude):
    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본")
    final = gen.run_job(job["job_id"])

    assert final["status"] == "done" and final["kept"] == 2 and final["cost_usd"] == 0.0123
    drafts = lib.filter_cases(lib.load_cases(SUITE), {"job": job["job_id"]})
    assert [d["status"] for d in drafts] == ["draft", "draft"]
    first = drafts[0]
    assert first["path"] == ["혜택 탭", "상단 배너", ""]
    assert first["steps"] == ["앱 실행", "혜택 탭 선택"]                 # "1. " 번호 제거
    assert first["bullets"] == [{"text": "내일부터 참여할 수 있어요", "verified": False}]  # PRD 문구 = 추정
    assert first["source_refs"][0].startswith("file:") and first["draft_meta"]["quote_found"] is True
    order = [c["case_id"] for c in lib.load_cases(SUITE)]
    assert order.index(first["case_id"]) == order.index("BEN_0003") + 1  # 상단 배너 가지 끝
    args = json.loads(fake_claude.read_text())
    assert "tcs-job-" in args["cwd"] and "qa-native" not in args["cwd"]   # 저장소 밖에서 실행


def test_structural_errors_are_dropped_and_rule_errors_are_flagged(seeded, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "bad")
    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본")
    final = gen.run_job(job["job_id"])

    assert final["status"] == "done" and final["kept"] == 3 and final["invalid"] == 1
    assert gen.invalid_drafts(job["job_id"])[0]["errors"] == ["출처 'file:nope#§9'가 소스 목록에 없습니다"]
    vague = next(c for c in lib.filter_cases(lib.load_cases(SUITE), {"job": job["job_id"]})
                 if c["feature"] == "모호")
    assert vague["has_error"] and vague["draft_meta"]["quote_found"] is False


def test_claude_failure_marks_job_failed_with_log(seeded, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "error")
    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본")
    final = gen.run_job(job["job_id"])

    assert final["status"] == "failed" and "종료 코드 1" in final["reason"]
    assert "ERROR section 1: CLAUDE_ERROR" in gen.log_tail(job["job_id"])


def test_timeout_and_cancel(seeded, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "slow")
    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본")
    final = gen.run_job(job["job_id"], runner=lambda p, job_id: gen.run_claude(p, job_id=job_id, timeout=1))
    assert final["status"] == "failed" and "1초 안에" in final["reason"]

    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본")
    worker = threading.Thread(target=gen.run_job, args=(job["job_id"],))
    worker.start()
    time.sleep(1)
    with pytest.raises(gen.JobError) as exc:
        gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본")
    assert exc.value.code == "JOB_RUNNING"
    gen.cancel_job(job["job_id"])
    worker.join(15)
    assert gen.get_job(job["job_id"])["status"] == "cancelled"


def test_regenerate_rewrites_one_draft(seeded, fake_claude):
    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본")
    gen.run_job(job["job_id"])
    draft = lib.filter_cases(lib.load_cases(SUITE), {"job": job["job_id"]})[0]
    lib.patch_case(SUITE, draft["case_id"], draft["rev"], {"feature": "사람이 고친 이름"}, "tester")

    regen = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본", mode="regenerate",
                           case_id=draft["case_id"], note="조건별로 나눠 주세요")
    final = gen.run_job(regen["job_id"])
    case = lib.get_case(SUITE, draft["case_id"])
    assert final["kept"] == 1 and case["feature"] != "사람이 고친 이름"
    assert case["draft_meta"]["regenerated_note"] == "조건별로 나눠 주세요"
    with pytest.raises(gen.JobError):
        gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본", mode="regenerate", case_id="x")



def test_regenerate_still_works_after_source_removed_from_list(seeded, fake_claude):
    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본")
    gen.run_job(job["job_id"])
    draft = lib.filter_cases(lib.load_cases(SUITE), {"job": job["job_id"]})[0]
    src.remove_source(seeded, src.load_bundle(seeded)["sources"][0]["source_id"])

    regen = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본", mode="regenerate",
                           case_id=draft["case_id"], note="다시 써 주세요")
    final = gen.run_job(regen["job_id"])
    assert final["status"] == "done" and final["kept"] == 1

def test_retry_only_failed_sections(seeded, fake_claude):
    ref = src.load_bundle(seeded)["sources"][0]["ref"] + "#§3"
    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본", only_refs=[ref])
    final = gen.run_job(job["job_id"])
    drafts = lib.filter_cases(lib.load_cases(SUITE), {"job": job["job_id"]})
    assert final["sections"][0]["refs"] == [ref]
    assert {d["source_refs"][0] for d in drafts} == {ref}


def test_latest_new_job_is_saved_suite_context(seeded, fake_claude):
    assert gen.latest_job(SUITE) is None
    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile='기본')
    gen.run_job(job['job_id'])
    context = gen.latest_job(SUITE)
    assert context['job_id'] == job['job_id']
    assert context['bundle_id'] == seeded
    assert context['target'] == {'sheet': '혜택', 'path': ['혜택 탭', '상단 배너', '']}
    # 재생성은 원래 검토 묶음을 대체하지 않는다.
    case = lib.filter_cases(lib.load_cases(SUITE), {'job': job['job_id']})[0]
    again = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile='기본',
                           mode='regenerate', case_id=case['case_id'], note='원래 목적 유지')
    gen.run_job(again['job_id'])
    assert gen.latest_job(SUITE)['job_id'] == job['job_id']
    # 다른 스위트에는 이 소스 묶음을 노출하지 않는다.
    assert gen.latest_job('다른스위트') is None


def test_profile_style_examples_fill_prompt_and_drafts_get_style_warnings(seeded, fake_claude):
    from _tc_profiles import save_profile
    example = {"feature": "보물찾기 노출", "precondition": "- 첫 도전 상태", "steps": ["혜택 탭 선택"],
               "expected": "보물상자 바텀시트가 노출된다.", "bullets": [], "priority": "P1"}
    save_profile("문체", {"rules": ["Step은 명사형으로 끝낸다"], "banned_phrases": ["혜택 탭"],
                        "expected_endings": ["절대없는끝."], "style_examples": [example]})
    prompts = []
    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="문체")
    gen.run_job(job["job_id"], runner=lambda p, job_id: prompts.append(p) or gen.run_claude(p, job_id=job_id))

    assert '"feature": "보물찾기 노출"' in prompts[0]           # 같은 가지 예시가 모자라 기준 예시로 채움
    assert '"절대없는끝."' in prompts[0]                         # 끝맺음 규칙이 프롬프트에 들어감
    drafts = [lib.with_issues(d) for d in lib.filter_cases(lib.load_cases(SUITE), {"job": job["job_id"]})]
    assert drafts and all(d["draft_meta"]["profile"] == "문체" for d in drafts)
    codes = {i["code"] for d in drafts for i in d["issues"]}
    assert {"STYLE_ENDING", "STYLE_BANNED"} <= codes            # Step의 "혜택 탭 선택"이 금지 표현
    assert all(i["level"] == "warning" for d in drafts for i in d["issues"] if i["code"].startswith("STYLE_"))
