# Dashboard Static Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 거대한 `dashboard.html`에서 CSS와 JavaScript를 동작 변경 없이 분리하고 실제 서버 및 브라우저에서 동일하게 동작하도록 한다.

**Architecture:** HTML은 외부 CSS/JavaScript를 참조하고 FastAPI 라우터가 두 자산을 명시적 허용 목록으로 제공한다. 기존 전역 JavaScript 계약은 그대로 유지하며 테스트는 HTTP 응답과 브라우저 결과를 검증한다.

**Tech Stack:** FastAPI, HTML/CSS, 브라우저 JavaScript, pytest, Playwright

**Spec:** `docs/superpowers/specs/2026-09-17-dashboard-static-assets-design.md`

## Global Constraints

- 기능과 디자인을 변경하지 않는다.
- 기존 전역 함수명, 전역 상태, 인라인 이벤트 계약, 실행 순서를 유지한다.
- 현재 작업 트리의 관련 없는 변경을 수정하거나 정리하지 않는다.
- 정적 파일 경로는 `/static/dashboard.css`와 `/static/dashboard.js`로 고정한다.

---

### Task 1: 정적 자산 HTTP 계약

**Files:**
- Create: `tests/dashboard/test_dashboard_assets.py`
- Modify: `agents/dashboard/routes/api.py`

**Interfaces:**
- Consumes: FastAPI `app`과 `HERE` 대시보드 경로
- Produces: `GET /static/dashboard.css`, `GET /static/dashboard.js`

- [x] **Step 1: 실패 테스트 작성**

실제 ASGI 앱에 요청해 두 경로가 200, 올바른 content-type, 비어 있지 않은 본문을 반환하는지 검사한다. 알 수 없는 자산은 404여야 한다.

- [x] **Step 2: RED 확인**

Run: `pytest -q tests/dashboard/test_dashboard_assets.py`

Expected: 두 정적 자산 요청이 404라서 실패한다.

- [x] **Step 3: 최소 구현**

`routes/api.py`에 파일명 허용 목록을 둔 정적 자산 엔드포인트를 추가한다. 경로 입력을 파일시스템 경로로 직접 결합하지 않는다.

- [x] **Step 4: GREEN 확인**

Run: `pytest -q tests/dashboard/test_dashboard_assets.py`

Expected: 모든 테스트가 통과한다.

### Task 2: HTML/CSS/JavaScript 기계적 분리

**Files:**
- Create: `agents/dashboard/static/dashboard.css`
- Create: `agents/dashboard/static/dashboard.js`
- Modify: `agents/dashboard/dashboard.html`
- Create: `tests/dashboard/dashboard_source.py`
- Modify: `tests/dashboard/test_serve.py`
- Modify: `tests/dashboard/test_observability_ui.py`
- Modify: `tests/dashboard/test_capture_launch.py`
- Modify: `tests/dashboard/test_env_phase3_html.py`

**Interfaces:**
- Consumes: 기존 인라인 `<style>`과 `<script>` 본문
- Produces: 외부 자산 참조 및 테스트용 `load_dashboard_source()`

- [x] **Step 1: 실패 테스트 작성**

루트 문서가 외부 stylesheet/script를 참조하고 인라인 블록을 포함하지 않으며, 테스트 소스 로더가 HTML과 JS 계약을 함께 제공하는지 검사한다.

- [x] **Step 2: RED 확인**

Run: `pytest -q tests/dashboard/test_dashboard_assets.py`

Expected: 현재 문서가 여전히 인라인 자산을 포함하므로 실패한다.

- [x] **Step 3: 자산 추출 및 회귀 테스트 로더 적용**

태그 사이 본문을 그대로 새 파일로 이동하고 HTML에는 같은 위치에 외부 참조를 둔다. 기존 소스 회귀 테스트 네 개는 `load_dashboard_source()`를 사용한다.

- [x] **Step 4: 내용 및 문법 검증**

Run: `node --check agents/dashboard/static/dashboard.js`

Expected: exit code 0.

- [x] **Step 5: 대상 테스트 확인**

Run: `pytest -q tests/dashboard/test_dashboard_assets.py tests/dashboard/test_serve.py tests/dashboard/test_observability_ui.py tests/dashboard/test_capture_launch.py tests/dashboard/test_env_phase3_html.py`

Expected: 모든 테스트가 통과한다.

### Task 3: 전체 회귀 및 브라우저 검증

**Files:**
- Modify only if a regression is found in files from Tasks 1-2.

**Interfaces:**
- Consumes: 분리된 대시보드와 FastAPI 앱
- Produces: 검증된 동일 동작

- [x] **Step 1: 전체 대시보드 테스트**

Run: `pytest -q tests/dashboard`

Expected: 모든 테스트가 통과한다.

- [x] **Step 2: 실제 서버 브라우저 스모크 테스트**

임시 포트에서 앱을 실행하고 Playwright로 루트 화면을 연다. CSS/JS 응답 200, console/page error 없음, 빠른 실행 및 파이프라인 화면의 핵심 요소 표시를 확인한다.

- [x] **Step 3: 변경 범위 점검**

Run: `git diff --check -- agents/dashboard/dashboard.html agents/dashboard/static agents/dashboard/routes/api.py tests/dashboard docs/superpowers/specs/2026-09-17-dashboard-static-assets-design.md docs/superpowers/plans/2026-09-17-dashboard-static-assets.md`

Expected: 새 변경에 공백 오류가 없다.
