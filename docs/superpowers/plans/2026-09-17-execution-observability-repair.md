# Execution Observability Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair execution observability so generated-test attempts produce reliable, queryable video/log evidence and the Android `obs_demo` flow passes end-to-end verification.

**Architecture:** The pytest collector lazily owns one manifest per logical run and appends immutable attempt records. Dashboard launchers pass run-scoped environment dictionaries, APIs normalize legacy and current manifests, and the UI consumes the normalized attempt contract.

**Tech Stack:** Python 3, pytest, FastAPI/Starlette, subprocess/adb/xcrun, vanilla HTML/CSS/JavaScript.

**Spec:** `docs/superpowers/specs/2026-09-17-execution-observability-repair-design.md`

## Global Constraints

- Preserve unrelated uncommitted user changes.
- Do not add ffmpeg or another runtime dependency.
- Collection failures must never change a test result.
- New manifests use `attempts[]`; APIs remain compatible with legacy flat entries.
- Final acceptance uses `tests/generated/android/obs_demo/`.

---

### Task 1: Lock collector lifecycle and manifest behavior with tests

**Files:**
- Modify: `tests/_observability.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_observability_collector.py`

**Interfaces:**
- Produces: `ensure_session()`, `record_report()`, `start()`, `stop()`, `session_finish()` and attempt-based manifest entries.

- [ ] Add failing tests proving non-generated sessions create no files, `never` starts no processes, setup errors are retained, attempts append, configuration values apply, and empty iOS bundle IDs do not create match-all predicates.
- [ ] Run `python3 -m pytest tests/test_observability_collector.py -q` and confirm failures identify current behavior.
- [ ] Implement lazy initialization, outcome aggregation, normalized configuration, and attempt persistence.
- [ ] Re-run the collector tests and existing `tests/_observability.py` tests.

### Task 2: Make captured media trustworthy

**Files:**
- Modify: `tests/_observability.py`
- Test: `tests/test_observability_collector.py`

**Interfaces:**
- Produces: `_mp4_duration_seconds(path)`, `_validate_mp4(path)`, Android remote PID lifecycle helpers.

- [ ] Add failing tests for missing `moov`, zero-duration MP4, positive-duration MP4, remote stop timeout, pull failure, and remote cleanup.
- [ ] Run the focused tests and confirm RED.
- [ ] Implement exact remote PID stop/stability polling and MP4 validation; reject/delete invalid media with `video_invalid`.
- [ ] Run focused collector tests and confirm GREEN.

### Task 3: Isolate pipeline environments and preserve logical run identity

**Files:**
- Modify: `agents/dashboard/routes/pipeline.py`
- Modify: `scripts/05_execute.py`
- Test: `tests/test_observability_pipeline.py`

**Interfaces:**
- Produces: `_build_run_env(...) -> dict`, one run ID reused by healing, and consistent `--mode`/`--udid` propagation.

- [ ] Add real-route/unit tests proving global environment remains unchanged, selected device parameters reach execute, and healing calls reuse one run ID.
- [ ] Run the tests and confirm RED.
- [ ] Refactor subprocess launchers to accept explicit `env`; allocate run ID once per logical execution.
- [ ] Re-run pipeline tests and related dashboard route tests.

### Task 4: Normalize API and retention contracts

**Files:**
- Modify: `agents/dashboard/routes/observability.py`
- Test: `tests/test_observability_api.py`

**Interfaces:**
- Produces: `GET /api/runs`, compatibility `GET /api/run_artifacts`, attempt-aware detail/video/log endpoints, legacy normalization.

- [ ] Add failing API tests for canonical listing, legacy normalization, attempt selection, active deletion, deletion failure, and path validation.
- [ ] Run and confirm RED.
- [ ] Implement normalization and endpoints with resolved-path guards.
- [ ] Run API tests and confirm GREEN.

### Task 5: Complete dashboard evidence behavior

**Files:**
- Modify: `agents/dashboard/dashboard.html`
- Modify: `scripts/report_html.py`
- Modify: `scripts/05_execute.py`
- Test: `tests/dashboard/test_observability_ui.py`

**Interfaces:**
- Consumes: normalized API `attempts[]` and artifact URLs.
- Produces: attempt selector, error explanations, log presets, manifest-based Livetail summary, report artifact link.

- [ ] Add failing DOM/behavior contract tests for attempt switching, required presets, localized errors, and report link.
- [ ] Run and confirm RED.
- [ ] Implement the minimal UI/report behavior while preserving existing layout changes.
- [ ] Run dashboard and report tests.

### Task 6: Align documentation and replace misleading tests

**Files:**
- Modify: `docs/EXECUTION_OBSERVABILITY_PRD.md`
- Modify: `CLAUDE.md`
- Modify: `tests/_observability_e2e.py`

- [ ] Replace the test-only probe endpoint with tests of production routes.
- [ ] Resolve attempt-layout contradictions in the PRD and document `video_invalid`.
- [ ] Run all observability tests, compile checks, and `git diff --check`.

### Task 7: Real Android obs_demo E2E

**Files:**
- Runtime outputs only: `state/runs/`, `logs/run_test_android_obs_demo.txt`, reports.

- [ ] Verify Appium and an Android emulator are available.
- [ ] Run `python3 scripts/05_execute.py --platform android --mode emulator --tc-dir obs_demo`.
- [ ] Validate the newest manifest, every retained MP4 with `ffprobe`, log retrieval through the API, and absence of leftover `screenrecord`/`adb logcat` processes.
- [ ] Run final regression tests and report exact pass/fail counts and any external blocker.
