---
id: tc_005
priority: high
tags: [hybrid, native, webview, input, playwright]
type: structured
---
# TC-005: ApiDemos WebView 텍스트 입력

## 목적
native 화면 확인 후 WebView로 전환하여 입력 필드 값을 변경하고 검증할 수 있는지 확인한다.

## 플랫폼
- Android

## 전제조건
- Android 에뮬레이터와 Appium UiAutomator2 서버가 실행 중이다.
- Appium 공식 `ApiDemos-debug.apk`가 `io.appium.android.apis` 패키지로 설치되어 있다.
- 시작 Activity는 `io.appium.android.apis/.view.WebView1`이다.
- WebView debugging이 활성화되어 있다.

## 테스트 케이스 1

### 테스트 함수명
`test_webview_text_input_after_native_detection`

### 단계
1. 앱을 `NATIVE_APP` context에서 실행한다.
2. native_header 요소가 존재하는지 확인한다.
3. WebView context가 감지되면 해당 context로 전환한다.
4. webview_textbox 요소의 기존 값을 지운다.
5. webview_textbox 요소에 `hybrid-test`를 입력한다.
6. webview_textbox 요소의 값을 확인한다.

### 기대결과
- WebView가 감지되기 전에는 native locator만 사용한다.
- WebView 전환 후 webview_textbox 값이 `hybrid-test`로 표시된다.

### 셀렉터 힌트
- native_header: `//*[@text="Views/WebView"]`
- webview_textbox: `#i_am_a_textbox`
