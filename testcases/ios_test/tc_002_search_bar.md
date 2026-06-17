# TC-002: Settings 검색창 탭

## 목적
Settings 앱의 검색 항목을 탭했을 때 검색 화면으로 전환되는지 검증한다.

## 플랫폼
- iOS

## 전제조건
- Settings 앱이 실행된 상태 (precondition: app_launch)

---

## 테스트 케이스 1

### 테스트 함수명
`test_search_bar_tap`

### 단계
1. 검색 항목을 탭한다
2. 검색 항목이 존재하는지 확인한다

### 기대결과
- 검색 항목이 화면에 표시된다

### 셀렉터 힌트
- search_bar: accessibility_id=`검색`
