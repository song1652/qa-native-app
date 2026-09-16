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
- [ ] **Android Studio** 설치 완료
  - AVD 생성은 STEP 16에서 자동화 — 아직 없어도 됩니다
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
pip show pytest-rerunfailures | grep Version
```

**기대 결과**: `OK` 출력 후 `Version: x.x.x` 출력 (pytest-rerunfailures는 05_execute.py 자동 재시도 기능에 필수)

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

# 현재 shell에 맞는 프로파일 감지
if [ -n "$ZSH_VERSION" ] || [ "$SHELL" = "/bin/zsh" ]; then
  PROFILE_FILE="$HOME/.zshrc"
elif [ -f "$HOME/.bash_profile" ]; then
  PROFILE_FILE="$HOME/.bash_profile"
else
  PROFILE_FILE="$HOME/.bashrc"
fi
echo "프로파일: $PROFILE_FILE"

if ! grep -q "ANDROID_HOME" "$PROFILE_FILE" 2>/dev/null; then
  echo "" >> "$PROFILE_FILE"
  echo "# Android SDK" >> "$PROFILE_FILE"
  echo "export ANDROID_HOME=\"$ANDROID_SDK_PATH\"" >> "$PROFILE_FILE"
  echo "export PATH=\"\$PATH:\$ANDROID_HOME/platform-tools\"" >> "$PROFILE_FILE"
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

> **Android AVD가 아직 없으면** 1–2번을 건너뛰고 STEP 16 완료 후 돌아와 입력하세요.

1. **Android AVD 이름**: 이미 AVD가 있으면 입력 (예: `Pixel_7_Android15`). 없으면 STEP 16 후 입력
2. **Android 플랫폼 버전**: 에뮬레이터 OS 버전 (예: `15.0`)
3. **iOS 시뮬레이터 이름** (iOS 사용 시): `xcrun simctl list devices` 로 확인한 정확한 이름 — STEP 17에서 생성 가능. **주의**: Capture Studio iOS 세션은 `config/devices.json`의 `deviceName`이 `xcrun simctl list devices` 출력의 이름과 **정확히** 일치해야 합니다.
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
      "bundle_id": "<ios_bundle_id>",
      "app_path": ""
    }
  }
}
```

---

## STEP 12 — 대시보드 서버 기동 테스트

```bash
source .venv/bin/activate
python agents/dashboard/serve.py &
SERVER_PID=$!
sleep 4
curl -s http://localhost:8767/api/status \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('서버 OK' if 'appium' in str(d) else 'FAIL')" \
  2>/dev/null || echo "서버 응답 없음 — 의존성 확인 필요"
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null
```

**기대 결과**: `서버 OK`

**실패 시**: 에러 메시지를 확인하고 누락된 의존성을 설치합니다.

---

## STEP 13 — Playwright 브라우저 설치

```bash
source .venv/bin/activate
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
python3 -m py_compile scripts/*.py \
  agents/dashboard/serve.py \
  agents/dashboard/shared.py \
  agents/dashboard/ws.py \
  agents/dashboard/routes/*.py \
  agents/dashboard/utils/*.py
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
echo "   # --allow-insecure 플래그: Capture Studio Android MJPEG 스트리밍에 필수"
echo ""
echo "2. 대시보드 시작:"
echo "   source .venv/bin/activate && python agents/dashboard/serve.py"
echo ""
echo "3. 브라우저에서 열기:"
echo "   http://localhost:8767"
```

---

## STEP 16 — Android 에뮬레이터(AVD) 생성 및 시작

### 16-0. cmdline-tools 경로 탐지

```bash
# sdkmanager / avdmanager 위치 자동 탐지
SDKMANAGER=""
AVDMANAGER=""
for BIN_DIR in \
  "$ANDROID_HOME/cmdline-tools/latest/bin" \
  "$ANDROID_HOME/cmdline-tools/bin" \
  "$(find "$ANDROID_HOME/cmdline-tools" -name sdkmanager 2>/dev/null | xargs -I{} dirname {} | head -1)"; do
  if [ -x "$BIN_DIR/sdkmanager" ]; then
    SDKMANAGER="$BIN_DIR/sdkmanager"
    AVDMANAGER="$BIN_DIR/avdmanager"
    echo "✅ cmdline-tools: $BIN_DIR"
    break
  fi
done

if [ -z "$SDKMANAGER" ]; then
  echo "⚠️  cmdline-tools 없음"
  echo "   Android Studio → SDK Manager → SDK Tools → Android SDK Command-line Tools 설치 후 재시도"
fi
```

---

### 16-1. 사용 가능한 시스템 이미지 설치

사용자에게 물어보세요:
> "어떤 Android 버전으로 테스트하실 건가요? (예: 15, 14, 13)"

입력받은 버전에 맞는 시스템 이미지를 설치합니다:

```bash
# Android 15 (API 35) 예시 — 버전에 따라 API 레벨 교체
$SDKMANAGER "system-images;android-35;google_apis;arm64-v8a"
$SDKMANAGER "platform-tools" "platforms;android-35"
```

API 레벨 참고:
- Android 15 → `android-35`
- Android 14 → `android-34`
- Android 13 → `android-33`

**검증**:
```bash
$SDKMANAGER --list_installed | grep "system-images"
```

**cmdline-tools가 없으면**: 16-0 오류 메시지에 따라 Android Studio에서 수동 설치 후 STEP 16 전체 재시도

---

### 16-2. AVD 생성

사용자에게 물어보세요:
> "AVD 이름을 정해주세요 (예: Pixel_7_Android15). 기기 종류는요? (예: pixel_7, pixel_6, pixel_4)"

```bash
# 기기 종류 목록 확인
$AVDMANAGER list device | grep -E "^id:|Name:"

# AVD 생성 (이름과 API 레벨, 기기 종류를 입력값으로 교체)
$AVDMANAGER create avd \
  --name "Pixel_7_Android15" \
  --package "system-images;android-35;google_apis;arm64-v8a" \
  --device "pixel_7" \
  --force
```

**검증**:
```bash
$AVDMANAGER list avd
```

**기대 결과**: 생성한 AVD 이름이 목록에 표시됨

> **주의**: `config/devices.json`의 `android.emulator[0].avd` 값은 위에서 생성한 AVD 이름과 **정확히** 일치해야 합니다. 대소문자·공백 포함 완전 일치가 필요합니다. STEP 10에서 건너뛰었다면 지금 업데이트하세요.

---

### 16-3. 에뮬레이터 시작

```bash
# emulator 바이너리 탐지
EMULATOR=""
for path in \
  "$ANDROID_HOME/emulator/emulator" \
  "$(which emulator 2>/dev/null)"; do
  if [ -x "$path" ]; then
    EMULATOR="$path"
    break
  fi
done

if [ -z "$EMULATOR" ]; then
  echo "⚠️  emulator 없음 — Android Studio → SDK Manager → SDK Tools → Android Emulator 설치 필요"
  exit 1
fi

nohup "$EMULATOR" -avd Pixel_7_Android15 \
  -no-snapshot-save \
  -gpu swiftshader_indirect \
  > logs/android_avd.log 2>&1 &

echo "에뮬레이터 시작 중... (30–60초 소요)"
```

**부팅 완료 대기**:
```bash
# adb로 부팅 완료 감지 (최대 90초)
for i in $(seq 1 18); do
  STATUS=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
  if [ "$STATUS" = "1" ]; then
    echo "✅ 에뮬레이터 부팅 완료"
    break
  fi
  echo "부팅 대기 중... ($((i*5))초)"
  sleep 5
done
```

**검증**:
```bash
adb devices
```

**기대 결과**: `emulator-5554   device` 출력

> 이후에는 **대시보드 → 환경 설정 → Android → ▶ 시작**으로 관리할 수 있습니다.

---

## STEP 17 — iOS 시뮬레이터 생성 및 시작

> iOS 테스트를 사용하지 않는다면 이 단계를 건너뛰세요.

### 17-1. 사용 가능한 런타임 확인

```bash
xcrun simctl list runtimes
```

**기대 결과**: `iOS 17.x` 또는 `iOS 18.x` 항목 출력

**런타임이 없으면**: Xcode → Preferences → Platforms → 원하는 iOS 버전 다운로드 (수동, Xcode 내 GUI)

---

### 17-2. 시뮬레이터 생성

사용자에게 물어보세요:
> "어떤 기기로 시뮬레이터를 만들까요? (예: iPhone 16 Pro, iPhone 15) iOS 버전은요? (예: 18.0)"

```bash
# 사용 가능한 기기 타입 목록
xcrun simctl list devicetypes | grep iPhone

# 시뮬레이터 생성 (기기명과 런타임을 입력값으로 교체)
DEVICE_NAME="iPhone 16 Pro"
IOS_VERSION="18.0"
RUNTIME_ID=$(xcrun simctl list runtimes | grep "iOS $IOS_VERSION" | awk '{print $NF}')

xcrun simctl create "$DEVICE_NAME" "$DEVICE_NAME" "$RUNTIME_ID"
```

**검증**:
```bash
xcrun simctl list devices | grep "iPhone 16 Pro"
```

**기대 결과**: 생성된 시뮬레이터 UDID와 함께 `(Shutdown)` 상태 출력

---

### 17-3. 시뮬레이터 UDID를 devices.json에 반영

```bash
# UDID 추출 (기기명은 앞 단계에서 생성한 이름으로 교체)
UDID=$(xcrun simctl list devices | grep "iPhone 16 Pro" | head -1 | grep -oE '[A-F0-9-]{36}')
echo "UDID: $UDID"

# config/devices.json에 자동 반영
python3 << EOF
import json
udid = "$UDID"
with open('config/devices.json', 'r') as f:
    d = json.load(f)
sims = d.get('ios', {}).get('simulator', [])
if sims:
    sims[0]['udid'] = udid
    with open('config/devices.json', 'w') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    print(f'✅ UDID {udid} → config/devices.json 반영 완료')
else:
    print('⚠️  ios.simulator 배열이 비어 있습니다. STEP 10을 확인하세요.')
EOF
```

---

### 17-4. 시뮬레이터 시작

```bash
# 부팅
xcrun simctl boot "iPhone 16 Pro"

# Simulator.app 열기
open /Applications/Simulator.app

echo "iOS 시뮬레이터 시작 중... (30–60초 소요)"
```

**부팅 완료 대기**:
```bash
for i in $(seq 1 20); do
  STATUS=$(xcrun simctl list devices | grep "iPhone 16 Pro" | grep -o "Booted")
  if [ "$STATUS" = "Booted" ]; then
    echo "✅ 시뮬레이터 부팅 완료"
    break
  fi
  echo "부팅 대기 중... ($((i*3))초)"
  sleep 3
done
```

**검증**:
```bash
xcrun simctl list devices | grep "Booted"
```

**기대 결과**: `(Booted)` 상태 출력

> 이후에는 **대시보드 → 환경 설정 → iOS → ▶ 시작**으로 관리할 수 있습니다.

> **WDA(WebDriverAgent) 자동 설치**: Capture Studio iOS 세션을 처음 연결하면 Appium XCUITest 드라이버가 WDA를 시뮬레이터에 자동 빌드·설치합니다. 첫 연결 시 30초 이상 소요될 수 있으며, 화면 미러링이 표시되기 전까지 기다려야 합니다.

---

## 자주 발생하는 오류

| 오류 | 원인 | 해결 |
|---|---|---|
| `Neither ANDROID_HOME nor ANDROID_SDK_ROOT` | 환경변수 미설정 | STEP 9 재실행 |
| `UiAutomator2 세션 초기화 실패` | 에뮬레이터 이미 실행 중에 `avd` 캡 사용 | `deviceName: "emulator-5554"` 또는 대시보드 재연결 |
| `port 8767 already in use` | 대시보드 이미 실행 중 | `lsof -ti :8767 \| xargs kill` |
| `xcrun: error` | Xcode Command Line Tools 미설치 | `xcode-select --install` |
| `collected 0 items` | 테스트 함수 없는 빈 파일 | Capture Studio에서 액션 추가 후 재생성 |
| iOS 세션 충돌 / 드라이버 None | 시뮬레이터당 XCUITest 세션 1개 제한 — Capture Studio iOS 세션이 열린 채 pytest 동시 실행 | Capture Studio 세션 종료 후 실행하거나 대시보드 "🔄 세션 재연결" 버튼 클릭 |

---

## Nova MCP 설정 (선택)

Claude Code에서 디바이스를 직접 제어하려면 MCP 서버를 1회 등록합니다.

`.claude/settings.json` (또는 전역 `~/.claude/settings.json`)에 아래 블록을 추가하세요.

```json
{
  "mcpServers": {
    "qa-capture-studio": {
      "url": "http://localhost:8767/mcp"
    }
  }
}
```

설정 후 Claude Code를 재시작합니다.

**사용 방법:**
1. 대시보드에서 Capture Studio 세션을 먼저 시작합니다.
2. Claude Code에 자연어로 요청합니다.
   - 예: `"현재 화면 스크린샷 찍어줘"` / `"지금 화면 hierarchy 가져와줘"`
3. Claude가 MCP 툴을 호출하면 대시보드 상단 칩이 **MCP ON**으로 전환됩니다.

> Capture Studio 세션이 없으면 `session_not_active` 에러가 반환됩니다.  
> MCP ON 상태에서 칩을 클릭하면 수동으로 연결을 해제할 수 있습니다.

---

## 다음 단계

온보딩 완료 후 아래 순서로 시작하세요:

1. 대시보드 서버 시작: `source .venv/bin/activate && python agents/dashboard/serve.py`
2. 브라우저에서 열기: `http://localhost:8767`
3. **환경 설정** 탭 → Appium 시작 → 에뮬레이터/시뮬레이터 시작
4. **Import Studio** 탭 → `import/` 폴더에 Excel 파일 → TC 등록
5. **Capture Studio** 탭 → 앱 화면 보면서 TC 직접 생성 (또는 Nova MCP로 Claude에게 위임)
   - 상단 **Livetail** 버튼(항상 표시)을 클릭하면 user·mcp·pipeline 이벤트 실시간 확인 가능
6. **파이프라인 실행** 탭 → 전체 실행 (단계 시작·완료가 Livetail에 실시간 표시됩니다)
   - TC 파일이 없으면 `collected 0 items` 로 종료됩니다 — 오류가 아니라 TC 등록 전 정상 상태입니다.
   - TC 등록 후 실행 시 `tests/reports/` 에 HTML 리포트가 생성되면 성공입니다.
7. **리포트 목록** 탭 → 결과 확인

더 자세한 사용법은 [`docs/USER_GUIDE.html`](docs/USER_GUIDE.html)을 참고하세요.
