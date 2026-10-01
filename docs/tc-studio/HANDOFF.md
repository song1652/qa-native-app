# TC 스튜디오 이식 — 다른 LLM에게 일 맡기는 법

> 이 문서는 **사람(작업 지시자)** 이 읽고, 아래 프롬프트를 복사해 다른 LLM(코딩 에이전트)에게 붙여 넣는 용도다.
> 작성: 2026-10-01 · 2026-10-02 갱신: Phase 1~7 검증 완료. 실제 Claude 호출·실제 TC 반영을 확인했다.

## 1. 한눈에 보기

| 항목 | 내용 |
|---|---|
| 무엇을 | 웹 저장소의 TC 스튜디오(LLM으로 TC 초안 생성, 엑셀 가져오기·내보내기, TC 라이브러리)를 **이 저장소에 이식**하고, 앱 TC에 **And/iOS 결과 비교**를 넣는다 |
| 작업 저장소 | `/Users/junghoyoung/qa-native-app` (이 저장소, FastAPI 대시보드 8767) |
| 참고 저장소 | `/Users/junghoyoung/qa-native-fixed` — **읽기 전용**, 기준 커밋 `f4e7a6b` |
| 설계 | [TC_STUDIO_APP_DESIGN.md](TC_STUDIO_APP_DESIGN.md) |
| 작업 목록 | [TC_STUDIO_APP_PLAN.md](TC_STUDIO_APP_PLAN.md) — Phase 0~7, 체크박스로 진행 추적 |

## 2. 맡기기 전에 사람이 할 일

1. LLM이 두 저장소 폴더를 **읽을 수** 있고, `qa-native-app`에만 **쓸 수** 있게 한다. 가능하면 `qa-native-fixed`는 쓰기 권한을 주지 않는다.
2. 터미널에서 `claude` CLI가 로그인돼 있는지 확인한다(`claude -p "hi"`). Phase 3의 실제 생성 확인과 Phase 7 통합 검증에서만 쓴다. 테스트는 가짜 LLM을 쓴다.
3. 한 번에 **Phase 1개**씩 맡긴다. 끝나면 4장의 "검토 체크리스트"로 확인하고 다음 Phase를 맡긴다.
4. LLM이 "사용자 확인"이라며 멈추면 직접 답한다(5장).

## 3. 프롬프트

### 3.1 공통 규칙 — 모든 프롬프트 맨 앞에 붙인다

```text
[작업 규칙 — 반드시 지켜]
- 작업 저장소: /Users/junghoyoung/qa-native-app (여기에만 쓴다)
- 참고 저장소: /Users/junghoyoung/qa-native-fixed 는 읽기 전용이다.
  파일 수정·생성·삭제, git commit/push/checkout, 8766 서버 실행·재시작을 절대 하지 마.
  원본은 `git -C /Users/junghoyoung/qa-native-fixed show f4e7a6b:<경로>` 로 읽어.
- 먼저 읽을 것: qa-native-app/CLAUDE.md, docs/tc-studio/README.md,
  docs/tc-studio/TC_STUDIO_APP_DESIGN.md, docs/tc-studio/TC_STUDIO_APP_PLAN.md
- PLAN의 "Global Constraints"를 모두 지켜. 특히:
  · 이식 파이썬은 웹과 같은 파일 이름(scripts/_tc_*.py), API는 웹과 같은 URL·응답 모양
  · LLM은 `claude -p` CLI subprocess로만 호출. anthropic/openai/langchain SDK import 금지
  · 엑셀은 특정 양식(야핏무브·LODIS)에 맞추지 마. 예시일 뿐이다
  · 테스트를 먼저 옮기거나 쓰고 실패를 확인한 뒤(RED) 구현해 통과시켜(GREEN)
  · 테스트는 tmp_path만 쓴다. 실제 state/tc_library, testcases/, import/ 를 건드리지 마
  · 파이썬을 고치면 8767 대시보드를 재시작해
- PLAN에 "사용자 확인"이라고 적힌 곳에서는 멈추고 나에게 물어봐.
- 이 범위를 넘는 기능(웹 TC 스튜디오에 없는 것, PLAN에 없는 것)은 만들지 마.
- 커밋: Task 단위, 한국어 conventional commit, 끝에
  "Co-Authored-By: <너의 모델 이름> <noreply@...>" 한 줄. 끝난 항목은 PLAN 체크박스를 [x]로 바꿔 같은 커밋에 넣어.
- git push 는 절대 하지 마(내가 따로 시킨다).
- 보고는 한국어로 짧고 쉽게.
```

### 3.2 Phase 하나를 맡길 때 (기본)

`N`만 바꿔서 쓴다. Phase 1부터 7까지 순서대로.

```text
(3.1 공통 규칙)

docs/tc-studio/TC_STUDIO_APP_PLAN.md 의 Phase N 만 진행해줘.
- Phase N의 모든 Task와 체크박스를 끝내고 멈춰. 다음 Phase로 넘어가지 마.
- 끝나면 아래 형식으로 보고해:
  1) 한 일 (Task별 한 줄)
  2) 테스트 결과: 실행한 명령과 통과/실패 건수 (출력 마지막 줄 그대로)
  3) 커밋 목록 (git log --oneline)
  4) `git -C /Users/junghoyoung/qa-native-fixed status --short` 출력 (비어 있어야 함)
  5) 웹 원본과 다르게 만든 점과 이유
  6) 막힌 점·확인이 필요한 점
```

### 3.3 끊겼다가 이어갈 때

```text
(3.1 공통 규칙)

docs/tc-studio/TC_STUDIO_APP_PLAN.md 의 체크박스와 `git log --oneline -20`,
`git status` 를 보고 어디까지 했는지 먼저 알려줘.
반쯤 된 Task가 있으면 무엇이 남았는지 설명하고, 그 Task만 마저 끝낸 뒤 멈춰.
```

### 3.4 다 끝났을 때 (push 직전 점검)

```text
(3.1 공통 규칙)

PLAN의 모든 체크박스가 [x]인지 확인하고, PLAN "검증 명령"을 전부 다시 실행해.
docs/tc-studio/ 와 docs/guides/USER_GUIDE.html, CLAUDE.md 의 링크가 실제 파일을 가리키는지 점검해.
결과만 보고하고 push 는 하지 마.
```

push는 결과를 보고 사람이 직접 하거나, 확인 후 "main에 push해줘"라고 따로 시킨다.

## 4. Phase별 검토 체크리스트 (사람용)

LLM의 보고를 받으면 아래를 확인한다. 하나라도 아니면 그 Phase를 다시 시킨다.

**모든 Phase 공통**
- [ ] `git -C /Users/junghoyoung/qa-native-fixed status --short` 가 비어 있다.
- [ ] `cd /Users/junghoyoung/qa-native-app && python3 -m pytest tests/unit tests/dashboard -q` 가 통과한다(직접 실행해 본다).
- [ ] `git diff HEAD~N --stat`에 `testcases/`, `import/`, `state/tc_library/` 아래 파일이 없다(테스트가 실데이터를 쓰지 않았다).
- [ ] `grep -rn "import anthropic\|from anthropic\|openai\|langchain" scripts agents` 결과가 없다.
- [ ] PLAN의 해당 Phase 체크박스가 [x]다.

**Phase별**

| Phase | 확인할 것 |
|---|---|
| 1 코어 | `tests/unit/tc_library/`에 웹 테스트가 옮겨져 있고 `test_tc_platform_results.py`가 있다. `scripts/_paths.py`의 라이브러리 경로가 이 저장소 `state/tc_library`다 |
| 2 엑셀 | 2줄 헤더(`환경` 아래 `And | iOS`)와 1줄 헤더(`Android | iOS`) 워크북 테스트가 있다. 왕복 후 Android Pass·iOS Fail이 그대로다. 특정 파일 이름(야핏무브·LODIS)을 코드에서 쓰지 않는다 |
| 3 LLM | `_tc_generate.py`의 `claude` 명령에 `--restricted`, `--tools ""`, `--strict-mcp-config`, `--json-schema`가 있고 `--dangerously-skip-permissions`가 없다. 자격 증명 파일이 `.gitignore`에 있다 |
| 4 API | 대시보드 재시작 후 `curl -s localhost:8767/api/tc-library` 가 JSON을 준다. `mismatch` 필터 테스트가 있다 |
| 5 md | 테스트가 `tmp_path`에만 md를 쓴다. 생성 md를 `02_generate.parse_tc_blocks`가 0건이 아니게 읽는 테스트가 있다. md 형식 코드가 `import_excel._render_markdown` 하나다 |
| 6 화면 | 브라우저에서 `http://localhost:8767` → 사이드바 "TC 작성 › TC 스튜디오"를 누르면 웹 원본과 같은 독립된 `/tc-studio` 화면이 열린다. 앱 스위트에서 `And | iOS` 2칸과 "결과가 다른 것만" 필터가 동작한다. Capture·Import·ENV 화면이 그대로다 |
| 7 마무리 | 3.4 결과에서 실패 0, 링크 깨짐 0 |

## 5. LLM이 물어볼 "사용자 확인" 지점과 미리 정한 답

| 위치 | 질문 | 답 |
|---|---|---|
| Phase 0 · 0.1 | 작업 트리 정리 | **완료.** 삭제된 TC(`tc_capture_settings_search_input.py`)와 `-` 스크린샷은 출처를 몰라 보류 중. 손대지 말라고 답한다 |
| Phase 6 | 기존 Import Studio를 둘지 합칠지 | TC Studio로 통합. 독립 메뉴 제거, 예전 주소는 가져오기 모달로 연결. 직접 변환 API는 호환용 유지 |
| Phase 7 | 실제 `claude`로 초안 생성 시험 | 2026-10-02 사용자 지시로 진행 완료. 초안 3건 생성 |
| Phase 7 | 실제 `testcases/`에 md 반영 | 2026-10-02 사용자 지시로 진행 완료. 신규 검증 폴더에 Markdown 3건 반영 |

## 6. 자주 생기는 실수와 막는 말

| 실수 | 보이면 이렇게 지시 |
|---|---|
| 웹 저장소 파일을 고치거나 거기서 테스트·서버를 돌림 | "qa-native-fixed 변경을 `git -C ../qa-native-fixed checkout -- .`로 되돌리지 말고, 무엇을 바꿨는지만 보고해." (되돌리기는 사람이 확인 후 직접) |
| 웹 코드를 크게 고쳐 쓰거나 파일 이름을 바꿈 | "웹과 같은 파일 이름·함수 이름을 유지해. 바꾼 이유가 이 저장소 경로·FastAPI 때문이 아니면 원본대로 돌려." |
| API 경로·응답 모양을 바꿈 | "웹 `routes_tc_*.py`와 같은 URL·응답 키로 맞춰. JS를 거의 안 고치고 옮기는 게 목적이다." |
| 테스트 없이 한꺼번에 이식 | "해당 웹 테스트를 먼저 옮겨 실패를 보여 주고 나서 구현해." |
| 예시 엑셀 구조를 하드코딩 | "열 위치·시트 이름을 고정하지 말고 라벨 별칭(`platform_key`)과 열 매핑 프로필로 처리해." |
| 범위 밖 기능 추가(자동 실행 결과 역반영, AUTO 열 등) | "DESIGN 3장 '범위 밖'이다. 빼." |
| 한 번에 여러 Phase 진행 | "Phase N만 하고 멈춰." |

## 7. 참고: 웹 원본 위치 (f4e7a6b)

- 파이썬: `scripts/_tc_*.py` (21개, 합계 약 4,300줄)
- 라우트: `agents/dashboard/routes_tc_library.py`, `routes_tc_authoring.py`, `routes_tc_connectors.py`, `routes_tc_import_admin.py`, `routes_tc_md.py`
- 화면: `agents/dashboard/static/js/tc-studio/*.js`(10개, 약 2,800줄), `static/css/tc-studio.css`
- 테스트: `tests/unit/tc_library/` (픽스처 5개 + 테스트 32개, 가짜 LLM `fake_claude.py`)
- 사용자 설명서: `doc/guides/tc-studio/TC_AUTHORING_USER_GUIDE.md`
