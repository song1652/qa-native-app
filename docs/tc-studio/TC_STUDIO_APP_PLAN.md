# TC 스튜디오 앱 지원 — 실행 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (또는 subagent-driven-development) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**핵심 요구:** And와 iOS 결과를 비교할 수 있으면 된다(사용자 2026-10-01). 범위를 넘는 기능은 만들지 않는다.

**Goal:** 웹 TC 스튜디오(코드 1벌)에 앱 스위트 모드(공통 TC + Android/iOS 결과)를 넣고, 앱 대시보드에서 같은 화면을 메뉴로 쓰며, 앱 TC를 엑셀로 이 저장소 Import Studio에 넘긴다.

**Design:** [TC_STUDIO_APP_DESIGN.md](TC_STUDIO_APP_DESIGN.md) · **안내:** [README.md](README.md)

**두 저장소:**
- `WEB` = `/Users/junghoyoung/qa-native-fixed` (TC 스튜디오 본체, Python 표준 서버, 포트 8766)
- `APP` = `/Users/junghoyoung/qa-native-app` (이 저장소, FastAPI, 포트 8767)

## Global Constraints

- TC 스튜디오 코드를 APP으로 복사하지 않는다. WEB에서만 고친다.
- **웹 스위트 동작은 바꾸지 않는다.** 플랫폼 요소는 `kind === "app"`일 때만. WEB 기존 테스트 전부 통과가 각 Phase 완료 조건.
- 각 저장소의 `CLAUDE.md` 규칙을 따른다. WEB: 상태 쓰기는 `update_state`, 레지스트리 상수, 동작 변경 시 사용자 설명서(`doc/guides/tc-studio/TC_AUTHORING_USER_GUIDE.md`) 함께 갱신, 기능 버그는 `agents/lessons_learned.md`에 기록하지 않음(힐링 전용).
- 실패하는 테스트를 먼저 쓰고(RED) 고친다(GREEN). 수정 전 코드에서 테스트가 실패하는지 확인한다.
- 파이썬 수정 후에는 해당 대시보드 서버를 재시작해야 화면에 반영된다. JS는 새로고침(서버가 `Cache-Control: no-cache`).
- 사용자 데이터(WEB `state/tc_library`, APP `testcases/`, `import/`)를 테스트에서 건드리지 않는다. 테스트는 `tmp_path`·격리 서버를 쓴다(WEB `tests/unit/import_studio/import_studio_test_support.py:dashboard_server`).
- 커밋은 Phase(또는 Task) 단위, 메시지는 한국어 conventional commit. **push는 사용자 확인 후**.
- 설명·보고는 한국어, 짧고 쉽게.

## 검증 명령

```bash
# WEB 전체 단위·E2E (약 3.5분, 905건 기준)
cd /Users/junghoyoung/qa-native-fixed && python3 -m pytest tests/unit -q -W ignore -p no:cacheprovider
# WEB 서버 재시작
cd /Users/junghoyoung/qa-native-fixed && kill $(lsof -tiTCP:8766 -sTCP:LISTEN); nohup python3 agents/dashboard/serve.py --port 8766 >/tmp/dash8766.log 2>&1 &
# APP 테스트
cd /Users/junghoyoung/qa-native-app && python3 -m pytest tests/unit tests/dashboard -q
```

---

## Phase 0 — 준비 (APP)

### Task 0.1: APP 작업 트리 정리 — **사용자 확인**

**작업 위치:** APP

현재 미커밋 변경(2026-10-01): `config/devices.json`, `logs/*`, `state/*`(capture_session, pytest_report 등) 수정, `tests/generated/android/capture_studio_e2e/tc_capture_settings_search_input.py` 삭제, 이름이 `-`인 파일, `config/devices.json.lock`, `reports/screenshots/…`, `state/captures/` 등 추적 안 된 파일.

- [ ] `git status`로 목록을 사용자에게 보여 주고 처리 방법을 묻는다(커밋 / `.gitignore` 추가 / 되돌리기). **임의로 지우거나 되돌리지 않는다.**
- [ ] 이름이 `-`인 파일은 내용을 확인해 보여 준 뒤 처리 방법을 묻는다.
- [ ] 결정대로 정리하고 커밋. 완료 조건: `git status`가 사용자가 남기기로 한 항목만 보여 줌.

### Task 0.2: 코드 없는 경로 검증 (MVP)

**작업 위치:** WEB 대시보드 화면 + APP 대시보드 화면 (코드 수정 없음)

목적: "TC 스튜디오 엑셀 → APP Import Studio → 02_generate"가 지금도 되는지, 어디서 막히는지 확인한다.

- [ ] WEB TC 스튜디오에서 앱 TC 3~5건이 든 스위트를 엑셀로 내보낸다(예: LODIS 스위트를 시트 1개만 선택). 야핏무브(`~/Downloads/야핏무브_Full.xlsx`, 마스터 TC)도 같은 경로로 시험한다.
- [ ] 그 xlsx를 APP `import/`에 복사하고 APP Import Studio에서 열 매핑 → 미리보기 → 반영(Android·iOS). `testcases/{android,ios}/{시트}/`에 md 생성 확인.
- [ ] `python3 scripts/02_generate.py --platform android` 로 생성 파일 수(`tc_blocks` 0이 아님) 확인. 실기기 실행은 하지 않는다.
- [ ] 막힌 지점을 기록한다. 이미 알려진 것: (a) 우선순위 `P0`/`P1`이 `medium`이 됨(`scripts/import_excel.py:56`), (b) TC ID에 `_`도 숫자도 없으면 그 행을 건너뜀(`:213`), (c) 행별 플랫폼 지정 불가.
- [ ] 생성된 md는 시험용이므로 사용자에게 남길지 물어 정리한다.
- 완료 조건: 검증 결과 표(단계 / 성공 여부 / 문제)를 보고.

---

## Phase 1 — 플랫폼별 결과 (WEB) ★ 버그 수정 포함

**작업 위치:** WEB. 현재 버그: `scripts/_tc_xlsx_import.py:82-93`이 결과 열들을 `merge_results`로 하나로 합치고, `scripts/_tc_xlsx_export.py:59-61`이 그 값을 모든 결과 열에 같은 값으로 쓴다(Android Pass·iOS Fail → 왕복 후 둘 다 Fail).

### Task 1.1: 모델 — `platforms`, `results`, 파생 `execution_result`

**Files:**
- Modify: `scripts/_tc_model.py` (`EDITABLE_FIELDS` :15, `new_case` :27, `merge_results` :86, `validate_case`)
- Create: `tests/unit/tc_library/test_tc_platform_results.py`

- [ ] RED: `results={"android":"pass","ios":"fail"}`인 케이스의 `execution_result`가 `fail`로 파생되는지, `results`가 없으면 기존 `execution_result`를 그대로 쓰는지 테스트.
- [ ] 플랫폼 키 정규화 함수 `platform_key(label) -> "android"|"ios"|None` (**And**/Android/AOS/안드로이드 → android, iOS/IOS/아이폰 → ios — 대소문자 무시, 앞뒤 공백 무시). 하나의 모듈에만 둔다. 테스트에 `And`(야핏무브)와 `Android`(LODIS) 둘 다 포함.
- [ ] `EDITABLE_FIELDS`에 `platforms`, `results` 추가. `results` 값은 `EXECUTION_RESULTS` 검증, `platforms`는 `{"android","ios"}`의 비어 있지 않은 부분집합.
- [ ] 저장 시 `results`가 있으면 `execution_result = merge_results(results.values())`로 맞춘다(패치·일괄 변경 공통 경로 `scripts/_tc_library.py:_apply`).

### Task 1.2: 엑셀 가져오기 — 결과를 플랫폼별로 저장, 스위트 `kind`

**Files:**
- Modify: `scripts/_tc_xlsx_import.py:82-93`, `scripts/_tc_library.py`(`list_suites` :147 근처에 `kind`), 가져오기 커밋 경로 `scripts/_tc_import_ops.py`
- Test: `tests/unit/tc_library/test_tc_platform_results.py`

- [ ] RED: 야핏무브 형식(`환경` 아래 `And | iOS`, 헤더 11행) 픽스처에서 `And=NA`, `iOS=` 빈 행 → `platforms == ["ios"]`. LODIS 형식 픽스처(`tests/unit/tc_library/test_tc_template.py`의 `test_test_level_sub_header_becomes_priority…` 워크북 생성 방식 재사용)에서 Android Pass·iOS Fail 행 → `results == {"android":"pass","ios":"fail"}`.
- [ ] 결과 열 라벨 → `platform_key`로 `results` 구성. 플랫폼 열이 없으면 지금처럼 `execution_result`만.
- [ ] 한쪽 결과가 `na`이고 다른 쪽이 값이면 `platforms`를 값 있는 쪽만으로(전용 TC). 둘 다 비면 둘 다.
- [ ] 스위트 `kind`: 템플릿 프로필 `result_columns` 라벨에 플랫폼 키가 있으면 `"app"`. `GET /api/tc-library` 응답 스위트 항목에 `kind` 추가(테스트 기대값 `tests/unit/tc_library/test_tc_library.py:28`, `test_tc_library_api.py:66` 갱신).

### Task 1.3: 엑셀 내보내기 — 각 결과 열에 해당 플랫폼 값

**Files:** Modify `scripts/_tc_xlsx_export.py:59-61` · Test 동일 파일

- [ ] RED: 가져오기 → 내보내기 왕복 후 Android 열 Pass, iOS 열 Fail 유지.
- [ ] 결과 열 라벨 → `platform_key` → `results[key]`, 없으면 `execution_result`.
- [ ] 요약 수식 보정(`_rewrite_summary` :108-125)이 그대로 동작하는지 확인.

### Task 1.4: 화면 — 앱 스위트일 때만 `AOS | iOS`

**Files:**
- Modify: `agents/dashboard/static/js/tc-studio/library.js` (결과 칸 :206-208, 저장 :306, 필터 :484, 일괄 변경 :529, 열 정의 `colgroup` :61)
- Modify: `agents/dashboard/static/js/tc-studio/detail.js` (결과 :37, :139, :296)
- Modify: `agents/dashboard/static/js/tc-studio/state.js` (현재 스위트 `kind` 헬퍼)
- Modify: `agents/dashboard/static/css/tc-studio.css`
- Test: `tests/unit/tc_library/test_tc_studio_e2e.py` (앱 스위트 시드 추가)

- [ ] 표: 앱 스위트면 "실행 결과" 1칸 대신 `And`·`iOS` 2칸(각각 선택 상자). 플랫폼 밖이면 회색 N/A, 선택 불가. 웹 스위트는 지금 그대로(회귀 E2E).
- [ ] 필터: 앱 스위트에만 `플랫폼(전체/And/iOS)`, **`And·iOS 결과가 다른 것만`**(이 계획의 핵심 — E2E로 반드시 검증). 서버 `filter_cases`(`scripts/_tc_library.py`)에 `platform`, `mismatch` 쿼리 추가.
- [ ] 상세 패널: 결과 선택 2개 + 대상 플랫폼 체크박스.
- [ ] 일괄 변경 "실행 결과": 앱 스위트는 대상 플랫폼 선택(And/iOS/둘 다).
- [ ] 레이아웃 회귀: `tests/unit/dashboard/test_view_layout_e2e.py` 통과.

### Task 1.5: LLM 초안 — 대상 플랫폼

**Files:** `agents/dashboard/static/js/tc-studio/generate.js`(생성 대상), `scripts/_tc_generate.py`(job target), `scripts/_tc_prompt.py`(규칙 줄) · Test `tests/unit/tc_library/test_tc_generate.py`

- [ ] 앱 스위트일 때 생성 대상에 `대상 플랫폼(둘 다/And/iOS)` 선택. 초안 `platforms`에 반영.
- [ ] 프롬프트 규칙(팀 관행): "공통 동작으로 쓴다. 흐름 전체가 한쪽에만 있으면 별도 TC(platforms 하나). 같은 TC에서 문구만 다르면 Expected에 `And : …` / `iOS : …` 줄로 적는다." 두 벌 생성 금지.
- [ ] 가짜 LLM(`tests/unit/tc_library/conftest.py:fake_claude`)으로 생성 → 초안 `platforms` 확인.

### Task 1.6: 기존 데이터·문서

- [ ] 이미 가져온 앱 스위트(`results` 없음): 화면은 `execution_result`를 두 칸에 같은 값으로 보여 주고 상단에 "원본 엑셀을 다시 가져오면 플랫폼별 결과가 채워집니다" 1회 안내. **자동 변환으로 결과를 추측하지 않는다.**
- [ ] 사용자 설명서에 "앱 스위트(iOS/Android)" 절 추가: 판정 기준, 결과 2칸, 필터, 전용 TC, 생성 대상 플랫폼, 재가져오기 안내. 문제 해결 표 1행.
- [ ] `doc/reference/API_REFERENCE.md`: `kind`, `platforms`, `results`, 필터 쿼리.
- [ ] 완료 조건: WEB 전체 테스트 통과, 야핏무브 원본 가져오기 → iOS 전용 21건이 `platforms=["ios"]`, 내보내기 후 `And` 칸 `NA` 유지, LODIS 원본 재가져오기 → 내보내기 왕복에서 결과 불일치 27건 보존(사용자 화면에서 확인 요청).

---

## Phase 2 — 임베드 모드와 앱으로 보내기 (WEB)

**작업 위치:** WEB

### Task 2.1: `/tc-studio?embed=1`

**Files:** `agents/dashboard/index.html`, `agents/dashboard/static/js/router.js`(`TC_STUDIO_PATH` :2-18), CSS · Test 새 E2E `tests/unit/tc_library/test_tc_studio_embed_e2e.py`

- [ ] `embed=1`이면 대시보드 사이드바·상단 바·다른 뷰 폴링(`app.js`의 `refreshAll` 5초 주기)을 끄고 TC 스튜디오만 전체 폭으로.
- [ ] 다른 화면으로 가는 링크가 없도록 확인. 새 창 열기 등은 동작 유지.
- [ ] E2E: `embed=1`에서 `.sidebar` 숨김, `#main`에 TC 스튜디오만, 탭 4개 동작.

### Task 2.2: "앱으로 보내기"

**Files:** Create `scripts/_tc_app_handoff.py` · Modify 내보내기 라우트(`agents/dashboard/routes_tc_library.py`), `agents/dashboard/static/js/tc-studio/export.js`, `config/`(경로 설정) · Test `tests/unit/tc_library/test_tc_app_handoff.py`

- [ ] 설정: `config/tc_studio.json`의 `app_import_dir`(기본 `../qa-native-app/import`, 프로젝트 루트 기준). 폴더가 없으면 버튼 비활성 + 안내.
- [ ] xlsx 1개 생성: 시트 1개, 헤더 `tc_id | title | precondition | steps | expected | priority | platform`. `tc_id`=`source_tc_id` 또는 `case_id`, `steps`는 줄바꿈 번호 목록, `expected`는 결과 문장 + `- 화면 문구`, `platform`=`both|android|ios`.
- [ ] 파일명 `tc_studio_{스위트}_{YYYYMMDD_HHMMSS}.xlsx`(덮어쓰기 없음). 범위는 엑셀 내보내기와 동일(전체/시트/필터/승인).
- [ ] 앱 스위트에서만 버튼 노출. 결과 토스트: "N건을 앱 Import 폴더로 보냈습니다 — 앱 대시보드 Import Studio에서 반영하세요".
- [ ] 테스트는 `tmp_path`를 `app_import_dir`로 주입. 실제 APP 폴더에 쓰지 않는다.

---

## Phase 3 — 앱 대시보드 "TC 스튜디오" 메뉴 (APP)

**작업 위치:** APP

### Task 3.1: 메뉴와 뷰

**Files:**
- Modify: `agents/dashboard/dashboard.html` (사이드바 "TC 작성" :47-55, 뷰 카드 영역 — `#view-import` :271 근처에 `#view-tc_studio` 추가)
- Modify: `agents/dashboard/static/dashboard-shell.js` (`selectView` :164, `rightViews` 배열 :171에 `tc_studio`)
- Create: `agents/dashboard/static/tc-studio-embed.js`
- Modify: `agents/dashboard/shared.py` (`TC_STUDIO_URL`, 환경변수 우선, 기본 `http://localhost:8766/tc-studio?embed=1`)
- Modify: `agents/dashboard/routes/api.py` (`GET /api/tc-studio/status` → `{url, reachable}`; 서버 쪽에서 1초 타임아웃 HEAD/GET)
- Test: `tests/dashboard/test_tc_studio_embed.py`

- [ ] 사이드바 "TC 작성" 첫 항목 **TC 스튜디오**(Import Studio 위).
- [ ] 뷰를 열 때 `/api/tc-studio/status` 확인 → 닿으면 `iframe`(높이 = 뷰 영역 전체, 테두리 없음), 아니면 안내 카드: "TC 스튜디오 서버(8766)가 꺼져 있습니다" + 실행 명령 + "다시 확인" + "새 창에서 열기".
- [ ] 다른 메뉴로 갔다 와도 iframe을 다시 만들지 않는다(편집 중 내용 유지).
- [ ] 테스트: 상태 API(닿음/안 닿음은 가짜 서버로), 메뉴 노출, 안내 카드.

### Task 3.2: 문서

- [ ] APP `docs/USER_GUIDE.html`에 TC 스튜디오 메뉴 절: 무엇을 하는 곳인지, 웹 설명서 링크(`../qa-native-fixed/doc/guides/tc-studio/TC_AUTHORING_USER_GUIDE.md`), 서버 실행 방법, 앱으로 보내기 → Import Studio 흐름.
- [ ] APP `CLAUDE.md`에 "TC 스튜디오" 절 3~5줄(코드는 WEB, 이 저장소는 메뉴·Import만).

---

## Phase 4 — Import Studio 보강 (APP)

**작업 위치:** APP · **Files:** `scripts/import_excel.py`, `agents/dashboard/routes/import_studio.py`, `agents/dashboard/static/import-studio.js` · **Test:** `tests/unit/`(기존 `tests/unit/tc_import_excel.py`는 `test_` 접두가 없어 수집되지 않음 — 새 파일 `tests/unit/test_import_excel_platform.py`)

### Task 4.1: 행별 플랫폼

- [ ] RED: `platform` 열이 `ios`인 행은 iOS md만, `both`/빈 값은 선택한 플랫폼 전부.
- [ ] 매핑 필드에 선택 항목 `platform` 추가(필수 아님). `_effective_platforms`(:38) + 행 값으로 결정. 미리보기 집계도 반영.

### Task 4.2: 우선순위·ID

- [ ] 우선순위 매핑(:56): `P0`/`P1`/`BAT`/`Level 1`/`high` → high, `P3`/`low` → low, 그 외 medium. 앱 md 형식의 허용 값을 먼저 확인(`02_generate.py`가 priority를 어떻게 쓰는지).
- [ ] TC ID 규칙(:213): TC 스튜디오가 보내는 `case_id`(예: `S01_0001`)와 `source_tc_id`(예: `인증_1`)가 통과하는지 테스트. 건너뛰는 행은 미리보기에 "건너뜀(이유)"로 보이게.

### Task 4.3 (선택): 옛 형식 md 9개

- [ ] `testcases/**` 중 `## 테스트 케이스` 블록이 없는 9개 목록을 보여 주고 변환할지 **사용자에게 묻는다**. 변환 시 `_render_markdown` 형식으로, 원본은 git으로 복구 가능하게 커밋 분리.

---

## Phase 5 — 통합 검증과 마무리

- [ ] 두 대시보드 실행 → APP 메뉴에서 TC 스튜디오 열기 → LODIS 앱 스위트 시트 1개를 "앱으로 보내기" → APP Import Studio 반영 → `02_generate --platform android`·`--platform ios` 생성 수 확인(실기기 실행 없음).
- [ ] WEB 전체 테스트, APP 테스트 통과.
- [ ] 두 저장소 문서 최종 확인(링크 깨짐 0).
- [ ] 결과 보고 후 push 여부를 사용자에게 묻는다.

## 완료 정의

- 앱 스위트에서 Android/iOS 결과가 엑셀 왕복 후에도 보존된다.
- 웹 스위트 화면·동작·테스트가 이전과 같다.
- APP 대시보드에서 TC 스튜디오를 메뉴로 열고, 앱 TC를 Import Studio로 넘겨 플랫폼별 md가 생성된다.
- TC 스튜디오 코드는 WEB에만 있다.
