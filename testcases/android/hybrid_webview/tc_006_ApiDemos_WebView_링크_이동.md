---
id: tc_006
priority: high
tags: [hybrid, native, webview, navigation, playwright]
type: structured
---
# TC-006: ApiDemos WebView 링크 이동 및 native 복귀

## 목적
WebView 링크 이동 결과를 검증한 뒤 native context로 정상 복귀할 수 있는지 확인한다.

## 플랫폼
- Android

## 전제조건
- Android 에뮬레이터와 Appium UiAutomator2 서버가 실행 중이다.
- Appium 공식 `ApiDemos-debug.apk`가 `io.appium.android.apis` 패키지로 설치되어 있다.
- 시작 Activity는 `io.appium.android.apis/.view.WebView1`이다.
- WebView debugging이 활성화되어 있다.

## 테스트 케이스 1

### 테스트 함수명
`test_webview_link_navigation_and_native_restore`

### 단계
1. 앱을 `NATIVE_APP` context에서 실행한다.
2. WebView context가 감지되면 해당 context로 전환한다.
3. webview_link 요소를 탭한다.
4. linked_page_content 요소가 존재하는지 확인한다.
5. `NATIVE_APP` context로 다시 전환한다.
6. native_header 요소가 존재하는지 확인한다.

### 기대결과
- WebView URL이 `file:///android_asset/html/linked.html`로 변경된다.
- linked_page_content 요소에 `I am some other page content`가 표시된다.
- native context 복귀 후 native_header 요소에 `Views/WebView`가 다시 표시된다.

### 셀렉터 힌트
- webview_link: `[id="i am a link"]`
- linked_page_content: `body`
- native_header: `//*[@text="Views/WebView"]`
