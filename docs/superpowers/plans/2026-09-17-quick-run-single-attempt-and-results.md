# Quick Run Single-Attempt and Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make quick runs default to one attempt with healing skipped, always replace the legacy result card with the latest observability workspace, and capture screenshots even for driverless Android/iOS simulator tests.

**Architecture:** The quick-run checkbox controls both the dashboard healing pass and pytest reruns through a `--no-rerun` execution flag. The browser resolves the completed run ID from memory, local storage, or `/api/status` before rendering artifacts, so missed WebSocket messages cannot strand the legacy result. The observability collector uses Appium screenshots when available and a platform-native ADB/simctl fallback otherwise.

**Tech Stack:** FastAPI, Python subprocess execution, pytest/pytest-rerunfailures, vanilla JavaScript, Playwright.

**Spec:** `docs/EXECUTION_OBSERVABILITY_PRD.md`

## Global Constraints

- Android and iOS quick-run behavior must remain equivalent.
- A checked `힐링 생략` control means one pytest attempt, no healing process, and no healing re-execution.
- Existing user and Claude worktree changes must be preserved.
- Observability evidence order remains video, log, screenshot.

---

### Task 1: Single-attempt quick-run contract

**Files:**
- Modify: `tests/test_execute_observability.py`
- Modify: `tests/test_observability_pipeline.py`
- Modify: `tests/dashboard/test_observability_workspace_e2e.py`
- Modify: `scripts/05_execute.py`
- Modify: `agents/dashboard/routes/pipeline.py`
- Modify: `agents/dashboard/dashboard.html`

**Interfaces:**
- Consumes: quick-run `heal: bool` request field.
- Produces: `--no-rerun` CLI option and a checked-by-default `#generated-heal` control.

- [x] **Step 1: Write failing tests** proving the checkbox is initially checked, rerun options are empty when disabled, and the quick-run backend adds `--no-rerun` when healing is false.
- [x] **Step 2: Run the focused tests and verify they fail for the missing behavior.**
- [x] **Step 3: Add the `--no-rerun` option, conditionally build rerun flags, pass it from `/api/run_test`, and render the checkbox checked.**
- [x] **Step 4: Run the focused tests and verify they pass.**

### Task 2: Reliable completed-run workspace rendering

**Files:**
- Modify: `tests/dashboard/test_observability_workspace_e2e.py`
- Modify: `agents/dashboard/dashboard.html`

**Interfaces:**
- Consumes: `/api/status?platform={android|ios}` response field `obs_last_run_id`.
- Produces: `_obsResolveLatestRunId(platform): Promise<string>` used after quick-run completion and saved-result restoration.

- [x] **Step 1: Write a failing browser test** that clears the WebSocket/local-storage run ID, returns a current run ID from `/api/status`, and expects the observability workspace to render.
- [x] **Step 2: Run the browser test and verify the legacy result remains.**
- [x] **Step 3: Implement the status fallback with platform/run-ID validation and await it before artifact injection.**
- [x] **Step 4: Run the browser test and verify the workspace replaces the legacy card.**

### Task 3: Driverless device screenshot fallback

**Files:**
- Modify: `tests/test_observability_collector.py`
- Modify: `tests/_observability.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: platform, UDID, mode, and kept-attempt artifact directory.
- Produces: `_capture_device_screenshot(platform, udid, mode, path) -> bool` and manifest `screenshot` metadata.

- [x] **Step 1: Write failing unit tests** for Android ADB screencap and iOS simulator `simctl io screenshot` command behavior.
- [x] **Step 2: Run the tests and verify the helper is absent.**
- [x] **Step 3: Implement native screenshot capture and call it during `stop()` only when a kept attempt has no Appium screenshot.**
- [x] **Step 4: Run collector and conftest tests and verify screenshot metadata is populated.**

### Task 4: Regression and device E2E verification

**Files:**
- Modify only if a verified defect is found in the preceding implementation.

**Interfaces:**
- Consumes: the complete quick-run and observability flow.
- Produces: test evidence for UI, backend, collector, Android `obs_demo`, and available iOS test execution.

- [x] **Step 1: Run focused dashboard, pipeline, execute, and observability suites.**
- [x] **Step 2: Run JavaScript and Python syntax checks.**
- [x] **Step 3: Run the Android `obs_demo` quick-run equivalent with healing and reruns disabled; verify one attempt per TC and screenshot metadata for failures.**
- [x] **Step 4: Run the corresponding available iOS E2E and verify the common workspace and screenshot path.**
- [x] **Step 5: Inspect the final manifests and confirm there are no stale test processes.**
