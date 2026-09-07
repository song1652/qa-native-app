---
id: tc_001
priority: medium
tags: [imported]
type: structured
---
# TC-001: Settings 메인 화면 표시

## 목적
Settings 메인 화면 표시

## 플랫폼
- Android

## 전제조건
- 앱이 실행된 상태 (precondition: app_launch)

## 테스트 케이스 1

### 테스트 함수명
`test_settings_메인_화면_표시`

### 단계
1. homepage_title 요소가 존재하는지 확인한다

### 기대결과
- homepage_title 요소에 "Settings" 텍스트가 표시된다
