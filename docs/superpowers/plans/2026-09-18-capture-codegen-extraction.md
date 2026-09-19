# Capture Code Generation Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture Studio의 actions 기반 pytest 코드 생성을 FastAPI 라우터에서 독립 모듈로 분리한다.

**Architecture:** 라우터는 HTTP 요청과 오류 매핑만 담당하고 `utils.capture_codegen.generate_test_from_actions()`가 검증, 코드 렌더링과 파일 저장을 수행한다. 생성 결과와 API payload는 기존과 동일하게 유지한다.

**Tech Stack:** Python 3.14, FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-09-18-capture-codegen-extraction-design.md`

## Global Constraints

- `/capture/generate_from_actions` 경로와 응답 필드를 변경하지 않는다.
- Android/iOS 생성 코드의 런타임 동작을 변경하지 않는다.
- FastAPI 의존성을 코드 생성 모듈에 넣지 않는다.
- 현재 작업 트리의 관련 없는 변경을 수정하지 않는다.

---

### Task 1: 코드 생성 서비스 계약

**Files:**
- Create: `tests/dashboard/test_capture_codegen.py`
- Create: `agents/dashboard/utils/capture_codegen.py`

**Interfaces:**
- Produces: `CaptureCodegenValidationError`, `generate_test_from_actions(body, session, project_root, generated_at=None) -> dict`

- [x] **Step 1: 실패 테스트 작성**

임시 project root와 Android/iOS body를 서비스에 전달한다. 반환된 `code`를 `compile()`하고 `file` 경로에 같은 코드가 저장됐는지 확인한다. 잘못된 platform은 `CaptureCodegenValidationError`여야 한다.

- [x] **Step 2: RED 확인**

Run: `.venv/bin/pytest -q tests/dashboard/test_capture_codegen.py`

Expected: `utils.capture_codegen` 모듈이 없어 collection error가 발생한다.

- [x] **Step 3: 기존 로직 이동**

`capture_generate_from_actions`의 body/session 파싱부터 응답 payload 생성까지를 새 함수로 이동한다. `datetime.now()`는 `generated_at or datetime.now()`로 대체하고 `PROJECT_ROOT`는 `project_root` 인자를 사용한다.

- [x] **Step 4: GREEN 확인**

Run: `.venv/bin/pytest -q tests/dashboard/test_capture_codegen.py`

Expected: Android/iOS/검증 테스트 통과.

### Task 2: 라우터 연결

**Files:**
- Modify: `agents/dashboard/routes/capture.py`
- Test: `tests/dashboard/test_capture_launch.py`

**Interfaces:**
- Consumes: `generate_test_from_actions()` 반환 dict 또는 `CaptureCodegenValidationError`
- Produces: 기존 `/capture/generate_from_actions` JSON 계약

- [x] **Step 1: 라우터를 얇은 어댑터로 교체**

request JSON과 `load_capture_session()` 결과를 서비스에 전달한다. 검증 예외는 기존 메시지 `tc_id와 platform이 필요합니다`와 status 400으로 반환한다.

- [x] **Step 2: 통합 테스트 실행**

Run: `.venv/bin/pytest -q tests/dashboard/test_capture_launch.py tests/dashboard/test_capture_codegen.py`

Expected: 기존 endpoint 생성 테스트와 새 서비스 테스트 통과.

### Task 3: 전체 검증

**Files:**
- Modify only if Task 1-2 대상 파일에서 회귀가 확인된다.

**Interfaces:**
- Consumes: 분리된 코드 생성 서비스와 기존 Capture Studio UI
- Produces: 기존 동작 유지 증거

- [x] **Step 1: Python 문법 검사**

Run: `.venv/bin/python -m py_compile agents/dashboard/routes/capture.py agents/dashboard/utils/capture_codegen.py`

- [x] **Step 2: 전체 dashboard 테스트**

Run: `.venv/bin/pytest -q tests/dashboard`

Expected: 모든 테스트 통과.

- [x] **Step 3: 변경 범위 검사**

대상 추적 파일에 `git diff --check`를 실행하고 새 파일의 trailing whitespace를 검사한다.
