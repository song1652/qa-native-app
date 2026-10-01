# 문서 안내

문서는 사용 목적에 따라 아래 폴더에 모았습니다. 제품 사용법은 사용자 가이드에서 시작하고, 구현 기준은 요구사항과 운영 정책을 확인하세요.

## 사용 가이드

- [QA Dashboard 사용자 가이드](guides/USER_GUIDE.html): 화면별 사용법과 TC Studio, 실행 및 결과 확인

## 요구사항

- [환경 설정 UI](requirements/ENV_SETUP_PRD.md): Appium, Android 에뮬레이터, iOS 시뮬레이터 관리
- [TC 실행 관측성](requirements/EXECUTION_OBSERVABILITY_PRD.md): 실행 영상, 로그, 스크린샷과 증거 화면
- [실기기 병렬 실행](requirements/PARALLEL_EXECUTION_PRD.md): 병렬 실행 범위와 설계 초안

## 운영 정책

- [Locator Healing](operations/LOCATOR_HEALING.md): locator 자동 복구 기준과 실패 시 확인 절차

## 기능별 자료

- [TC Studio](tc-studio/README.md): 이식 설계, 실행 계획, 인수인계 문서
- [환경 설정 이미지](images/env-setup/): 환경 설정 화면과 상태별 캡처
- [디자인 가이드와 화면 목업](design-refresh/HANDOFF.md): 디자인 토큰, 공통 부품, 화면별 HTML과 스크린샷

## 설계 및 작업 기록

- [설계 문서](superpowers/specs/): 기능 설계와 구조 변경 기록
- [실행 계획](superpowers/plans/): 기능별 구현 작업과 검증 기록

`superpowers/`의 날짜가 붙은 문서는 당시의 설계와 계획을 보존한 기록입니다. 현재 동작과 사용법은 사용자 가이드와 코드에서 확인하세요.
