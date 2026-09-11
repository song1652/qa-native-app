# Design

## Source of truth

Status: Active. Updated: 2026-09-07. Surfaces: dashboard, Capture Studio, pipeline, quick run, Import Studio, reports, history, Appium settings. Evidence: current dashboard implementation, native-fixed Import Studio, approved Import Studio screenshot, two reference captures of a semi-manual device inspector workflow, and the approved element-first mockup. Product requirements are defined in `docs/PRD.md`; screen behavior is defined in `docs/CAPTURE_STUDIO_PLAN.md`.

## Brand

Dark QA control-center interface: precise, operational, and calm. Trust comes from explicit status, execution evidence, and reversible actions. Avoid decorative UI that competes with test state.

## Product goals

Make Appium test discovery, generation, execution, healing, import, and reporting understandable in one workspace. Capture Studio must let a QA engineer select actual Native/WebView elements and perform a path once, then reuse the recorded element evidence for Step generation, deterministic code generation, and healing. Preserve existing Python dashboard commands and APIs. Do not conceal failures or imply unsupported automation.

## Personas and jobs

Primary user: a QA engineer preparing and running Android/iOS test cases. Core jobs: import TC data, connect a device, select an element from the mirrored screen, inspect its Native/WebView structure, record actions, confirm locators, add expected results, generate code, run tests, inspect evidence, and respond to failures. The user should not need to operate Appium Inspector repeatedly after a flow has been approved.

## Information architecture

Persistent top status bar and left navigation. Each menu opens one focused work surface. Capture Studio sits between Import Studio and pipeline execution and follows six steps: session setup, element inspection, action capture, locator review, TC preview, save and generate. Within the capture workspace, visual priority is device and selected element first, hierarchy/DOM second, Action Timeline third, and Step/expected-result editing after the evidence is recorded. Import Studio follows five steps: file selection, column/sheet mapping, preview, safe application, completion.

## Design principles

Show the current scope before actions; keep platform and context synchronized; expose progress and disabled states; retain native-fixed interaction patterns where workflows match. Selection starts from the mirrored app element, not from manual TC prose. Treat captured hierarchy, DOM, context, screenshot, selected element, and action logs as evidence. Generate Step drafts from evidence and require user confirmation for ambiguous locators instead of silently guessing.

## Visual language

Use the existing dark purple dashboard tokens. Import Studio uses `#0B0B14` background, `#1A1A2E` cards, `#8B5CF6` accent, compact 6–10px radii, 12–20px typography, and restrained borders instead of heavy shadows.

## Components

Shared shell: top status bar and sidebar. Capture Studio components: connection bar, live device viewport, element highlight overlay, Native/WebView context switcher, hierarchy/DOM tree, element detail panel, record controls, action timeline, locator candidate table, confidence badge, Step/expected-result editor, Markdown preview, generated-code preview, and save/generate action bar. Locator and structure panels support the element workflow but must not visually dominate the device and Action Timeline. Quick-run results use collapsible folder summaries; each expanded folder exposes All/Pass/Fail filters and test-level details without mixing folders. Import components: wizard header, expandable file card with sheet checkboxes, three-column mapping workspace (selected source, common mapping, validation result), platform selector, preview summary, safe-apply policy cards, commit summary, completion result, bottom action bar. Safe apply exposes only the supported `skip-conflict` and `overwrite` policies.

## Accessibility

Controls use native buttons/inputs, visible disabled states, text labels, keyboard focus, and status text that does not rely on color alone. Maintain readable contrast and 13px minimum control text.

## Responsive behavior

Desktop-first dashboard. Wizard lines and cards may wrap at narrower widths; bottom actions remain visible and content scrolls independently.

## Interaction states

Support device disconnected, Appium unavailable, session starting, Native context, WebView detected, WebView unavailable, recording, paused, ambiguous locator, stale snapshot, validation error, save in progress, generation success, and generation failure. Existing import states remain: loading, empty import folder, selected file, unavailable sheet, validation error, conversion in progress, success, and conversion failure.

## Content voice

Use short operational Korean labels. State what will happen: “다음: 열 매핑”, “안전한 반영”, “반영 시작”, and “원본 파일은 변경되지 않습니다.”

## Implementation constraints

Vanilla HTML/CSS/JavaScript served by `agents/dashboard/serve.py`. Capture Studio extends the existing Appium session and `hybrid_runtime.py`; it must not create a second competing driver for the same device. Captures persist under a dedicated session directory and update `config/screens.json` and `config/locators.json` only after review. It generates one Markdown file per TC and then invokes the existing strict generator. Reuse `/api/import/files`, `/api/import/sheets`, and `/api/import/convert`. Import conversion must apply the selected column mapping and split output into `testcases/android/{sheet}` and `testcases/ios/{sheet}`. Generated code mirrors the group below the platform root into `tests/generated/{platform}/{sheet}`. Validate JavaScript syntax, Python tests, API path safety, and the live localhost surface.

## Open questions

- [ ] Whether reusable mapping profiles and per-sheet override mappings should be added; owner: product; impact: repeated imports with heterogeneous Excel formats.
- [ ] Whether multi-file/multi-sheet conversion should be transactional; owner: backend; impact: Step 4 rollback semantics.
- [ ] Whether Capture Studio should support remote physical-device farms in its first release; owner: product; impact: session transport and authentication.
- [ ] Whether iOS WebView DOM capture should be Appium-context-only or optionally integrate Safari Web Inspector; owner: architecture; impact: parity with Android CDP capture.
