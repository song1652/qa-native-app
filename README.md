# QA Automation — Native App

Appium 기반 Android/iOS 네이티브 앱 테스트 자동화 프로젝트입니다. 대시보드 또는 CLI에서 UI hierarchy 분석, 테스트 코드 생성, 린트, 실행, locator healing을 하나의 파이프라인으로 수행합니다.

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
- `config/locators.json`: 테스트 대상 native locator의 기준값
- `config/jira_config.json`: 이 제품 전용 Jira 프로젝트/이슈 설정

locator는 `strategy`와 `value`를 명시합니다.

```json
{
  "schema_version": 1,
  "targets": {
    "login.username_field": {
      "android": {"strategy": "ID", "value": "com.example:id/username"},
      "ios": {"strategy": "ACCESSIBILITY_ID", "value": "username"}
    }
  }
}
```

권장 locator 우선순위는 Android `ID`/accessibility, iOS `ACCESSIBILITY_ID`/predicate 또는 class chain, XPath는 마지막 수단입니다. Inspector에서 확인한 값을 registry에 저장한 뒤 코드를 생성합니다.

### Appium 서버 및 대시보드

```bash
ANDROID_HOME="$HOME/Library/Android/sdk" appium --address 0.0.0.0 --port 4723
python agents/dashboard/serve.py
```

브라우저에서 <http://localhost:8767>을 엽니다. 대시보드에는 Appium 연결, Android/iOS 플랫폼, 디바이스 연결, 분석·생성·린트·실행·힐링 단계, 로그, 생성 테스트, 리포트, 실행 히스토리가 표시됩니다.

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

테스트 케이스는 `testcases/{app}/tc_*.md`에 작성합니다. 최종 실행 locator의 기준값은 `config/locators.json`에서 관리합니다.

```text
TC Markdown → target_ref + config/locators.json
            → Android/iOS AppiumBy 코드 생성
            → 실패 시 최신 page_source 수집
            → 유일 후보만 registry 갱신
```

DOM을 모르는 상태에서 locator를 추측해 코드를 확정하지 않습니다. `01_analyze.py`와 `06_heal.py`는 Appium `page_source`로 native hierarchy를 수집합니다. 자세한 정책은 [docs/LOCATOR_HEALING.md](docs/LOCATOR_HEALING.md)를 참고하세요.

## 주요 파일

| 경로 | 역할 |
|---|---|
| `agents/dashboard/serve.py` | 대시보드 서버와 파이프라인 API |
| `scripts/01_analyze.py` | Appium native UI hierarchy 수집 |
| `scripts/02_generate.py` | TC Markdown → pytest 코드 생성 |
| `scripts/03_lint.py` | 생성 코드 lint 검사 |
| `scripts/05_execute.py` | pytest/Appium 실행과 리포트 생성 |
| `scripts/06_heal.py` | 실패 locator의 Inspector 스타일 healing |
| `scripts/locator_registry.py` | locator 정규화·registry·후보 탐색 공통 모듈 |
| `config/locators.json` | 플랫폼별 locator source of truth |
| `state/pipeline.json` | 단계별 상태와 UI hierarchy snapshot |
| `docs/LOCATOR_HEALING.md` | locator healing 운영 정책 |

## 산출물 및 제한사항

- 산출물: `tests/generated/`, `tests/reports/`, `state/pipeline.json`, `logs/run_*.txt`, `agents/lessons_learned.md`
- 실제 디바이스/Appium 서버가 없으면 end-to-end 실행은 검증할 수 없습니다.
- 후보가 여러 개이거나 snapshot이 없으면 자동 healing하지 않고 실패 원인을 남깁니다.
- GUI Appium Inspector를 매 실행마다 조작하지는 않지만, 같은 native hierarchy를 Appium `page_source`로 자동 수집합니다.
