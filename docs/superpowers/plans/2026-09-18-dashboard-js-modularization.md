# Dashboard JavaScript Modularization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 단일 `dashboard.js`를 현재 동작을 유지하는 여섯 개의 기능별 classic script로 분리한다.

**Architecture:** HTML은 기능 파일을 의존 순서대로 동기 로드하며 초기화 파일을 마지막에 둔다. 기존 전역 함수와 상태는 유지하고 FastAPI는 명시적으로 허용된 자산만 제공한다.

**Tech Stack:** HTML, browser JavaScript, FastAPI, pytest, Playwright

**Spec:** `docs/superpowers/specs/2026-09-18-dashboard-js-modularization-design.md`

## Global Constraints

- UI 디자인과 사용자 문구를 변경하지 않는다.
- 기존 전역 함수명, 인라인 이벤트, API와 WebSocket 계약을 유지한다.
- 초기화 파일은 다른 다섯 기능 파일 뒤에서 한 번만 실행한다.
- 현재 작업 트리의 관련 없는 변경을 수정하거나 커밋하지 않는다.
- 기존 `dashboard.js`의 코드가 새 파일 분리 과정에서 누락되거나 중복되지 않아야 한다.

---

### Task 1: 다중 JavaScript 자산 계약

**Files:**
- Modify: `tests/dashboard/test_dashboard_assets.py`
- Modify: `tests/dashboard/dashboard_source.py`

**Interfaces:**
- Consumes: 루트 HTML의 `<script src="/static/...">` 선언
- Produces: 정확한 로딩 순서 검증과 HTML 기반 테스트 소스 결합

- [x] **Step 1: 실패 테스트 작성**

`test_dashboard_assets.py`에 다음 고정 순서를 기대하는 테스트를 추가한다.

```python
EXPECTED_SCRIPTS = [
    "/static/dashboard-shell.js",
    "/static/execution.js",
    "/static/observability.js",
    "/static/environment.js",
    "/static/capture-studio.js",
    "/static/dashboard-init.js",
]
```

루트 HTML에서 script `src`를 파싱해 위 목록과 동일한지 확인하고, 각 URL이 200과 JavaScript content-type을 반환하는지 확인한다.

- [x] **Step 2: RED 확인**

Run: `.venv/bin/pytest -q tests/dashboard/test_dashboard_assets.py`

Expected: 현재 문서가 `/static/dashboard.js` 하나만 참조하므로 실패한다.

- [x] **Step 3: 테스트 소스 로더 일반화**

`dashboard_source.py`가 HTML에서 `/static/*.js`를 정규식으로 추출하고 선언 순서대로 로컬 파일을 읽도록 변경한다. 반환값은 HTML, CSS, JavaScript 파일들의 결합 문자열이다.

### Task 2: 기능별 파일 추출과 서버 연결

**Files:**
- Create: `agents/dashboard/static/dashboard-shell.js`
- Create: `agents/dashboard/static/execution.js`
- Create: `agents/dashboard/static/observability.js`
- Create: `agents/dashboard/static/environment.js`
- Create: `agents/dashboard/static/capture-studio.js`
- Create: `agents/dashboard/static/dashboard-init.js`
- Delete: `agents/dashboard/static/dashboard.js`
- Modify: `agents/dashboard/dashboard.html`
- Modify: `agents/dashboard/routes/api.py`

**Interfaces:**
- Consumes: 기존 `dashboard.js`의 marker 기반 연속 구간
- Produces: 설계 문서의 여섯 classic script와 HTTP 정적 자산 URL

- [x] **Step 1: 경계 검증형 추출 실행**

추출 스크립트는 다음 marker가 각각 한 번 존재하는지 먼저 검사한다.

```text
// ── 스텝 숫자 상태
// 증거 수집 관측성 (Execution Observability — PRD §8)
// ── 초기화
// ── ENV 상태 카드 (Appium + Android + iOS)
// ── Capture Studio
```

초기화 IIFE의 닫힘까지를 별도 `dashboard-init.js`로 이동한다. 나머지 구간은 원본 문자 그대로 저장한다.

- [x] **Step 2: 코드 보존 확인**

새 파일을 원래 소스 순서인 shell, execution, observability, init, environment, capture 순으로 결합해 기존 `dashboard.js`와 바이트 단위로 비교한다. 차이가 있으면 HTML이나 서버를 변경하지 않고 중단한다.

- [x] **Step 3: HTML과 허용 목록 갱신**

HTML의 단일 script 태그를 설계된 여섯 script 태그로 교체한다. `routes/api.py`의 `_DASHBOARD_ASSETS`에서 `dashboard.js`를 제거하고 여섯 파일을 `text/javascript`로 허용한다.

- [x] **Step 4: 기존 번들 제거**

새 파일과 참조가 준비되고 보존 비교가 통과한 뒤 `dashboard.js`를 제거한다.

- [x] **Step 5: GREEN 확인**

Run: `.venv/bin/pytest -q tests/dashboard/test_dashboard_assets.py`

Expected: 자산 경로, 순서, content-type과 미등록 경로 차단 테스트가 모두 통과한다.

### Task 3: 소스 및 브라우저 회귀 검증

**Files:**
- Modify only if a regression is found in Task 1-2 files.

**Interfaces:**
- Consumes: 여섯 JavaScript 파일과 테스트 소스 로더
- Produces: 기존 전역 계약과 브라우저 동작 유지 증거

- [x] **Step 1: 모든 JavaScript 문법 검사**

Run:

```bash
for file in agents/dashboard/static/*.js; do node --check "$file"; done
```

Expected: 모든 파일 exit code 0.

- [x] **Step 2: 소스 계약 테스트**

Run:

```bash
.venv/bin/pytest -q \
  tests/dashboard/test_dashboard_assets.py \
  tests/dashboard/test_serve.py \
  tests/dashboard/test_observability_ui.py \
  tests/dashboard/test_capture_launch.py \
  tests/dashboard/test_env_phase3_html.py
```

Expected: 모든 테스트 통과.

- [x] **Step 3: 전체 대시보드 테스트**

Run: `.venv/bin/pytest -q tests/dashboard`

Expected: 모든 API 및 Playwright 테스트 통과.

### Task 4: 실제 Android 관측성 검증과 마무리

**Files:**
- Generated only: `state/runs/<run_id>/`, `tests/reports/report_android_<run_id>.html`

**Interfaces:**
- Consumes: 연결된 `emulator-5554`, `tests/generated/android/obs_demo`
- Produces: 실제 실패 증거 manifest와 HTML 리포트

- [x] **Step 1: Android 연결 확인**

Run: `adb devices -l`

Expected: `emulator-5554 device`.

- [x] **Step 2: 단일 시도 E2E 실행**

Run:

```bash
DEVICE_MODE=emulator DEVICE_UDID=emulator-5554 QA_OBS_KEEP=on_failure \
  .venv/bin/python -u scripts/05_execute.py \
  --platform android --tc-dir obs_demo --no-rerun \
  --mode emulator --udid emulator-5554
```

Expected: 명령 자체는 의도된 실패 때문에 exit code 1이며 결과는 1 passed, 2 failed, 추가 error 0.

- [x] **Step 3: manifest 검증**

최신 Android run manifest에서 세 entry가 각각 attempt 1개인지 확인한다. 두 실패 entry는 video, syslog, screenshot이 있고 `collect_errors`가 비어 있어야 한다.

- [x] **Step 4: 변경 범위 검사**

Run: `git diff --check`를 이번 작업의 추적 파일에 적용하고 새 파일은 trailing whitespace를 별도로 검사한다.

Expected: 새 공백 오류 없음.
