# Lessons Learned — App QA

> 앱 테스트 자동화 과정에서 발견된 패턴과 교훈을 기록합니다.
> 코드 패치 전 반드시 이 파일을 확인하세요.

## Appium / Android

### [Locator Heal Failed] settings_multi — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_multi 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] network_internet — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: network_internet 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] settings_menu_scroll — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_menu_scroll 화면 heal 재시도 시 참고

---

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

### [Locator Heal Failed] settings_v6 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_v6 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] settings_v5 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_v5 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] settings_v3 — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_v3 화면 heal 재시도 시 참고

---

### [Locator Heal Failed] settings_general — UNKNOWN
**문제**: `SEL_* 상수를 찾을 수 없음` — XML에서 유사 요소를 찾지 못함
**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성
**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요
**적용 범위**: settings_general 화면 heal 재시도 시 참고

---

<!-- iOS 관련 패턴은 여기에 추가 -->

## 공통

### [세션 초기화 실패] 연속 Appium 세션 실행 시 3번째 세션 UiAutomator2 초기화 오류
**문제**: 3개 이상의 테스트를 순차 실행할 때 3번째 세션에서 UiAutomator2 서버 초기화 실패
**원인**: 이전 세션 정리가 완료되기 전 새 세션이 시작되어 서버가 충돌
**해결**: `pytest-rerunfailures`로 제품 레벨에서 처리 (`--reruns 2 --reruns-delay 5` 자동 적용). 테스트 파일 수정 불필요
**적용 범위**: `requirements.txt`에 `pytest-rerunfailures` 추가, `05_execute.py`에 설치 여부 감지 후 자동 적용

---

### [assertion 실패] 한국어 단말에서 영문 텍스트 assertion 실패
**문제**: `assert 'Settings' in el.text` 형태의 검증이 한국어 단말에서 실패 ("설정"으로 표시됨)
**원인**: 단말 언어 설정에 따라 UI 문자열이 달라짐
**해결**: `assert el.text`(비어있지 않음)로 수정하거나 locator를 resource-id/accessibility-id 기반으로 변경
**적용 범위**: 생성 코드에서 텍스트 직접 비교 assertion을 사용할 때 주의

---

### [빠른 실행 체크박스] 숨겨진 탭의 체크박스가 함께 선택되는 오동작
**문제**: `document.querySelectorAll('.quick-group-cb:checked')`가 숨겨진 탭의 체크박스까지 수집하여 의도하지 않은 TC가 실행됨
**원인**: CSS 선택자가 현재 활성 탭 범위를 제한하지 않음
**해결**: `.quick-group-list .quick-group-cb:checked`로 범위를 현재 목록으로 한정
**적용 범위**: `dashboard.html` 빠른 실행 체크박스 수집 로직

---

### [conftest 스크린샷 실패] teardown 후 세션 끊김 상태에서 스크린샷 시도
**문제**: 드라이버 teardown 이후 conftest에서 스크린샷을 시도하면 세션이 이미 끊긴 상태라 오류 발생
**원인**: teardown_method 이후 드라이버 세션이 종료된 상태
**해결**: `teardown_method`에 `try/except` 추가로 드라이버 종료 예외를 흡수. 자체 완결형 테스트 파일에서는 conftest 공유 fixture를 사용하지 않음
**적용 범위**: Capture Studio generate 엔드포인트(`/capture/generate_from_actions`)가 생성하는 pytest 파일

---

### [Capture Studio 계층 트리 높이] 우측 패널 높이에 맞지 않아 잘리는 현상
**문제**: hierarchy tree 패널이 우측 패널 높이를 채우지 못하거나 넘침
**원인**: JS로 height를 동기화하는 방식은 resize 이벤트 타이밍에 따라 불일치 발생
**해결**: CSS `grid-template-rows:1fr` + `min-height:0` 조합으로 부모 컨테이너 안에서 자연스럽게 채움. JS height sync 불필요
**적용 범위**: Capture Studio hierarchy tree CSS

---

### [대시보드 KPI 미갱신] 빠른 실행 완료 후 KPI·히스토리가 갱신되지 않는 문제
**문제**: 빠른 실행 완료 후 대시보드 Overview KPI와 실행 히스토리가 자동으로 갱신되지 않음
**원인**: 빠른 실행 완료 콜백에서 `refreshOverview()`와 `renderRunHistory()` 호출이 누락됨
**해결**: 빠른 실행 완료 시 두 함수를 순서대로 자동 호출하도록 추가
**적용 범위**: `dashboard.html` 빠른 실행 완료 핸들러
