---
id: tc_002
priority: medium
tags: [imported]
type: structured
---
# TC-002: Settings 검색창 탭

## 목적
Settings 검색창 탭

## 플랫폼
- Android

## 전제조건
- Settings 앱이 실행된 상태 (precondition: app_launch)

## 테스트 케이스 1

### 테스트 함수명
`test_settings_검색창_탭`

### 단계
1. search_action_bar_title 버튼을 탭한다
2. open_search_view 요소가 존재하는지 확인한다

### 기대결과
- open_search_view 요소가 표시된다
