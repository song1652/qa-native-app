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

## 설치

### 0. Homebrew (미설치 시)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 1. Python (pyenv)

```bash
brew install pyenv
pyenv install 3.12.9
pyenv global 3.12.9
```

`~/.zshrc` (또는 `~/.bash_profile`)에 추가:

```bash
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
```

적용:

```bash
source ~/.zshrc
python --version   # Python 3.12.9 확인
```

### 2. Node.js (nvm)

```bash
brew install nvm
```

`~/.zshrc`에 추가:

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"
```

적용:

```bash
source ~/.zshrc
nvm install 20
nvm use 20
node --version   # v20.x.x 확인
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
appium --version   # 2.x 확인
```

### 5. Android 환경 설정

1. [Android Studio](https://developer.android.com/studio) 설치
2. Android Studio 실행 → **SDK Manager** 열기:
   - `SDK Platforms` 탭 → **Android 14.0 (API 34)** 이상 체크 후 설치
   - `SDK Tools` 탭 → **Android SDK Build-Tools**, **Android SDK Platform-Tools** 체크 후 설치
3. **AVD Manager** → 에뮬레이터 생성 (API 30+)
4. `~/.zshrc`에 환경변수 추가:

```bash
export ANDROID_HOME=$HOME/Library/Android/sdk
export PATH=$PATH:$ANDROID_HOME/platform-tools
export PATH=$PATH:$ANDROID_HOME/emulator
```

적용 및 확인:

```bash
source ~/.zshrc
adb --version
emulator -list-avds   # 생성한 AVD 이름 확인 → devices.json의 avd 값에 입력
```

### 6. iOS 환경 설정 (Mac 전용)

1. App Store에서 **Xcode** 설치 (15 이상)
2. Command Line Tools 설치:

```bash
xcode-select --install
```

3. 시뮬레이터 UDID 확인:

```bash
# 시뮬레이터 부팅
xcrun simctl boot "iPhone 16"
# UDID 확인
xcrun simctl list devices booted
# → devices.json의 udid 값에 입력
```

4. (실기기 테스트 시) libimobiledevice 설치:

```bash
brew install libimobiledevice
idevice_id -l   # 연결된 실기기 UDID 확인
```

### 7. config 파일 수정

설치 후 반드시 아래 두 파일을 실제 앱 정보로 수정해야 합니다.

**`config/test_data.json`** — 앱 패키지명 입력:

```json
{
  "app": {
    "android": {
      "package":  "com.example.app",        ← 실제 패키지명으로 변경
      "activity": "com.example.app.MainActivity",  ← 실제 액티비티로 변경
      "app_path": ""
    },
    "ios": {
      "bundle_id": "com.example.app",       ← 실제 번들 ID로 변경
      "app_path":  ""
    }
  }
}
```

**`config/devices.json`** — 에뮬레이터/시뮬레이터 정보 입력:

```json
{
  "android": {
    "emulator": {
      "deviceName":        "Android Emulator",
      "platformVersion":   "14.0",
      "automationName":    "UiAutomator2",
      "avd":               "여기에_avd_이름",   ← emulator -list-avds 결과값
      "noReset":           true,
      "forceAppLaunch":    true,
      "shouldTerminateApp": true
    }
  },
  "ios": {
    "simulator": {
      "deviceName":      "iPhone 16",
      "platformVersion": "18.5",
      "automationName":  "XCUITest",
      "udid":            "여기에_UDID"          ← xcrun simctl list devices booted 결과값
    }
  }
}
```

### 8. Appium 서버 실행

테스트 실행 전 항상 먼저 실행:

```bash
ANDROID_HOME=~/Library/Android/sdk \
  appium --address 0.0.0.0 --port 4723
```

---

## 실행

### 대시보드 (권장)

```bash
python agents/dashboard/serve.py
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

## 설정 파일 상세

### config/screens.json — 화면 정의

분석 단계에서 어떤 화면을 탐색할지 지정합니다.

```json
{
  "screen_key": {
    "description": "화면 설명",
    "actions": [
      {"type": "tap",        "target": "element-id"},
      {"type": "input_text", "target": "field-id", "value_key": "account.id"}
    ],
    "platform": ["android", "ios"]
  }
}
```

- `actions: []` — 앱 초기 화면 그대로 (탐색 불필요)
- `platform` — `["android"]` / `["ios"]` / `["android", "ios"]`
- `value_key` — `test_data.json`의 경로 (예: `"account.id"` → `test_data["account"]["id"]`)

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
| `Android 디바이스 없음` | 에뮬레이터 미실행 또는 adb 미연결 | Android Studio에서 에뮬레이터 실행 후 `adb devices` 확인 |
| `iOS Simulator 없음` | 시뮬레이터 미부팅 | `xcrun simctl boot "iPhone 16"` 실행 |
| `pyenv: command not found` | pyenv 쉘 초기화 미설정 | `~/.zshrc`에 pyenv init 추가 후 `source ~/.zshrc` |
| `nvm: command not found` | nvm 쉘 초기화 미설정 | `~/.zshrc`에 nvm 초기화 추가 후 `source ~/.zshrc` |
| `ANDROID_HOME` 오류 | Appium 환경변수 미설정 | Appium 서버 실행 시 `ANDROID_HOME` 명시 |
| 코드 생성 실패 | TC 마크다운 형식 오류 | `testcases/` 파일 형식 확인 |
| lint 실패 | 생성 코드 문법 오류 | 해당 `.py` 직접 수정 후 lint 재실행 |
| 힐링 3회 모두 실패 | selector / assertion 불일치 | `tests/reports/recordings/` 영상 확인 후 수동 수정 |
