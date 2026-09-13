# QA Automation — Native App

Appium 기반 Android/iOS 앱 테스트 자동화 프로젝트입니다. native 화면을 기본으로 실행하고, 실제 WebView context가 감지된 화면만 Playwright DOM locator를 선택적으로 사용합니다.

## 현재 파이프라인

```text
01_analyze → 02_generate → 03_lint → 05_execute → 06_heal
```

`06_heal`은 실행 실패가 있을 때만 사용합니다. 전체 실행은 대시보드의 단일 `파이프라인 실행` 흐름이며, 별도의 단일/병렬 실행 유형을 제공하지 않습니다.

### 플랫폼

- Android: Appium UiAutomator2
- iOS: Appium XCUITest
- 실행 전 Appium 서버와 대상 에뮬레이터/시뮬레이터 또는 실제 디바이스가 준비되어야 합니다.
- 화면 분석 결과는 Android/iOS별로 분리해 `state/pipeline.json`에 저장합니다.

## 빠른 시작

### 설치

```bash
pip install -r requirements.txt
npm install -g appium
appium driver install uiautomator2
appium driver install xcuitest
```

`requirements.txt`에는 `pytest-rerunfailures`가 포함되어 있습니다. `05_execute.py`가 패키지 설치 여부를 감지해 `--reruns 2 --reruns-delay 5`를 자동으로 적용하므로 별도 설정이 필요 없습니다.

Android는 `ANDROID_HOME`과 `adb`를 설정하고, iOS는 Xcode 및 `xcrun simctl`을 준비합니다.

```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
export PATH="$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator"
```

### 설정

실제 앱에 맞게 다음 파일을 먼저 수정합니다.

- `config/test_data.json`: Android package/activity, iOS bundle ID/app path
- `config/devices.json`: Android emulator 또는 device, iOS simulator 또는 device capability
- `config/screens.json`: 분석 대상 화면과 화면 이동 action
- `config/locators.json`: native/WebView locator의 기준값
- `config/jira_config.json`: 이 제품 전용 Jira 프로젝트/이슈 설정

locator는 Appium용 `strategy`와 `value`를 유지하며 `surface`를 지정할 수 있습니다. `auto`는 native를 먼저 찾고 실패한 경우에만 실제 WebView context를 확인합니다.

```json
{
  "schema_version": 1,
  "targets": {
    "login.username_field": {
      "android": {"surface": "auto", "strategy": "ID", "value": "com.example:id/username", "webview": {"strategy": "label", "value": "아이디"}},
      "ios": {"strategy": "ACCESSIBILITY_ID", "value": "username"}
    }
  }
}
```

권장 locator 우선순위는 Android `ID`/accessibility, iOS `ACCESSIBILITY_ID`/predicate 또는 class chain, XPath는 마지막 수단입니다. Inspector에서 확인한 값을 registry에 저장한 뒤 코드를 생성합니다.

WebView가 없는 앱과 화면에서는 Playwright를 시작하지 않습니다. Android Chromium WebView를 Playwright로 제어하려면 CDP endpoint를 `PLAYWRIGHT_WEBVIEW_CDP_URL`에 설정합니다. CDP를 사용할 수 없는 iOS WKWebView 등의 환경은 Appium WebView context로 동일 locator를 실행합니다.

### Appium 서버 및 대시보드

```bash
ANDROID_HOME="$HOME/Library/Android/sdk" appium --address 0.0.0.0 --port 4723
python agents/dashboard/serve.py
```

브라우저에서 <http://localhost:8767>을 엽니다. 대시보드에는 Appium 연결, Android/iOS 플랫폼, 디바이스 연결, 분석·생성·린트·실행·힐링 단계, 로그, 생성 테스트, 리포트, 실행 히스토리가 표시됩니다.

### Excel Import Studio

`import/` 폴더의 `.xlsx` 테스트 케이스를 5단계 위저드로 가져옵니다.

현재 Markdown 테스트 케이스를 Import Studio 형식의 Excel로 다시 만들려면 다음 명령을 사용합니다.

```bash
python scripts/export_testcases_excel.py
```

기본 결과는 `import/qa_native_app_testcases.xlsx`이며 `전체`, `android`, `ios` 시트를 포함합니다.

```text
파일·시트 선택 → 열 매핑 → 미리보기 → 안전한 반영 → 완료
```

- 파일 카드에서 가져올 시트를 하나 이상 선택합니다.
- 열 매핑에서는 Excel `A열~Z열`을 TC ID, 제목, 사전 조건, 테스트 단계, 예상 결과 등의 QA-Native 필드에 연결합니다.
- 매핑 또는 대상 플랫폼을 변경하면 우측 검증 패널이 Excel을 다시 분석해 추가·업데이트·충돌·오류 수를 즉시 갱신합니다.
- 열 매핑 우측에는 상태 집계만 표시하고, 다음 미리보기 단계에서 전체 TC를 상태별로 필터링해 전제조건·단계·기대결과·그룹까지 확인합니다.
- 기본 매핑은 `TC ID=B열`, `제목=F열`, `사전 조건=G열`, `테스트 단계=H열`, `예상 결과=I열`, `우선순위=J열`입니다.
- 필수 필드 5개가 모두 연결되어야 미리보기 단계로 이동할 수 있습니다.
- Android/iOS를 모두 선택하면 같은 TC를 플랫폼별 Markdown으로 분리해 저장합니다.
- 시트명이 `android` 또는 `ios`이면 해당 플랫폼에만 반영하며 `testcases/{platform}/` 바로 아래에 저장합니다.
- 안전한 반영에서는 기존 파일을 보존하는 `skip-conflict`(기본값) 또는 덮어쓰는 `overwrite`를 선택합니다.
- 원본 Excel 파일은 변경하지 않습니다.

```text
import/{파일}.xlsx
  ├─ Android → testcases/android/{시트명}/tc_*.md
  └─ iOS     → testcases/ios/{시트명}/tc_*.md

testcases/android/{시트명}/ → tests/generated/android/{시트명}/
testcases/ios/{시트명}/     → tests/generated/ios/{시트명}/
```

서로 다른 시트에서 같은 TC 번호를 사용해도 시트별 하위 폴더로 분리되므로 파일이 덮어써지지 않습니다. 빠른 실행은 선택한 OS의 `tests/generated/{platform}`만 조회합니다.

### Capture Studio

대시보드의 Capture Studio 탭에서 실제 앱 화면을 보면서 요소를 선택하고 TC를 직접 생성합니다.

```text
1. 세션 설정   — OS(Android) · 디바이스 · 앱 package/activity 선택 후 세션 시작
2. 화면 탐색   — MJPEG 미러링 + hierarchy 트리에서 요소 선택
3. 동작 기록   — Tap/Input/Back 등 실제 조작을 Action Timeline에 기록
4. Locator 검토 — 후보 별점 확인 및 승인
5. 미리보기   — Markdown TC와 pytest 코드 나란히 확인
6. 저장 및 생성 — registry·TC 저장 후 02_generate.py 실행
```

**현재 구현된 기능:**
- Phase 0: FastAPI 전환 완료, 세션 충돌 방지 UX, MJPEG 환경 확인
- Phase 1: 세션 설정 화면 (앱·디바이스·그룹 설정), Appium 세션 시작 API
- `/capture/generate_from_actions` 엔드포인트: actions 배열로 pytest 코드 자동 생성
- 실패 TC에서 Capture Studio Locator 재확인 화면 재진입 (Healing 연계)

**제약사항:**
- iOS 미지원 (MJPEG 방식이 iOS Simulator에서 동작하지 않음; 후속 범위)
- MJPEG 스트리밍 포트 8093이 열려 있어야 합니다
- Capture Studio 세션과 파이프라인 실행 세션은 동시에 존재할 수 없습니다

생성된 pytest 파일은 자체 완결형(`_build_driver()` + `_el()` + class 구조 포함)으로, 수정 없이 `05_execute.py`로 바로 실행할 수 있습니다.

### CLI 실행

```bash
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

`--strict-locators`는 `config/locators.json`에 등록되지 않은 대상의 생성을 중단해 placeholder 코드 생성을 막습니다.

## Jira 실패 보고

대시보드 전체 파이프라인이 healing 3회 후에도 실패하면 `scripts/jira_reporter.py`가 이 제품의 `config/jira_config.json`을 사용해 Jira Bug를 생성합니다. 실패 스크린샷과 최종 실패 영상도 자동 첨부합니다. Jira 설정이 비활성화되었거나 토큰이 없으면 Jira만 건너뛰고 테스트 결과는 유지합니다.

```bash
export JIRA_TOKEN="<Atlassian API token>"
```

Jira 설정은 `qa-native-fixed`와 공유하지 않습니다. URL, 이메일, 프로젝트 키, 이슈 타입, 에픽, 버전은 이 프로젝트의 `config/jira_config.json`에서 별도로 관리하고, 토큰은 환경변수로만 주입합니다.

## 테스트 케이스와 locator 흐름

테스트 케이스는 `testcases/{platform}/{group}/tc_*.md`에 작성합니다. `{platform}`은 `android` 또는 `ios`이고, Import Studio에서는 `{group}`에 Excel 시트명이 사용됩니다. 최종 실행 locator의 기준값은 `config/locators.json`에서 관리합니다.

```text
TC Markdown → target_ref + config/locators.json
            → Android/iOS AppiumBy 코드 생성
            → 실패 시 최신 page_source 수집
            → 유일 후보만 registry 갱신
```

DOM을 모르는 상태에서 locator를 추측해 코드를 확정하지 않습니다. `01_analyze.py`는 native XML과 감지된 WebView DOM을 분리해 저장하고, `06_heal.py`도 locator의 surface 안에서만 후보를 찾습니다. 자세한 정책은 [docs/LOCATOR_HEALING.md](docs/LOCATOR_HEALING.md)를 참고하세요.

## 주요 파일

| 경로 | 역할 |
|---|---|
| `agents/dashboard/serve.py` | 대시보드 서버와 파이프라인 API |
| `agents/dashboard/dashboard.html` | 대시보드 UI와 Import Studio 위저드 |
| `scripts/import_excel.py` | Excel 열 매핑과 OS별 TC Markdown 변환 |
| `scripts/01_analyze.py` | Appium native UI hierarchy 수집 |
| `scripts/02_generate.py` | TC Markdown → pytest 코드 생성 |
| `scripts/03_lint.py` | 생성 코드 lint 검사 |
| `scripts/05_execute.py` | pytest/Appium 실행과 리포트 생성 |
| `scripts/06_heal.py` | 실패 locator의 Inspector 스타일 healing |
| `scripts/locator_registry.py` | locator 정규화·registry·후보 탐색 공통 모듈 |
| `config/locators.json` | 플랫폼별 locator source of truth |
| `state/pipeline.json` | 단계별 상태와 UI hierarchy snapshot |
| `docs/PRD.md` | 요소 중심 Capture Studio 제품 요구사항 |
| `docs/LOCATOR_HEALING.md` | locator healing 운영 정책 |
| `docs/CAPTURE_STUDIO_PLAN.md` | 반수동 Capture Studio 기획·화면·상태 계약 |
| `docs/mockups/capture_studio.html` | 브라우저에서 확인하는 Capture Studio 인터랙티브 목업 |
| `DESIGN.md` | 대시보드와 Import Studio 디자인 계약 |

## 산출물 및 제한사항

- 산출물: `tests/generated/`, `tests/reports/`, `state/pipeline.json`, `logs/run_*.txt`, `agents/lessons_learned.md`
- 실제 디바이스/Appium 서버가 없으면 end-to-end 실행은 검증할 수 없습니다.
- 후보가 여러 개이거나 snapshot이 없으면 자동 healing하지 않고 실패 원인을 남깁니다.
- GUI Appium Inspector를 매 실행마다 조작하지는 않지만, 같은 native hierarchy를 Appium `page_source`로 자동 수집합니다.
