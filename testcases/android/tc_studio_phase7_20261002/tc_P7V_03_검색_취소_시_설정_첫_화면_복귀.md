---
id: tc_P7V_03
priority: medium
tags: [imported]
type: structured
---
# TC-P7V_03: 검색 취소 시 설정 첫 화면 복귀

## 목적
검색 취소 시 설정 첫 화면 복귀

## 플랫폼
- Android

## 전제조건
- 설정 앱(com.android.settings/.homepage.SettingsHomepageActivity)을 실행한 상태

## 테스트 케이스 1

### 테스트 함수명
`test_검색_취소_시_설정_첫_화면_복귀`

### 단계
1. 설정 첫 화면에서 검색창(settings_search_bar)을 탭한다
2. 검색 화면에서 뒤로 버튼(settings_back_button)을 누른다

### 기대결과
- 홈 화면 제목(settings_homepage_title)이 표시된다.

### 셀렉터 힌트
- settings_search_bar: `com.android.settings:id/search_action_bar`
- settings_back_button: `뒤로`
- settings_homepage_title: `com.android.settings:id/homepage_title`
