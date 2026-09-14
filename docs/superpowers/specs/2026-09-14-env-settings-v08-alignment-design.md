# Environment Settings v0.8 Alignment Design

**Date:** 2026-09-14

**Status:** Approved in chat; pending written-spec review

## Goal

Make Environment Settings match the v0.8 design specification and interactive mockup while ensuring every visible control works against the locally installed Appium, Android emulator, and iOS simulator tools.

## Sources of Truth

When the artifacts disagree, use this order:

1. The latest design specification (`55ba3c71-e480-4493-b60a-d0a2aad70fb1`) controls layout, component styling, labels, spacing, and visible states.
2. The latest interactive mockup (`466103b7-6be2-4811-b34e-f0c088462334`) controls click flow, modal behavior, row actions, and state transitions.
3. `docs/ENV_SETUP_PRD.md` controls runtime safety, persistence, API errors, command execution, and capture/pipeline guards.
4. Existing dashboard conventions control only details not specified by the three sources above.

The local reference images in `docs/images/env-setup/` are the reproducible visual baseline because automated access to the Claude artifact pages is blocked by authentication/robots restrictions.

## Scope

This change covers the complete Environment Settings user journey:

- Appium detection, start, restart, refresh, log access, and stop.
- Android AVD discovery, registration, listing, start, stop, refresh, and removal.
- iOS simulator discovery, registration, listing, boot, shutdown, refresh, and removal.
- Driver detection for UiAutomator2 and XCUITest.
- Persistent dashboard process behavior needed for browser actions to remain usable.
- API, unit, browser E2E, real-tool smoke, and visual regression verification.
- PRD and user-manual corrections after implementation.

Physical-device Phase 3 controls remain present and must not regress, but redesigning those flows is outside this alignment unless a shared component change requires it.

## UI Architecture

Keep the existing dashboard shell and replace the current generic environment cards and generic add modal with mockup-specific components.

### Appium

The Appium card renders one of five explicit states: `stopped`, `starting`, `managed`, `external`, or `error`. Buttons and status text follow the mockup state table. Managed Appium can be restarted or stopped; external Appium cannot be killed and instead offers state refresh. Errors remain visible until retry or dismissal.

### Android AVD list

Render one row per configured `android.emulator[]` entry. Each row shows:

- status indicator;
- display name and Android version;
- AVD identifier;
- default badge when applicable;
- row-specific start or stop button;
- remove button.

Only the active/booting AVD is shown as running. When one AVD is starting or running, start buttons for other AVDs are disabled. A full-width dashed add row opens the Android-specific modal.

### Android add modal

Opening the modal fetches locally installed AVDs. The user selects an AVD from a dropdown; `deviceName` and `platformVersion` are read-only and auto-filled from discovered metadata. The modal provides close, cancel, and register actions. Empty discovery, discovery errors, duplicates, and successful registration each have visible feedback.

### iOS simulator list

Render one row per configured `ios.simulator[]` entry. Each row shows status, device name, iOS version, abbreviated UDID, default badge, row-specific boot/shutdown, and remove. A full-width dashed add row opens the iOS-specific modal.

### iOS add modal

Opening the modal fetches available local simulators. Selection auto-fills read-only `deviceName`, `platformVersion`, and `udid`. Registration sends all three identifiers. Already registered simulators are disabled or clearly marked in the dropdown.

### Accessibility and responsive behavior

All icon-only controls receive Korean accessible labels. Modal focus moves inside on open, Escape closes it, and focus returns to the trigger. Disabled controls expose their reason in nearby text. Cards stack on narrow screens without horizontal scrolling; modal contents remain usable at 320 CSS pixels.

## Backend Interfaces

### Discovery

`GET /api/env/android/list_system_avds` returns installed AVD metadata for the add modal. `GET /api/env/android/avds` remains the configured/runtime list endpoint:

```json
{
  "ok": true,
  "avds": [
    {
      "avd": "Pixel_8_Android16",
      "deviceName": "Pixel 8",
      "platformVersion": "16"
    }
  ]
}
```

Discovery uses the resolved emulator binary and AVD configuration files. It never interpolates user text into a shell command.

`GET /api/env/ios/list_system_simulators` returns available simulators from `xcrun simctl` JSON for the add modal. `GET /api/env/ios/simulators` remains the configured/runtime list endpoint:

```json
{
  "ok": true,
  "simulators": [
    {
      "deviceName": "iPhone 16 Plus",
      "platformVersion": "26.5",
      "udid": "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
      "state": "Shutdown"
    }
  ]
}
```

Only available runtimes and devices are returned.

### Registration

`POST /api/env/android/add` requires `avd`, `deviceName`, and `platformVersion`. It rejects duplicate AVD keys with HTTP 409 and writes the PRD-defined defaults, including UiAutomator2, `noReset`, launch/termination flags, and MJPEG port/scaling/quality. The first AVD becomes default automatically.

`POST /api/env/ios/add` in simulator mode requires `deviceName`, `platformVersion`, and a valid UDID. Duplicate UDID is the primary conflict key; duplicate device name is also rejected when it would make existing name-based consumers ambiguous. The first simulator becomes default automatically.

Writes to `config/devices.json` remain atomic and preserve unrelated sections and user-defined values.

### Row actions

- `POST /api/env/android/avd/start` accepts `{ "avd": "..." }`.
- `POST /api/env/android/avd/stop` accepts the configured AVD identity and terminates only the resolved running emulator.
- `POST /api/env/ios/simulator/start` accepts `{ "udid": "..." }`.
- `POST /api/env/ios/simulator/stop` accepts `{ "udid": "..." }`.

Name-based iOS start input remains temporarily backward compatible, but the dashboard uses UDID exclusively. Status responses include enough identity to match the running process to one configured row.

## Runtime and State Rules

- Appium, Android, and iOS actions run as argument arrays with `shell=False`.
- Executable discovery supports interactive-shell and GUI-launched dashboard environments.
- UI enters `starting`/`booting` immediately and polls until ready, timeout, or failure.
- Refresh reconciles stale PIDs and stored state against real processes.
- One Android emulator and one iOS simulator are controllable at a time for this MVP.
- Platform-specific capture guards block only destructive actions affecting that platform; Appium stop is blocked by any active capture.
- External Appium is never terminated by the dashboard.
- Dashboard launch must survive the terminal/tool session that initiated it; stale server state must not make buttons appear successful when the web server is gone.
- Appium versions without `GET /sessions` support do not produce repeated poll errors; unsupported capability is detected once and handled quietly.

## Errors and User Feedback

Every action returns structured JSON with `ok`, a stable error code, and a Korean user-facing message. The UI keeps the current card or modal visible and shows recovery guidance.

Required cases include:

- command or SDK tool not found;
- no installed AVDs or simulators;
- invalid AVD/UDID;
- duplicate registration (409);
- another device already starting/running (409);
- capture or pipeline conflict (403/409/423 according to PRD);
- boot/start timeout;
- stale PID or externally owned Appium;
- atomic configuration write failure.

## Verification Strategy

Implementation follows test-driven development.

1. Unit tests cover executable discovery, AVD metadata parsing, simctl JSON parsing, validation, defaults, duplicate detection, and state reconciliation.
2. API tests cover every discovery, add, remove, start, stop, timeout, and conflict response.
3. Browser E2E tests cover the full user flow from Environment Settings through automatic discovery, registration, row-specific actions, refresh, removal, modal keyboard behavior, and visible error recovery.
4. Real-tool smoke tests run against the installed Appium drivers, Android emulator, and iOS simulator on this Mac when available.
5. Screenshots are captured for the overview, stopped/running/error cards, Android list/add modal, and iOS list/add modal and compared manually with `docs/images/env-setup/01-13`.
6. The complete non-generated regression suite runs after focused tests.

## Documentation

After behavior is verified:

- Update `docs/ENV_SETUP_PRD.md` to v0.8, remove obsolete “not implemented” corrections, and make endpoint/schema descriptions match the shipped code.
- Update `docs/ENV_SETUP_USER_GUIDE.md` only where verified UI or behavior changed.
- Replace or add screenshots when the final implementation is materially different from existing reference captures.
- Record real-device-only limitations explicitly instead of presenting them as implemented.

## Non-goals

- Creating or deleting AVDs in Android Studio.
- Creating or deleting simulators in Xcode.
- Supporting multiple simultaneously controlled emulators per platform.
- Reworking Capture Studio or pipeline UI beyond environment readiness integration.
- Terminating externally owned Appium processes.
