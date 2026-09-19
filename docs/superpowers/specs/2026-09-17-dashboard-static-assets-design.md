# Dashboard Static Assets Design

## 목적

`agents/dashboard/dashboard.html`에 함께 들어 있는 약 7천 줄의 HTML, CSS, JavaScript를 동작 변경 없이 분리해 파일 책임을 명확히 하고 이후 변경의 충돌 위험을 낮춘다.

## 범위

- HTML 구조는 `dashboard.html`에 유지한다.
- 인라인 `<style>` 본문은 `static/dashboard.css`로 이동한다.
- 인라인 `<script>` 본문은 `static/dashboard.js`로 이동한다.
- 기존 전역 함수명, 전역 상태, 인라인 `onclick` 계약, 스크립트 실행 순서를 유지한다.
- FastAPI가 허용 목록에 있는 두 정적 파일만 `/static/dashboard.css`와 `/static/dashboard.js`로 제공한다.
- 기존 화면 기능, API 요청, Android/iOS 실행 흐름, 관측성 UI의 동작과 디자인은 변경하지 않는다.

## 안전 전략

현재 작업 트리에는 사용자가 Claude와 완료한 미커밋 변경이 포함되어 있다. 새 워크트리는 이 기준 상태를 잃으므로 현재 작업공간에서 대상 파일만 변경한다. 먼저 HTTP 자산 제공 계약을 실패 테스트로 고정하고, 추출 전후 CSS/JavaScript 본문의 SHA-256을 비교해 기계적 이동 중 내용 손실을 방지한다.

소스 문자열을 직접 검사하던 기존 회귀 테스트는 HTML과 외부 JavaScript를 합친 테스트 전용 소스 로더를 사용하도록 바꾼다. 사용자 관점 검증은 실제 FastAPI 응답과 Playwright 브라우저 로딩으로 수행한다.

## 파일 책임

- `agents/dashboard/dashboard.html`: 문서 구조와 외부 자산 참조
- `agents/dashboard/static/dashboard.css`: 대시보드 전체 스타일
- `agents/dashboard/static/dashboard.js`: 기존 클라이언트 동작
- `agents/dashboard/routes/api.py`: 허용된 대시보드 정적 자산 제공
- `tests/dashboard/dashboard_source.py`: 정적 소스 회귀 테스트용 HTML/JS 결합 로더
- `tests/dashboard/test_dashboard_assets.py`: 실제 HTTP 자산 제공 계약 검증

## 완료 조건

- `dashboard.html`에 인라인 `<style>` 및 인라인 `<script>`가 없다.
- CSS와 JavaScript가 각각 기존 본문과 바이트 단위로 동일하다(끝 개행 정규화 제외).
- 브라우저에서 CSS와 JavaScript가 200으로 로드되고 기존 화면이 초기화된다.
- JavaScript 문법 검사와 전체 `tests/dashboard`가 통과한다.
