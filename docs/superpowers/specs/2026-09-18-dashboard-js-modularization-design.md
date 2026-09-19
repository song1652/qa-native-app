# Dashboard JavaScript Modularization Design

## 목적

`agents/dashboard/static/dashboard.js`에 모여 있는 5,241줄의 클라이언트 코드를 기능별 classic script로 분리한다. QA팀이 실행, 관측성, 환경설정, Capture Studio 기능을 서로 독립적으로 찾고 수정할 수 있게 하되 현재 UI와 런타임 동작은 변경하지 않는다.

## 선택한 접근

ES Module이나 새 프런트엔드 프레임워크를 도입하지 않고 브라우저의 일반 `<script src>` 로딩을 유지한다. 기존 HTML의 인라인 `onclick`, 전역 함수명, 전역 상태, API 경로와 이벤트 계약을 그대로 보존한다.

이 접근은 구조 개선과 동작 변경을 분리한다. 이번 작업에서는 파일 경계만 만든다. `window.QA` 네임스페이스나 모듈 비공개 상태 도입은 실제 사용이 안정된 뒤 별도 리팩터링으로 진행한다.

## 파일 구조

### `dashboard-shell.js`

화면 전환, 공통 상태, 개요 화면, 진행률, 실행 이력과 공통 로그 UI를 담당한다. 현재 `dashboard.js`의 처음부터 `// ── 스텝 숫자 상태` 직전까지가 기본 경계다.

### `execution.js`

파이프라인 실행, 취소, 디바이스 선택, 상태 폴링, 빠른 실행, Import Studio, 리포트와 TC 폴더 목록을 담당한다. 현재 `// ── 스텝 숫자 상태`부터 `Execution Observability` 직전까지가 경계다.

### `observability.js`

증거 보존 정책, 증거 상세, TC 결과 워크스페이스, 시스템 로그 필터와 실행 결과 복원을 담당한다. 기존 초기화 IIFE는 포함하지 않는다.

### `environment.js`

Appium 상태, Android/iOS 가상·실기기 관리, Wi-Fi ADB 페어링과 WDA 빌드를 담당한다.

### `capture-studio.js`

Capture Studio 세션, 미러링, hierarchy/locator, 단계 기록, 코드 생성, healing 재확인, MCP 상태, Livetail과 스와이프 입력을 담당한다.

### `dashboard-init.js`

다른 다섯 파일이 모두 로드된 후 초기 렌더링, API 조회, 관측성 복원과 주기적 폴링을 시작한다.

## 로딩 순서

`dashboard.html`은 다음 순서로 동기 classic script를 로드한다.

1. `dashboard-shell.js`
2. `execution.js`
3. `observability.js`
4. `environment.js`
5. `capture-studio.js`
6. `dashboard-init.js`

초기화 파일은 반드시 마지막이다. 기존 단일 파일에서는 초기화 IIFE가 `await`로 양보한 사이 뒤쪽 함수 선언이 실행되어 동작했다. 외부 파일을 단순 절단하면 네트워크 로딩 속도에 따라 초기화가 환경설정 파일보다 먼저 재개될 수 있으므로 초기화를 마지막 파일로 이동해 이 경쟁 조건을 제거한다.

## 정적 자산 제공

FastAPI의 대시보드 자산 허용 목록에 여섯 JavaScript 파일을 명시한다. 임의 경로나 디렉터리 전체를 노출하지 않는다. 기존 `dashboard.js`는 모든 참조와 테스트가 새 파일로 전환된 후 제거한다.

## 테스트 전략

1. 루트 HTML이 여섯 파일을 정확한 순서로 참조하는 HTTP 계약 테스트를 먼저 작성하고 실패를 확인한다.
2. 각 파일이 HTTP 200과 JavaScript content-type으로 제공되는지 확인한다.
3. 테스트용 소스 로더는 HTML의 script `src` 순서를 읽어 해당 JavaScript를 결합한다. 새 파일 추가 시 테스트 헬퍼 목록을 수동으로 수정하지 않게 한다.
4. 추출 전 `dashboard.js`와 새 파일의 원본 순서 재조합 결과를 SHA-256 및 바이트 비교로 확인한다. 초기화 블록은 원래 위치에 삽입해 비교한다.
5. 모든 JavaScript 파일에 `node --check`를 실행한다.
6. 전체 `tests/dashboard`와 Playwright E2E를 실행한다.
7. Android 에뮬레이터의 `obs_demo`를 `--no-rerun`으로 실행해 1 PASS/의도된 2 FAIL, 실패별 영상·로그·스크린샷과 단일 attempt를 확인한다.

## 변경하지 않는 항목

- UI 디자인과 문구
- 백엔드 API 및 WebSocket 계약
- Android/iOS 실행 정책
- 전역 함수와 인라인 이벤트 이름
- 힐링 생략 기본값과 단일 실행 정책
- 리포트 데이터 형식

## 완료 조건

- `dashboard.js`가 제거되고 여섯 기능 파일로 대체된다.
- 초기화는 모든 기능 파일 뒤에서 한 번만 실행된다.
- 기존 소스 계약과 사용자 동작이 유지된다.
- 전체 자동화 테스트와 실제 Android `obs_demo` 검증이 완료된다.

## 후속 작업

파일 분리 이후 실제 수정 빈도와 결합 지점을 관찰한다. 필요하면 별도 작업으로 `window.QA` 네임스페이스와 기능별 상태 캡슐화를 도입한다. 이번 작업에는 포함하지 않는다.
