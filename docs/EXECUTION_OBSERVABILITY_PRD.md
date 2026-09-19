# TC 실행 관측성 (Execution Observability) — PRD

| 항목 | 값 |
|---|---|
| 문서 버전 | v0.14 |
| 작성일 | 2026-09-17 |
| 상태 | M1 구현 및 Android·iOS E2E 검증 완료 |
| UI 목업 | [TC 실행 증거 패널 v0.3](https://claude.ai/artifact/E4JEz3FyB5cFZV9ad8oLrV) — §8 프론트엔드 3개 상태(실행 결과 · 증거 상세 · 수집 설정). 상단 `스펙 주석` 체크박스로 각 UI 요소의 PRD 근거 조항 표시 |
| 관련 문서 | [PARALLEL_EXECUTION_PRD.md](PARALLEL_EXECUTION_PRD.md) §6-2·§6-3, [ENV_SETUP_PRD.md](ENV_SETUP_PRD.md), [LOCATOR_HEALING.md](LOCATOR_HEALING.md) |
| 선행 조건 | 없음 — 병렬 실행 PRD와 **독립적으로 착수 가능** (§9-3에서 상호 관계 정의) |
| 변경 이력 | §15 |

---

## 1. 배경 및 목적

### 1-1. 현재 상태

TC 1건이 실패했을 때 저장소에 남는 것은 셋뿐입니다.

| 산출물 | 경로 | 생성 지점 | 범위 |
|---|---|---|---|
| 실패 스크린샷 PNG | `reports/screenshots/{platform}/{safe_nodeid}.png` | `tests/conftest.py:45` `pytest_runtest_makereport` | 실패 **순간 1프레임** |
| pytest 리포트 | `state/pytest_report.{xml,json}` | `05_execute.py`의 pytest 인자 | 스택트레이스 텍스트 |
| 실행 로그 | `logs/run_test_{platform}_{target}.txt` | `pipeline.py`의 `Popen(stdout=log_file)` | pytest stdout |

영상은 **부분적으로만** 존재합니다.

- `05_execute.py --record` — run 전체를 `adb screenrecord`로 1개 mp4에 담아 `tests/reports/recordings/test_run_{ts}.mp4`에 저장 (`05_execute.py:68-95`). 대시보드는 이 플래그를 쓰지 않습니다.
- 과거 `pipeline.py:_record_video()` — healing 최종 실패에서 TC별 수집과 동시에 두 번째 인코더를 실행해 충돌하므로 제거했습니다. 최종 healing도 동일 run의 TC별 attempt 증거를 사용합니다.

두 경로의 저장 디렉토리가 다르고(`tests/reports/recordings` vs `reports/recordings`), 어느 쪽도 **TC 단위로 구간이 나뉘지 않습니다.** 20건짜리 폴더를 돌리면 8분짜리 mp4 한 개가 나오고, 실패한 3번째 TC 구간을 찾으려면 사람이 스크럽해야 합니다.

시스템 로그(`adb logcat`, `log stream`)와 앱의 HTTP 통신은 **전혀 수집되지 않습니다.**

### 1-2. 문제

TC가 빨갛게 뜬 순간, QA가 답해야 하는 질문은 하나입니다 — **"이거 앱 버그야, 서버 버그야, 아니면 우리 테스트/기기 문제야?"**

현재 증거로는 이 셋을 구분할 수 없습니다.

| 실제 원인 | 현재 증거로 보이는 모습 | 구분에 필요한 증거 |
|---|---|---|
| 앱 크래시 | `NoSuchElementException` + 홈 화면 스크린샷 | logcat `FATAL EXCEPTION` 스택 |
| API 5xx / 타임아웃 | `NoSuchElementException` + 빈 목록 스크린샷 | HTTP 응답 코드·바디 |
| 앱의 정상적 에러 UI | `NoSuchElementException` + 에러 다이얼로그 | 다이얼로그 문구 (스크린샷으로 일부 가능) |
| locator 변경 | `NoSuchElementException` + 정상 화면 | 화면 hierarchy (06_heal이 이미 수집) |
| 기기 환경 (네트워크 끊김, 권한 팝업) | `NoSuchElementException` + 시스템 팝업 | 영상 — 팝업이 뜬 **시점**이 보여야 함 |
| 타이밍 flake | 재실행하면 통과 | 영상 — 어디서 얼마나 느렸는지 |

스크린샷 1장은 위 6개 중 2개만 부분적으로 가릅니다. 나머지는 QA가 기기를 직접 붙잡고 재현하거나 `adb logcat`을 수동으로 띄워 다시 돌려야 하고, 재현이 안 되는 flake는 거기서 조사가 끝납니다.

### 1-3. 목적

**TC 1건이 실패했을 때, 대시보드에서 그 TC의 실행 구간 영상과 시스템 로그를 즉시 열어 원인을 분류할 수 있게 한다.**

기대 효과:
- 실패 1건 분류에 드는 시간: 재현 실행(수 분) → 대시보드 조회(수 초)
- 재현이 안 되는 flake도 사후 조사 가능 — 영상·로그가 그 회차에 남아 있음
- Jira Bug 자동 생성 시 첨부 증거의 질 향상 (`jira_reporter.py`가 이미 스크린샷/영상을 첨부하는 경로를 가짐)

### 1-4. 비목적 (이 기능이 해결하지 않는 것)

- **실패 원인 자동 판정** — 수집된 증거로 "앱 버그다"라고 결론 내리는 분류기는 만들지 않습니다. 증거를 사람 앞에 놓는 데까지가 범위입니다. (외부 LLM SDK import 금지 — CLAUDE.md 절대 규칙)
- **성능 프로파일링** — CPU/메모리/FPS 계측은 다루지 않습니다.
- **테스트 코드 생성·healing 로직 변경** — `02_generate.py`, `06_heal.py`는 건드리지 않습니다.
- **기존 스크린샷 경로 이관** — ~~`reports/screenshots/`는 `report_html.py`와 `/screenshots/` 서빙이 의존하므로 M1에서 옮기지 않습니다~~ **(v0.13에서 철회)** `tests/conftest.py`의 legacy 실패 스크린샷 훅과 `state/screenshots.json`을 완전히 제거했습니다. `report_html.py`는 이제 관측성 manifest의 `screenshot_url`만 사용합니다 (§3-4, §8-3).
- **CI/CD 아티팩트 업로드** — 로컬 파일시스템 + 대시보드 조회까지입니다.

---

## 2. 범위

### 2-1. M1 — 영상 + 시스템 로그 _(이번 구현)_

| 항목 | Android | iOS 시뮬레이터 | iOS 실기기 | Android 실기기 |
|---|---|---|---|---|
| TC 구간 영상 | ✅ `adb screenrecord` | ✅ `simctl io recordVideo` | ❌ 범위 밖 (§6-3) | ✅ `adb screenrecord` (동일 경로) |
| 시스템 로그 | ✅ `adb logcat` | ✅ `simctl spawn log stream` | ❌ 범위 밖 | ✅ `adb logcat` (동일 경로) |
| 네트워크 | ❌ M2 | ❌ M2 | ❌ M2 | ❌ M2 |

### 2-2. M2 — 네트워크 트래픽 캡처 _(다음 마일스톤)_

mitmproxy 연동. **M1과 분리하는 이유** — 성격이 다른 의존성이 붙습니다.

| # | 사유 | M1과의 차이 |
|---|---|---|
| 1 | **앱 빌드 협조 필요** | Android 7(API 24)부터 앱은 user CA를 신뢰하지 않습니다. mitmproxy 인증서를 앱이 받아들이려면 DirectCloud 앱에 `network_security_config.xml`의 `debug-overrides`가 들어간 **디버그 빌드**가 필요합니다. 이건 우리 저장소 밖의 의존성입니다. M1은 릴리스 빌드 그대로 동작합니다. |
| 2 | **certificate pinning 미검증** | 앱이 pinning을 쓰면 mitmproxy로는 복호화가 불가능하고, 우회하려면 Frida 같은 계측 도구가 추가로 들어옵니다. 착수 전 스파이크로 확인해야 하는 사항입니다. |
| 3 | **디바이스 전역 설정** | 프록시는 기기 단위 설정(`adb shell settings put global http_proxy`)이라 병렬 실행 시 기기별 프록시 포트를 따로 띄워야 합니다. 병렬 실행 PRD와 설계가 얽힙니다. M1의 영상·로그는 기기별 프로세스가 독립이라 얽히지 않습니다. |
| 4 | **신규 런타임 의존성** | `mitmproxy` 패키지 + 별도 프로세스 수명 관리. M1은 이미 쓰고 있는 `adb`/`xcrun`만 씁니다. |

**M1이 네트워크 문제를 부분적으로 커버하는 지점**: 앱이 OkHttp logging interceptor나 `NSURLSession` 로깅을 켠 빌드라면 요청/응답 요약이 logcat / log stream에 이미 흘러갑니다. M1의 시스템 로그 수집이 이걸 그대로 잡습니다. M2는 "그 로깅이 없거나, 바디까지 봐야 할 때" 필요한 것입니다.

### 2-3. 두 실행 탭에 대한 적용 범위

수집은 **pytest 훅 안에서** 일어납니다. 두 탭 모두 최종적으로 `05_execute.py → pytest subprocess`로 수렴하므로 **양쪽 탭에 자동으로 적용됩니다.**

| 탭 | 엔드포인트 | M1 적용 | run_id 발급 주체 |
|---|---|---|---|
| 파이프라인 실행 | `POST /api/run_all` | ✅ `execute` 단계에서만 수집. analyze/generate/lint는 기기 조작이 없어 수집 대상 아님 | `pipeline.py`가 run 시작 시 1회 발급, healing 재실행까지 **같은 run_id 유지** |
| 빠른 실행 | `POST /api/run_test` | ✅ | `pipeline.py`가 발급, heal 후 재실행까지 같은 run_id |
| 단건 실행 | `POST /api/run` (`step=execute`) | ✅ | `pipeline.py`가 발급 |
| CLI 직접 | `python scripts/05_execute.py ...` | ✅ | `05_execute.py`가 자동 발급 (§4-1) |

파이프라인 탭에서 healing 3회차까지 돌면 `execute`가 최대 4번 실행됩니다. 이 4회가 **하나의 run_id 아래 4개 attempt**로 쌓입니다 — 회차별로 무엇이 달라졌는지 비교하는 것이 healing 디버깅의 핵심이기 때문입니다.

### 2-4. 제외 — 근거 포함

| 제외 항목 | 근거 |
|---|---|
| iOS 실기기 영상·로그 | Phase 3(실기기) 미도달. `xcrun devicectl`은 화면 녹화를 제공하지 않고, WDA 기반 `mobile: startXCTestScreenRecording`은 Xcode·WDA 버전 조합 검증이 필요한데 검증 기기가 없습니다. 수집 시도 자체를 하지 않고 manifest에 `"reason": "ios_real_device_unsupported"`를 기록합니다. |
| 오디오 녹음 | `adb screenrecord`·`simctl recordVideo` 모두 미지원. 대상 앱이 오디오 앱이 아닙니다. |
| Appium 서버 로그 수집 | Appium 서버는 대시보드가 `logs/appium_server.log`에 이미 남기고 있으며 run 단위가 아닌 서버 단위 수명을 가집니다. run별 슬라이싱은 M2 이후 검토. |
| 영상 자동 트림/썸네일 | ffmpeg 의존성 추가. 브라우저 `<video>` 태그가 seek을 처리하므로 M1에는 불필요. |
| 실시간 영상 스트리밍(실행 중 관전) | Capture Studio의 MJPEG 미러링이 이미 담당하는 영역입니다. 이 PRD는 **사후 재생**만 다룹니다. |

---

## 3. 저장 경로 설계

### 3-1. 아티팩트 루트 — `QA_ARTIFACT_DIR` _(확정)_

병렬 실행 PRD는 `QA_RUN_DIR`로 **상태 JSON**(`pipeline.json`, `pytest_report.*`, `screenshots.json`)을 격리합니다. 관측 아티팩트는 별도 변수 `QA_ARTIFACT_DIR`을 쓰되, **기본값이 `QA_RUN_DIR` 하위를 가리키게** 해서 병렬 실행 시 자동으로 함께 격리되도록 합니다.

해석 순서 (앞에서 정해지면 뒤는 보지 않음):

```
1. QA_ARTIFACT_DIR 이 설정돼 있으면            → 그 경로
2. QA_RUN_DIR 이 설정돼 있으면                 → {QA_RUN_DIR}/artifacts
3. QA_RUN_ID 가 설정돼 있으면                  → state/runs/{QA_RUN_ID}/artifacts
4. 아무것도 없으면 (CLI 직접 실행)              → state/runs/{자동 발급 run_id}/artifacts
```

**왜 `QA_RUN_DIR`을 그대로 쓰지 않는가** — `QA_RUN_DIR`을 단일 실행에도 강제하면 `state/pipeline.json`의 위치가 바뀝니다. `06_heal.py`와 `report_html.py`, 대시보드 `/api/state`가 모두 `state/pipeline.json` 고정 경로를 읽으므로 그 전부를 함께 고쳐야 하고, 이는 병렬 실행 PRD F-2의 범위입니다. 이 PRD는 **상태 JSON 경로를 건드리지 않고** 아티팩트만 새 트리에 쌓습니다. 병렬 PRD가 나중에 `QA_RUN_DIR`을 도입하면 규칙 2가 자동으로 발동해 정합이 맞습니다 — 이 PRD 쪽 코드 변경은 없습니다.

### 3-2. 디렉토리 구조 _(확정)_

```text
state/runs/{run_id}/
  artifacts/
    manifest.json                      # run 단위 인덱스 — 조회 API의 단일 소스
    {node_slug}/
      attempt1/
        video.mp4                      # 해당 시도 구간 화면 영상
        syslog.txt                     # logcat (android) 또는 log stream (ios)
        meta.json                      # 해당 attempt의 시각·종료코드·수집 오류
      attempt2/                        # pytest rerun/healing 시 순차 추가
```

병렬 실행이 도입되면 규칙 2에 의해 자동으로 이렇게 됩니다 (구조 동일):

```text
state/parallel/{par_run_id}/{udid}/artifacts/manifest.json
```

**`run_id` 형식**: `run_{platform}_{YYYYMMDD}_{HHMMSS}_{mmm}` — 예 `run_android_20260917_143012_881`. 정규식 `^run_[a-z]+_[0-9]{8}_[0-9]{6}_[0-9]{3}$`. API 경로 세그먼트로 쓰이므로 §5-4의 검증을 통과해야 합니다.

**`node_slug`**: pytest nodeid에서 파생. 기존 `tests/conftest.py:63`의 `safe_name` 규칙을 그대로 재사용합니다.

```python
def _node_slug(nodeid: str) -> str:
    s = nodeid.replace("/", "_").replace("::", "__").replace(" ", "_")
    s = re.sub(r"[^A-Za-z0-9._-]", "_", s)
    if len(s) > 200:                      # 파일명 255바이트 한계
        s = s[:200] + "_" + hashlib.sha1(nodeid.encode()).hexdigest()[:12]
    return s
```

`safe_name`과 동일한 입력에 동일한 접두를 내므로, 기존 스크린샷 파일명과 manifest 항목을 눈으로 대조할 수 있습니다.

**`attempt{n}/` 서브디렉토리 _(v0.4 확정)_**: pytest 재시도와 healing 재실행은 같은 run의 다음 attempt로 추가합니다. 이전 시도의 실패 증거를 덮어쓰지 않으며, 대시보드에서 시도별 영상·로그를 전환할 수 있습니다. 기존 flat manifest는 조회 API가 단일 attempt로 정규화해 하위 호환합니다.

### 3-3. `manifest.json` 스키마 _(확정)_

```json
{
  "run_id": "run_android_20260917_143012_881",
  "platform": "android",
  "mode": "emulator",
  "udid": "emulator-5554",
  "device_name": "Android Emulator",
  "keep_policy": "on_failure",
  "started_at": "2026-09-17T14:30:12",
  "finished_at": "2026-09-17T14:38:44",
  "entries": [
    {
      "nodeid": "tests/generated/android/settings/tc_settings_battery.py::test_settings_battery",
      "slug": "tests_generated_android_settings_tc_settings_battery.py__test_settings_battery",
      "outcome": "failed",
      "attempt_count": 1,
      "attempts": [{
        "n": 1,
        "outcome": "failed",
        "started_at": "2026-09-17T14:31:02.113",
        "finished_at": "2026-09-17T14:31:44.902",
        "duration_sec": 41.6,
        "kept": true,
        "video":  {"path": "tests_.../attempt1/video.mp4", "bytes": 15728640,
                   "source": "adb_screenrecord", "truncated": false},
        "syslog": {"path": "tests_.../attempt1/syslog.txt", "bytes": 1048576,
                   "source": "adb_logcat", "truncated": false},
        "screenshot": {"path": "tests_.../attempt1/screenshot.png", "bytes": 154074,
                       "source": "appium_driver", "external": false},
        "failure_offset_sec": 39.1,
        "network": null,
        "collect_errors": []
      }]
    }
  ]
}
```

| 필드 | 규칙 |
|---|---|
| `video.path` / `syslog.path` | `artifacts/` 기준 **상대 경로**. 각 attempt 디렉토리를 포함하며 API가 루트를 붙입니다 |
| `attempt_count` | 실행된 시도 회차 수. `pytest-rerunfailures`·healing 재실행 모두 포함 |
| `failure_offset_sec` | 영상 내 실패 지점 상대 위치(초). `started_at`→`finished_at` 간격으로 계산. 프론트가 `videoEl.currentTime`에 설정해 seek (§2-3, §8-2). 수집 실패·통과 시 `null` |
| `screenshot.path` | 관측 수집본은 `artifacts/` 기준 attempt 내부 상대 경로이며 `external: false`. 구버전 실패 리포트 PNG 포인터는 `external: true`로 계속 조회할 수 있습니다 |
| `kept` | 보존 정책상 파일이 남았는지. `false`면 `video`/`syslog`가 `null` |
| `truncated` | 크기 상한(§3-5)에 걸려 잘렸는지 |
| `collect_errors` | 수집 실패 사유 코드 배열. 비어 있으면 정상. 값은 §10 에러 카탈로그 |
| `network` | M1에서는 항상 `null`. M2 예약 필드 |

**쓰기 방식**: pytest 프로세스 하나가 단독으로 씁니다. 각 TC teardown에서 `manifest.json.tmp` 기록 → `Path.replace()` 원자 교체. `save_devices_json()`(`utils/state.py`)과 같은 패턴입니다. 조회 API가 실행 중에 읽어도 반쪽 JSON을 만나지 않습니다.

### 3-4. attempt 스크린샷과 기존 실패 리포트 _(확정)_

보존되는 attempt는 call 단계 마지막 화면을 `{node_slug}/attempt{n}/screenshot.png`에 직접 저장합니다. `always`는 통과·실패 모두, `on_failure`는 실패/error와 flaky attempt만 촬영합니다. Android와 iOS 모두 Appium `driver.save_screenshot()`을 사용합니다.

~~기존 `reports/screenshots/{platform}/{safe_name}.png` 실패 캡처는 HTML 리포트·Jira 호환을 위해 유지합니다.~~ **(v0.13에서 철회)** `tests/conftest.py`의 legacy 캡처 훅과 `state/screenshots.json`을 제거했습니다. `report_html.py`(HTML 리포트)와 `jira_reporter.py`(Jira 첨부) 모두 이제 이 manifest를 nodeid로 직접 조회해 스크린샷을 가져옵니다 — `report_html.py`는 `/api/run_artifacts/{run_id}/screenshot` URL을, `jira_reporter.py`는 `state/runs/{run_id}/artifacts/.../screenshot.png` 절대경로를 사용합니다(Jira 첨부는 실제 파일 바이트가 필요하므로 URL이 아닌 로컬 경로). 관측 UI는 그대로 `/api/run_artifacts/{run_id}/screenshot`을 사용하며, 구버전 `external: true` manifest만 기존 `/screenshots/` 경로를 사용합니다.

### 3-5. 크기 상한과 보존 정책 _(확정)_

#### 파일당 상한

| 산출물 | 상한 | 초과 시 |
|---|---|---|
| `video.mp4` | 녹화 180초 | `screenrecord --time-limit 180`이 자동 종료. `truncated: true` 기록 |
| `syslog.txt` | 20 MB | teardown에서 **뒤쪽 20MB만 남기고** 앞을 버림 (실패 직전이 중요). `truncated: true` |

#### 용량 예측

`adb screenrecord`의 기본 비트레이트는 20 Mbps입니다 — 60초에 150 MB. 이대로 두면 못 씁니다. **`--bit-rate 2000000`(2 Mbps)로 낮춥니다.** `--size`는 기기가 지원하는 해상도만 받으므로 지정하지 않습니다 (미지원 값이면 녹화 자체가 실패).

| 시나리오 | TC당 영상 | TC당 로그 | run당 (실패 3건 보존) |
|---|---|---|---|
| Android, TC 60초, 2 Mbps | ~15 MB | ~1.5 MB | ~50 MB |
| Android, TC 180초 (상한) | ~45 MB | ~4 MB | ~147 MB |
| iOS 시뮬레이터, TC 60초 | ~10–25 MB (비트레이트 제어 불가, §6-4) | ~2 MB | ~80 MB |

#### run 보존

```
최근 20개 run 유지  AND  state/runs/ 합계 2 GB 이하
```

둘 중 **먼저 걸리는 쪽**이 적용됩니다. 초과분은 `started_at` 오래된 run 디렉토리부터 통째로 삭제합니다. 20개는 병렬 실행 PRD의 `state/parallel/` 보존 정책과 같은 수치로 맞췄습니다.

**정리 시점**: 대시보드가 새 run을 시작할 때 1회 (`pipeline.py`에서 run_id 발급 직후). pytest 훅 안에서 하지 않습니다 — TC마다 디렉토리 전체를 스캔하면 실행 시간에 영향을 줍니다.

**정리 대상 제외**: 실행 중인 run(`finished_at`이 `null`이고 `started_at`이 6시간 이내)은 삭제하지 않습니다.

---

## 4. 수집 메커니즘

### 4-1. run_id 발급과 환경변수 계약 _(확정)_

| 환경변수 | 설정 주체 | 소비 지점 | 기본값 |
|---|---|---|---|
| `QA_RUN_ID` | `pipeline.py` (대시보드) 또는 `05_execute.py`(CLI 폴백) | `tests/conftest.py` | 자동 발급 |
| `QA_ARTIFACT_DIR` | 보통 미설정 — §3-1 규칙으로 유도 | `tests/conftest.py` | `state/runs/{run_id}/artifacts` |
| `QA_OBS_KEEP` | 대시보드 체크박스(§8-1, `on_failure`\|`always`) 또는 환경변수 직접 지정(CLI, `never` 포함 §5-3) | `tests/conftest.py` | `on_failure` |
| `QA_OBS_DISABLE` | 사용자 | `tests/conftest.py` | 미설정(=수집 on) |
| `DEVICE_UDID` | 기존 | 수집 대상 기기 식별에 재사용 | — |
| `DEVICE_MODE` | 기존 | iOS 시뮬레이터/실기기 분기 | — |

`05_execute.py`의 `main()`은 pytest를 띄우기 직전 `run_env`에 다음을 주입합니다.

```python
run_id = os.environ.get("QA_RUN_ID") or f"run_{platform}_{report_stamp}"
run_env["QA_RUN_ID"] = run_id
run_env.setdefault("QA_OBS_KEEP", "on_failure")
# 이미 계산된 report_stamp 재사용 — 리포트 HTML 파일명과 run_id가 같은 타임스탬프를 공유한다
```

그리고 결과를 `state`에 남겨 리포트·대시보드가 역참조할 수 있게 합니다.

```python
state["last_run_id"] = run_id
```

`report_stamp`를 재사용하는 이유: `tests/reports/report_android_{stamp}.html`과 `state/runs/run_android_{stamp}/`가 같은 stamp를 갖게 되어, 리포트 파일만 보고도 대응하는 아티팩트 디렉토리를 찾을 수 있습니다.

**stamp 형식 확인 완료** — `05_execute.py:324`의 `report_stamp`는 `datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]` 즉 `20260917_143012_881`(밀리초 3자리)입니다. 따라서 `run_{platform}_{report_stamp}`가 §3-2의 정규식 `^run_[a-z]+_[0-9]{8}_[0-9]{6}_[0-9]{3}$`와 §7-2의 `_RUN_ID_RE` 검증을 그대로 통과합니다. **stamp 생성 로직을 새로 만들지 말고 324행의 값을 재사용하세요** — 별도 `strftime`을 쓰면 밀리초가 빠져(같은 파일 400행이 그 예) API가 `400 invalid_run_id`를 냅니다.

### 4-2. Android 영상 — `adb screenrecord` _(확정)_

**대안 비교**

| | `adb screenrecord` | MJPEG 스트림 → mp4 |
|---|---|---|
| 기존 코드 | `05_execute.py:68-95`, `pipeline.py:299-338`에 이미 있고 동작 확인됨 | 없음 |
| 전제 조건 | 없음 | Appium 서버 `--allow-insecure=uiautomator2:adb_screen_streaming` 플래그 (CLAUDE.md) **+ Appium 세션 생존** |
| 세션이 죽는 실패에서 | 계속 녹화됨 | **스트림도 같이 끊김** |
| 추가 의존성 | 없음 | ffmpeg (MJPEG→mp4 인코딩) |
| 한계 | 180초 상한, 기기 저장 후 pull 필요, 일부 기기 미지원 | 프레임레이트 불안정 |

**`adb screenrecord` 채택.** 결정적 근거는 두 번째 줄입니다 — UiAutomator2 세션 초기화 실패(CLAUDE.md "연속 Appium 세션 주의사항"에 기록된 그 증상)는 우리가 **가장 보고 싶은** 실패인데, MJPEG은 바로 그 순간 아무것도 남기지 못합니다. screenrecord는 adb 레벨에서 돌기 때문에 Appium이 죽어도 화면을 계속 찍습니다.

**대상 기기 해석 순서**: `DEVICE_UDID` → `adb devices`의 첫 온라인 기기 → 실패 시 `collect_errors: ["no_device"]`.

```python
# setup — adb 로컬 프로세스가 아니라 기기 측 PID를 추적한다
remote = f"/sdcard/qa_obs_{hashlib.sha1(slug.encode()).hexdigest()[:12]}.mp4"
subprocess.run([ADB, "-s", udid, "shell", "rm", "-f", remote], capture_output=True)
result = subprocess.run([
    ADB, "-s", udid, "shell",
    f"screenrecord --bit-rate 2000000 --time-limit 180 {remote} >/dev/null 2>&1 & echo $!",
], capture_output=True, text=True)
remote_pid = int(result.stdout.strip())

# teardown — SIGINT가 moov atom을 완성한다. SIGTERM은 손상 파일을 남긴다.
subprocess.run([ADB, "-s", udid, "shell", "kill", "-2", str(remote_pid)])
# kill -0으로 종료를 확인하고, timeout이면 해당 PID만 SIGKILL한다.
if keep:
    subprocess.run([ADB, "-s", udid, "pull", remote, str(local)], capture_output=True)
subprocess.run([ADB, "-s", udid, "shell", "rm", "-f", remote], capture_output=True)
```

원격 파일명에 slug 전체가 아니라 sha1 앞 12자를 쓰는 이유: `/sdcard`의 파일명 제약과 shell 인자 이스케이프 문제를 피하기 위해서입니다. slug ↔ 원격 파일명 대응은 프로세스 안에서만 필요하므로 해시로 충분합니다.

시작 0.4초 뒤 PID 생존을 확인하고, 에뮬레이터 인코더가 즉시 종료되면 1회 재시도합니다. 매우 짧은 TC는 최소 1초간 녹화한 뒤 종료해 0프레임 파일을 줄입니다. pull 뒤에는 MP4 `mvhd` duration이 양수인지 검증하며, 손상 파일은 삭제하고 `video_invalid`를 기록합니다.

**보존하지 않는 경우(통과한 TC + `on_failure`)에는 `pull`을 건너뜁니다.** 기기에서 `rm`만 하며, 원격 PID와 파일은 결과에 관계없이 정리합니다.

### 4-3. iOS 영상 — `simctl io recordVideo` (시뮬레이터) _(확정)_

```python
# setup
proc = subprocess.Popen(
    ["xcrun", "simctl", "io", udid, "recordVideo", "--codec=h264", "--force", str(local)],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
)

# teardown
proc.send_signal(signal.SIGINT)     # ← SIGTERM 아님. 아래 주의사항 참조
proc.wait(timeout=10)
```

**🔴 기존 코드의 버그**: `pipeline.py:332`의 `_stop_video()`는 `rec_proc.terminate()`(SIGTERM)를 씁니다. `simctl recordVideo`는 **SIGINT를 받아야** 인코딩을 마무리하고 mp4 moov atom을 기록합니다. SIGTERM으로 죽이면 헤더가 없는 재생 불가 파일이 남습니다. M1에서 `pipeline.py`의 해당 줄도 함께 고칩니다 (§6-2).

**`booted` 대신 udid 명시**: 현재 `pipeline.py:306`은 `xcrun simctl io booted`를 씁니다. 시뮬레이터가 2대 부팅돼 있으면 `booted`가 모호해져 실패합니다. `devices.json`의 `ios.simulator[]`에서 `default: true` 또는 `DEVICE_UDID`로 해석한 udid를 명시합니다.

**iOS 실기기**: 수집을 시도하지 않고 `collect_errors: ["ios_real_device_unsupported"]`만 기록합니다 (§2-4).

### 4-4. Android 시스템 로그 — `adb logcat` _(확정)_

```python
# setup
f = open(syslog_path, "w", encoding="utf-8", errors="replace")
proc = subprocess.Popen(
    [ADB, "-s", udid, "logcat", "-b", "all", "-v", "threadtime", "-T", "1"],
    stdout=f, stderr=subprocess.STDOUT,
)

# teardown
proc.terminate(); proc.wait(timeout=5); f.close()
```

**`-c`(버퍼 클리어)를 쓰지 않고 `-T 1`을 쓰는 이유** — 두 가지를 동시에 해결합니다.

1. `-c`는 **기기 전역 버퍼**를 지웁니다. 병렬 실행에서 기기 A의 TC 시작이 다른 프로세스가 읽는 중인 버퍼를 날리는 일이 생깁니다. `-T 1`은 아무것도 지우지 않습니다.
2. `-T 1`은 "가장 최근 1줄부터 follow"라는 뜻이라, `-c` 없이도 **과거 버퍼 전체가 덤프되지 않습니다.** `-c` + 지연 시작 조합의 레이스도 사라집니다.

**`-b all`**: `main`만 잡으면 네이티브 크래시와 ANR을 놓칩니다. `crash`·`system`·`events` 버퍼가 함께 필요합니다.

**필터링하지 않고 전량 수집합니다.** 앱 PID 필터(`--pid`)는 앱이 죽고 재시작하면 PID가 바뀌어 로그가 끊기고, 실패 원인이 시스템 쪽(권한 팝업, OOM killer, 네트워크 스택)일 때 정작 필요한 줄을 버립니다. 패키지 기준 필터링은 대시보드 조회 화면의 프론트 기능으로 제공합니다 (§7-2).

### 4-5. iOS 시스템 로그 — `simctl spawn log stream` _(기본값 확정 · predicate는 열린 질문 Q-1)_

```python
# setup
f = open(syslog_path, "w", encoding="utf-8", errors="replace")
cmd = ["xcrun", "simctl", "spawn", udid, "log", "stream",
       "--style", "compact", "--level", "info"]
if predicate:  # Bundle ID가 설정된 경우에만 앱 필터 적용
    cmd += ["--predicate", predicate]
proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)

# teardown (finally 블록 안에서 실행)
proc.terminate()
try:
    proc.wait(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()
f.close()
```

`log stream`은 시작 시점부터의 로그만 내보내므로 Android의 `-T 1`에 해당하는 처리가 필요 없습니다. teardown에서 SIGTERM이 5초 내에 처리되지 않으면 SIGKILL로 강제 종료합니다 (F-9).

**predicate 기본값** (`config/observability.json`에서 오버라이드 가능):

```
processImagePath CONTAINS[c] "{bundle_last_segment}" OR subsystem CONTAINS[c] "{bundle_id}"
```

`bundle_id`는 `config/test_data.json`에서, `bundle_last_segment`는 bundle_id의 마지막 `.` 뒤 조각에서 얻습니다.

Bundle ID가 비어 있어도 로그 수집을 생략하지 않습니다. 이 경우 predicate 없이 전체 시뮬레이터 로그를 수집하고 teardown에서 §3-5의 20MB 상한을 적용합니다. Bundle ID가 있으면 위 predicate를 적용해 저장량을 줄입니다. 2026-09-17 실제 iOS Settings E2E에서는 무필터 199초 실행 로그가 약 792KB로 측정됐습니다.

이 기본 predicate가 DirectCloud 앱의 로그를 실제로 잡는지는 검증되지 않았습니다 → **Q-1**.

### 4-6. 신규 설정 파일 `config/observability.json` _(확정)_

```json
{
  "enabled": true,
  "keep": "on_failure",
  "video": {
    "android": {"bit_rate": 2000000, "time_limit_sec": 180, "min_duration_sec": 1.0},
    "ios": {"codec": "h264"}
  },
  "syslog": {
    "android": {"buffers": "all", "format": "threadtime"},
    "ios": {"level": "info",
            "predicate": "processImagePath CONTAINS[c] \"{bundle_suffix}\" OR subsystem CONTAINS[c] \"{bundle_id}\""}
  },
  "retention": {"max_runs": 20, "max_total_mb": 2048},
  "limits": {"syslog_max_mb": 20}
}
```

파일이 없으면 위 값이 하드코딩 기본값으로 적용됩니다 — **파일 생성은 선택**입니다. CLAUDE.md "설정 파일" 표에 행을 추가합니다 (§11).

---

## 5. pytest 훅 설계

### 5-1. 배치 위치 — `tests/conftest.py` _(확정)_

| 후보 | 판단 |
|---|---|
| `tests/conftest.py` | ✅ **채택** |
| `tests/generated/conftest.py` | ❌ |

근거 셋:

1. **기존 스크린샷 훅과 같은 파일에 있어야 합니다.** manifest 항목이 스크린샷 경로 포인터를 포함하므로(§3-3), `pytest_runtest_makereport`가 스크린샷을 저장한 직후 그 경로를 manifest에 넣어야 합니다. 두 파일로 나누면 훅 실행 순서에 의존하는 프로세스 전역 상태를 따로 만들어야 합니다.
2. **`tests/generated/conftest.py`는 생성 산출물 영역에 가깝습니다.** 현재는 수동 관리 파일이지만 위치상 `02_generate.py`의 출력 트리 안에 있고, 역할도 "생성 코드의 런타임 디바이스 오버라이드" 하나로 좁게 정의돼 있습니다. 관측 수집을 섞으면 그 파일의 책임이 흐려집니다.
3. **범위 가드로 부작용을 막을 수 있습니다.** `tests/conftest.py`는 `tests/unit/`(제품 자체 단위 테스트)에도 적용되는데, 거기엔 기기가 없습니다. nodeid 가드 한 줄로 해결합니다.

```python
def _is_observable(item) -> bool:
    if os.environ.get("QA_OBS_DISABLE"):
        return False
    return item.nodeid.startswith("tests/generated/")
```

### 5-2. 훅 배치

| 훅 | 하는 일 |
|---|---|
| `pytest_sessionstart` | 프로세스 로컬 상태만 초기화. 일반 단위 테스트에서는 파일·기기 접근 없음 |
| `pytest_runtest_setup(item)` | 첫 `_is_observable` TC에서 manifest를 지연 초기화하고 `{node_slug}/attempt{n}/` 생성 → 영상·로그 프로세스 **시작** |
| `pytest_runtest_makereport(item, call)` — `when == "call"` | 보존 정책을 판정해 attempt 마지막 화면 캡처. 실패 시에는 기존 HTML 리포트용 PNG도 유지 |
| `pytest_runtest_makereport(item, call)` — `when == "teardown"` | 영상·로그 프로세스 **종료** → 보존 정책 적용 → manifest 갱신(`attempt_count` +1) → 원자적 저장 |
| `pytest_sessionfinish` | `finished_at` 기록, manifest 최종 저장 |

**왜 종료가 `teardown`인가** — 스크린샷은 `call` 단계에서 찍힙니다. 영상을 `call`에서 같이 끊으면 스크린샷을 찍는 순간이 영상에 안 들어갈 수 있습니다. `teardown`까지 돌리면 **실패 화면이 영상 마지막 프레임에 남습니다.** 대신 TC 정리 동작(앱 종료 등)도 함께 찍히는데, 그건 노이즈가 아니라 정보입니다.

**attempt 카운터** — 각 시도는 `attempt{n}/`에 분리하고 manifest의 `attempts[]`에 추가합니다. `pytest-rerunfailures`의 `item.execution_count`에 의존하지 않는 이유: 그 속성은 플러그인 미설치 시 존재하지 않습니다. healing 재실행(§2-3)은 별개 pytest 프로세스라 manifest에서 기존 `attempts[]` 길이를 읽어 이어붙입니다.

```python
def _increment_attempt(slug: str, manifest: dict) -> int:
    entry = _find_entry(manifest, slug)
    count = (entry.get("attempt_count") or 0) + 1
    return count
```

### 5-3. 보존 정책 — 수집은 항상, 보존은 조건부 _(확정)_

수집은 **항상 시작합니다.** TC가 실패할지는 시작 시점에 알 수 없습니다.

`QA_OBS_KEEP` 값:

| 값 | 동작 | 용도 |
|---|---|---|
| `on_failure` **(기본)** | 실패·에러 시에만 파일 보존. 통과하면 pull/파일 삭제 | 일상 회귀 |
| `always` | 통과·실패 무관 전부 보존 | flaky 조사 세션, 데모 |
| `never` | 프로세스도 띄우지 않음 | 수집 오버헤드가 문제인 경우 |

**`never`는 CLI 전용입니다 _(확정)_.** `QA_OBS_KEEP=never` 환경변수로만 지정할 수 있고 **대시보드 UI에는 노출하지 않습니다.** 근거: UI에 `never`를 두면 "수집 안 함"과 `QA_OBS_DISABLE`이 기능적으로 같은 두 개의 스위치가 되어, 사용자가 어느 쪽을 껐는지 추적해야 합니다. UI에서 수집을 끄는 수단은 필요하지 않습니다 — 기본값 `on_failure`가 통과 TC의 파일을 이미 남기지 않으므로 UI에서 줄일 용량이 없고, 오버헤드가 문제인 상황은 CLI 회귀 배치입니다. 따라서 §8-1 체크박스는 `on_failure` ↔ `always` **2값만** 전환합니다. 서버는 `never`를 받아도 동작하지만(CLI 계약 유지) 프론트는 그 값을 전송하지 않습니다.

**트레이드오프 — `on_failure`를 기본으로 두는 대가**

`on_failure`에서는 실패·에러 attempt와 재시도가 발생한 flaky TC의 attempt를 보존합니다. 각 시도는 `attempt{n}/`에 분리되므로 최종 통과가 이전 실패 영상을 덮어쓰지 않습니다. 전체 통과 TC까지 조사하려면 `always`를 사용합니다.

```python
def _should_keep(policy: str, outcome: str) -> bool:
    if policy == "always":
        return True
    if policy == "never":
        return False
    return outcome in ("failed", "error")
```

대시보드 빠른 실행 탭에 "전체 보존" 체크박스를 두어 `always`를 한 번의 클릭으로 켤 수 있게 합니다 (§7-1).

### 5-4. 수집 실패는 테스트 결과를 바꾸지 않는다 _(확정)_

영상·로그 수집의 모든 예외는 삼키고 `collect_errors`에 코드만 남깁니다. TC 결과에 영향을 주지 않습니다.

근거: 관측은 부가 기능입니다. `screenrecord`를 지원하지 않는 기기에서 정상 TC가 빨갛게 뜨면, 이 기능이 해결하려던 문제(원인 분류)를 오히려 늘립니다.

훅 전체를 `try/except Exception`으로 감싸고, `teardown` 훅은 수집 프로세스 종료를 `finally`에 둡니다 — 예외 경로에서 좀비 `adb logcat` 프로세스가 남지 않아야 합니다.

---

## 6. 선행 이슈 — 구현 전 반드시 해소

### F-1. 영상 저장 경로 이원화 — 🟠 필수

`05_execute.py:40`의 `REPORTS_DIR = ROOT / "tests" / "reports"` 아래 `recordings/`와, `pipeline.py:301`의 `PROJECT_ROOT / "reports" / "recordings"`가 **서로 다른 디렉토리**입니다. 후자만 실제로 존재합니다(`reports/`에는 `screenshots/`만 있음).

조치: TC 단위 영상은 `state/runs/{run_id}/artifacts/`만 사용합니다. healing 중복 녹화는 같은 기기의 인코더와 충돌하므로 제거했습니다. CLI 호환용 `--record`는 유지하되 실행 시 TC별 수집을 비활성화하여 두 recorder가 동시에 뜨지 않게 했습니다 (§13 Q-3).

### F-2. `simctl recordVideo` 종료 시그널 — 🔴 블로커

기존 `pipeline.py`의 중복 run 녹화는 제거했습니다. TC별 iOS 수집은 §4-3대로 **SIGINT**로 종료하여 mp4 moov atom을 완성합니다.

검증: 시뮬레이터에서 10초 녹화 후 `ffprobe` 또는 QuickTime으로 재생 확인.

### F-3. `xcrun simctl io booted` 모호성 — 🟠 필수

`pipeline.py:306`이 `booted`를 씁니다. 시뮬레이터 2대 부팅 시 `simctl`이 "Multiple devices matched" 에러를 냅니다. udid 명시로 교체 (§4-3).

### F-4. Android `screenrecord` 지원 여부 미검증 — 🟡 정리

`adb shell screenrecord --help`가 실패하거나, 일부 벤더 기기·에뮬레이터 이미지에서 녹화가 0바이트로 나오는 사례가 있습니다.

조치: `pytest_sessionstart`에서 **1회** probe 합니다. 실패하면 그 run 전체의 영상 수집을 끄고 manifest에 `"video_unavailable": "<stderr 첫 줄>"`을 기록합니다. TC마다 재시도하지 않습니다.

```python
r = subprocess.run([ADB, "-s", udid, "shell", "screenrecord", "--help"],
                   capture_output=True, text=True, timeout=10)
video_ok = ("--bit-rate" in (r.stdout + r.stderr))
```

### F-5. adb 다중 명령 안정성 (병렬 실행 시) — 🟡 정리

병렬 실행에서 기기 3대에 `screenrecord` + `logcat` 프로세스가 각각 떠서 adb 서버에 동시 6개 스트림이 붙습니다. 안정성 미검증.

조치: M1은 단일 기기 실행만 완료 판정 대상으로 둡니다. 병렬 조합 검증은 병렬 실행 PRD M1과 함께 (§13 Q-4).

### F-6. 대상 기기 식별 로직 부재 — 🟠 필수

현재 `tests/conftest.py`에는 어떤 기기를 상대로 실행 중인지 알 수단이 없습니다. `_resolve_target_device()`를 신설합니다.

```python
def _resolve_target_device(platform: str) -> tuple[str, str]:
    """(udid, device_name) 반환. 실패 시 ("", "")."""
    udid = os.environ.get("DEVICE_UDID", "").strip()
    mode = os.environ.get("DEVICE_MODE", "").strip() or (
        "simulator" if platform == "ios" else "emulator")
    devices = _load_json(CONFIG / "devices.json").get(platform, {}).get(mode, [])
    if isinstance(devices, dict):            # 구 스키마 하위호환
        devices = [devices]
    if udid:
        m = next((d for d in devices if d.get("udid") == udid), None)
        return udid, (m or {}).get("deviceName", "")
    d = next((x for x in devices if x.get("default")), devices[0] if devices else {})
    resolved = d.get("udid", "")
    if platform == "android" and not resolved:
        resolved = _first_online_adb_device()     # 에뮬레이터는 udid를 안 적는 경우가 많다
    return resolved, d.get("deviceName", "")
```

`config/devices.json`의 `android.emulator[0]`에는 `udid` 키가 없습니다(현재 파일 확인). 에뮬레이터는 `adb devices` 폴백이 필수입니다.

### F-7. 저장 용량 — 🟡 정리

§3-5의 예측치는 계산값이며 실측이 아닙니다. M1 완료 판정에 "TC 20건 run 1회 후 `state/runs/` 실제 용량 측정" 항목을 포함합니다 (§12).

### F-8. `pipeline.py` `_spawn()` QA_RUN_ID 전달 메커니즘 미정의 — 🔴 블로커

`pipeline.py:273`의 `_spawn()`은 `subprocess.Popen` 호출 시 `env=` 인자를 전달하지 않습니다. `pipeline.py`가 run_id를 발급해 로컬 변수에 저장해도, `_spawn("execute")` → `05_execute.py` 프로세스가 `QA_RUN_ID`를 상속받지 못합니다 — Popen은 호출 시점의 `os.environ`을 복사하므로, 로컬 dict에만 존재하는 값은 자식 프로세스에 전달되지 않습니다.

조치: `os.environ.copy()`로 run 전용 환경을 만들고 `_spawn(..., env=run_env)`로 **execute 자식에만 전달**합니다. 서버 전역 환경은 변경하지 않으며, healing 재실행도 같은 `run_env`와 `run_id`를 재사용합니다.

```python
# pipeline.py — run_id 발급 후 즉시
run_env = os.environ.copy()
run_env["QA_RUN_ID"] = run_id
_spawn("execute", ..., env=run_env)
```

### F-9. iOS `simctl spawn log stream` 종료 — 🟡 정리

`proc.terminate()` 후 `proc.wait(timeout=5)` 없이 teardown이 끝나면 `log stream` 프로세스가 좀비로 남을 수 있습니다. macOS 일부 버전에서 `wait()` 자체가 5초를 초과하는 사례도 보고됩니다.

teardown 코드에 반드시 timeout + kill 폴백을 포함합니다.

```python
proc.terminate()
try:
    proc.wait(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()
```

§4-4 Android logcat teardown 예시와 동일한 패턴이며, §4-5 iOS 로그 수집 섹션에 teardown 코드가 빠져 있으므로 함께 보완합니다.

---

## 7. 기술 요구사항 — 백엔드 API

### 7-1. 신규 엔드포인트

모두 `agents/dashboard/routes/api.py`에 추가합니다. `pipeline.py`는 실행 제어, `api.py`는 조회/서빙 담당이라는 기존 분리를 따릅니다.

#### `GET /api/runs?platform=&limit=20`

run 목록. 빠른 실행 탭의 "최근 실행" 드롭다운용.

```json
{
  "ok": true,
  "runs": [
    {"run_id": "run_android_20260917_143012_881", "platform": "android",
     "started_at": "2026-09-17T14:30:12", "finished_at": "2026-09-17T14:38:44",
     "device_name": "Android Emulator",
     "counts": {"total": 12, "failed": 3, "with_video": 3, "with_syslog": 3},
     "size_mb": 51.2}
  ]
}
```

`state/runs/*/artifacts/manifest.json`을 스캔해 만듭니다. `started_at` 내림차순.

#### `GET /api/run_artifacts/{run_id}`

해당 run의 manifest 전체 + 각 아티팩트의 조회 URL을 덧붙여 반환합니다.

```json
{
  "ok": true,
  "run_id": "run_android_20260917_143012_881",
  "platform": "android", "device_name": "Android Emulator",
  "keep_policy": "on_failure",
  "entries": [
    {
      "nodeid": "tests/generated/android/settings/tc_settings_battery.py::test_settings_battery",
      "outcome": "failed",
      "attempts": [
        {"n": 1, "outcome": "failed", "duration_sec": 42.8, "kept": true,
         "video_url":  "/api/run_artifacts/run_.../video?nodeid=...&attempt=1",
         "syslog_url": "/api/run_artifacts/run_.../logcat?nodeid=...&attempt=1",
         "screenshot_url": "/api/run_artifacts/run_.../screenshot?nodeid=...&attempt=1",
         "video_bytes": 15728640, "syslog_bytes": 1048576,
         "collect_errors": []}
      ]
    }
  ]
}
```

신규 attempt 캡처는 안전 경로 검증을 거치는 `/screenshot` 엔드포인트로 제공합니다. 구버전 `external: true` 캡처만 기존 `/screenshots/{name:path}`를 재사용합니다 (§3-4).

에러: run_id 없음 → `404 run_not_found`.

#### `GET /api/run_artifacts/{run_id}/video?nodeid=...&attempt=1`

`attempt` 생략 시 **마지막 attempt**. `FileResponse(path, media_type="video/mp4")`로 반환합니다 — starlette의 `FileResponse`가 HTTP Range를 처리하므로 브라우저 `<video>` seek이 동작합니다. 직접 Range를 구현하지 마세요.

에러: `404 artifact_not_found` (미보존·수집 실패 포함).

#### `GET /api/run_artifacts/{run_id}/logcat?nodeid=...&attempt=1&tail=2000`

`text/plain; charset=utf-8`. `tail`(줄 수, 기본 전체, 최대 200000)로 뒤에서부터 잘라 반환합니다. 20MB 파일을 브라우저에 그대로 던지면 프론트가 멈춥니다.

`Content-Disposition: inline`. 전체 다운로드는 `?download=1`로 `attachment` 전환.

#### `DELETE /api/run_artifacts/{run_id}`

수동 삭제. 실행 중인 run(`finished_at`이 `null`)은 `409 run_active`.

### 7-2. 경로 검증 — 기존 패턴보다 강화 _(확정)_

`api.py`의 기존 `/reports/{name:path}`·`/screenshots/{name:path}`는 `if ".." in name: return 403`만 검사합니다. 심볼릭 링크와 URL 인코딩 우회에 약합니다. 신규 엔드포인트는 **정규식 + resolve 이중 가드**를 씁니다.

```python
_RUN_ID_RE = re.compile(r"^run_[a-z]+_\d{8}_\d{6}_\d{3}$")

def _artifact_root(run_id: str) -> Path:
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(400, "invalid run_id")
    root = (PROJECT_ROOT / "state" / "runs" / run_id / "artifacts").resolve()
    base = (PROJECT_ROOT / "state" / "runs").resolve()
    if not root.is_relative_to(base) or not root.is_dir():
        raise HTTPException(404, "run_not_found")
    return root
```

`nodeid`는 URL 파라미터로 들어오지만 **경로 조립에 직접 쓰지 않습니다.** manifest에서 `nodeid`로 항목을 찾아 거기 기록된 `path`를 사용하고, 그 `path`도 `_artifact_root` 하위인지 `is_relative_to`로 재확인합니다. 경로 문자열이 사용자 입력에서 파일시스템까지 직행하는 경로를 만들지 않는다는 원칙입니다.

### 7-3. Livetail 이벤트 추가

`pipeline.py`의 기존 `broadcast_timeline_sync` 패턴을 따릅니다. 이벤트는 pytest 프로세스가 아니라 **대시보드 쪽**에서 발행합니다 — pytest는 대시보드 이벤트 루프에 접근할 수 없습니다.

| 시점 | 이벤트 |
|---|---|
| run_id 발급 직후 | `{"type": "obs_run_start", "source": "pipeline", "run_id": "...", "keep": "on_failure"}` |
| `execute` 단계 종료 후 manifest 읽어서 | `{"type": "obs_run_summary", "source": "pipeline", "run_id": "...", "failed": 3, "with_video": 3, "size_mb": 51.2}` |

TC 단위 실시간 이벤트는 M1 범위 밖입니다. pytest → 대시보드 역방향 채널이 없어서 파일 폴링이나 IPC를 새로 만들어야 하는데, `execute` 종료 후 한 번 요약하는 것으로 충분합니다.

---

## 8. 기술 요구사항 — 프론트엔드

**UI 목업**: <https://claude.ai/artifact/E4JEz3FyB5cFZV9ad8oLrV> (v0.1)

아래 3개 상태를 인터랙티브하게 담고 있습니다. 상단 `스펙 주석` 체크박스를 켜면 각 UI 요소가 근거하는 PRD 조항과 판단 근거가 함께 표시됩니다.

| 목업 상태 | 대응 조항 | 확인 포인트 |
|---|---|---|
| 1 · 실행 결과 | §8-1, §8-2 | TC 목록의 pass/fail/flaky 배지, 보존된 아티팩트 3종 표시, 실패 TC 선택 시 증거 요약 패널 |
| 2 · 증거 상세 | §8-2, §7-1 | 영상 플레이어(실패 지점 마커) · logcat(레벨·검색 필터, §8-2 프리셋) · 스크린샷, attempt 1~3 전환, 재실행 버튼 |
| 3 · 수집 설정 | §5-3, §3-5, Q-2 | 보존 정책 라디오, 설정 변경 시 run당 용량·2 GB 상한 도달 run 수 실시간 반영 |

**목업과 PRD의 차이 4건 — v0.3에서 전부 확정.** 구현자는 아래 결론대로 만들면 됩니다.

| # | 항목 | 확정 방향 | 근거 |
|---|---|---|---|
| 1 | 영상·로그를 **개별로** 끄는 ON/OFF 토글 | ❌ **M1 미구현 · Q-2 종료.** M1은 §8-1 보존 컨트롤(체크박스 1개)만 노출. 목업 상태 3의 개별 토글은 **제거**됨 | 오버헤드 실측(§9-2) 전에 토글 추가는 근거 없음. 구현 시 manifest에 "왜 없는지" 상태를 별도로 기록해야 하는 복잡도만 증가. **영상·로그 개별 제어 수요는 M1 완료 후 재검토** |
| 2 | 증거 부재 시 탭 비활성 + 사유 문구 | ✅ **확정.** 탭을 비활성화하고 §10 에러 카탈로그 코드를 한국어 문구로 매핑해 표시. 원본 코드(`video_unsupported` 등)는 UI에 노출하지 않음 | 코드 노출은 QA 혼란 유발. 매핑표는 §8-2 끝에 있음 |
| 3 | 아티팩트 저장 경로 | ✅ **§3-2 확정값.** `state/runs/{run_id}/artifacts/{node_slug}/attempt{n}/`. `reports/artifacts/`는 폐기. `platform`은 경로가 아니라 manifest 필드 | 병렬 실행 시 `state/parallel/{par_run_id}/{udid}/artifacts/`로 자동 확장되는 구조. `reports/`는 기존 스크린샷·HTML 전용 |
| 4 | 영상 타임라인 **실패 지점 마커** | ✅ **확정.** attempt의 `finished_at`에서 계산한 상대 위치를 `<video>` seek에만 씀. ffmpeg 트림·썸네일은 §2-4 제외 항목 | ffmpeg 의존성 없이 브라우저 네이티브 `<video>` seek으로 동일 효과. 서버는 마커 타임스탬프(`failure_offset_sec`)를 manifest에 기록하고 프론트가 `videoEl.currentTime`으로 seek |

### 8-1. 빠른 실행 탭 — 실행 옵션

`힐링 생략`은 기본 체크 상태입니다. 체크 상태에서는 locator healing뿐 아니라
`pytest-rerunfailures`도 비활성화하여 각 TC를 정확히 1회만 실행하고, 실패 즉시
해당 TC 실행을 종료합니다. 체크를 해제한 경우에만 기존 재시도 및 healing
재실행 정책을 사용합니다. 이 계약은 Android와 iOS에 동일하게 적용합니다.

기존 실행 버튼 옆에 체크박스 하나만 추가합니다.

```
[ ] 모든 TC 증거 보존 (실패 TC는 항상 보존)
```

체크 시 `POST /api/run_test` 바디에 `"obs_keep": "always"`. 미체크면 필드 생략 → 서버 기본 `on_failure`.

**이 컨트롤은 2값만 전환합니다.** `never`는 UI에 노출하지 않으며(§5-3), 영상·로그 개별 토글도 M1에 없습니다(§8 표 #1). 프론트가 `obs_keep`에 보낼 수 있는 값은 `"always"` 하나뿐이고, 나머지는 필드 생략입니다.

### 8-2. 결과 화면 — 2열 증거 워크스페이스

실행 결과를 별도 모달로 가리지 않고 빠른 실행 결과 영역에 직접 표시합니다. 상단에는 run ID·기기·통과/실패·증거 용량·보존 정책을 요약하고, 본문은 왼쪽 TC 목록과 오른쪽 선택 TC 증거 패널의 2열 구조입니다. 900px 이하에서는 두 패널을 세로로 배치합니다.

기존 통계 카드·폴더 아코디언 결과는 생성하거나 localStorage에서 복원하지
않습니다. 실행 완료와 저장 결과 복원 모두 이 워크스페이스만 사용합니다.
WebSocket 이벤트를 놓친 경우 `/api/status`의 `obs_last_run_id`를 기준으로
manifest를 다시 읽습니다. 리포트 목록과 자체 완결 HTML 리포트 디자인은
v0.8 범위에서 변경하지 않습니다.

```
┌ RUN_ID          기기           결과       증거 용량    보존 ┐
├──────────────────────┬───────────────────────────────┤
│ TC 결과              │ FAIL tc_settings_battery...  │
│ • PASS TC            │ 시도 [1][2][3]               │
│ • FAIL TC  ◀ 선택    │ ▶ 영상                        │
│ • FLAKY TC           │ <video controls ...>          │
│                      │ ▤ 시스템 로그                 │
│                      │ <검색·프리셋·로그 본문>       │
│                      │ ▣ 스크린샷                     │
└──────────────────────┴───────────────────────────────┘
```

- **TC 목록**: PASS/FAIL/FLAKY 배지, 시도 횟수, 최신 시도 시간, 보존된 영상·로그·스크린샷 아이콘을 한 행에 표시합니다. 첫 진입 시 증거가 있는 첫 실패 TC를 선택합니다. `전체` / `성공` / `실패`로 필터링하며 10건 단위로 페이지를 나눕니다. 최종 통과한 FLAKY는 성공 집계에 포함하되 배지는 유지합니다.
- **직접 링크**: `#obs/{run_id}`는 다른 최신 run 복원 로직에 덮어써지지 않으며 지정한 run의 워크스페이스를 바로 엽니다.
- **세로 증거 흐름**: 탭으로 하나씩 가리지 않고 영상 → 시스템 로그 → 스크린샷을 한 화면에 모두 표시합니다.
- **영상 영역**: `<video controls preload="metadata">`. `preload="metadata"`로 두어야 화면을 열 때마다 전체 영상을 받지 않습니다.
- **시스템 로그 영역**: 영상 바로 아래에 배치하며 기본 `?tail=2000`. 검색창과 독립적으로 동작하는 `전체` / `오류` / `치명적` / `AndroidRuntime` / `앱 로그` 프리셋을 제공합니다. Android threadtime과 iOS compact 형식을 구조화해 시간·레벨·소스·메시지를 구분하고, 레벨별 색상과 검색어 강조를 적용합니다. 인식하지 못한 줄은 원문 그대로 표시합니다.
- **스크린샷 영역**: 로그 아래에 표시하며 해당 attempt의 마지막 화면을 제공합니다.
- 아티팩트가 없으면 해당 영역을 유지한 채 사유를 표시합니다 — "보존 정책에 따라 저장하지 않음" / "이 기기는 화면 녹화를 지원하지 않습니다" / "iOS 실기기 미지원".
- **플랫폼·진입 경로 일관성**: Android와 iOS manifest, 빠른 실행과 전체 파이프라인의 `obs_run_summary`는 모두 같은 공통 워크스페이스 렌더러를 사용합니다.

### 8-3. `report_html.py` HTML 리포트 _(v0.13에서 M1 계획 대체)_

~~M1에서는 변경하지 않습니다 — 리포트 상단에 run_id와 대시보드 링크 한 줄만 추가합니다.~~ 대신 **실패 케이스마다** 관측성 manifest(`state/runs/{run_id}/artifacts/manifest.json`)에서 nodeid로 최신 attempt를 찾아 스크린샷·영상을 case-detail 영역에 직접 표시합니다.

- 영상은 15MB base64 인라인 대신 `/api/run_artifacts/{run_id}/video?nodeid=...&attempt=...` HTTP URL을 `<video src>`로 참조합니다 — 리포트 HTML 자체는 가볍게 유지되고, 대시보드가 서빙 중일 때만 재생됩니다.
- 스크린샷도 동일한 방식으로 `/api/run_artifacts/{run_id}/screenshot?...` URL을 사용합니다.
- attempt가 `kept:false`(보존 정책 미대상)이면 스크린샷/영상 섹션이 생략됩니다.
- 상단의 "관측 아티팩트: http://localhost:8000/#obs/..." 링크 줄은 **제거했습니다** — 포트 번호가 실제 대시보드 포트(8767)와도 달라 원래 동작하지 않았고, 케이스별 증거가 리포트 안에 직접 보이므로 불필요합니다.

---

## 9. 제약 조건 및 다른 PRD와의 관계

### 9-1. CLAUDE.md 절대 규칙 준수

- 외부 LLM SDK(`anthropic`, `openai`, `langchain`) import 없음 — 이 기능은 수집·저장·조회만 합니다.
- 생성 테스트 파일의 자체 완결 형태 유지 — 수집 코드는 `tests/conftest.py`에만 들어가고 생성 코드 템플릿(`02_generate.py`)은 건드리지 않습니다.
- `config/locators.json`·`config/devices.json` 쓰기 없음 — 읽기만 합니다.

### 9-2. 실행 시간 오버헤드 예산 _(확정)_

| 구간 | 예산 |
|---|---|
| TC setup (프로세스 2개 기동) | ≤ 1.5초 |
| TC teardown, 미보존 | ≤ 3초 (원격 PID SIGINT + 종료 확인 + `rm`) |
| TC teardown, 보존 | ≤ 6초 (위 + 조건부 `pull` + MP4 검증) |

TC 20건 run에서 실패 3건 기준 총 증가: 20×1.5 + 17×3 + 3×6 ≈ 100초. 기존 8분 run 대비 +20%. **완료 판정 기준에 포함합니다** (§12).

고정 flush sleep 대신 기기 측 PID에 `kill -0`을 폴링합니다. 정상 종료는 즉시 진행하고, 제한 시간 초과 시 해당 PID만 SIGKILL해 불필요한 고정 지연을 피합니다.

### 9-3. 병렬 실행 PRD와의 관계 — 충돌 없음, 의존 없음

| 항목 | 이 PRD | 병렬 실행 PRD | 상호작용 |
|---|---|---|---|
| `QA_RUN_DIR` | 읽기만. 설정하지 않음 | 도입·설정 | ✅ 병렬 PRD가 설정하면 §3-1 규칙 2가 자동 발동 |
| `state/pipeline.json` 위치 | 변경 없음 | run별 이동 | ✅ 이 PRD는 의존하지 않음 |
| 스크린샷 PNG 경로 | 포인터만 기록 | `DEVICE_UDID` 하위 분리 추가 | ✅ manifest가 실제 반환 경로를 기록하므로 자동 추종 |
| `tests/conftest.py` | 훅 추가 | `_screenshots_json()` 동적 조회로 변경 | ⚠️ **같은 파일을 동시 수정** — 머지 충돌 가능. §9-4 |
| adb 동시 스트림 | 기기당 2개 추가 | 기기 3대 동시 | ⚠️ 미검증 조합 (F-5) |
| 보존 정책 수치 | 20 run / 2GB | 20 run | ✅ 동일 수치로 정렬 |

**착수 순서에 제약 없음.** 어느 쪽을 먼저 해도 다른 쪽이 깨지지 않습니다.

### 9-4. `tests/conftest.py` 동시 수정 주의

두 PRD 모두 이 파일을 고칩니다. 충돌을 줄이기 위해:

- 이 PRD의 수집 코드는 **새 헬퍼 모듈** `tests/_observability.py`에 두고, `conftest.py`에서는 훅 본문에서 그 모듈의 함수 4개(`start`, `stop`, `session_start`, `session_finish`)만 호출합니다.
- `conftest.py`에 추가되는 줄 수를 ~25줄로 제한하면, 병렬 PRD의 `_screenshots_json()` 변경과 물리적으로 겹치지 않습니다.

`tests/_observability.py`는 pytest가 수집하지 않도록 `test_`로 시작하지 않는 이름을 씁니다.

---

## 10. 에러 카탈로그

manifest의 `collect_errors[]`에 들어가는 코드입니다.

| 코드 | 의미 | 후속 동작 |
|---|---|---|
| `no_device` | `DEVICE_UDID`·`adb devices`·`devices.json` 모두에서 기기를 못 찾음 | 영상·로그 모두 미수집 |
| `video_unsupported` | `screenrecord --help` probe 실패 (F-4) | run 전체 영상 수집 off |
| `video_start_failed` | `Popen` 예외 또는 즉시 종료 | 이 attempt 영상 없음 |
| `video_pull_failed` | `adb pull` 비정상 종료 또는 0바이트 | 이 attempt 영상 없음 |
| `video_empty` | 파일은 있으나 0바이트 | 파일 삭제 후 기록 |
| `video_invalid` | MP4 moov 또는 양의 재생 시간이 없음 | 손상 파일 삭제 후 이 attempt 영상 없음 |
| `video_stop_timeout` | 기기 측 screenrecord 종료 시간 초과 | 강제 종료 후 파일 검증 |
| `ios_real_device_unsupported` | iOS 실기기 — 설계상 미지원 (§2-4) | 수집 시도 안 함 |
| `simctl_not_found` | `xcrun` 실행 불가 | iOS 수집 전체 off |
| `syslog_start_failed` | logcat / log stream 기동 실패 | 이 attempt 로그 없음 |
| `screenshot_capture_failed` | Appium 마지막 화면 PNG 저장 실패 | 영상·로그는 유지하고 스크린샷만 없음 |
| `ios_log_bundle_id_missing` | 구버전 manifest의 iOS Bundle ID 누락 기록 | UI에서 설명만 제공. 현재 수집기는 무필터 로그로 폴백하므로 새로 기록하지 않음 |
| `syslog_truncated` | 20MB 상한 초과 → 앞부분 버림 | `truncated: true` 동반 |
| `manifest_write_failed` | manifest 저장 실패 | stdout에 경고 출력, 테스트는 계속 |

API 에러:

| 코드 | HTTP | 메시지 |
|---|---|---|
| `invalid_run_id` | 400 | run_id 형식이 올바르지 않습니다 |
| `run_not_found` | 404 | 해당 run의 아티팩트를 찾을 수 없습니다 |
| `artifact_not_found` | 404 | 이 TC에는 해당 아티팩트가 없습니다 |
| `run_active` | 409 | 실행 중인 run은 삭제할 수 없습니다 |

---

## 11. CLAUDE.md 변경 필요 항목

### 변경 1 — "설정 파일" 표에 행 추가

```markdown
| `config/observability.json` | TC 실행 관측성 수집 옵션 (영상 비트레이트·로그 predicate·보존 정책). 파일이 없으면 기본값 적용 |
```

### 변경 2 — "디렉토리 규칙"에 추가

```text
state/runs/{run_id}/artifacts/  # TC 단위 영상·시스템 로그 + manifest.json
docs/EXECUTION_OBSERVABILITY_PRD.md
```

### 변경 3 — 신규 섹션 "TC 실행 관측성"

```markdown
## TC 실행 관측성

TC 실행 시 TC 단위로 화면 영상과 시스템 로그를 수집합니다. 수집은 `tests/conftest.py`의
pytest 훅에서 이뤄지며 두 실행 탭과 CLI 직접 실행 모두에 적용됩니다.

- 저장: `state/runs/{run_id}/artifacts/{node_slug}/attempt{n}/`
- 기본 보존: `on_failure` — 실패 TC와 재시도가 발생한 TC만 파일을 남깁니다
- 조회: 대시보드 결과 패널, 또는 `GET /api/run_artifacts/{run_id}`
- 보존 상한: 최근 20 run 또는 2GB 중 먼저 걸리는 쪽
- iOS 실기기는 미지원 — manifest에 `ios_real_device_unsupported`로 기록됩니다
- `QA_OBS_DISABLE=1`로 수집 전체를 끌 수 있습니다
```

### 변경 없음 확인

- "파이프라인" 섹션 — 단계 구성은 그대로입니다
- "Locator 작업 규칙" — 무관
- "Excel Import Studio", "Capture Studio" — 무관

---

## 12. 마일스톤

### M1 — TC 단위 영상 + 시스템 로그

**검증 순서**: 아래 5개 블록(선행 이슈 → 수집 → 저장·경로 → API → 프론트엔드)은 **app-developer가 구현하며 스스로 체크**합니다. 마지막 `M1 완료 판정 조건` 블록은 **app-qa가 실기 실행으로 검증**하며, 개발자 블록이 전부 체크된 뒤에 시작합니다. 개발자는 완료 판정 블록을 스스로 체크하지 않습니다 — 구현자와 검증자를 분리하는 것이 이 체크리스트의 목적입니다.

블록 간 의존: `선행 이슈` → `수집`+`저장·경로`(병행 가능) → `API` → `프론트엔드`. API 없이 프론트를 먼저 만들지 마세요.

#### 선행 이슈 해소 _(app-developer)_

- [ ] F-2: `pipeline.py:332` `terminate()` → `send_signal(SIGINT)` + 시뮬레이터 10초 녹화 재생 검증
- [ ] F-3: `pipeline.py:306` `simctl io booted` → udid 명시
- [ ] F-8: `pipeline.py` run_id 발급 후 `os.environ["QA_RUN_ID"] = run_id` 설정, run 종료 후 삭제
- [ ] F-9: iOS `log stream` teardown에 `proc.wait(timeout=5)` + `TimeoutExpired` → `proc.kill()` 폴백 추가
- [ ] F-6: `tests/_observability.py`에 `_resolve_target_device()` 구현 (에뮬레이터 `adb devices` 폴백 포함)
- [ ] F-4: `screenrecord --help` probe를 `pytest_sessionstart`에 배치
- [ ] F-1: 기존 두 녹화 경로는 유지, 제거 후보로 문서에 표시

F-1 ~ F-9 중 M1에서 **코드로 해소하지 않는** 2건 — 누락이 아니라 의도적 이월입니다.

- **F-5** (병렬 시 adb 동시 스트림 6개): M1은 단일 기기만 완료 판정 대상입니다. Q-4로 이월 — 병렬 실행 PRD M1 착수 시 검증
- **F-7** (저장 용량 실측): 코드 변경 없음. 아래 `M1 완료 판정 조건`의 `du -sh` 항목이 해소 수단이며 결과를 §3-5 표에 반영합니다 (Q-6)

#### 수집 _(app-developer)_

- [ ] `tests/_observability.py` 신규 — `session_start` / `start` / `stop` / `session_finish` 4함수
- [ ] `tests/conftest.py`에 훅 4개 연결 (추가 ~25줄, `_is_observable` 가드 포함)
- [ ] Android 영상: 기기 측 `screenrecord` PID 추적 + SIGINT + 종료 폴링 + 조건부 pull·MP4 검증
- [ ] iOS 영상: `simctl io {udid} recordVideo --codec=h264 --force` + SIGINT
- [ ] Android 로그: `logcat -b all -v threadtime -T 1` (`-c` 사용 금지)
- [ ] iOS 로그: `simctl spawn {udid} log stream --style compact` + Bundle ID가 있을 때만 `--predicate ...`
- [ ] attempt 카운터 — healing 재실행에서 manifest 이어붙이기 포함
- [ ] 보존 정책 `_should_keep()` — 재시도 발생 TC는 통과해도 보존
- [ ] 모든 수집 예외를 `collect_errors`로 흡수, 테스트 결과 무영향

#### 저장·경로 _(app-developer)_

- [ ] `QA_RUN_ID` / `QA_ARTIFACT_DIR` / `QA_OBS_KEEP` / `QA_OBS_DISABLE` 계약 (§4-1 해석 순서 4단계). 이 4개가 **전부**입니다 — `QA_RUN_DIR`은 병렬 실행 PRD 소유이며 이 PRD는 읽기만 합니다(§3-1 규칙 2, §9-3)
- [ ] `05_execute.py` — run_id 발급(`report_stamp` 재사용), `run_env` 주입, `state["last_run_id"]` 기록
- [ ] `pipeline.py` — `/api/run_all`·`/api/run_test`·`/api/run`에서 run_id 발급, healing 재실행까지 동일 run_id 유지
- [ ] `manifest.json` 원자적 저장 (`.tmp` → `Path.replace()`)
- [ ] 보존 정리 — 새 run 시작 시 20 run / 2GB 초과분 삭제, 실행 중 run 제외
- [ ] `config/observability.json` 로더 (파일 없으면 기본값)

#### API _(app-developer)_

- [ ] `GET /api/runs`
- [ ] `GET /api/run_artifacts/{run_id}`
- [ ] `GET /api/run_artifacts/{run_id}/video` — `FileResponse`로 Range 위임
- [ ] `GET /api/run_artifacts/{run_id}/logcat` — `tail` 기본 2000줄
- [ ] `GET /api/run_artifacts/{run_id}/screenshot` — attempt 내부 PNG 안전 서빙
- [ ] `DELETE /api/run_artifacts/{run_id}`
- [ ] §7-2 경로 검증 — 정규식 + `is_relative_to` 이중 가드, nodeid 직접 조립 금지

#### 프론트엔드 _(app-developer · 목업 https://claude.ai/artifact/E4JEz3FyB5cFZV9ad8oLrV)_

- [ ] 빠른 실행 탭 "모든 TC 증거 보존" 체크박스 → `obs_keep: "always"` (2값만, `never`·개별 토글 없음 — §8-1)
- [ ] 세로 결과 패널 (영상 → 시스템 로그 → 스크린샷) + attempt 전환
- [ ] 검색창과 독립된 로그 프리셋 (`오류`, `치명적`, `AndroidRuntime`, `앱 로그`)
- [ ] 아티팩트 부재 시 사유 표시
- [ ] Livetail `obs_run_start` / `obs_run_summary` 이벤트

#### M1 완료 판정 조건 _(app-qa — 개발자 블록 전부 체크 후 시작)_

- [ ] Android 에뮬레이터에서 **의도적으로 실패하는 TC 1건**을 실행하고, 대시보드에서 그 TC의 mp4가 재생되며 **실패 화면이 영상 마지막 부분에 보인다**
- [ ] 같은 실행의 `syslog.txt`에 TC 실행 구간의 logcat이 들어 있고, 앞뒤 TC의 로그가 섞여 있지 않다
- [ ] 통과한 TC의 `video.mp4`가 `on_failure` 정책에서 **디스크에 없고** 기기의 `/sdcard/qa_obs_*.mp4`도 남아 있지 않다
- [ ] `pytest-rerunfailures`로 재시도가 발생한 TC가 최종 통과해도 attempt 2개가 모두 보존된다
- [ ] iOS 시뮬레이터 TC 1건의 mp4가 QuickTime에서 재생된다 (F-2 회귀)
- [ ] `QA_OBS_DISABLE=1`로 실행하면 `state/runs/` 아래 새 디렉토리가 생기지 않고 실행 시간이 수집 전과 동일하다
- [ ] TC 20건 폴더 실행에서 **실행 시간 증가가 25% 이내** (§9-2 예산)
- [ ] TC 20건 실행 후 `du -sh state/runs/{run_id}` 실측치를 §3-5 예측표와 대조해 문서 갱신 (F-7)
- [ ] 21번째 run 시작 시 가장 오래된 run 디렉토리가 삭제된다
- [ ] `tests/unit/` 실행 시 수집이 동작하지 않는다 (`_is_observable` 가드)
- [ ] 기기를 뽑은 상태로 `05_execute.py`를 실행해도 수집 예외로 TC 결과가 바뀌지 않고, `collect_errors: ["no_device"]`가 기록된다
- [ ] `python3 -m py_compile scripts/*.py tests/*.py` 통과, `02_generate.py --strict-locators` 양 플랫폼 회귀 통과
- [ ] 좀비 프로세스 없음 — run 종료 후 `pgrep -f "adb.*logcat"` / `pgrep -f recordVideo` 결과 없음

### M2 — 네트워크 트래픽 캡처

- [ ] **스파이크 먼저**: DirectCloud 앱이 certificate pinning을 쓰는지 확인. 쓰면 M2 설계를 다시 함
- [ ] mitmproxy 프로세스 수명 관리 (run 단위 기동/종료)
- [ ] Android: `settings put global http_proxy` 설정/복원 + CA 설치 경로 확정
- [ ] iOS 시뮬레이터: `simctl keychain {udid} add-root-cert` + 프록시 설정
- [ ] HAR 저장 → `artifacts/{slug}/attempt{n}/network.har`
- [ ] manifest `network` 필드 채우기
- [ ] `GET /api/run_artifacts/{run_id}/network` + 결과 패널 4번째 탭 (요청 목록 · 상태코드 · 지연)
- [ ] 병렬 실행 시 기기별 프록시 포트 분리

---

## 13. 열린 질문 — 확정 필요

**읽는 법 (v0.2)**: 섹션 제목에 `_(확정)_`이 붙은 항목은 **그대로 구현하면 되며 질문할 필요가 없습니다.** 아래 표의 Q-1 ~ Q-7만 미확정이고, 각 질문은 §2~§12 본문에 **M1에서 쓸 기본 동작이 이미 지정돼 있습니다** — 즉 열린 질문 때문에 M1 구현이 막히는 지점은 없습니다. Q가 하는 일은 "M1 이후 이 값을 재검토한다"를 예약하는 것입니다.

M1 구현을 막던 §6의 선행 이슈는 구현에서 해소됐습니다. 특히 F-2는 SIGINT 종료로, F-8은 자식 전용 `env` 전달로 반영했습니다.

| # | 질문 | 현재 제안 | 확정 필요 시점 |
|---|---|---|---|
| **Q-1** | iOS `log stream` predicate 기본값이 DirectCloud 앱 로그를 실제로 잡는가? | §4-5 기본값으로 시작, `config/observability.json`으로 오버라이드 | M1 착수 전 — 시뮬레이터에서 앱 1회 실행 후 predicate 적용/미적용 로그량 비교 |
| **Q-2** | `always` 보존을 대시보드에 상시 노출할 것인가, 개발자 옵션으로 숨길 것인가? 영상·로그를 **개별로** 끄는 토글까지 둘 것인가? | 상시 노출 (체크박스 1개, §8-1). 개별 토글은 오버헤드 실측(§9-2) 전까지 보류 — 목업 상태 3에서 두 안을 나란히 비교 가능 | M1 프론트 착수 전 |
| **Q-3** | 기존 run 단위 녹화(`05_execute.py --record`, healing 최종 실패 녹화)를 제거할 것인가? | healing의 중복 녹화는 TC별 `screenrecord`와 인코더가 충돌하므로 제거. CLI `--record` 호환 옵션은 별도 유지 | M1에서 결정 완료 |
| **Q-4** | 병렬 실행 3대 × (screenrecord + logcat) = adb 동시 스트림 6개가 안정적인가? | 미검증. M1 완료 판정에서 제외 | 병렬 실행 PRD M1 착수 시 |
| **Q-5** | screenrecord 종료 후 고정 `sleep(2)` 대신 종료를 확인할 수 있는가? | 기기 측 PID에 `kill -0`을 폴링하고 timeout 시 해당 PID만 종료하는 방식으로 구현 | M1에서 결정 완료 |
| **Q-6** | 보존 상한 20 run / 2GB가 실제 사용 패턴에 맞는가? | F-7 실측 후 조정 | M1 완료 판정 직후 |
| **Q-7** | Appium 서버 로그(`logs/appium_server.log`)를 run 구간으로 슬라이싱해 함께 제공할 것인가? | M1 범위 밖. 세션 초기화 실패 원인 분석에 유용하므로 M1.5 후보 | M1 완료 후 |

---

## 14. 성공 지표

| 지표 | 목표 | 측정 방법 |
|---|---|---|
| 실패 1건 원인 분류 시간 | 재현 실행 불필요 — 대시보드 조회만으로 §1-2 표의 6개 원인 중 하나로 분류 | QA가 실패 10건을 분류하며 "기기를 직접 봐야 했던" 횟수 기록 |
| 증거 커버리지 | 실패 TC의 90% 이상에서 영상·로그가 둘 다 존재 | manifest의 `collect_errors` 비어 있는 비율 |
| 실행 시간 오버헤드 | ≤ 25% | 수집 on/off로 같은 TC 폴더 3회씩 실행 비교 |
| 저장 용량 | `state/runs/` 합계 2GB 이하 유지 | `du -sh state/runs` 주간 확인 |
| flake 사후 조사 가능률 | 재시도 후 통과한 TC의 attempt 1 증거가 100% 남아 있음 | §5-3 완화 규칙 검증 |

---

## 15. 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v0.14 | 2026-09-17 | 디바이스 선택 글꼴·행·상태 배지 확대, TC 10건 고정 페이지 범위 표시, TC 목록과 FAIL 증거 패널 높이 분리 및 데스크톱 sticky 적용 |
| v0.13 | 2026-09-17 | §1-1·§1-4·§3-4·§8-3 갱신 — legacy `tests/conftest.py` 실패 스크린샷 훅(`screenshots.json`)을 제거하고 `report_html.py`가 관측성 manifest의 `screenshot_url`/`video_url`을 직접 사용하도록 변경(§8-3에서 계획했던 "M1 미변경 + 아티팩트 링크 한 줄" 결정을 대체). "관측 아티팩트" 링크 줄은 요청에 따라 제거 |
| v0.12 | 2026-09-17 | 파이프라인·빠른 실행 보존 정책 라디오 그룹 충돌 수정, 선택 체크·영향 설명 강화, TC 결과 글꼴·행 높이·상태 배지 가독성 개선 |
| v0.11 | 2026-09-17 | 빠른 실행과 파이프라인 실행 화면의 920px 제한을 해제해 데스크톱 가용 폭 전체를 사용하도록 확장 |
| v0.10 | 2026-09-17 | TC 결과의 전체·성공·실패 필터와 10건 단위 페이지네이션, Android·iOS 시스템 로그 구조화·레벨 색상·검색 강조·반응형 줄바꿈 반영 |
| v0.9 | 2026-09-17 | iOS `obs_demo`에 고정 1 PASS / 2 FAIL 시나리오와 Simulator 영상·로그·스크린샷 E2E 검증 추가 |
| v0.8 | 2026-09-17 | 빠른 실행의 힐링 생략 기본 체크·단일 attempt 계약, WebSocket 누락 시 run ID 복구, 기존 결과 카드 제거, driverless ADB/simctl 스크린샷 폴백 반영 |
| v0.7 | 2026-09-17 | 보존되는 Android·iOS attempt의 마지막 화면 PNG 수집, 안전한 screenshot API, 이해하기 쉬운 독립 로그 프리셋 반영 |
| v0.6 | 2026-09-17 | 목업에 맞춰 영상 아래 로그·스크린샷을 함께 표시하고 Android·iOS·파이프라인 결과를 공통 렌더러로 통일 |
| v0.5 | 2026-09-17 | 디자인 목업 기반 2열 증거 워크스페이스, TC·attempt·증거 탭 전환, 모바일 적응형 배치 및 실패 시점 영상 이동 반영 |
| v0.4 | 2026-09-17 | attempt별 저장, 자식 전용 환경, API·대시보드, Android PID/SIGINT 녹화 및 `obs_demo` E2E 검증 반영 |
| v0.3 | 2026-09-17 | 구현 중 발견된 저장·보존·오류 처리 계약 보강 |
| v0.2 | 2026-09-17 | 개발자 검토 반영(F-8 `QA_RUN_ID` env 주입 · F-9 iOS log stream teardown), 디자인 목업 반영, 불일치 3건 해소 |
| v0.1 | 2026-09-17 | 초안 — 범위·저장 경로·수집 메커니즘·pytest 훅·선행 이슈 F-1~F-7·API·마일스톤 |

### v0.2 상세

**개발자 검토 반영** (PRD 본문에 직접 반영 완료)
- **F-8 신규** (§6) — `pipeline.py` `_spawn()`이 `env=`를 넘기지 않아 `QA_RUN_ID`가 자식 프로세스에 전달되지 않는 문제. 서버 전역을 건드리지 않는 자식 전용 `run_env` 전달로 해소. 🔴 블로커
- **F-9 신규** (§6) — iOS `simctl spawn log stream` teardown에 timeout + kill 폴백 부재. §4-5에 teardown 코드 블록 추가
- **§3-3 주석 추가** — `screenshot.path`의 기준 경로 불일치(`conftest.py:75`는 `reports/` 기준, manifest는 프로젝트 루트 기준)와 재조립 방법 명시
- 라인 번호 정정 (`05_execute.py`, `pipeline.py`, `tests/conftest.py` 참조 지점)
- **§4-1 stamp 형식 확인** — `05_execute.py:324`의 `report_stamp`가 §3-2/§7-2 정규식을 통과함을 확인하고, stamp 재사용을 명시(별도 `strftime` 금지)

**디자인 목업 반영**
- 메타 테이블과 §8 머리에 목업 URL 기재. §8에 목업 3개 상태 ↔ PRD 조항 대응표 추가
- §12 프론트엔드 블록에 목업 링크 병기

**불일치 3건 해소** (§8 표)
1. 저장 경로 — 초기 요청서의 `reports/artifacts/` 폐기, §3-2 `state/runs/{run_id}/artifacts/`로 통일 확정
2. 수집 설정 컨트롤 — M1은 보존 컨트롤(`on_failure`↔`always`)만. 영상·로그 개별 토글은 Q-2로 이월 명시
3. `never` 보존값 — CLI 전용(`QA_OBS_KEEP=never`), UI 미노출을 §5-3에 확정 기재

**최종 검토 결과**
- env var 4종(`QA_RUN_ID`·`QA_ARTIFACT_DIR`·`QA_OBS_KEEP`·`QA_OBS_DISABLE`) 표기 일관성 확인. `QA_RUN_DIR`은 병렬 실행 PRD 소유이며 이 PRD는 읽기 전용임을 §12에 재확인
- §12 체크리스트에 담당자 표기(app-developer / app-qa)와 블록 간 의존 순서 추가
- §13에 "확정 항목은 질문 불필요" 읽는 법 추가 — 열린 질문이 M1 구현을 막지 않음을 명시
- F-5 · F-7이 M1에서 코드 해소 대상이 아닌 **의도적 이월**임을 §12에 명시 (F-1~F-9 목록 완전성 확보)
