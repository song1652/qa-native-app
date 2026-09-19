# Dashboard Maintainability 9.x Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve all QA dashboard behavior while splitting oversized frontend and backend modules into independently testable responsibilities.

**Architecture:** Keep the existing classic-script global API and FastAPI route contracts. Move cohesive functions into ordered static assets and narrow Python utility modules, with contract tests guarding every boundary.

**Tech Stack:** Python 3.14, FastAPI, pytest, vanilla JavaScript, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-18-maintainability-nine-design.md`

## Global Constraints

- Preserve all existing global JavaScript handler names.
- Preserve API paths, status codes, and JSON field names.
- Add no runtime dependency.
- Do not overwrite unrelated dirty-worktree changes.
- Use test-first red/green cycles for each extraction.

---

### Task 1: Capture Studio asset boundaries

**Files:**
- Create: `agents/dashboard/static/capture-inspector.js`
- Create: `agents/dashboard/static/capture-actions.js`
- Create: `agents/dashboard/static/capture-livetail.js`
- Modify: `agents/dashboard/static/capture-studio.js`
- Modify: `agents/dashboard/dashboard.html`
- Modify: `tests/dashboard/test_dashboard_assets.py`

**Interfaces:**
- Consumes: browser globals declared by `capture-studio.js`.
- Produces: the existing `cs*` global handlers with unchanged signatures.

- [x] Add an asset contract test that requests all three new files and asserts the HTML load order is core, inspector, actions, live tail.
- [x] Run the focused test and verify it fails because the assets do not exist.
- [x] Move contiguous function groups without changing their bodies and add the ordered script tags.
- [x] Run asset and Capture Studio browser tests and verify they pass.

### Task 2: Execution asset boundaries

**Files:**
- Create: `agents/dashboard/static/import-studio.js`
- Create: `agents/dashboard/static/quick-run.js`
- Create: `agents/dashboard/static/reports.js`
- Modify: `agents/dashboard/static/execution.js`
- Modify: `agents/dashboard/dashboard.html`
- Modify: `tests/dashboard/test_dashboard_assets.py`

**Interfaces:**
- Consumes: shared `_quickPlatform`, `_reports`, and DOM helpers from `execution.js`/`dashboard-shell.js`.
- Produces: existing import, quick-run, and report global handlers.

- [x] Extend the asset contract test with the three files and exact dependency order.
- [x] Run it and verify the new expectations fail.
- [x] Move the import block, quick-run block, and report block mechanically into the new files.
- [x] Run static asset, quick-run, observability workspace, and browser tests.

### Task 3: Capture streaming service

**Files:**
- Create: `agents/dashboard/utils/capture_streaming.py`
- Modify: `agents/dashboard/routes/capture.py`
- Create: `tests/dashboard/test_capture_streaming.py`

**Interfaces:**
- Produces: `iter_jpeg_frames(stdout)`, `resolve_adb_serial(devices_config)`, and stream command builders.
- Consumes: byte streams and device configuration dictionaries.

- [x] Write literal byte-stream tests covering split JPEG frames and leading noise.
- [x] Run them and verify import failure.
- [x] Implement the pure parser and command/serial helpers.
- [x] Replace route-local helpers with imports while preserving stream responses.
- [x] Run Capture route and focused service tests.

### Task 4: Environment discovery service

**Files:**
- Create: `agents/dashboard/utils/env_devices.py`
- Modify: `agents/dashboard/routes/env.py`
- Create: `tests/dashboard/env/test_env_devices.py`

**Interfaces:**
- Produces: parsers for AVD names, simulator JSON, adb device rows, and configured-device normalization.
- Consumes: command output strings and existing device config dictionaries.

- [x] Add literal parser tests for Android, iOS, offline devices, and malformed rows.
- [x] Run them and verify import failure.
- [x] Implement pure parsing/normalization functions and delegate from routes.
- [x] Run environment unit and endpoint tests.

### Task 5: Observability support boundary

**Files:**
- Create: `tests/observability/runtime.py`
- Create: `tests/observability/__init__.py`
- Modify: `tests/_observability.py`
- Modify: observability tests only where imports require compatibility coverage.

**Interfaces:**
- Produces: the same names currently imported from `tests._observability`.
- Consumes: pytest lifecycle events and run artifact paths.

- [x] Add an import-compatibility test enumerating the public runtime symbols used by callers.
- [x] Verify the test fails when pointed at the not-yet-created runtime module.
- [x] Move runtime collectors into the package and re-export them from the facade.
- [x] Run observability collector, API, pipeline, and E2E tests.

### Task 5b: Environment frontend boundary

**Files:**
- Create: `agents/dashboard/static/environment-devices.js`
- Modify: `agents/dashboard/static/environment.js`
- Modify: `agents/dashboard/dashboard.html`
- Modify: `agents/dashboard/routes/api.py`
- Modify: `tests/dashboard/test_dashboard_assets.py`

**Interfaces:**
- Consumes: Appium environment globals from `environment.js`.
- Produces: existing Android/iOS device card and action handlers.

- [x] Extend the asset contract with the device asset and exact load order.
- [x] Verify the test fails before the asset exists.
- [x] Move the contiguous device-card block without changing handler signatures.
- [x] Run JavaScript syntax, environment UI, and endpoint regression tests.

### Task 6: Full verification and live smoke

**Files:**
- Modify only files required by failures proven during verification.

- [x] Compile all changed Python modules.
- [x] Run `pytest -q tests/dashboard`.
- [x] Run the focused observability and execution suites.
- [x] Run `git diff --check` on changed source and test files.
- [x] Restart the dashboard server and verify `/`, `/api/env/status`, and Capture validation responses.
- [x] Record actual line-count reductions and remaining risks.
