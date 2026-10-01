---
id: tc_P7V_02
priority: medium
tags: [imported]
type: structured
---
# TC-P7V_02: 검색어 입력 시 관련 설정 목록 노출

## 목적
검색어 입력 시 관련 설정 목록 노출

## 플랫폼
- Android

## 전제조건
- 설정 앱(com.android.settings/.homepage.SettingsHomepageActivity)을 실행한 상태

## 테스트 케이스 1

### 테스트 함수명
`test_검색어_입력_시_관련_설정_목록_노출`

### 단계
1. 설정 첫 화면에서 검색창(settings_search_bar)을 탭한다
2. 검색 입력창(settings_search_input)에 `위치`를 입력한다

### 기대결과
- 검색 결과에 '위치' 항목이 표시된다.

### 셀렉터 힌트
- settings_search_bar: `com.android.settings:id/search_action_bar`
- settings_search_input: `com.google.android.settings.intelligence:id/open_search_view_edit_text`
