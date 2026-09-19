# Backend Maintainability 9.x Design

## Goal

기존 환경설정·Capture·관측성 API의 동작을 보존하면서 HTTP, 도메인 규칙, 외부 프로세스, 파일 저장 책임을 분리한다.

## Boundaries

- `device_registry.py`: Android/iOS 기기 등록·중복·default·최소 보유 정책
- `capture_validation.py`: XML hierarchy locator 평가와 좌표 추출
- `tests/observability/manifest.py`: slug, 보존 정책, attempt manifest, MP4 메타데이터 규칙
- 기존 route/runtime 모듈은 호환 facade 역할과 외부 I/O orchestration을 유지한다.

## Compatibility

- 모든 HTTP 경로, 상태 코드, 오류 코드와 응답 필드를 유지한다.
- `routes.env` 및 `tests._observability`의 기존 monkeypatch 지점을 유지한다.
- 새 서비스는 외부 프로세스나 전역 경로에 의존하지 않는 순수 함수로 작성한다.
- 새 런타임 의존성을 추가하지 않는다.

## Testing

- 서비스별 literal fixture 단위 테스트를 먼저 실패시킨다.
- 기존 환경설정 endpoint 전체 테스트로 HTTP 계약을 검증한다.
- Capture locator route 테스트를 서비스와 API 양쪽에서 검증한다.
- 관측성 collector, API, pipeline, E2E 테스트를 다시 실행한다.
- 최종적으로 dashboard 전체 테스트, 문법 검사, 실제 HTTP smoke를 실행한다.
