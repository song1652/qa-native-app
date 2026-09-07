# Design

## Source of truth

Status: Active. Updated: 2026-09-07. Surfaces: dashboard, pipeline, quick run, Import Studio, reports, history, Appium settings. Evidence: current dashboard implementation, native-fixed Import Studio, and approved Import Studio screenshot.

## Brand

Dark QA control-center interface: precise, operational, and calm. Trust comes from explicit status, execution evidence, and reversible actions. Avoid decorative UI that competes with test state.

## Product goals

Make Appium test generation, execution, healing, import, and reporting understandable in one workspace. Preserve existing Python dashboard commands and APIs. Do not conceal failures or imply unsupported automation.

## Personas and jobs

Primary user: a QA engineer preparing and running Android/iOS test cases. Core jobs: import TC data, select platform and scope, run tests, inspect evidence, and respond to failures.

## Information architecture

Persistent top status bar and left navigation. Each menu opens one focused work surface. Import Studio follows five steps: file selection, column/sheet mapping, preview, safe application, completion.

## Design principles

Show the current scope before actions; keep platform context synchronized; expose progress and disabled states; retain native-fixed interaction patterns where workflows match.

## Visual language

Use the existing dark purple dashboard tokens. Import Studio uses `#0B0B14` background, `#1A1A2E` cards, `#8B5CF6` accent, compact 6–10px radii, 12–20px typography, and restrained borders instead of heavy shadows.

## Components

Shared shell: top status bar and sidebar. Import components: wizard header, expandable file card with sheet checkboxes, three-column mapping workspace (selected source, common mapping, validation result), platform selector, preview summary, safe-apply policy cards, commit summary, completion result, bottom action bar. Safe apply exposes only the supported `skip-conflict` and `overwrite` policies.

## Accessibility

Controls use native buttons/inputs, visible disabled states, text labels, keyboard focus, and status text that does not rely on color alone. Maintain readable contrast and 13px minimum control text.

## Responsive behavior

Desktop-first dashboard. Wizard lines and cards may wrap at narrower widths; bottom actions remain visible and content scrolls independently.

## Interaction states

Support loading, empty import folder, selected file, unavailable sheet, validation error, conversion in progress, success, and conversion failure states.

## Content voice

Use short operational Korean labels. State what will happen: “다음: 열 매핑”, “안전한 반영”, “반영 시작”, and “원본 파일은 변경되지 않습니다.”

## Implementation constraints

Vanilla HTML/CSS/JavaScript served by `agents/dashboard/serve.py`. Reuse `/api/import/files`, `/api/import/sheets`, and `/api/import/convert`. Import conversion must apply the selected column mapping and split output into `testcases/android/{sheet}` and `testcases/ios/{sheet}`. Generated code mirrors the group below the platform root into `tests/generated/{platform}/{sheet}`. Validate JavaScript syntax, Python tests, and the live localhost surface.

## Open questions

- [ ] Whether reusable mapping profiles and per-sheet override mappings should be added; owner: product; impact: repeated imports with heterogeneous Excel formats.
- [ ] Whether multi-file/multi-sheet conversion should be transactional; owner: backend; impact: Step 4 rollback semantics.
