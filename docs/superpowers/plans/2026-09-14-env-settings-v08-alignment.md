# Environment Settings v0.8 Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a browser-usable Environment Settings flow that matches the v0.8 design/mockup and controls the locally installed Appium, Android AVDs, and iOS simulators end to end.

**Architecture:** Add deterministic discovery and validation helpers to `utils/system.py`, expose them through the existing environment router, and make runtime actions target configured AVD/UDID identities. Replace the generic dashboard modal and platform-wide controls with platform-specific list rows and add modals while preserving Phase 3 real-device controls.

**Tech Stack:** Python 3.14, FastAPI, subprocess argument arrays, vanilla HTML/CSS/JavaScript, pytest, FastAPI TestClient, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-14-env-settings-v08-alignment-design.md`

## Global Constraints

- Design specification v0.8 controls visual details; interactive mockup v0.8 controls interaction; `docs/ENV_SETUP_PRD.md` controls runtime safety.
- All commands use argument arrays, `shell=False`, resolved executable paths, and tool-specific environments.
- iOS simulator operations use validated UDIDs; Android operations use AVD names returned by system discovery.
- Only one controlled emulator per platform may be starting or running.
- Existing Phase 3 real-device controls and unrelated dirty-worktree changes must be preserved.
- Production behavior is written only after its focused test has failed for the expected reason.

---

### Task 1: Installed virtual-device discovery

**Files:**
- Modify: `agents/dashboard/utils/system.py`
- Modify: `agents/dashboard/routes/env.py`
- Create: `tests/unit/env/test_virtual_device_discovery.py`
- Modify: `tests/dashboard/env/test_env_endpoints.py`

**Interfaces:**
- Produces: `list_system_avds() -> list[dict[str, str]]`
- Produces: `list_system_simulators() -> list[dict[str, str]]`
- Produces: `GET /api/env/android/list_system_avds`
- Produces: `GET /api/env/ios/list_system_simulators`

- [ ] **Step 1: Write failing Android discovery tests**

```python
def test_list_system_avds_returns_name_device_and_platform_version(tmp_path):
    # emulator -list-avds -> Pixel_8_Android16; config.ini -> target=android-36
    result = system.list_system_avds()
    assert result == [{
        "avd": "Pixel_8_Android16",
        "deviceName": "Pixel 8",
        "platformVersion": "16",
    }]
```

Cover `target=android-36`, `image.sysdir.1=system-images;android-35;google_apis;arm64-v8a`, missing metadata fallback, non-zero command exit, and GUI-launch PATH resolution.

- [ ] **Step 2: Run Android discovery tests and confirm RED**

Run: `pytest -q tests/unit/env/test_virtual_device_discovery.py -k avd`

Expected: collection/import failure because `list_system_avds` does not exist.

- [ ] **Step 3: Implement minimal Android discovery**

Run `[EMULATOR_BIN, "-list-avds"]`, resolve each AVD's `config.ini`, derive its display name and Android release without shell interpolation, and return stable dictionaries sorted by AVD name.

- [ ] **Step 4: Write and run failing iOS discovery tests**

```python
def test_list_system_simulators_joins_devices_to_available_runtime():
    result = system.list_system_simulators()
    assert result == [{
        "deviceName": "iPhone 16 Plus",
        "platformVersion": "26.5",
        "udid": "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
        "state": "Shutdown",
    }]
```

Mock `xcrun simctl list devices available --json` and runtime JSON. Exclude unavailable runtimes/devices and preserve exact UDID/state values.

Run: `pytest -q tests/unit/env/test_virtual_device_discovery.py -k simulator`

Expected: failure because `list_system_simulators` does not exist.

- [ ] **Step 5: Implement minimal iOS discovery**

Parse simctl JSON, join device groups to runtime versions, filter unavailable entries, and return device dictionaries sorted by version then name.

- [ ] **Step 6: Add failing API contract tests**

```python
def test_get_system_simulators_returns_discovered_metadata(client):
    with patch("routes.env.list_system_simulators", return_value=[SIMULATOR]):
        response = client.get("/api/env/ios/list_system_simulators")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "simulators": [SIMULATOR]}
```

Add the Android equivalent plus structured `binary_not_found`/`discovery_failed` cases.

- [ ] **Step 7: Run endpoint tests and confirm RED**

Run: `pytest -q tests/dashboard/env/test_env_endpoints.py -k 'list_system'`

Expected: 404 responses.

- [ ] **Step 8: Add discovery endpoints and verify GREEN**

Run: `pytest -q tests/unit/env/test_virtual_device_discovery.py tests/dashboard/env/test_env_endpoints.py -k 'discovery or list_system'`

Expected: all selected tests pass.

### Task 2: Registration schema, defaults, and duplicate safety

**Files:**
- Modify: `agents/dashboard/routes/env.py`
- Modify: `tests/dashboard/env/test_env_endpoints.py`
- Modify: `tests/unit/env/test_save_devices_json.py`

**Interfaces:**
- Consumes: `list_system_avds`, `list_system_simulators`
- Produces: validated Android emulator and iOS simulator registration records in `config/devices.json`

- [ ] **Step 1: Write failing Android registration tests**

```python
def test_android_add_persists_mockup_fields_and_caps(client):
    response = client.post("/api/env/android/add", json={
        "mode": "emulator",
        "avd": "Pixel_8_Android16",
        "deviceName": "Pixel 8",
        "platformVersion": "16",
    })
    assert response.status_code == 200
    assert saved["automationName"] == "UiAutomator2"
    assert saved["mjpegScalingFactor"] == 75
    assert saved["mjpegServerScreenshotQuality"] == 70
```

Assert all PRD defaults: `noReset`, `forceAppLaunch`, `shouldTerminateApp`, `mjpegServerPort=8093`, empty `appPackage`/`appActivity`, and first-item `default=true`. Add missing field, unknown AVD, and duplicate AVD 409 tests.

- [ ] **Step 2: Run Android registration tests and confirm RED**

Run: `pytest -q tests/dashboard/env/test_env_endpoints.py -k 'android_add'`

Expected: failures for absent `platformVersion`, wrong MJPEG defaults, and missing whitelist validation.

- [ ] **Step 3: Implement Android registration contract and verify GREEN**

Use discovery output as the whitelist and canonical metadata source. Preserve backward-compatible real-device registration behavior.

Run: `pytest -q tests/dashboard/env/test_env_endpoints.py -k 'android_add'`

- [ ] **Step 4: Write failing iOS registration tests**

```python
def test_ios_simulator_add_persists_udid_and_version(client):
    response = client.post("/api/env/ios/add", json={
        "mode": "simulator",
        "deviceName": "iPhone 16 Plus",
        "platformVersion": "26.5",
        "udid": "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
    })
    assert response.status_code == 200
    assert saved["udid"].startswith("A1B2C3D4")
```

Add invalid UDID, unknown UDID, duplicate UDID 409, ambiguous duplicate name 409, and automatic first default tests.

- [ ] **Step 5: Run iOS registration tests and confirm RED**

Run: `pytest -q tests/dashboard/env/test_env_endpoints.py -k 'ios_add'`

Expected: failures because simulator UDID/version are not currently required or stored.

- [ ] **Step 6: Implement iOS registration contract and verify GREEN**

Validate `^[0-9A-F-]{36}$`, compare against discovered simulator UDIDs, store canonical discovery values, and keep real-device behavior separate.

Run: `pytest -q tests/dashboard/env/test_env_endpoints.py -k 'android_add or ios_add'`

- [ ] **Step 7: Run atomic persistence regression tests**

Run: `pytest -q tests/unit/env/test_save_devices_json.py tests/dashboard/env/test_env_endpoints.py -k 'add or save or default or duplicate'`

Expected: all selected tests pass and unrelated configuration sections remain unchanged.

### Task 3: Row-targeted runtime actions and identity reconciliation

**Files:**
- Modify: `agents/dashboard/utils/system.py`
- Modify: `agents/dashboard/routes/env.py`
- Modify: `tests/unit/env/test_device_runtime_status.py`
- Modify: `tests/dashboard/env/test_env_endpoints.py`

**Interfaces:**
- Consumes: configured AVD/UDID records
- Produces: row-identifiable status fields (`avd`, `serial`, `simulator`, `udid`)
- Produces: targeted start/stop request bodies

- [ ] **Step 1: Write failing Android identity/action tests**

```python
def test_android_stop_targets_requested_running_avd(client):
    response = client.post("/api/env/android/avd/stop", json={"avd": "Pixel_8"})
    assert response.status_code == 200
    assert run.call_args.args[0] == [ADB_BIN, "-s", "emulator-5554", "emu", "kill"]
```

Add tests mapping emulator serial to AVD using `adb -s SERIAL emu avd name`, rejecting non-configured AVDs, and disabling a second start with 409.

- [ ] **Step 2: Run Android action tests and confirm RED**

Run: `pytest -q tests/unit/env/test_device_runtime_status.py tests/dashboard/env/test_env_endpoints.py -k 'android and (target or identity or requested)'`

Expected: stop endpoint ignores the requested AVD and runtime detection cannot reliably identify the row.

- [ ] **Step 3: Implement Android row targeting and verify GREEN**

Use configured AVD identity as input, resolve the corresponding running serial, retain platform-specific capture guards, and update session state atomically.

- [ ] **Step 4: Write failing iOS UDID action tests**

```python
def test_ios_start_and_stop_use_udid(client):
    response = client.post("/api/env/ios/simulator/start", json={"udid": SIM_UDID})
    assert response.status_code == 202
    assert run.call_args.args[0] == ["xcrun", "simctl", "boot", SIM_UDID]
```

Cover shutdown by UDID, unknown UDID rejection, already booted state, and temporary name-based start compatibility.

- [ ] **Step 5: Run iOS action tests and confirm RED**

Run: `pytest -q tests/dashboard/env/test_env_endpoints.py tests/unit/env/test_device_runtime_status.py -k 'ios and udid'`

Expected: current start uses a device name and stop accepts no body.

- [ ] **Step 6: Implement iOS UDID actions and verify GREEN**

Run: `pytest -q tests/dashboard/env/test_env_endpoints.py tests/unit/env/test_device_runtime_status.py`

Expected: complete action/status suites pass.

### Task 4: Mockup-aligned Android and iOS UI

**Files:**
- Modify: `agents/dashboard/dashboard.html`
- Create: `tests/dashboard/env/test_virtual_device_settings_e2e.py`
- Modify: `tests/dashboard/test_env_phase3_html.py`

**Interfaces:**
- Consumes: status, discovery, registration, start, stop, refresh, and remove APIs
- Produces: platform-specific list rows and add modals matching reference images 06, 07, 10, and 11

- [ ] **Step 1: Write failing browser tests for Android list and modal**

```python
def test_android_add_modal_discovers_and_autofills(page):
    page.get_by_role("button", name="Android 에뮬레이터 추가").click()
    expect(page.get_by_label("시스템에 설치된 AVD")).to_have_value("Pixel_8_Android16")
    expect(page.get_by_label("기기명")).to_have_value("Pixel 8")
    expect(page.get_by_label("Android 버전")).to_have_value("16")
```

Also assert the dashed add row, default badge, row-specific button, removal control, Escape/focus behavior, duplicate 409 feedback, and request payload.

- [ ] **Step 2: Run Android browser tests and confirm RED**

Run: `pytest -q tests/dashboard/env/test_virtual_device_settings_e2e.py -k android`

Expected: role/label lookups fail because the generic modal and global buttons are still rendered.

- [ ] **Step 3: Implement Android list and dedicated modal**

Replace inline platform-global controls with semantic rows. Fetch discovery when opening the modal, populate read-only fields, register the selected AVD, refresh status after every successful action, and show structured errors in place.

- [ ] **Step 4: Write failing browser tests for iOS list and modal**

```python
def test_ios_add_modal_sends_selected_udid(page):
    page.get_by_role("button", name="iOS 시뮬레이터 추가").click()
    page.get_by_label("시뮬레이터 선택").select_option(SIM_UDID)
    page.get_by_role("button", name="등록").click()
    assert captured_json["udid"] == SIM_UDID
```

Assert device name, iOS version, UDID auto-fill, registered-option disabling, row-specific boot/shutdown, default badge, removal confirmation, and error recovery.

- [ ] **Step 5: Run iOS browser tests and confirm RED**

Run: `pytest -q tests/dashboard/env/test_virtual_device_settings_e2e.py -k ios`

Expected: current generic modal has no discovery dropdown or read-only UDID.

- [ ] **Step 6: Implement iOS list and dedicated modal**

Use UDID as option value and action identity. Keep Android/iOS real-device add controls functional through their existing branch.

- [ ] **Step 7: Add responsive and accessibility assertions**

At 320px viewport assert no body-level horizontal overflow, modal buttons remain visible, icon buttons have accessible names, Escape closes, and focus returns to the triggering add row.

- [ ] **Step 8: Verify UI and Phase 3 regression suites**

Run: `pytest -q tests/dashboard/env/test_virtual_device_settings_e2e.py tests/dashboard/env/test_env_phase3_e2e.py tests/dashboard/test_env_phase3_html.py`

Expected: all tests pass.

### Task 5: Appium polling and browser-action reliability

**Files:**
- Modify: `agents/dashboard/utils/system.py`
- Modify: `agents/dashboard/dashboard.html`
- Modify: `tests/unit/env/test_detect_appium_status.py`
- Modify: `tests/dashboard/env/test_appium_settings_e2e.py`

**Interfaces:**
- Produces: quiet Appium session-count fallback when `/sessions` is unsupported
- Produces: visible pending/success/error feedback for every Appium action

- [ ] **Step 1: Write failing unsupported-session-route test**

```python
def test_appium_sessions_404_is_cached_as_unsupported():
    first = detect_appium_status()
    second = detect_appium_status()
    assert first["active_sessions"] == 0
    assert sessions_request_count == 1
```

Run: `pytest -q tests/unit/env/test_detect_appium_status.py -k sessions`

Expected: repeated detection calls request the unsupported route repeatedly.

- [ ] **Step 2: Implement capability caching and verify GREEN**

Cache unsupported `/sessions` behavior per detected Appium server lifetime; reset it when the server disappears or PID/ownership changes.

- [ ] **Step 3: Write failing browser feedback tests**

Assert one click immediately disables the action, displays `시작 중`, handles 202/409/500 without silent failure, and returns to the real polled state.

Run: `pytest -q tests/dashboard/env/test_appium_settings_e2e.py -k 'action or start or restart'`

- [ ] **Step 4: Implement feedback and verify the Appium UI suite**

Run: `pytest -q tests/unit/env/test_detect_appium_status.py tests/dashboard/env/test_appium_settings_e2e.py`

Expected: all tests pass without repeated `/sessions` errors.

### Task 6: Documentation, screenshots, and full E2E verification

**Files:**
- Modify: `docs/ENV_SETUP_PRD.md`
- Modify: `docs/ENV_SETUP_USER_GUIDE.md`
- Update as verified: `docs/images/env-setup/*.png`
- Modify if needed: `README.md`

**Interfaces:**
- Consumes: verified implementation and captured browser screens
- Produces: consistent v0.8 product documentation and reproducible operator steps

- [ ] **Step 1: Run focused non-browser suites**

Run: `pytest -q tests/unit/env tests/dashboard/env/test_env_endpoints.py`

Expected: all tests pass.

- [ ] **Step 2: Run all environment browser suites**

Run: `pytest -q tests/dashboard/env tests/dashboard/test_env_phase3_html.py`

Expected: all tests pass.

- [ ] **Step 3: Start the dashboard independently and run real-tool smoke checks**

Launch the dashboard on `127.0.0.1:8767` with output in `logs/dashboard.log`. In a clean browser, verify Appium start/status/stop or external ownership, Android AVD discovery/start/stop, and iOS simulator discovery/boot/shutdown using the installed tools. Restore the user's preferred final runtime state and do not terminate externally owned processes.

- [ ] **Step 4: Capture visual evidence**

Capture overview, Appium stopped/running/error, Android list/add, iOS list/add, and action-error states. Compare component hierarchy, copy, colors, spacing, and button states against `docs/images/env-setup/01-13`; fix material mismatches and rerun affected E2E tests.

- [ ] **Step 5: Update PRD and user guide**

Set artifact correspondence to v0.8, remove stale “UI/API not implemented” notes, document the actual discovery and UDID contracts, and ensure every manual instruction names a control that exists in the verified UI.

- [ ] **Step 6: Run documentation consistency checks**

Run: `rg -n "v0\.7|미구현|구현되지|deviceName.*boot|UDID.*미저장" docs/ENV_SETUP_PRD.md docs/ENV_SETUP_USER_GUIDE.md`

Expected: no obsolete statement remains; any remaining limitation is explicitly scoped to Phase 3 or future work.

- [ ] **Step 7: Run the complete non-generated regression suite**

Run: `pytest -q --ignore=tests/generated`

Expected: all tests pass.

- [ ] **Step 8: Confirm live browser readiness**

Verify `GET http://127.0.0.1:8767/api/env/status` returns 200, reload the dashboard in a new browser context, and repeat one safe refresh plus one reversible simulator action. Record final dashboard/Appium ownership and PID state in the handoff.
