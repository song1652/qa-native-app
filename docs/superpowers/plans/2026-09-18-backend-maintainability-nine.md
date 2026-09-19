# Backend Maintainability 9.x Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move backend domain rules out of oversized route/runtime modules without changing external behavior.

**Architecture:** FastAPI routes retain request parsing and external I/O. Pure device-registry, Capture-validation, and observability-manifest modules own deterministic business rules and are tested independently.

**Tech Stack:** Python 3.14, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-09-18-backend-maintainability-nine-design.md`

## Global Constraints

- Preserve API paths, response fields, status codes, and error codes.
- Preserve existing monkeypatch compatibility surfaces.
- Add no runtime dependency.
- Use red/green TDD for every extraction.

### Task 1: Device registry domain service

- [x] Add failing pure tests for add, duplicate, default, remove, and last-device rules.
- [x] Implement `utils/device_registry.py` with `DeviceRegistryError`.
- [x] Delegate four environment registration endpoints to the service.
- [x] Run registry and full environment endpoint tests.

### Task 2: Capture locator validation service

- [x] Add failing XML locator tests for Android, iOS, XPath, and invalid strategies.
- [x] Implement `utils/capture_validation.py` returning a result dictionary or validation exception.
- [x] Make `/capture/validate_locator` a thin HTTP adapter.
- [x] Run focused Capture and dashboard tests.

### Task 3: Observability manifest service

- [x] Add failing tests for slugging, keep policy, attempt aggregation, and MP4 duration.
- [x] Move pure rules to `tests/observability/manifest.py` and re-export compatibility names.
- [x] Run collector, API, pipeline, and E2E tests.

### Task 4: Verification

- [x] Compile changed Python modules.
- [x] Run all dashboard tests and focused observability suites.
- [x] Run changed-file whitespace validation.
- [x] Restart the server and verify live API contracts.
