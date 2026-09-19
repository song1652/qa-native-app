# Resilience Fault Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실기기 없이 로컬 QA 도구의 장시간 실행, 가상 디바이스 복구, 프로세스 비정상 종료, 아티팩트 보존을 자동 검증한다.

**Architecture:** 기존 상태 감지 함수에는 결정적 입력을 주입하고, 파일 보존 정책은 독립 프로덕션 서비스로 이동한다. 모든 파괴적 테스트는 테스트 전용 프로세스와 `tmp_path`에 한정한다.

**Tech Stack:** Python 3.14, pytest, FastAPI route helpers, subprocess, pathlib

**Spec:** `docs/superpowers/specs/2026-09-19-resilience-fault-injection-design.md`

## Global Constraints

- 실제 기기 및 사용자 Appium/에뮬레이터 프로세스를 변경하지 않는다.
- 테스트는 실제 장시간 대기 없이 결정적으로 끝나야 한다.
- 프로덕션 변경 전 실패 테스트를 확인한다.
- 기존 API 응답 계약을 유지한다.

---

### Task 1: 아티팩트 보존 서비스

**Files:**
- Create: `agents/dashboard/utils/artifact_retention.py`
- Create: `tests/dashboard/test_artifact_retention.py`
- Modify: `tests/observability/runtime.py`
- Modify: `agents/dashboard/routes/pipeline.py`

- [x] 최근 실행 보호, stale 실행, 개수, 용량 한도 실패 테스트 작성
- [x] 실패 확인 후 독립 보존 서비스 구현
- [x] 관측성 런타임과 파이프라인을 서비스에 연결
- [x] 집중 테스트 실행

### Task 2: 실행 프로세스 복구

**Files:**
- Modify: `agents/dashboard/shared.py`
- Create: `tests/dashboard/test_process_resilience.py`

- [x] 살아 있는 PID 복원과 죽은 PID 제거 실패 테스트 작성
- [x] 복원 결과와 정리된 상태를 결정적으로 반환하도록 구현
- [x] 테스트 전용 자식 프로세스로 집중 테스트 실행

### Task 3: 가상 디바이스와 Appium 장애 전환

**Files:**
- Create: `tests/dashboard/env/test_resilience_transitions.py`

- [x] Android 및 iOS disconnect/reconnect 전환 테스트 작성
- [x] Appium managed error/dead/external 전환 테스트 작성
- [x] 필요한 최소 프로덕션 수정 후 집중 테스트 실행

### Task 4: 전체 검증

- [x] dashboard 전체 테스트 실행
- [x] observability/execute 전체 집중 테스트 실행
- [x] Python 컴파일 및 diff 검사
- [x] 실행 중 서버 재시작 후 읽기 전용 상태 API 확인
