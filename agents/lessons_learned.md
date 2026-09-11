# Lessons Learned — App QA

> 앱 테스트 자동화 과정에서 발견된 패턴과 교훈을 기록합니다.
> 코드 패치 전 반드시 이 파일을 확인하세요.

## Appium / Android

### [Locator Heal Failed] ApiDemos_WebView_링크_이동 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: ApiDemos_WebView_링크_이동 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] ApiDemos_WebView_텍스트_입력 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: ApiDemos_WebView_텍스트_입력 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] ApiDemos_네이티브_WebView_탐지 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: ApiDemos_네이티브_WebView_탐지 화면 heal 재시도 시 참고

---

## iOS

<!-- iOS 관련 패턴은 여기에 추가 -->

## 공통

<!-- 플랫폼 공통 패턴 -->
