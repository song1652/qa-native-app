# TC-001: Settings 메인 화면 표시

## 목적
Settings 앱을 실행했을 때 메인 화면의 제목과 검색창이 올바르게 표시되는지 검증한다.

## 플랫폼
- Android

## 전제조건
- 앱이 실행된 상태 (precondition: app_launch)

---

## 테스트 케이스 1

### 테스트 함수명
`test_settings_main_screen`

### 단계
1. homepage_title 요소가 존재하는지 확인한다

### 기대결과
- homepage_title 요소에 "Settings" 텍스트가 표시된다

### 셀렉터 힌트
- homepage_title: `com.android.settings:id/homepage_title`
- search_action_bar_title: `com.android.settings:id/search_action_bar_title`
