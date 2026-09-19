# Lessons Learned — App QA

> 앱 테스트 자동화 과정에서 발견된 패턴과 교훈을 기록합니다.
> 코드 패치 전 반드시 이 파일을 확인하세요.

## Appium / Android

### [Locator Heal Failed] toggle — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: toggle 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] brightness — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: brightness 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] settings_search_input — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_search_input 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] v2 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: v2 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] v1 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: v1 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] ui_v3 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: ui_v3 화면 heal 재시도 시 참고

---

### [환경변수] ANDROID_HOME 미설정 시 UiAutomator2 세션 실패
**문제**: `Neither ANDROID_HOME nor ANDROID_SDK_ROOT environment variable was exported` 오류와 함께 Android Appium 세션 생성 실패
**원인**: Appium 프로세스를 시작한 쉘에 `ANDROID_HOME`이 설정되어 있지 않으면 UiAutomator2 드라이버가 adb를 찾지 못함
**해결**: Appium 기동 전 `export ANDROID_HOME=/Users/junghoyoung/Library/Android/sdk` 설정 필수. `~/.zshrc`에 영구 등록 권장
```bash
export ANDROID_HOME=/Users/junghoyoung/Library/Android/sdk
export PATH=$PATH:$ANDROID_HOME/platform-tools
appium --address 127.0.0.1 --port 4723 --allow-insecure=uiautomator2:adb_screen_streaming
```
**적용 범위**: Appium 서버 기동 스크립트 또는 쉘 프로파일 설정 시 참고

---

### [Appium 세션 caps] 에뮬레이터 이미 실행 중일 때 avd 캡 사용 금지
**문제**: `appium:avd` 캡을 설정하면 에뮬레이터가 이미 실행 중이어도 새 에뮬레이터를 띄우려 시도 → 30초 타임아웃 후 UiAutomator2 초기화 실패
**원인**: `avd` 캡은 에뮬레이터를 신규 기동할 때만 유효. 이미 실행 중인 에뮬레이터에 연결할 때는 serial로 지정해야 함
**해결**: 에뮬레이터가 이미 실행 중이면 `appium:udid: "emulator-5554"` 또는 `appium:deviceName: "emulator-5554"`로 연결. `avd` 캡 제거
**적용 범위**: Capture Studio `_do_start_android_session()`은 `avd` 캡 미사용, `deviceName: "Android Emulator"` 제네릭 값 사용 — 정상 동작 확인됨

---

### [Locator Heal Failed] settings_multi — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_multi 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] network_internet — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: network_internet 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] settings_menu_scroll — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_menu_scroll 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] ApiDemos_WebView_링크_이동 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: ApiDemos_WebView_링크_이동 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] ApiDemos_WebView_텍스트_입력 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: ApiDemos_WebView_텍스트_입력 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] ApiDemos_네이티브_WebView_탐지 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: ApiDemos_네이티브_WebView_탐지 화면 heal 재시도 시 참고

---

## iOS

### [iOS 시뮬레이터 부팅] subprocess.run(블로킹) 대신 Popen(비동기) 사용
**문제**: `xcrun simctl boot`를 `subprocess.run(timeout=60)`으로 실행하면 API가 60초 블로킹 → "부팅 중..." 상태가 대시보드에 표시되지 않음
**원인**: 블로킹 호출이 완료될 때 시뮬레이터는 이미 Booted 상태 → 폴링이 즉시 `running`을 감지해 `starting` 상태를 건너뜀
**해결**: `subprocess.Popen(["xcrun", "simctl", "boot", udid], stdout=DEVNULL, stderr=DEVNULL)` 비동기 실행. API가 즉시 202 + `status: "starting"` 반환. 3초 폴링(`detect_ios_runtime`)이 `simctl list` Booted 감지 시 `running`으로 전환
**적용 범위**: `agents/dashboard/routes/env.py` `post_simulator_start()`. Android `post_avd_start()`와 동일한 Popen 패턴 사용

---

### [Locator Heal Failed] settings_v6 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_v6 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] settings_v5 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_v5 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] settings_v3 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_v3 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] settings_general — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_general 화면 heal 재시도 시 참고

---

<!-- iOS 관련 패턴은 여기에 추가 -->

## 공통

### [스키마 설계] emulator 키 단수 확정 — 배열 전환 시 소비 코드 3곳 일괄 수정 필요
**문제**: `android.emulator`를 단수 객체 → 배열로 전환할 때 소비 코드를 놓쳐 KeyError/AttributeError 발생
**원인**: `devices["android"]["emulator"]`를 직접 `.copy()`하는 코드가 3곳의 실제 소스 파일과 해당 파일에서 생성되는 pytest 템플릿에 분산되어 있음
**해결**: 배열 전환 시 아래 3곳을 일괄 수정. `devices["android"]["emulator"]` → `next(d for d in devices["android"]["emulator"] if d.get("default")).copy()` 패턴 적용
- `scripts/drivers/android_driver.py` L35
- `scripts/02_generate.py` L388 (생성 코드 템플릿 내부)
- `agents/dashboard/routes/capture.py` L645 (생성 코드 템플릿 내부)
**적용 범위**: M2.0 배열 전환 작업 시 반드시 세 파일을 동시에 수정. 각 배열 항목에 `"default": true` 필드가 있어야 함

---

### [스키마 설계] MJPEG caps 이중 분산 버그 — devices.json과 capture.py 하드코딩 동시 존재
**문제**: MJPEG 관련 caps(`mjpegServerPort`, `mjpegScalingFactor`, `mjpegServerScreenshotQuality`)가 `config/devices.json`과 `agents/dashboard/routes/capture.py` 양쪽에 분산되어 있음
**원인**: `_do_start_android_session()`은 devices.json을 읽지 않고 직접 `opts.set_capability()`로 MJPEG caps를 설정(L128-130). devices.json의 MJPEG 값은 Capture Studio 경로에서 무시됨
**해결**: M2.0에서 `capture.py` L128-130 하드코딩 제거. devices.json의 emulator 항목에서 MJPEG caps를 읽어 적용하도록 통합. 이중 관리 상태 해소
**적용 범위**: `agents/dashboard/routes/capture.py` `_do_start_android_session()` 함수 리팩터링 시 참고

---

### [케이스 규칙] camelCase/snake_case 역할 분리 — 의도된 설계
**문제**: `config/devices.json`의 키(camelCase)와 내부 state 키(snake_case)가 달라 혼란 발생 가능
**원인**: 설계 의도: devices.json은 Appium caps를 그대로 담는 파일로 Appium 스펙을 따라 camelCase 사용. 내부 state(capture_session.json 등)는 Python 관례를 따라 snake_case 사용
**해결**: 변경 없음. camelCase(Appium) / snake_case(Python 내부) 분리는 유지해야 함
**적용 범위**: devices.json 편집 시 `deviceName`, `platformVersion`, `automationName` 등 Appium 공식 caps 키 이름 그대로 유지. state 파일(capture_session.json 등)은 `app_package`, `mjpeg_port` 등 snake_case 유지

---

### [세션 초기화 실패] 연속 Appium 세션 실행 시 3번째 세션 UiAutomator2 초기화 오류
**문제**: 3개 이상의 테스트를 순차 실행할 때 3번째 세션에서 UiAutomator2 서버 초기화 실패
**원인**: 이전 세션 정리가 완료되기 전 새 세션이 시작되어 서버가 충돌
**해결**: `pytest-rerunfailures`로 제품 레벨에서 처리 (`--reruns 2 --reruns-delay 5` 자동 적용). 테스트 파일 수정 불필요
**적용 범위**: `requirements.txt`에 `pytest-rerunfailures` 추가, `05_execute.py`에 설치 여부 감지 후 자동 적용

---

### [assertion 실패] 한국어 단말에서 영문 텍스트 assertion 실패
**문제**: `assert 'Settings' in el.text` 형태의 검증이 한국어 단말에서 실패 ("설정"으로 표시됨)
**원인**: 단말 언어 설정에 따라 UI 문자열이 달라짐
**해결**: `assert el.text`(비어있지 않음)로 수정하거나 locator를 resource-id/accessibility-id 기반으로 변경
**적용 범위**: 생성 코드에서 텍스트 직접 비교 assertion을 사용할 때 주의

---

### [빠른 실행 체크박스] 숨겨진 탭의 체크박스가 함께 선택되는 오동작
**문제**: `document.querySelectorAll('.quick-group-cb:checked')`가 숨겨진 탭의 체크박스까지 수집하여 의도하지 않은 TC가 실행됨
**원인**: CSS 선택자가 현재 활성 탭 범위를 제한하지 않음
**해결**: `.quick-group-list .quick-group-cb:checked`로 범위를 현재 목록으로 한정
**적용 범위**: `dashboard.html` 빠른 실행 체크박스 수집 로직

---

### [conftest 스크린샷 실패] teardown 후 세션 끊김 상태에서 스크린샷 시도
**문제**: 드라이버 teardown 이후 conftest에서 스크린샷을 시도하면 세션이 이미 끊긴 상태라 오류 발생
**원인**: teardown_method 이후 드라이버 세션이 종료된 상태
**해결**: `teardown_method`에 `try/except` 추가로 드라이버 종료 예외를 흡수. 자체 완결형 테스트 파일에서는 conftest 공유 fixture를 사용하지 않음
**적용 범위**: Capture Studio generate 엔드포인트(`/capture/generate_from_actions`)가 생성하는 pytest 파일

---

### [Capture Studio 계층 트리 높이] 우측 패널 높이에 맞지 않아 잘리는 현상
**문제**: hierarchy tree 패널이 우측 패널 높이를 채우지 못하거나 넘침
**원인**: JS로 height를 동기화하는 방식은 resize 이벤트 타이밍에 따라 불일치 발생
**해결**: CSS `grid-template-rows:1fr` + `min-height:0` 조합으로 부모 컨테이너 안에서 자연스럽게 채움. JS height sync 불필요
**적용 범위**: Capture Studio hierarchy tree CSS

---

### [대시보드 KPI 미갱신] 빠른 실행 완료 후 KPI·히스토리가 갱신되지 않는 문제
**문제**: 빠른 실행 완료 후 대시보드 Overview KPI와 실행 히스토리가 자동으로 갱신되지 않음
**원인**: 빠른 실행 완료 콜백에서 `refreshOverview()`와 `renderRunHistory()` 호출이 누락됨
**해결**: 빠른 실행 완료 시 두 함수를 순서대로 자동 호출하도록 추가
**적용 범위**: `dashboard.html` 빠른 실행 완료 핸들러
