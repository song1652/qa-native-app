# Dashboard Maintainability 9.x Design

## Goal

QA 팀이 사용하는 현재 대시보드의 사용자 동작과 HTTP 계약을 유지하면서, 대형 파일의 책임을 분리하고 회귀 테스트로 경계를 고정한다. 목표는 내부 도구 기준 유지보수성 9.0 이상이며 프레임워크 교체나 화면 재작성은 범위에 포함하지 않는다.

## Constraints

- 현재 `main` 작업공간의 미커밋 변경을 보존한다.
- 기존 HTML 인라인 이벤트가 호출하는 전역 JavaScript 함수 이름을 유지한다.
- 기존 API 경로, 상태 코드, JSON 필드 이름을 변경하지 않는다.
- Android와 iOS 실행 흐름을 동일한 회귀 테스트 범위에 둔다.
- 각 분리는 먼저 실패하는 경계 테스트를 추가한 다음 최소한의 이동으로 구현한다.
- 새 런타임 의존성을 추가하지 않는다.

## Architecture

### Frontend assets

클래식 script의 전역 호환성을 유지하되 책임별 파일로 로드한다.

- Capture Studio
  - `capture-studio.js`: 공유 상태, 초기화, 세션 연결
  - `capture-inspector.js`: 미러, 계층 구조, locator 탐색
  - `capture-actions.js`: 액션 기록, 저장, 코드 생성, healing
  - `capture-livetail.js`: MCP 상태, live tail, swipe gesture
- Execution
  - `execution.js`: 파이프라인 실행과 공통 실행 상태
  - `quick-run.js`: 생성 테스트 선택, 빠른 실행, 결과 제어
  - `import-studio.js`: Excel 가져오기 wizard
  - `reports.js`: 보고서 목록, 미리보기, 삭제

각 파일은 `dashboard.html`에서 의존 순서대로 로드한다. 번들러 도입은 하지 않는다.

### Backend services

라우트는 요청 파싱과 HTTP 응답만 담당한다. OS 명령 실행, 환경 상태 계산, Capture 스트림 프레임 파싱 같은 로직은 `agents/dashboard/utils/`의 순수하거나 좁은 어댑터 함수로 이동한다.

- `env_devices.py`: AVD, simulator, 실제 기기 조회와 정규화
- `env_processes.py`: Appium 및 장치 프로세스 상태/종료 보조 함수
- `capture_streaming.py`: JPEG frame parsing, ADB serial 선택, 스트림 명령 구성

이번 단계에서 route 모듈 자체를 여러 router로 쪼개지 않는다. FastAPI 등록 순서와 테스트 monkeypatch 경계를 보존하기 위해 서비스 추출부터 수행한다.

### Observability test support

`tests/_observability.py`는 수집 runtime과 테스트 fixture 역할을 분리한다. 외부에서 import하는 기존 이름은 facade에서 재노출해 호환성을 유지한다.

## Error Handling

기존 사용자 오류 메시지와 HTTP 상태 코드는 그대로 유지한다. 추출된 서비스는 도메인 값 또는 명시적 예외를 반환하고, route에서 기존 JSON 응답으로 변환한다. 외부 프로세스의 stderr/stdout 처리 방식도 변경하지 않는다.

## Testing

- 정적 자산 API 응답과 script 로드 순서를 검증한다.
- Playwright 기반 대시보드 smoke/E2E로 전역 handler 누락과 브라우저 오류를 검증한다.
- 추출된 Python 서비스는 literal fixture 기반 단위 테스트를 추가한다.
- 각 단계 후 관련 테스트, 최종 단계 후 전체 `tests/dashboard`와 핵심 observability 테스트를 실행한다.
- 최종 서버를 재시작하고 `/`, 환경 상태, Capture 유효성 오류 API를 HTTP로 확인한다.

## Non-goals

- React/Vue 등 프레임워크 도입
- UI 디자인 변경
- API 스키마 변경
- 테스트 생성 규칙 변경
- 실행 결과나 보존 정책 변경
