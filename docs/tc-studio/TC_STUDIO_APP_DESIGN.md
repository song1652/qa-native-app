# TC 스튜디오 앱 이식 — 설계

> 상태: 개정(2026-10-01). 이전 안(웹 수정 + iframe 임베드)은 사용자 지시로 폐기 — 웹 저장소는 읽기 전용.
> 실행 계획: [TC_STUDIO_APP_PLAN.md](TC_STUDIO_APP_PLAN.md)

## 1. 목표

> **핵심 요구(사용자 2026-10-01): And와 iOS 결과를 비교할 수 있으면 된다.** 아래 결정은 이 범위와 "웹 TC 스튜디오와 같은 기능"을 넘지 않는다.

- 웹 TC 스튜디오의 기능을 이 저장소에 이식한다: TC 라이브러리(스위트·시트·분류), 엑셀 가져오기·내보내기, 기획 정보(파일·붙여넣기·URL·Confluence·Figma) → LLM 초안 생성·검토·승인, 작성 프로필, 휴지통, 이력.
- 앱 스위트는 TC 하나에 **And/iOS 결과 두 칸**을 두고, 결과가 다른 TC만 걸러 볼 수 있다.
- 승인한 TC는 `testcases/{android,ios}/{group}/` md로 내보내고, 앱 파이프라인(`01_analyze → 02_generate → …`)은 고치지 않고 그대로 소비한다.
- `qa-native-fixed`는 수정하지 않는다.

## 2. 결정

### 2.1 구조: 웹 코드를 참고해 이 저장소로 이식

```text
qa-native-fixed (읽기 전용, f4e7a6b)           qa-native-app (8767)
┌──────────────────────────────┐              ┌──────────────────────────────────┐
│ scripts/_tc_*.py              │  참고·이식   │ scripts/_tc_*.py (이식본)         │
│ routes_tc_*.py (Mixin)        │ ───────────▶ │ routes/tc_studio.py (FastAPI)     │
│ static/js/tc-studio/*.js      │              │ static/tc-studio/*.js, .css       │
└──────────────────────────────┘              │ state/tc_library/ (라이브러리)    │
                                               │   └ md 내보내기 → testcases/{os}/ │
                                               └──────────────────────────────────┘
```

| 안 | 판단 | 이유 |
|---|---|---|
| A. 이 저장소로 이식 | **채택** | 웹 저장소 수정 금지(사용자 지시). 순수 파이썬 모듈(`scripts/_tc_*.py`)은 `_paths`·`_state` 두 의존만 바꾸면 거의 그대로 쓸 수 있다 |
| B. 웹 화면 iframe 임베드 | 거절 | 웹에 `embed` 모드를 넣어야 하고(수정 금지), 웹의 결과 병합 버그 때문에 And/iOS 비교가 안 된다 |
| C. 공통 패키지 분리 | 거절 | 웹 저장소 수정이 필요하다 |

**이식 원칙**
- 파이썬 모듈은 **같은 파일 이름**(`scripts/_tc_*.py`)으로 가져온다. 웹과 비교·추적하기 쉽게 하기 위해서다. 웹 의존 `_paths`·`_state`는 이 저장소에 필요한 것만 담은 작은 `scripts/_paths.py`·`scripts/_state.py`로 대신한다(경로는 이 저장소 기준 `state/tc_library/`).
- 라우트는 웹의 `ThreadingHTTPServer` 믹스인을 **FastAPI 라우터 1개**(`agents/dashboard/routes/tc_studio.py`)로 다시 쓴다. **URL 경로와 응답 모양은 웹과 같게 유지**한다(`/api/tc-library/...`). 그래야 JS와 테스트를 거의 그대로 옮길 수 있다.
- JS·CSS는 `agents/dashboard/static/tc-studio/`로 옮기고, 앱 대시보드 사이드바 "TC 작성"에 **TC 스튜디오** 메뉴를 추가한다.
- 웹 모듈 중 앱에 필요 없는 것(웹 md 형식 내보내기 `_tc_md_export.py`가 쓰는 웹 `_import_commit`·`_import_validator`)은 가져오지 않고 2.4로 대신한다.
- 웹 테스트(`tests/unit/tc_library/`)를 함께 옮겨 이식이 맞는지 확인한다. 가짜 LLM(`fake_claude.py`)도 옮긴다.

### 2.2 데이터 모델: 공통 TC 하나 + 플랫폼별 결과

> **엑셀은 특정 양식에 맞추지 않는다.** 아래 두 파일은 팀 관행을 보여 주는 **예시**일 뿐이다(사용자 2026-10-01). 플랫폼 결과 열은 라벨 별칭으로 자동 인식하고, 인식이 안 되면 가져오기의 열 매핑(작성 프로필)에서 사용자가 지정한다. 테스트 픽스처도 `tmp_path`에 만든 작은 워크북을 쓰고, 예시 파일의 건수를 완료 조건으로 쓰지 않는다.

예시에서 본 관행:

- **마스터 TC 형식(예: 야핏무브)**: 헤더가 2줄로, 상위 `환경` 아래 하위 `And | iOS` 두 결과 칸. 한쪽 전용 TC는 반대쪽 칸이 `NA`. 같은 TC 안 문구 차이는 Expected에 `And : …` / `iOS : …` 줄로 적음. `AUTO` 열은 쓰지 않는다(사용자 확인).
- **실행 기록 형식(예: LODIS)**: `… | Android | iOS | 검증자 | …` 한 줄 헤더, 한 행 = 한 TC를 두 플랫폼에서 수행. 전용 TC는 반대쪽 N/A. 두 결과가 다른 행이 대부분 실제 결함 — 그래서 "결과가 다른 것만" 필터가 핵심이다.

케이스 필드(이식본 `scripts/_tc_model.py`에 추가):

| 필드 | 값 | 비고 |
|---|---|---|
| `platforms` | `["android","ios"]` 기본, 전용 TC는 하나 | 앱 스위트에서만 의미 있음 |
| `results` | `{"android": "pass", "ios": "fail"}` | 값은 기존 `EXECUTION_RESULTS` |
| `execution_result` | **파생값** = `merge_results(results.values())` | 기존 화면·필터·요약과 호환 |

스위트 필드 `kind`: `"web"` / `"app"`. 엑셀 가져오기 때 결과 열 라벨에 플랫폼 키가 있으면 `app`.

결과 열 라벨 별칭(`platform_key`, 한 모듈에만): `And`·`Android`·`AOS`·`안드로이드` → android / `iOS`·`IOS`·`아이폰` → ios. 대소문자·앞뒤 공백 무시.

- 한쪽이 `NA`이고 다른 쪽이 비었거나 값이 있으면 그 TC는 다른 쪽 전용(`platforms` 하나). 둘 다 비면 둘 다.
- 엑셀 내보내기는 각 결과 열에 해당 플랫폼 값을 쓴다(웹 원본의 병합 버그를 이식본에서는 처음부터 고친 형태로 만든다).
- Expected 안의 `And : …` / `iOS : …` 줄은 본문 그대로 둔다.

거절한 모델: 플랫폼별로 TC를 둘로 쪼갬(건수 2배·어긋남), 플랫폼별 Step/Expected 덮어쓰기(요구는 결과 비교뿐).

### 2.3 화면 원칙

- 웹 TC 스튜디오 화면(라이브러리·기획 정보·생성·검토·내보내기)을 그대로 옮긴다. 웹 스위트 동작은 원본과 같다.
- 앱 스위트(`kind === "app"`)일 때만: 결과 1칸 → `And | iOS` 2칸, 전용 TC 반대쪽은 회색 N/A.
- 필터: `플랫폼(전체/And/iOS)`, **`And·iOS 결과가 다른 것만`**(핵심 기능).
- 상세 패널: 결과 선택 2개, 대상 플랫폼 체크박스. 일괄 변경 "실행 결과"는 대상 플랫폼 선택.
- LLM 초안: 생성 대상에 `대상 플랫폼(둘 다/And/iOS)`. 프롬프트 규칙: "공통 동작으로 쓴다. 흐름 전체가 한쪽에만 있으면 별도 TC(platforms 하나). 같은 TC에서 문구만 다르면 Expected에 `And : …` / `iOS : …` 줄로 적는다." 두 벌 생성 금지.

### 2.4 md 내보내기 → 앱 파이프라인

- 라이브러리의 승인된 TC를 `testcases/{android,ios}/{group}/` md로 쓴다. `platforms`에 든 OS에만 쓴다.
- md 형식은 이 저장소 `scripts/import_excel.py:_render_markdown`이 **유일하게 소유**한다(형식을 그리는 코드를 두 곳에 만들지 않는다). 이 형식은 `02_generate.parse_tc_blocks`가 읽는 `## 테스트 케이스 N` 블록이다.
- 충돌 정책은 Import Studio와 같다: 기본 `skip-conflict`, 명시적으로 `overwrite`.
- 웹의 md 내보내기 미리보기·반영·되돌리기 흐름(화면)은 유지하되, 쓰는 대상과 형식만 위처럼 바꾼다.

### 2.5 LLM 호출과 자격 증명

- 웹 `_tc_generate.py`의 보안 설정을 그대로 쓴다: `claude -p --restricted --tools "" --strict-mcp-config --json-schema`, 저장소 밖 임시 작업 폴더, `--dangerously-skip-permissions` 금지.
- Confluence·Figma 토큰은 웹 `_tc_credentials.py` 방식대로 이 저장소 쪽에 따로 저장한다(웹 저장소 파일을 읽지 않는다). git에 올라가지 않게 한다.
- 외부 요청은 웹 `_tc_fetch.py`의 호스트 허용 정책(Policy)을 그대로 쓴다.

## 3. 범위 밖 (이번에 하지 않음)

- `qa-native-fixed` 수정, 웹과의 자동 동기화.
- AUTO 열 기능.
- 앱 파이프라인 자동 실행 결과를 `results`에 역반영.
- Expected의 `And :`/`iOS :` 줄을 플랫폼별로 쪼개기.
- 플랫폼별 Step/Expected 덮어쓰기.
- 기존 Import Studio를 없애거나 합치기 — 마지막에 사용자에게 묻는다(PLAN Phase 6).

## 4. 위험과 대응

| 위험 | 대응 |
|---|---|
| 이식본과 웹이 시간이 지나며 어긋남 | 같은 파일 이름 유지, 기준 커밋 `f4e7a6b` 기록. 웹 변경은 필요할 때 수동으로 가져온다 |
| 이식 규모가 큼(파이썬 약 20개, JS 10개, 테스트 30여 개) | Phase를 모듈 의존 순서로 나누고, 각 Phase마다 옮긴 웹 테스트가 통과해야 다음으로 |
| FastAPI 재작성 중 API 모양이 달라짐 | URL·응답 모양을 웹과 같게. 웹 API 테스트를 옮겨 그대로 통과시킨다 |
| 사용자 데이터 손상 | 테스트는 `tmp_path`만. 실제 `state/tc_library`, `testcases/`, `import/`를 건드리지 않는다 |
| 기존 Import Studio와 기능 겹침 | 이번엔 둘 다 유지, Phase 6에서 사용자 결정 |
| `claude` CLI 미설치·미로그인 | 생성 버튼에서 웹과 같은 오류 안내(`claude CLI를 찾을 수 없습니다…`) |
