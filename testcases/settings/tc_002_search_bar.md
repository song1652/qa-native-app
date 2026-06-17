# TC-002: Settings 검색창 탭

## 목적
Settings 앱의 검색창을 탭했을 때 검색 화면으로 전환되는지 검증한다.

## 플랫폼
- Android

## 전제조건
- Settings 앱이 실행된 상태 (precondition: app_launch)

---

## 테스트 케이스 1

### 테스트 함수명
`test_search_bar_tap`

### 단계
1. search_action_bar_title 버튼을 탭한다
2. open_search_view 요소가 존재하는지 확인한다

### 기대결과
- open_search_view 요소가 표시된다

### 셀렉터 힌트
- search_action_bar_title: `com.android.settings:id/search_action_bar_title`
- open_search_view: `com.google.android.settings.intelligence:id/open_search_view`
