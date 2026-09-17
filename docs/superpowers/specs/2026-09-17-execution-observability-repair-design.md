# Execution Observability Repair Design

## Goal

Make Android and iOS execution observability reliable end to end: every generated test attempt is classified correctly, playable video and bounded system logs are retained according to policy, healing stays in one run, APIs and the dashboard expose the same attempt model, and unrelated pytest runs produce no observability state.

## Scope

This repair covers `tests/conftest.py`, the observability collector, dashboard pipeline process launching, observability APIs, the dashboard evidence panel, the observability PRD, and focused automated tests. It preserves unrelated Capture Studio, ENV Setup, import, locator, and generated-test behavior.

The final acceptance run uses `tests/generated/android/obs_demo/` against the connected Android emulator and running Appium server. If either external dependency is unavailable, automated verification still runs and the exact E2E blocker is reported instead of being treated as a product success.

## Canonical attempt model

The canonical storage layout is:

```text
state/runs/{run_id}/artifacts/
  manifest.json
  {node_slug}/
    attempt1/
      video.mp4
      syslog.txt
      meta.json
    attempt2/
      video.mp4
      syslog.txt
      meta.json
```

Each manifest test entry contains stable test identity plus an `attempts` array. Every attempt contains its own outcome, timestamps, duration, retention state, artifact metadata, screenshot pointer, failure offset, and collection errors. The entry also exposes final-attempt summary fields for compatibility with existing dashboard code while the API is migrated.

Existing flat manifests remain readable. The API normalizes a legacy entry into one synthetic attempt without rewriting historical data.

## Pytest lifecycle and outcome handling

`pytest_sessionstart` must not touch the filesystem or probe a device. Collection or the first observable test lazily initializes the run only when at least one node under `tests/generated/` executes.

Collection outside `tests/generated/`, including `tests/unit/` and `tests/dashboard/`, creates no `state/runs` directory and starts no collector process.

For every observable attempt:

1. Setup starts collection unless observability is disabled or the keep policy is `never`.
2. `pytest_runtest_makereport` records failures from setup, call, and teardown, with setup or teardown errors classified as `error`.
3. Teardown stops collection exactly once and writes the attempt.
4. A missing call report never downgrades a setup failure to `unknown`.
5. Collector exceptions are converted to catalogued `collect_errors` and never alter the pytest result.

## Collector configuration

One normalized configuration object controls enabled state, keep policy defaults, video codec/bitrate/time limit, log options, retention, and file limits. Environment variables override file defaults where the PRD defines them.

`QA_OBS_DISABLE` and `enabled: false` prevent all initialization. `QA_OBS_KEEP=never` also prevents collector processes and artifact creation for test attempts.

The iOS log predicate reads `config/test_data.json` at `app.ios.bundle_id`. An empty bundle ID disables iOS log collection with a specific error instead of constructing a predicate that matches every process.

## Android video lifecycle

Android recording is managed as a device-side process, not by assuming that terminating the local `adb` client finalizes the remote encoder.

- Start `screenrecord` on the selected UDID and retain its remote PID.
- At teardown, signal that exact remote PID and poll until it exits or a bounded timeout expires.
- Wait for the remote file size to stabilize, then pull only when retention policy requires it.
- Remove the remote file in every exit path.
- Validate the downloaded MP4 before registering it: it must contain a `moov` box and report a positive movie duration. Invalid files are deleted and recorded as `video_invalid`.
- Mark recordings that reach the configured time limit as truncated.

The implementation remains safe when `screenrecord` is unsupported, the device disconnects, the process exits early, or an attempt is shorter than recorder startup.

## iOS collection

iOS simulator video targets an explicit UDID, stops with SIGINT, waits for encoder completion, and applies the same local MP4 validation before registration. Simulator log streaming uses the configured level and resolved non-empty bundle predicate. iOS real devices remain explicitly unsupported in M1.

## Pipeline environment and run identity

Dashboard routes never mutate process-global `os.environ` for a run. Every child receives an explicit environment mapping containing `QA_RUN_ID`, `QA_PLATFORM`, `QA_OBS_KEEP`, `DEVICE_MODE`, and `DEVICE_UDID` as applicable.

One logical execution gets one run ID. Initial execution and all healing reruns reuse it, allowing attempt arrays to append to the same manifest. Separate selected folders remain separate logical executions unless the existing pipeline treats them as one run; the implementation follows the current route's user-visible execution boundary.

All `/api/run`, `/api/run_all`, and `/api/run_test` execute paths pass the selected mode and UDID to `05_execute.py`.

## API contract

The canonical listing endpoint is `GET /api/runs?platform=&limit=20`. `GET /api/run_artifacts` remains as a compatibility alias.

Artifact detail returns normalized entries with `attempts[]`. Video and log endpoints accept optional `attempt`; omission selects the latest attempt. Paths are resolved only from validated manifest metadata beneath the artifact root.

Active manifests cannot be manually deleted. Deletion reports failure if the directory remains. Run summaries include total, failed, with-video, with-syslog, and byte size.

## Dashboard behavior

The evidence panel renders the normalized attempt list and allows attempt switching. Each tab uses URLs returned by the API. Missing evidence displays a Korean explanation derived from the collection error catalog, including unsupported recorder, failed pull, invalid video, missing device, unsupported iOS real device, and disabled log predicate.

Log presets include `FATAL`, `AndroidRuntime`, the configured app package, and `E/`. The video seeks to the selected attempt's failure offset after metadata loads.

Livetail completion summaries use the completed manifest and include failure count, video count, syslog count, and size. HTML reports include the run ID and dashboard artifact link without embedding media.

## Retention and compatibility

Retention applies at new logical-run creation and protects active runs. It enforces both maximum run count and total byte limit. Existing flat runs count toward both constraints.

The collector and API accept legacy flat entries during migration. New writes use only the canonical attempt schema.

## Testing strategy

Development follows red-green-refactor cycles. Focused tests cover:

- setup errors retained as `error`;
- non-generated pytest sessions producing no run directory;
- `never` and disabled policies starting no processes;
- Android remote PID stop, stable pull, invalid MP4 rejection, and cleanup;
- iOS bundle predicate resolution and empty-bundle handling;
- multiple attempts appended under one run;
- healing reusing one run ID;
- child-specific environment mappings with no global leakage;
- selected device propagation through all execute routes;
- `/api/runs`, attempt selection, legacy manifest normalization, active-delete protection, and traversal guards;
- dashboard attempt switching and error/preset rendering;
- real route tests instead of a test-only probe endpoint.

Verification finishes with compilation, focused observability tests, unaffected unit/dashboard tests available in the environment, and `git diff --check`. The final external E2E runs:

```bash
python3 scripts/05_execute.py \
  --platform android \
  --mode emulator \
  --tc-dir obs_demo
```

Acceptance requires a completed manifest, correct per-attempt outcomes, no leftover remote recording or logcat processes, playable positive-duration retained videos, readable logs, and API retrieval of those artifacts.

## Non-goals

This work does not add network capture, iOS real-device recording, ffmpeg as a required dependency, parallel execution architecture, or unrelated dashboard redesign.
