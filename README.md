# QA Automation — App (Appium)

> **독자**: 사람 — 신규 진입점. 설치·실행 방법과 내부 문서 링크 모음.

Android / iOS 앱 테스트 자동화 시스템.  
Appium 기반으로 UI XML 수집 → 테스트 코드 자동 생성 → 린트 → 실행 → 자가 힐링까지 전 과정을 대시보드에서 실행.

---

## 실행 파일 목록

| 파일 | 언제 실행? | 하는 일 |
|---|---|---|
| `agents/dashboard/serve.py` | 대시보드 서버 실행 | http://localhost:8767 에서 파이프라인 실행·모니터링·로그 확인 |
| `scripts/01_analyze.py` | UI 수집 | Appium으로 앱 접속 → screens.json 기반 page_source XML 수집 |
| `scripts/02_generate.py` | 테스트 코드 생성 | TC 마크다운 → pytest 코드 자동 생성 |
| `scripts/03_lint.py` | 린트 검사 | 생성된 코드 flake8 검사 |
| `scripts/05_execute.py` | 테스트 실행 | pytest 실행 + HTML 리포트 생성 |
| `scripts/06_heal.py` | 자동 힐링 | 실패 TC 자동 패치 (최대 3회) |

> **대시보드 ▶ 전체 실행** 버튼으로 01 → 02 → 03 → 05 → 06 순서가 자동 실행됩니다.

---

## 사전 요구사항

| 항목 | 최소 버전 | 확인 방법 |
|------|----------|----------|
| **Python** | 3.12+ (pyenv 권장) | `python --version` |
| **Node.js** | 18+ (nvm v20 권장) | `node --version` |
| **Appium** | 2.x | `appium --version` |
| **Android Studio** | 최신 (Android 테스트 시) | Android Studio 실행 확인 |
| **Xcode** | 15+ (iOS 테스트 시) | `xcodebuild -version` |

---

## 설치

### 1. Python (pyenv)

```bash
# pyenv 설치 (미설치 시)
brew install pyenv
pyenv install 3.12.9
pyenv global 3.12.9
```

### 2. Node.js (nvm)

```bash
# nvm 설치 (미설치 시)
brew install nvm
nvm install 20
nvm use 20
```

### 3. Python 패키지

```bash
pip install -r requirements.txt
```

| 패키지 | 용도 |
|---|---|
| `appium-python-client` | Appium Python 드라이버 |
| `pytest` | 테스트 실행 |
| `pytest-html` | HTML 리포트 생성 |
| `pytest-json-report` | JSON 리포트 생성 (결과 파싱 정확도 향상) |
| `flake8` | 린트 검사 |

### 4. Appium 및 드라이버

```bash
npm install -g appium
appium driver install uiautomator2   # Android
appium driver install xcuitest       # iOS
```

### 5. Android 환경 설정

1. [Android Studio](https://developer.android.com/studio) 설치
2. **SDK Manager** → `Android SDK Platform-Tools` 설치 (adb 포함)
3. **AVD Manager** → 에뮬레이터 생성 (API 30+)
4. 환경변수 설정 (`~/.zshrc` 또는 `~/.bash_profile`에 추가):

```bash
export ANDROID_HOME=$HOME/Library/Android/sdk
export PATH=$PATH:$ANDROID_HOME/platform-tools
export PATH=$PATH:$ANDROID_HOME/emulator
```

설치 확인:

```bash
adb --version
emulator -list-avds   # 생성한 AVD 이름 확인 → devices.json의 avd 값에 입력
```

### 6. iOS 환경 설정 (Mac 전용)

1. App Store에서 **Xcode** 설치
2. Command Line Tools 설치:

```bash
xcode-select --install
```

3. 시뮬레이터 UDID 확인:

```bash
xcrun simctl list devices booted
# 부팅된 시뮬레이터가 없으면: xcrun simctl boot "iPhone 16"
```

4. (실기기 테스트 시) libimobiledevice 설치:

```bash
brew install libimobiledevice
idevice_id -l   # 연결된 실기기 UDID 확인
```

### 7. Appium 서버 실행

```bash
ANDROID_HOME=~/Library/Android/sdk \
  appium --address 0.0.0.0 --port 4723
```

---

## 실행

### 대시보드 (권장)

```bash
~/.pyenv/versions/3.12.9/bin/python agents/dashboard/serve.py
# http://localhost:8767
```

1. 플랫폼 선택 (Android / iOS)
2. **▶ 전체 실행** 클릭 → 파이프라인 자동 순차 실행

### 직접 실행

```bash
# Android
python scripts/01_analyze.py --platform android --mode emulator
python scripts/02_generate.py --platform android
python scripts/03_lint.py --platform android
python scripts/05_execute.py --platform android

# iOS
python scripts/01_analyze.py --platform ios --mode simulator
python scripts/02_generate.py --platform ios
python scripts/03_lint.py --platform ios
python scripts/05_execute.py --platform ios
```

---

## 설정 파일 작성

### config/screens.json — 화면 정의

```json
{
  "screen_key": {
    "description": "화면 설명",
    "actions": [
      {"type": "tap", "target": "element-id"},
      {"type": "input_text", "target": "field-id", "value_key": "account.id"}
    ],
    "platform": ["android", "ios"]
  }
}
```

- `actions: []` — 앱 초기 화면 그대로 (탐색 불필요)
- `platform` — `["android"]` / `["ios"]` / `["android", "ios"]`

### config/test_data.json — 앱 식별자

```json
{
  "app": {
    "android": {
      "package":  "com.example.app",
      "activity": "com.example.app.MainActivity",
      "app_path": ""
    },
    "ios": {
      "bundle_id": "com.example.app",
      "app_path":  ""
    }
  }
}
```

- `app_path` 비워두면 이미 설치된 앱 사용, 절대경로 지정 시 `.apk`/`.ipa` 설치 후 실행

### config/devices.json — Appium Capabilities

```json
{
  "android": {
    "emulator": {
      "deviceName": "Android Emulator",
      "platformVersion": "14.0",
      "automationName": "UiAutomator2",
      "avd": "avd_name",
      "noReset": true,
      "forceAppLaunch": true,
      "shouldTerminateApp": true
    }
  },
  "ios": {
    "simulator": {
      "deviceName": "iPhone 16",
      "platformVersion": "18.5",
      "automationName": "XCUITest",
      "udid": "simulator-udid"
    }
  }
}
```

- Android UDID 확인: `adb devices`
- iOS Simulator UDID 확인: `xcrun simctl list devices booted`

---

## 테스트 케이스 작성

케이스는 `testcases/` 하위 앱 폴더에 `.md` 파일로 작성합니다. **1파일 = 1케이스.**

```
testcases/
  {앱이름}/
    tc_001_main_screen.md
    tc_002_search_bar.md
    ...
```

**케이스 파일 형식:**

```markdown
---
id: tc_001
priority: high
tags: [smoke]
---
# 메인 화면 진입 확인

## Steps
1. 앱 실행
2. 메인 화면 로드 확인

## Expected
- 메인 화면 타이틀이 표시되어야 한다.
```

파일명 규칙: `tc_{번호}_{english_snake_case}.md`

---

## 산출물

| 파일 | 내용 |
|---|---|
| `tests/generated/android/{앱}/tc_*.py` | 생성된 Android pytest 코드 |
| `tests/generated/ios/{앱}/tc_*.py` | 생성된 iOS pytest 코드 |
| `tests/reports/report_android.html` | Android HTML 리포트 |
| `tests/reports/report_ios.html` | iOS HTML 리포트 |
| `tests/reports/recordings/*.mp4` | 힐링 3회 실패 시 자동 저장 영상 |
| `state/pipeline.json` | 파이프라인 실행 상태 |

---

## 파일 구조

```
qa-native-app/
├── config/
│   ├── screens.json       # 화면 정의
│   ├── devices.json       # Appium Capabilities
│   └── test_data.json     # 앱 패키지명 / 계정
├── scripts/
│   ├── drivers/
│   │   ├── android_driver.py
│   │   └── ios_driver.py
│   ├── 01_analyze.py
│   ├── 02_generate.py
│   ├── 03_lint.py
│   ├── 05_execute.py
│   ├── 06_heal.py
│   └── report_html.py
├── testcases/             # TC 마크다운 (앱별 서브폴더)
├── tests/
│   ├── generated/         # 생성된 pytest 파일
│   └── reports/           # HTML 리포트 + 영상
├── state/
│   └── pipeline.json      # 파이프라인 상태
├── agents/
│   ├── dashboard/
│   │   └── serve.py       # 대시보드 서버 (포트 8767)
│   └── lessons_learned.md
└── requirements.txt
```

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `Appium 연결 확인하세요` | Appium 서버 미실행 | `ANDROID_HOME=~/Library/Android/sdk appium --port 4723` 실행 |
| `Android 디바이스 없음` | 에뮬레이터 미실행 또는 adb 미연결 | `adb devices` 확인 후 에뮬레이터 실행 |
| `iOS Simulator 없음` | 시뮬레이터 미부팅 | Xcode에서 시뮬레이터 실행 또는 `xcrun simctl boot {udid}` |
| 코드 생성 실패 | TC 마크다운 형식 오류 | `testcases/` 파일 형식 확인 |
| lint 실패 | 생성 코드 문법 오류 | 해당 `.py` 직접 수정 후 lint 재실행 |
| 힐링 3회 모두 실패 | selector / assertion 불일치 | `tests/reports/recordings/` 영상 확인 후 수동 수정 |
| `ANDROID_HOME` 오류 | Appium 환경변수 미설정 | Appium 서버 실행 시 `ANDROID_HOME` 명시 |

