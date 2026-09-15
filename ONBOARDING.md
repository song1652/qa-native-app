# QA Dashboard 온보딩 가이드

> **Claude Code 사용자라면**: 이 파일을 열고 `"온보딩 해줘"` 라고 하면 Claude Code가 아래 단계를 자동으로 실행합니다.
> **직접 진행하는 경우**: 각 단계의 명령어를 순서대로 실행하세요.

---

## Claude Code 실행 지침 (사람이 읽지 않아도 됩니다)

아래 단계를 위에서부터 순서대로 실행하세요.
각 단계마다 검증 명령을 실행하고, 통과하면 다음 단계로 넘어갑니다.
실패 시 해당 단계의 Fix 지침을 실행하고 다시 검증합니다.
사용자에게 값을 입력받아야 하는 단계는 반드시 먼저 물어보세요.

---

## 전제 조건 (수동 필수)

아래 항목은 자동화가 불가능합니다. 시작 전 사람이 직접 확인하세요.

- [ ] **macOS** 13 이상
- [ ] **Android Studio** 설치 + AVD 하나 이상 생성 완료
  - AVD 이름 메모 (예: `Pixel_7_Android15`)
- [ ] **Xcode** 설치 완료 (iOS 테스트를 사용하는 경우)
  - `xcrun simctl list` 로 시뮬레이터 이름 확인

---

## STEP 1 — Homebrew 확인

**목적**: 이후 도구 설치에 필요한 패키지 매니저를 확인합니다.

```bash
brew --version
```

**기대 결과**: `Homebrew 4.x.x` 출력

**없으면**:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

---

## STEP 2 — Python 3.11+ 확인

```bash
python3 --version
```

**기대 결과**: `Python 3.11.x` 이상

**없으면**:
```bash
brew install python@3.11
```

---

## STEP 3 — 프로젝트 루트 확인

```bash
ls ONBOARDING.md agents/ config/ scripts/ tests/
```

**기대 결과**: 파일 목록이 출력됨
**실패 시**: 프로젝트 루트로 이동 후 다시 실행

---

## STEP 4 — Python 가상환경 생성 및 활성화

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 --version
```

**기대 결과**: `.venv` 내 Python 버전 출력

---

## STEP 5 — Python 의존성 설치

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**검증**:
```bash
python3 -c "import fastapi, appium, pytest, playwright; print('OK')"
```

**기대 결과**: `OK`

---

## STEP 6 — Node.js 확인

```bash
node --version
npm --version
```

**기대 결과**: `v18` 이상

**없으면**:
```bash
brew install node
```

---

## STEP 7 — Appium 설치

```bash
npm list -g appium 2>/dev/null | grep appium || npm install -g appium
```

**검증**:
```bash
appium --version
```

**기대 결과**: `3.x.x` 출력

---

## STEP 8 — Appium 드라이버 설치

```bash
appium driver list --installed
```

**UiAutomator2 (Android) 없으면**:
```bash
appium driver install uiautomator2
```

**XCUITest (iOS) 없으면**:
```bash
appium driver install xcuitest
```

**검증**:
```bash
appium driver list --installed
```

**기대 결과**: `uiautomator2` 또는 `xcuitest` 항목 출력

---

## STEP 9 — Android SDK 환경변수 설정

```bash
echo $ANDROID_HOME
```

**비어 있으면** 사용자에게 물어보세요:
> "Android SDK 경로를 확인합니다. Android Studio → Settings → SDK → Android SDK Location 경로를 알려주세요."

일반적으로 `/Users/{사용자명}/Library/Android/sdk` 입니다.

**shell 프로파일에 영구 등록**:
```bash
# 아래 경로를 실제 경로로 교체하세요
ANDROID_SDK_PATH="$HOME/Library/Android/sdk"

if ! grep -q "ANDROID_HOME" ~/.zshrc 2>/dev/null; then
  echo "" >> ~/.zshrc
  echo "# Android SDK" >> ~/.zshrc
  echo "export ANDROID_HOME=\"$ANDROID_SDK_PATH\"" >> ~/.zshrc
  echo "export PATH=\"\$PATH:\$ANDROID_HOME/platform-tools\"" >> ~/.zshrc
fi

export ANDROID_HOME="$ANDROID_SDK_PATH"
export PATH="$PATH:$ANDROID_HOME/platform-tools"
```

**검증**:
```bash
adb --version
echo "ANDROID_HOME=$ANDROID_HOME"
```

**기대 결과**: `Android Debug Bridge version 1.x.x` + ANDROID_HOME 경로 출력

---

## STEP 10 — config/devices.json 설정

사용자에게 다음 항목을 물어보세요:

1. **Android AVD 이름**: Android Studio에서 만든 AVD 이름 (예: `Pixel_7_Android15`)
2. **Android 플랫폼 버전**: 에뮬레이터 OS 버전 (예: `15.0`)
3. **iOS 시뮬레이터 이름** (iOS 사용 시): `xcrun simctl list | grep Booted` 결과 또는 원하는 시뮬레이터 이름
4. **iOS 플랫폼 버전** (iOS 사용 시): 시뮬레이터 iOS 버전 (예: `18.0`)

입력값으로 `config/devices.json`의 다음 필드를 업데이트하세요:
- `android.emulator[0].avd` → Android AVD 이름
- `android.emulator[0].platformVersion` → Android 버전
- `ios.simulator[0].deviceName` → iOS 시뮬레이터 이름
- `ios.simulator[0].platformVersion` → iOS 버전

**주의**: `config/devices.json`은 `.gitignore`에 없으므로 민감 정보를 넣지 마세요. 실기기 `udid`, `wifi_ip`는 선택 사항입니다.

---

## STEP 11 — config/test_data.json 설정

사용자에게 다음 항목을 물어보세요:

1. **테스트할 Android 앱 패키지명** (예: `com.android.settings`)
2. **Android 앱 액티비티명** (예: `.Settings`)
3. **iOS 앱 Bundle ID** (iOS 사용 시, 예: `com.apple.Preferences`)

`config/test_data.json`이 없으면 아래 템플릿으로 생성하세요:

```json
{
  "app": {
    "android": {
      "package": "<android_package>",
      "activity": "<android_activity>",
      "app_path": ""
    },
    "ios": {
      "bundle_id": "<ios_bundle_id>"
    }
  }
}
```

---

## STEP 12 — 대시보드 서버 기동 테스트

```bash
source .venv/bin/activate
timeout 8 python agents/dashboard/serve.py &
sleep 4
curl -s http://localhost:8767/api/status | python3 -c "import sys,json; d=json.load(sys.stdin); print('서버 OK' if 'appium' in str(d) else 'FAIL')"
kill %1 2>/dev/null
```

**기대 결과**: `서버 OK`

**실패 시**: 에러 메시지를 확인하고 누락된 의존성을 설치합니다.

---

## STEP 13 — Playwright 브라우저 설치

```bash
playwright install chromium
```

**검증**:
```bash
python3 -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); b.close(); p.stop(); print('Playwright OK')"
```

---

## STEP 14 — Python 문법 검증

```bash
source .venv/bin/activate
python3 -m py_compile scripts/*.py agents/dashboard/serve.py agents/dashboard/routes/*.py
echo "문법 오류 없음"
```

**기대 결과**: `문법 오류 없음`

---

## STEP 15 — 최종 확인

```bash
echo "=== 온보딩 체크리스트 ==="
echo -n "Python venv: " && source .venv/bin/activate && python3 -c "import fastapi" && echo "✅" || echo "❌"
echo -n "Appium: " && appium --version > /dev/null && echo "✅" || echo "❌"
echo -n "adb: " && adb --version > /dev/null && echo "✅" || echo "❌"
echo -n "ANDROID_HOME: " && [ -n "$ANDROID_HOME" ] && echo "✅ $ANDROID_HOME" || echo "❌ 미설정"
echo -n "devices.json: " && python3 -c "import json; json.load(open('config/devices.json'))" && echo "✅" || echo "❌"
echo -n "test_data.json: " && python3 -c "import json; json.load(open('config/test_data.json'))" && echo "✅" || echo "❌"
echo ""
echo "=== 실행 방법 ==="
echo "1. Appium 서버 시작:"
echo "   export ANDROID_HOME=$HOME/Library/Android/sdk"
echo "   appium --address 127.0.0.1 --port 4723 --allow-insecure=uiautomator2:adb_screen_streaming"
echo ""
echo "2. 대시보드 시작:"
echo "   source .venv/bin/activate && python agents/dashboard/serve.py"
echo ""
echo "3. 브라우저에서 열기:"
echo "   http://localhost:8767"
```

---

## 수동 필수 단계 (자동화 불가)

### Android 에뮬레이터 시작
```bash
# AVD 이름 목록 확인
emulator -list-avds

# 에뮬레이터 시작 (AVD 이름을 실제 이름으로 교체)
$ANDROID_HOME/emulator/emulator -avd Pixel_7_Android15 &
```

또는 **대시보드 → 환경 설정 → Android → ▶ 시작** 클릭

### iOS 시뮬레이터 시작
```bash
# 사용 가능한 시뮬레이터 목록
xcrun simctl list devices available

# 시뮬레이터 이름으로 부팅
xcrun simctl boot "iPhone 16 Pro"
open /Applications/Simulator.app
```

또는 **대시보드 → 환경 설정 → iOS → ▶ 시작** 클릭

---

## 자주 발생하는 오류

| 오류 | 원인 | 해결 |
|---|---|---|
| `Neither ANDROID_HOME nor ANDROID_SDK_ROOT` | 환경변수 미설정 | STEP 9 재실행 |
| `UiAutomator2 세션 초기화 실패` | 에뮬레이터 이미 실행 중에 `avd` 캡 사용 | `deviceName: "emulator-5554"` 또는 대시보드 재연결 |
| `port 8767 already in use` | 대시보드 이미 실행 중 | `lsof -ti :8767 \| xargs kill` |
| `xcrun: error` | Xcode Command Line Tools 미설치 | `xcode-select --install` |
| `collected 0 items` | 테스트 함수 없는 빈 파일 | Capture Studio에서 액션 추가 후 재생성 |

---

## 다음 단계

온보딩 완료 후 아래 순서로 시작하세요:

1. **환경 설정** 탭 → Appium 시작 → 에뮬레이터/시뮬레이터 시작
2. **Import Studio** 탭 → `import/` 폴더에 Excel 파일 → TC 등록
3. **Capture Studio** 탭 → 앱 화면 보면서 TC 직접 생성
4. **파이프라인 실행** 탭 → 전체 실행
5. **리포트 목록** 탭 → 결과 확인

더 자세한 사용법은 [`docs/USER_GUIDE.html`](docs/USER_GUIDE.html)을 참고하세요.
