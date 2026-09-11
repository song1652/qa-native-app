---
id: tc_004
priority: high
tags: [hybrid, native, webview, appium, playwright]
type: structured
---
# TC-004: ApiDemos 네이티브·WebView 탐지

## 목적
한 화면에 포함된 native 영역과 WebView 영역을 자동으로 구분하고 각 영역의 요소를 조회할 수 있는지 확인한다.

## 플랫폼
- Android

## 전제조건
- Android 에뮬레이터와 Appium UiAutomator2 서버가 실행 중이다.
- Appium 공식 `ApiDemos-debug.apk`가 `io.appium.android.apis` 패키지로 설치되어 있다.
- 시작 Activity는 `io.appium.android.apis/.view.WebView1`이다.
- WebView debugging이 활성화되어 있다.

## 테스트 케이스 1

### 테스트 함수명
`test_native_header_and_webview_content_are_detected`

### 단계
1. 앱을 `NATIVE_APP` context에서 실행한다.
2. native_header 요소가 존재하는지 확인한다.
3. 사용 가능한 context 목록을 조회한다.
4. `WEBVIEW_io.appium.android.apis` context가 존재하는지 확인한다.
5. WebView context로 전환한다.
6. webview_heading 요소가 존재하는지 확인한다.

### 기대결과
- native_header 요소에 `Views/WebView`가 표시된다.
- context 목록에 `NATIVE_APP`과 `WEBVIEW_io.appium.android.apis`가 모두 표시된다.
- webview_heading 요소에 `This page is a Selenium sandbox`가 표시된다.

### 셀렉터 힌트
- native_header: `//*[@text="Views/WebView"]`
- webview_heading: `h1`
