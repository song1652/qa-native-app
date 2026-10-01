---
id: tc_P7V_01
priority: medium
tags: [imported]
type: structured
---
# TC-P7V_01: 검색 아이콘 탭 시 검색 입력창 진입

## 목적
검색 아이콘 탭 시 검색 입력창 진입

## 플랫폼
- Android

## 전제조건
- 설정 앱(com.android.settings/.homepage.SettingsHomepageActivity)을 실행한 상태

## 테스트 케이스 1

### 테스트 함수명
`test_검색_아이콘_탭_시_검색_입력창_진입`

### 단계
1. 설정 첫 화면에서 검색창(settings_search_bar)을 탭한다

### 기대결과
- 검색 입력창(settings_search_input)이 표시된다.

### 셀렉터 힌트
- settings_search_bar: `com.android.settings:id/search_action_bar`
- settings_search_input: `com.google.android.settings.intelligence:id/open_search_view_edit_text`
