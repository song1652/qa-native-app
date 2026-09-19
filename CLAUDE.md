# QA Automation — Native App 작업 가이드

이 저장소는 웹 QA 프로젝트와 분리된 Appium 기반 Android/iOS 네이티브 앱 자동화 프로젝트입니다.

## 핵심 원칙

- 외부 LLM SDK(`anthropic`, `langchain`, `openai` 등)를 제품 코드에 import하지 않습니다.
- 파이프라인 단계 결과는 `state/pipeline.json`에 기록합니다.
- 테스트 함수명은 `test_{english_snake_case}`를 사용합니다.
- 생성 테스트 파일은 드라이버 초기화까지 포함하는 자체 완결 형태를 유지합니다.
- locator의 기준값은 `config/locators.json`에서 관리합니다. 생성된 `.py` 파일은 산출물입니다.
- Android와 iOS UI hierarchy snapshot은 동일한 화면명 아래에서도 플랫폼별로 분리합니다.

## 파이프라인

```text
01_analyze → 02_generate → 03_lint → 05_execute → 06_heal
```

- `01_analyze.py`: Appium native hierarchy와 감지된 WebView DOM을 분리 수집
- `02_generate.py`: native 우선·선택적 Playwright WebView pytest 생성
- `03_lint.py`: 생성 코드 flake8 검사
- `05_execute.py`: pytest/Appium 실행 및 리포트 저장. `pytest-rerunfailures`가 설치된 경우 `--reruns 2 --reruns-delay 5` 자동 적용
- `06_heal.py`: 실패 직전 최신 hierarchy를 다시 수집하고 유일 후보만 healing

대시보드의 전체 실행은 위 순서의 단일 파이프라인입니다. 제품에는 단일/병렬 실행 유형을 별도로 노출하지 않습니다.

플랫폼별 TC 입력과 생성 코드는 다음 경로를 사용합니다.

```text
testcases/android/{group}/ → tests/generated/android/{group}/
testcases/ios/{group}/     → tests/generated/ios/{group}/
```

대시보드에서 Android를 선택하면 `testcases/android`만, iOS를 선택하면 `testcases/ios`만 실행 대상으로 노출합니다. 플랫폼 루트는 생성 결과에 다시 중첩하지 않습니다.

## Excel Import Studio

- 흐름: `파일·시트 선택 → 열 매핑 → 미리보기 → 안전한 반영 → 완료`
- 입력 파일은 `import/*.xlsx`에 두며 원본을 수정하지 않습니다.
- 파일을 선택한 뒤 카드 내부에서 하나 이상의 시트를 선택해야 합니다.
- 필수 매핑은 `tc_id`, `title`, `precondition`, `steps`, `expected`입니다.
- 선택한 Excel 열 매핑은 `scripts/import_excel.py` 변환에 실제로 전달되어야 합니다.
- `/api/import/preview`는 현재 매핑과 플랫폼을 기준으로 상태 집계와 전체 TC 상세 데이터를 반환하며, 열 매핑 화면 변경 시 다시 호출합니다.
- 미리보기 단계는 `전체/추가/업데이트/충돌/오류/동일` 필터와 전체 TC 상세 테이블을 제공하며 열 매핑 화면에는 중복 미니 테이블을 노출하지 않습니다.
- Android는 `testcases/android/{sheet}/`, iOS는 `testcases/ios/{sheet}/`에 별도 Markdown을 생성합니다.
- 단, 시트명 자체가 `android` 또는 `ios`이면 같은 OS에만 반영하고 플랫폼 루트 바로 아래에 생성하여 중첩 플랫폼 폴더를 만들지 않습니다.
- 두 플랫폼을 선택하면 플랫폼별 파일을 각각 생성하고 각 Markdown의 `## 플랫폼`에는 하나의 OS만 기록합니다.
- 파일명 충돌은 시트별 하위 폴더로 방지합니다.
- 안전한 반영의 기본 정책은 `skip-conflict`이며 기존 Markdown을 보존합니다. 명시적으로 `overwrite`를 선택하면 동일 경로 파일을 덮어씁니다.

## Capture Studio

대시보드의 Capture Studio 탭에서 실제 앱 화면을 보며 요소를 선택하고 TC를 직접 생성합니다.

**구성 요소:**
- FastAPI 세션 API, 플랫폼별 세션 충돌 방지, Android MJPEG/iOS polling 화면, 세션 설정 화면
- hierarchy 트리 렌더링·노드 선택, 동작 기록(tap/scroll/back/wait), Locator 후보·승인
- `저장 및 생성` 버튼 → `/capture/generate_from_actions` → 자체 완결형 pytest 파일 생성
- 생성 코드 구조: `_build_driver()` + `_el()` + `_ios_tap()` (iOS 전용) + class + test 함수
- Healing 연계: 실패 TC에서 Locator 검토 단계 재진입
- **iOS 화면 미러링**: XCUITest + `GET /capture/screenshot` polling (1.2초), 25회 실패 후 에러 표시 (WDA 안정화 30초 여유)
- **화면 전환 자동 감지**: `GET /capture/page_source_hash` 4초 폴링 → hash 변경 시 hierarchy 자동 새로고침 (쿨다운 3초)
- **back 액션**: 실행 후 1.2초 뒤 hierarchy 자동 새로고침
- **세션 복구**: mirror 에러 시 "🔄 세션 재연결" 버튼 → `csReLaunch()` → Back 없이 드라이버 재시작
- **Nova MCP** (`routes/mcp.py`): HTTP+SSE MCP 서버, JSON-RPC 2.0, 툴 9종. Claude Code에서 MCP 툴 호출 시 자동 연결, 대시보드 MCP ON/OFF 칩으로 상태 확인·수동 해제
- **TC 생성 소스 필터**: `/capture/generate_from_actions`에 `source_filter` 파라미터 추가 (`all`|`user`|`mcp`, 기본 `all`). `screenshot`·`hierarchy` 등 비실행 타입은 자동 제거. 생성 TC docstring에 출처(user/mcp/mixed)·액션 수 표기
- **Livetail**: Livetail 버튼이 Capture Studio 세션 없이도 항상 표시. 페이지 로드 시 WebSocket 자동 연결
- **파이프라인 Livetail 연동**: `pipeline.py`의 각 단계 시작·완료가 Livetail에 `source: pipeline` 이벤트로 실시간 표시 (단건 `/api/run` 포함)

**TC 파일 명명 규칙:**
- `tc_group` → 폴더명: `tests/generated/{platform}/{tc_group}/`
- `tc_id` → 파일명: `{tc_id}.py` (같은 그룹에 여러 TC 누적 가능)
- 예: group=`settings`, id=`tc_settings_v1` → `tests/generated/android/settings/tc_settings_v1.py`
- `pytest tests/generated/android/settings/` 한 번에 그룹 전체 실행

**Locator 생성 규칙:**
- Android: app-specific `resource-id` > `content-desc` > `text` > generic-id(android:id/*) > class
- iOS: `label`(사람이 읽는 텍스트) > `name`(bundle ID 스타일) > predicate > xpath
- iOS accessibility-id tap → `_ios_tap(label)` 헬퍼 생성: `find_element` 실패 시 `mobile: scroll` 자동 스크롤 후 탭

**제약 및 주의사항:**
- Android: MJPEG 스트리밍은 포트 8093, Appium 서버에 `--allow-insecure=uiautomator2:adb_screen_streaming` 플래그 필요 (Appium 3.x)
- iOS: XCUITest 세션에는 `bundle_id`와 `device_name`(Simulator 이름)이 필요합니다. `xcrun simctl list`로 정확한 이름 확인
- **iOS XCUITest 세션 충돌**: 시뮬레이터당 세션 1개만 허용. Capture Studio iOS 세션이 열려 있으면 iOS pytest TC를 동시에 실행할 수 없음 (반대도 동일). 충돌 시 드라이버가 None이 되며 "🔄 세션 재연결" 버튼으로 복구
- **플랫폼별 독립 가드**: iOS Capture Studio 세션이 열려 있어도 Android 파이프라인 실행 가능 (반대도 동일). 같은 플랫폼에서만 세션이 충돌합니다
- Android 세션 key는 `app_package` / `app_activity`, iOS는 `bundle_id`를 사용합니다

## Locator 작업 규칙

1. Appium Inspector 또는 native hierarchy에서 요소 속성을 확인합니다.
2. 확인한 플랫폼별 locator를 `config/locators.json`에 저장합니다.
3. strict 생성으로 registry 누락을 차단합니다.
4. 실패 시 `06_heal.py`가 locator surface에 따라 native XML 또는 WebView DOM에서 후보를 찾습니다.
5. 후보가 유일하고 신뢰도가 높을 때만 registry를 갱신합니다.
6. 후보가 모호하거나 snapshot이 없으면 자동 변경하지 않고 실패 상태로 남깁니다.

```bash
python scripts/02_generate.py --platform android --strict-locators
python scripts/02_generate.py --platform ios --strict-locators
```

상세 healing 정책은 [docs/LOCATOR_HEALING.md](docs/LOCATOR_HEALING.md)에 있습니다.

## 설정 파일

| 파일 | 역할 |
|---|---|
| `config/test_data.json` | 앱 package/activity, bundle ID, 테스트 데이터 |
| `config/devices.json` | Android/iOS capability. **스키마 (v0.6 확정)**: 모든 모드 키는 **단수형 배열** — `android.emulator[]`, `android.real_device[]`, `ios.simulator[]`, `ios.real_device[]`. 각 항목에 `default: true`로 기본 디바이스 지정. **케이스 규칙**: Appium에 직접 전달되는 필드는 camelCase(`deviceName`, `mjpegServerPort` 등), 대시보드 전용 필드는 snake_case(`default`, `wifi_ip`, `team_id`). ENV Setup UI에서 관리 — 직접 편집 시 배열 형식·케이스 규칙 유지 필수. **MJPEG caps**는 각 emulator 항목 안에 flat하게 포함 (`mjpegServerPort`, `mjpegScalingFactor`, `mjpegServerScreenshotQuality`). **Android 실기기 식별자**: `android.real_device[]` 항목에서 adb serial은 `udid` 키에 저장하고, `/api/env/status` 응답에서는 `serial`로 노출됨 — `config/devices.json` 직접 편집 시 `udid` 키 사용 필수. |
| `config/screens.json` | 분석 화면과 진입 action |
| `config/locators.json` | 플랫폼별 target locator registry |
| `config/jira_config.json` | 이 제품 전용 Jira 프로젝트/이슈 설정 |
| `config/observability.json` | TC 실행 관측성 옵션. 파일이 없으면 코드 기본값 적용 |

`config/locators.json` target key는 `{tc_slug}.{selector_key}` 형식입니다. entry의 `surface`는 `auto`(native 우선), `native`, `webview` 중 하나이며 WebView locator는 `webview` 객체에 별도로 둡니다. WebView가 감지되지 않으면 Playwright를 시작하지 않으며, CDP 미지원 WebView는 Appium context로 실행합니다.

대시보드 전체 실행이 healing 3회 후에도 실패하면 `scripts/jira_reporter.py`가 이 프로젝트의 Jira 설정으로 Bug를 생성하고 스크린샷/영상을 첨부합니다. `JIRA_TOKEN`이 없으면 Jira 보고만 건너뛰며 테스트 결과는 유지합니다. Jira 설정은 다른 제품과 공유하지 않습니다.

## 실행 명령

```bash
appium --address 127.0.0.1 --port 4723
python agents/dashboard/serve.py

# Android
python scripts/01_analyze.py --platform android --mode emulator
python scripts/02_generate.py --platform android --strict-locators
python scripts/03_lint.py --platform android
python scripts/05_execute.py --platform android

# iOS
python scripts/01_analyze.py --platform ios --mode simulator
python scripts/02_generate.py --platform ios --strict-locators
python scripts/03_lint.py --platform ios
python scripts/05_execute.py --platform ios
```

## 디렉토리 규칙

```text
config/locators.json       # locator source of truth
config/{devices,screens,test_data}.json
scripts/                   # 분석·생성·린트·실행·힐링
import/                    # Import Studio Excel 입력
testcases/{android,ios}/   # OS별 입력 TC Markdown
tests/generated/{android,ios}/ # OS별 생성 코드
tests/reports/             # 실행 리포트
state/pipeline.json        # 실행 상태와 snapshot
state/capture_session.json # Capture Studio 세션 상태
state/runs/{run_id}/artifacts/ # TC attempt별 영상·시스템 로그 + manifest.json
logs/                      # 단계별 로그
docs/LOCATOR_HEALING.md    # healing 정책
docs/CAPTURE_STUDIO_PLAN.md # Capture Studio 구현 플랜
```

## 변경 시 검증

```bash
python3 -m py_compile scripts/*.py
python3 scripts/02_generate.py --platform android --strict-locators
python3 scripts/02_generate.py --platform ios --strict-locators
git diff --check
```

`pytest-rerunfailures` 동작 확인: `pip show pytest-rerunfailures` 후 `05_execute.py` 실행 로그에서 `--reruns 2 --reruns-delay 5` 포함 여부를 확인합니다.

실제 Appium 실행은 연결된 서버와 디바이스가 있을 때 별도로 수행합니다.

## ENV Setup UI

대시보드 ENV Setup 탭에서 Appium 서버와 디바이스(에뮬레이터/시뮬레이터/실기기)를 관리합니다.

**PRD**: `docs/ENV_SETUP_PRD.md` (v0.8 — F1·F3·F6 코드 반영 완료 · US-3 디바이스 CRUD API)  
**디자인 스펙**: https://claude.ai/code/artifact/55ba3c71-e480-4493-b60a-d0a2aad70fb1  
**목업**: https://claude.ai/code/artifact/466103b7-6be2-4811-b34e-f0c088462334

**M2.0 마이그레이션 선행 5단계** (M2.0 스프린트 착수 시 순서대로 수행):
1. `config/devices.json` 단일 객체 → 배열 전환 + `.bak` 백업
2. `utils/system.py`에 `default: true` 리더 함수 추가 (dict 하위호환 분기 포함)
3. 소비 코드 3곳 교체: `android_driver.py:35`, `02_generate.py:388`, `capture.py:645`
4. `capture.py:128-130` MJPEG 하드코딩 제거 → devices.json에서 읽도록 통일
5. caps 조립 시 `default`/`wifi_ip`/`team_id` 등 비-Appium 필드 제거

각 단계 후 `python3 -m py_compile scripts/*.py` + `02_generate --strict-locators` 회귀 확인 필수.

**Appium 5값 상태 모델**: `stopped` / `starting` / `managed` / `external` / `error`  
`error` 상태는 자동 해소 없음 — 사용자가 "다시 시도" 클릭 또는 명시적 액션 시에만 전이.

**Appium 바인딩**: `--address 127.0.0.1` 고정. Appium은 인증 없이 앱 설치·파일 전송·셸 실행 권한을 노출하므로 `0.0.0.0` 바인딩을 금지합니다. 원격 디바이스 팜이 필요하면 인증·TLS를 포함한 별도 설계로 다룹니다.

**에뮬레이터/시뮬레이터는 Appium과 독립적으로 시작합니다.** Appium이 `stopped`/`error` 상태여도 AVD 시작·시뮬레이터 부팅이 가능합니다. Appium은 **Capture Studio 세션 시작과 파이프라인 실행**의 선행 조건일 뿐이며, 디바이스 컨트롤에 잠금(`locked`) 상태를 표시하지 않습니다.

**Capture 가드는 플랫폼별로 분리됩니다**: `is_capture_active(platform: str | None = None)` (`agents/dashboard/utils/state.py`). 인자를 생략하면 플랫폼 무관 전체 확인이고, `"android"` / `"ios"`를 넘기면 해당 플랫폼 세션만 확인합니다. `state/capture_session.json`에 `platform` 필드가 없는 구버전 레코드는 보수적으로 `True`(차단)를 반환합니다. 무인자 기존 호출부는 하위호환으로 그대로 동작합니다.

**API 가드 정책**:
- `POST /api/env/appium/stop`: `is_capture_active()` (플랫폼 무관 전체) 활성 시 `403 capture_session_active`, 파이프라인 실행 중 `409 pipeline_running`. **`external` 상태에서도 중지 가능** — `lsof -ti :<port>`로 PID 탐색 후 SIGTERM (v1.0)
- `POST /api/env/android/avd/stop`: `is_capture_active("android")` 활성 시 `403 capture_session_active` — iOS Capture 세션은 차단 사유가 아님
- `POST /api/env/ios/simulator/stop`: `is_capture_active("ios")` 활성 시 `403 capture_session_active` — Android Capture 세션은 차단 사유가 아님
- `POST /api/env/android/avd/start`: 다른 에뮬레이터 실행 중 `409 already_running`. **Appium 상태 가드 없음**
- `POST /api/env/ios/simulator/start`: **Appium 상태 가드 없음**. 생략 시 `devices.json`의 `default: true` 시뮬레이터를 사용. `subprocess.Popen`(비동기)으로 즉시 202 + `status: "starting"` 반환 — 3초 폴링이 `simctl list` Booted 감지 시 `running` 전환 (v1.0)

> ⚠️ start 계열(`avd/start`, `simulator/start`)은 아직 `is_capture_active()`를 무인자로 호출해 무관한 플랫폼 세션도 시작을 차단합니다. 플랫폼 분리는 stop 계열에만 적용된 상태입니다 (PRD §15-7 항목 5).

**디바이스 추가/삭제**: `POST /api/env/{android,ios}/{add,remove}` 4종이 구현되어 있으며, 모든 `devices.json` 쓰기는 `agents/dashboard/utils/state.py`의 `save_devices_json()`을 경유합니다 (`.json.tmp` 기록 → `Path.replace()` 원자적 교체, `default` 중복 시 `ValueError` → 400). `config/devices.json`에 직접 `write_text()`하는 경로를 새로 만들지 마세요.

- 요청 스키마: `add` = `{mode, deviceName, avd?|udid?, default?}`, `remove` = `{mode, deviceName}`. `mode`는 Android `emulator|real_device`, iOS `simulator|real_device`
- 마지막 1개 항목은 삭제 불가 (`400 last_device`). `default: true` 항목 삭제 시 남은 첫 항목이 승계
- 대시보드 ENV Setup 탭에 추가 버튼·모달·✕ 삭제 UI가 구현되어 있습니다 (PRD §15-7 항목 1 완료)
- add·remove에 Capture/파이프라인 **잠금 가드가 구현**되어 있습니다. 세션 활성 중 호출 시 403이 반환됩니다 (PRD §15-7 항목 2 완료)

`is_capture_active(platform: str | None = None)` — 인자를 생략하면 전체 플랫폼을 확인합니다(기존 무인자 호출부와 하위호환). 세션 레코드에서 플랫폼을 식별할 수 없으면 보수적으로 `True`를 반환합니다.

## TC 실행 관측성

`tests/generated/` TC 실행 시 attempt 단위 화면 영상과 시스템 로그를 수집합니다.

- 저장: `state/runs/{run_id}/artifacts/{node_slug}/attempt{n}/`
- 기본 보존: `on_failure`; 대시보드에서 `always` 선택 가능
- 조회: 대시보드 증거 패널 또는 `GET /api/run_artifacts/{run_id}`
- 보존 상한: 최근 20 run 및 총 2GB
- healing과 pytest rerun은 최초 run_id 아래 다음 attempt로 누적
- `QA_OBS_DISABLE=1` 또는 `QA_OBS_KEEP=never`이면 수집 프로세스를 시작하지 않음
- iOS 실기기는 M1에서 미지원

## 연속 Appium 세션 주의사항

3개 이상의 테스트를 순차 실행할 때 3번째 이후 세션에서 UiAutomator2 초기화 실패가 발생할 수 있습니다. `pytest-rerunfailures`(`--reruns 2 --reruns-delay 5`)가 이를 제품 레벨에서 처리합니다. 테스트 파일을 수정하지 않아도 됩니다. 재시도 후에도 반복 실패하면 `agents/lessons_learned.md`를 확인하고 Appium 서버를 재기동하세요.

## 대시보드 서버 재시작 시 프로세스 복구

대시보드 서버(`serve.py`)가 재시작되면 `state/running_procs.json`에 저장된 PID를 읽어 살아있는 프로세스를 자동으로 `_running` dict에 복원합니다(`shared.restore_running_procs()`). 덕분에:

- 재시작 후에도 `/api/cancel`로 실행 중인 프로세스를 정상 취소할 수 있습니다.
- 폴링(`/api/run_log`)이 `done: false`를 올바르게 반환해 UI가 "완료"로 오판하지 않습니다.
- 중복 실행 가드가 재시작 전 프로세스도 감지합니다.

대시보드 WebSocket(Livetail)이 서버 재시작으로 끊기면 지수 백오프(1초→2초→…→30초)로 자동 재연결합니다. 재연결 후 이후 이벤트부터 정상 수신됩니다.

`state/running_procs.json`은 `_running`의 살아있는 PID 스냅샷입니다. 직접 편집하지 마세요. 프로세스가 정상 종료되면 자동으로 제거됩니다.
