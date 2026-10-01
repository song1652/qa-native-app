# TC 스튜디오 앱 이식 — 실행 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (또는 subagent-driven-development) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**핵심 요구:** And와 iOS 결과를 비교할 수 있으면 된다(사용자 2026-10-01). 웹 TC 스튜디오와 같은 기능 범위를 넘는 것은 만들지 않는다.

**Goal:** 웹 TC 스튜디오(`qa-native-fixed` `f4e7a6b`)를 참고해 이 저장소에 TC 라이브러리·엑셀 왕복·LLM 초안 생성을 이식하고, 앱 스위트에 And/iOS 결과 비교를 넣고, 승인 TC를 `testcases/{android,ios}/` md로 내보낸다.

**Design:** [TC_STUDIO_APP_DESIGN.md](TC_STUDIO_APP_DESIGN.md) · **안내:** [README.md](README.md)

**용어:** `WEB` = `/Users/junghoyoung/qa-native-fixed`(**읽기 전용**, 기준 `f4e7a6b`) · `APP` = 이 저장소(FastAPI, 포트 8767)

## Global Constraints

- **WEB은 읽기만 한다.** 수정·커밋·push·8766 서버 재시작 금지. 원본은 `git -C ../qa-native-fixed show f4e7a6b:<경로>`로 읽는다.
- 이식 파이썬은 웹과 **같은 파일 이름**(`scripts/_tc_*.py`). 웹 의존 `_paths`·`_state`는 APP용 작은 `scripts/_paths.py`·`scripts/_state.py`로 대신한다.
- API는 웹과 **같은 URL·응답 모양**(`/api/tc-library/...`)으로 FastAPI 라우터 `agents/dashboard/routes/tc_studio.py`에 다시 쓴다.
- LLM은 `claude -p` CLI subprocess만. LLM SDK import 금지(APP `CLAUDE.md`).
- 엑셀은 특정 양식에 맞추지 않는다. 예시 파일(야핏무브·LODIS)의 건수를 완료 조건으로 쓰지 않는다.
- 웹 테스트를 옮겨 먼저 실패를 확인하고(RED) 이식해 통과시킨다(GREEN). 새 동작(플랫폼별 결과 등)도 테스트 먼저.
- 사용자 데이터(`state/tc_library`, `testcases/`, `import/`)를 테스트에서 건드리지 않는다. 테스트는 `tmp_path`·격리 경로를 쓴다.
- 파이썬 수정 후 8767 앱 대시보드를 재시작한다. JS·CSS는 새로고침.
- 커밋은 Task 단위, 한국어 conventional commit. 끝난 항목은 이 문서 체크박스를 체크해 같은 커밋에 넣는다. **push는 사용자 확인 후**.
- 설명·보고는 한국어, 짧고 쉽게.

## 검증 명령

```bash
# APP 테스트 (이식 테스트는 tests/unit/tc_library/)
cd /Users/junghoyoung/qa-native-app && python3 -m pytest tests/unit tests/dashboard -q
# APP CLAUDE.md '변경 시 검증'
python3 -m py_compile scripts/*.py
python3 scripts/02_generate.py --platform android --strict-locators
python3 scripts/02_generate.py --platform ios --strict-locators
git diff --check
# 8767 재시작
kill $(lsof -tiTCP:8767 -sTCP:LISTEN); nohup python3 agents/dashboard/serve.py >/tmp/dash8767.log 2>&1 &
```

---

## Phase 0 — 준비

### Task 0.1: APP 작업 트리 정리 — **사용자 확인**

현재 미커밋 변경(2026-10-01): `config/devices.json`, `logs/*`, `state/*` 수정, `tests/generated/android/capture_studio_e2e/tc_capture_settings_search_input.py` 삭제, 이름이 `-`인 파일, `config/devices.json.lock`, `reports/screenshots/…`, `state/captures/` 등.

- [x] `git status` 목록을 보여 주고 처리 방법을 묻는다(커밋 / `.gitignore` / 되돌리기). **임의로 지우거나 되돌리지 않는다.**
- [x] 이름이 `-`인 파일은 내용을 보여 준 뒤 묻는다.
- [x] 결정대로 정리·커밋. (2026-10-01: 산출물 `.gitignore`, devices.json 커밋. 삭제된 TC·`-` 스크린샷은 사용자도 출처를 몰라 손대지 않고 보류)

### Task 0.2: 이식 준비 확인

- [x] WEB이 `f4e7a6b`에 있는지, 이식 대상 파일 목록(아래 Phase별 Files)이 그 커밋에 있는지 확인.
- [x] APP 환경: `openpyxl`, `claude` CLI(`which claude`), FastAPI 테스트 클라이언트 사용 가능 여부.
- [x] WEB 테스트 픽스처(`tests/unit/tc_library/conftest.py`, `tc_fixtures.py`, `source_fixtures.py`, `connector_fixtures.py`, `fake_claude.py`)가 무엇에 의존하는지 정리해 보고.

---

## Phase 1 — 코어: 모델·라이브러리 저장소

**Files:**
- Create: `scripts/_paths.py`, `scripts/_state.py`(APP용 최소 shim: `TC_LIBRARY_DIR = state/tc_library`, `read_state`/`update_state` — 원자적 쓰기·잠금)
- Create(이식): `scripts/_tc_model.py`, `scripts/_tc_library.py`, `scripts/_tc_trash.py`, `scripts/_tc_review.py`
- Create(이식): `tests/unit/tc_library/` — `conftest.py`, `tc_fixtures.py`, `test_tc_model.py`, `test_tc_library.py`, `test_tc_library_phase2.py`, `test_tc_trash.py`, `test_tc_review.py`

- [ ] 웹 테스트를 옮기고 실패 확인(RED).
- [ ] 모듈 이식 → 통과(GREEN). 웹 전용 의존(`_validators` 등)은 필요한 함수만 옮긴다.
- [ ] **플랫폼별 결과(신규)**: `platform_key(label)`(별칭: And/Android/AOS/안드로이드 → android, iOS/IOS/아이폰 → ios), `platforms`·`results` 필드, `execution_result` 파생, 스위트 `kind`. 테스트 `tests/unit/tc_library/test_tc_platform_results.py`.
- [ ] 저장 경로(`_tc_library._apply`)에서 `results`가 있으면 `execution_result = merge_results(results.values())`.

## Phase 2 — 엑셀 가져오기·내보내기 (+ 플랫폼별 결과 보존)

**Files(이식):** `scripts/_tc_template.py`, `scripts/_tc_profiles.py`, `scripts/_tc_xlsx_import.py`, `scripts/_tc_xlsx_export.py`, `scripts/_tc_import_ops.py` · 테스트 `test_tc_template.py`, `test_tc_mapping.py`, `test_tc_xlsx_import.py`, `test_tc_xlsx_export.py`, `test_tc_import_ops.py`, `test_tc_prompt_profiles.py`(프로필 부분)

- [ ] 웹 테스트 이식 → RED → GREEN.
- [ ] **신규 RED**: `tmp_path`에 만든 두 양식 워크북 — (a) 2줄 헤더(상위 `환경`, 하위 `And | iOS`), (b) 1줄 헤더(`Android | iOS`) — 에서 `results`가 플랫폼별로 저장되고, 한쪽 `NA` → `platforms` 하나, 결과 열이 있으면 `kind == "app"`.
- [ ] 가져오기: 결과 열 라벨 → `platform_key`. 인식 안 되는 라벨은 열 매핑에서 플랫폼을 지정할 수 있게(웹 매핑 프로필 구조 재사용).
- [ ] 내보내기: 각 결과 열에 해당 플랫폼 값. **왕복 테스트: Android Pass·iOS Fail 유지, `NA` 유지.** 요약 수식 보정(`_rewrite_summary`) 동작 확인.

## Phase 3 — 기획 정보와 LLM 초안 생성

**Files(이식):** `scripts/_tc_html.py`, `scripts/_tc_fetch.py`, `scripts/_tc_sources.py`, `scripts/_tc_credentials.py`, `scripts/_tc_connectors.py`, `scripts/_tc_source_watch.py`, `scripts/_tc_prompt.py`, `scripts/_tc_generate.py` · 테스트 `source_fixtures.py`, `connector_fixtures.py`, `fake_claude.py`, `test_tc_fetch.py`, `test_tc_sources.py`, `test_tc_credentials.py`, `test_tc_connectors.py`, `test_tc_source_watch.py`, `test_tc_generate.py`, `test_tc_prompt_profiles.py`

- [ ] 웹 테스트 이식 → RED → GREEN. 실제 네트워크·실제 `claude` 호출 없이(가짜 서버·`fake_claude`).
- [ ] `claude -p` 보안 옵션을 웹과 동일하게 유지(`--restricted`, `--tools ""`, `--strict-mcp-config`, `--json-schema`, 저장소 밖 임시 작업 폴더). 테스트로 명령 인자 확인.
- [ ] 자격 증명 저장 위치를 APP 쪽으로(웹 파일을 읽지 않음), `.gitignore`에 포함 확인.
- [ ] **신규**: 앱 스위트 생성 대상 `대상 플랫폼(둘 다/And/iOS)` → 초안 `platforms`. 프롬프트 규칙 줄 추가(DESIGN 2.3). 가짜 LLM으로 확인.

## Phase 4 — API (FastAPI)

**Files:** Create `agents/dashboard/routes/tc_studio.py` · Modify `agents/dashboard/serve.py`(라우터 등록) · 테스트(이식·변환) `test_tc_library_api.py`, `test_tc_authoring_api.py`, `test_tc_connectors_api.py`, `test_tc_import_admin.py`, `test_tc_md_api.py`(Phase 5에서)

- [ ] 웹 라우트 목록(`routes_tc_library.py`, `routes_tc_authoring.py`, `routes_tc_connectors.py`, `routes_tc_import_admin.py`)을 같은 URL·응답 모양으로 옮긴다. 웹 API 테스트를 FastAPI `TestClient`용으로 바꿔 통과.
- [ ] 업로드 크기 제한·잘못된 id 검증 등 웹의 입력 검증을 빠짐없이 옮긴다.
- [ ] **신규**: `filter_cases`에 `platform`, `mismatch`(And·iOS 결과가 다른 것만) 쿼리. 응답 스위트 항목에 `kind`.
- [ ] 8767 재시작 후 `curl`로 `/api/tc-library` 응답 확인.

## Phase 5 — md 내보내기 → `testcases/{android,ios}/`

**Files:** Create(웹 `_tc_md_export.py` 참고) `scripts/_tc_md_export.py` · Modify `scripts/import_excel.py`(필요하면 `_render_markdown`을 재사용 가능하게만) · 테스트 `test_tc_md_export.py`, `test_tc_md_api.py`

- [ ] RED: 승인 TC → `platforms`의 OS에만 md 생성, 형식은 `import_excel._render_markdown`, `02_generate.parse_tc_blocks`가 블록 수를 0이 아니게 읽음.
- [ ] 충돌 정책 `skip-conflict` 기본 / `overwrite` 명시. 미리보기·반영·되돌리기(웹 흐름) 유지.
- [ ] 테스트는 `tmp_path`를 testcases 루트로 주입. 실제 `testcases/`에 쓰지 않는다.

## Phase 6 — 화면과 메뉴

**Files:** Create `agents/dashboard/static/tc-studio/*.js`, `tc-studio.css`(웹 `static/js/tc-studio/*`, `static/css/tc-studio.css` 이식) · Modify `agents/dashboard/dashboard.html`(사이드바 "TC 작성" 첫 항목 **TC 스튜디오**, `#view-tc_studio`), `agents/dashboard/static/dashboard-shell.js`(`selectView`) · 테스트 웹 E2E(`test_tc_studio_e2e.py` 등) 중 핵심 흐름을 APP 대시보드용으로 변환

- [ ] 웹 화면 4개 탭(라이브러리·기획 정보/생성·검토·내보내기)을 옮긴다. 웹 스위트 동작은 원본과 동일.
- [ ] 앱 스위트만: 결과 `And | iOS` 2칸, 전용 TC 반대쪽 회색 N/A, 필터 `플랫폼`·**`And·iOS 결과가 다른 것만`**, 상세 패널 결과 2개 + 대상 플랫폼, 일괄 변경 대상 플랫폼.
- [ ] **E2E 필수**: 2양식 픽스처 가져오기 → "결과가 다른 것만" 필터 → 불일치 행만 표시.
- [ ] 기존 대시보드 화면(Capture/Import/ENV 등) 회귀 없음: `tests/dashboard` 통과.
- [ ] **사용자 확인**: 기존 Import Studio(엑셀 → md 직접 변환)를 그대로 둘지, TC 스튜디오로 합칠지 묻는다. 결정 전에는 둘 다 유지.

## Phase 7 — 문서와 통합 검증

- [ ] APP `docs/USER_GUIDE.html`에 TC 스튜디오 절(웹 설명서 구성 참고, 앱 스위트·결과 비교·md 내보내기 포함).
- [ ] APP `CLAUDE.md` "TC 스튜디오" 절 갱신(이식 위치, 웹은 읽기 전용, md 형식 소유자).
- [ ] 통합: 8767 재시작 → 예시 엑셀(사용자 파일, 읽기만) 가져오기 → 불일치 필터 확인 → 기획 텍스트로 초안 생성(실제 `claude`, 사용자 확인 후) → 승인 → md 미리보기. **실제 `testcases/` 반영은 사용자 확인 후.**
- [ ] 검증 명령 전부 통과, 문서 링크 깨짐 0.
- [ ] 결과 보고 후 push 여부를 사용자에게 묻는다.

## 완료 정의

- 이 저장소만으로 TC 라이브러리·엑셀 왕복·LLM 초안 생성·md 내보내기가 동작한다.
- 앱 스위트에서 And/iOS 결과가 엑셀 왕복 후에도 보존되고, 결과가 다른 TC만 걸러 볼 수 있다.
- 승인 TC가 `testcases/{android,ios}/` md로 나가 `02_generate`가 읽는다.
- `qa-native-fixed`에는 아무 변경도 없다(`git -C ../qa-native-fixed status` 확인).
