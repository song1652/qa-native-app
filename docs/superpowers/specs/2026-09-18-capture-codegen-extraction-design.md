# Capture Code Generation Extraction Design

## 목적

`agents/dashboard/routes/capture.py`의 `capture_generate_from_actions`에 포함된 대규모 pytest 코드 생성 로직을 별도 모듈로 분리한다. Capture Studio의 HTTP 계약과 생성 코드 내용은 유지하면서 라우터가 요청·응답에 집중하도록 만든다.

## 범위

- 새 `agents/dashboard/utils/capture_codegen.py`가 actions 기반 pytest 코드 생성과 생성 파일 저장을 담당한다.
- `routes/capture.py`의 `/capture/generate_from_actions` 엔드포인트는 request JSON과 현재 세션을 서비스에 전달하고 결과를 `JSONResponse`로 반환한다.
- platform 또는 tc_id 검증 실패는 서비스의 명시적 예외로 표현하고 라우터가 기존 400 응답으로 변환한다.
- 현재 응답 필드 `ok`, `file`, `code`, `lines`와 생성 파일 경로를 유지한다.
- Android/iOS 템플릿, action 필터, locator 변환, 앱 초기화, assertion 생성 결과를 변경하지 않는다.

## 인터페이스

```python
class CaptureCodegenValidationError(ValueError):
    pass


def generate_test_from_actions(
    body: dict,
    session: dict,
    project_root: Path,
    *,
    generated_at: datetime | None = None,
) -> dict:
    ...
```

성공 시 기존 JSON payload와 동일한 dict를 반환한다. 검증 실패 시 `CaptureCodegenValidationError`를 발생시킨다. `generated_at`은 테스트가 생성 시각을 고정할 때만 사용하며 실제 요청에서는 현재 시각을 사용한다.

## 의존성 방향

`routes/capture.py`가 `utils.capture_codegen`을 import한다. 코드 생성 모듈은 FastAPI, dashboard shared state 또는 라우터를 import하지 않는다. 파일시스템 기준은 인자로 전달된 `project_root`만 사용한다.

## 안전 전략

기존 엔드포인트 회귀 테스트를 먼저 실행해 기준선을 확인한다. 새 서비스의 실제 Android/iOS 생성 결과를 임시 디렉터리에서 컴파일하는 테스트를 먼저 작성하고 import 실패를 확인한 후 구현한다. 기존 함수 본문은 동작 변경 없이 이동하며, 라우터 통합 테스트와 전체 dashboard 테스트를 실행한다.

## 완료 조건

- `capture_generate_from_actions`가 얇은 HTTP 어댑터가 된다.
- 새 모듈이 Android/iOS 생성 코드와 파일 저장을 담당한다.
- 생성된 두 플랫폼 코드가 Python `compile()`을 통과한다.
- 기존 Capture Studio와 전체 dashboard 테스트가 통과한다.
