# TC-003: Settings Network 항목 표시

## 목적
Settings 메인 화면에 "Network & internet" 항목이 표시되는지 검증한다.

## 플랫폼
- Android

## 전제조건
- Settings 앱이 실행된 상태 (precondition: app_launch)

---

## 테스트 케이스 1

### 테스트 함수명
`test_network_item_visible`

### 단계
1. homepage_container 요소가 존재하는지 확인한다

### 기대결과
- homepage_container 요소가 표시된다

### 셀렉터 힌트
- homepage_container: `com.android.settings:id/homepage_container`
