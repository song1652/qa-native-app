# TC 스튜디오 앱 지원 — 설계

> 상태: 확정(사용자 승인 2026-10-01). 근거는 에이전트 4명(데이터 모델·아키텍처·QA 실무/UX·반대 검토) 분석.
> 실행 계획: [TC_STUDIO_APP_PLAN.md](TC_STUDIO_APP_PLAN.md)

## 1. 목표

- 앱 QA도 웹과 **같은 TC 스튜디오 기능**(라이브러리, 엑셀 왕복, LLM 초안 생성·검토, 톤앤매너, 가져옴 구분, 휴지통)을 쓴다.
- iOS/Android 두 플랫폼의 **결과를 잃지 않고** 엑셀과 왕복한다.
- TC 스튜디오 코드는 **한 곳**(`qa-native-fixed`)에만 둔다.
- 앱 파이프라인(`01_analyze → 02_generate → …`)은 고치지 않고 그대로 소비한다.

## 2. 결정

### 2.1 구조: TC 스튜디오는 1벌, 앱 대시보드는 메뉴로 띄운다

```text
qa-native-fixed (8766)                         qa-native-app (8767)
┌──────────────────────────────┐              ┌──────────────────────────────┐
│ TC 스튜디오 (코드 1벌)         │  iframe      │ 사이드바 "TC 작성"             │
│  ├ 웹 스위트 → 웹 md 내보내기  │ ◀──────────── │   ├ TC 스튜디오 (새 메뉴)      │
│  └ 앱 스위트 (AOS|iOS 결과)    │              │   ├ Import Studio             │
│       └ 앱으로 보내기 ─────────┼── xlsx ────▶ │   │   import/*.xlsx → md        │
└──────────────────────────────┘  파일 1개     │   └ Capture Studio            │
                                                │ testcases/{android,ios}/…    │
                                                └──────────────────────────────┘
```

| 안 | 판단 | 이유 |
|---|---|---|
| A. 앱 저장소로 코드 복사 | 거절 | 앱 대시보드는 FastAPI(`agents/dashboard/serve.py:13-54`), 웹은 `ThreadingHTTPServer` + 믹스인. 파일 약 35개를 다시 써야 하고 영구히 두 벌이 된다 |
| B. 공통 패키지로 분리 | 보류 | `_paths`/`_state`(웹) ↔ `shared.py`/`utils/state.py`(앱) 경로·락 체계가 달라 주입 계층이 필요. 다른 팀이 따로 배포해야 할 때 재검토 |
| C. 웹이 앱 md를 직접 씀 | 거절 | 앱 md를 그리는 코드가 두 곳(`scripts/import_excel.py:54-80` + 웹)에 생기고, 롤백 스냅샷(웹 `state`)과 실제 파일(앱 저장소)이 어긋남 |
| **D. 엑셀로 넘김 + 메뉴 임베드** | **채택** | 앱 Import Studio가 이미 엑셀 → `testcases/{android,ios}/` md 변환을 함(`routes/import_studio.py`, `scripts/import_excel.py`). 다른 저장소에 쓰는 것은 xlsx 파일 1개뿐 |

### 2.2 데이터 모델: 공통 TC 하나 + 플랫폼별 결과

LODIS 실데이터(1,561~1,731건) 근거:
- 모든 시트가 `Test Level | Android | iOS | 검증자 | 검증일 | BTS_No | Comment` 구조. 한 행 = 한 TC를 두 플랫폼에서 수행.
- 플랫폼 전용 TC는 7건(예: "AOS 뒤로가기 버튼") — 별도 TC로 나누지 않고 반대쪽 결과를 N/A로 둠.
- Step/Expected는 거의 공통. 두 플랫폼 결과가 다른 27건은 대부분 실제 결함.

케이스 필드(웹 `scripts/_tc_model.py`에 추가):

| 필드 | 값 | 비고 |
|---|---|---|
| `platforms` | `["android","ios"]` 기본, 전용 TC는 하나 | 앱 스위트에서만 의미 있음 |
| `results` | `{"android": "pass", "ios": "fail"}` | 값은 기존 `EXECUTION_RESULTS` |
| `execution_result` | **파생값** = `merge_results(results.values())` | 기존 웹 화면·필터·md 내보내기 호환 유지 |

스위트 필드:

| 필드 | 값 | 판정 |
|---|---|---|
| `kind` | `"web"` / `"app"` | 엑셀 가져오기 때 결과 열 라벨에 Android/iOS(별칭 AOS, IOS, 안드로이드, 아이폰)가 있으면 `app`. 없으면 `web`. 기존 스위트는 템플릿 프로필로 1회 판정 |

결과 열 ↔ 플랫폼 매핑: 템플릿 프로필의 `result_columns`(라벨 → 열, `scripts/_tc_template.py:81-94`)에서 라벨을 정규화해 `android`/`ios` 키로 읽고 쓴다.

거절한 모델:
- 플랫폼별로 TC를 둘로 쪼갬 — 1,561건이 3,122건, 한쪽만 고쳐져 어긋남, 검토 2배.
- 공통 + 플랫폼별 Step/Expected 덮어쓰기(`platform_notes`) — 엑셀에 담을 열이 없고 필요 근거 부족. **실제로 단계가 다른 TC가 반복되면** 그때 추가한다.

### 2.3 화면 원칙

- **웹 스위트 화면은 지금과 동일.** 플랫폼 관련 요소는 `kind === "app"`일 때만 그린다.
- 앱 스위트: 라이브러리 표의 "실행 결과" 1칸 → `AOS | iOS` 2칸. 전용 TC의 반대쪽은 회색 N/A.
- 필터: `플랫폼(전체/AOS/iOS)`, `결과 불일치만`.
- 상세 패널: 실행 결과 선택 2개(AOS/iOS), 대상 플랫폼 체크박스.
- LLM 초안: 생성 대상에 `대상 플랫폼(둘 다/AOS/iOS)` 선택 1개. 프롬프트 규칙: "공통 동작으로 쓴다. 한쪽에만 있는 기능(예: 단말 뒤로가기)은 별도 TC로 만들고 platforms를 하나로 한다". 두 벌 생성 금지.
- 엑셀 내보내기: 원본 열 순서(`Test Level | Android | iOS | …`) 유지, 각 열에 해당 플랫폼 결과.

### 2.4 앱으로 넘기기

- 웹 TC 스튜디오 앱 스위트의 내보내기 화면에 **"앱으로 보내기"**: 앱 Import Studio가 읽는 단순 표 xlsx를 만들어 앱 저장소 `import/`(앱 `shared.py:31 IMPORT_DIR`)에 저장. 경로는 웹 `config`의 설정값(기본 `../qa-native-app/import`)이며 없으면 버튼 비활성 + 안내.
- 열: `tc_id | title | precondition | steps | expected | priority | platform`. `platform`은 `android`/`ios`/`both`.
- 앱 `scripts/import_excel.py`는 행 단위 `platform` 매핑을 받아 그 행만 해당 플랫폼에 쓴다(현재는 시트 이름 또는 선택값으로만 정함, `:38-43`).
- md 형식은 앱 `import_excel._render_markdown`(`:54-80`)이 소유한다. 이 형식은 `02_generate.parse_tc_blocks`(`scripts/02_generate.py:152`)가 읽는 `## 테스트 케이스 N` 블록 형식이라 생성 단계가 그대로 소비한다.

### 2.5 앱 대시보드 메뉴

- 사이드바 "TC 작성" 섹션(`agents/dashboard/dashboard.html:47-55`)에 **TC 스튜디오** 항목을 Import Studio 위에 추가.
- 뷰는 웹 TC 스튜디오를 `iframe`으로 띄운다: `TC_STUDIO_URL`(기본 `http://localhost:8766/tc-studio?embed=1`).
- 웹 쪽 `?embed=1`: 대시보드 사이드바·상단 바 없이 TC 스튜디오만 그린다.
- 웹 서버가 꺼져 있으면 iframe 대신 안내 카드: 실행 명령, "새 창에서 열기" 링크, 다시 확인 버튼.
- 웹 대시보드는 `X-Frame-Options`를 보내지 않아 임베드 가능(확인함). CSRF Origin 검사는 iframe 문서 자체가 8766 출처라 영향 없음.

## 3. 범위 밖 (이번에 하지 않음)

- TC 스튜디오 공통 패키지 분리(안 B).
- 플랫폼별 Step/Expected 덮어쓰기.
- 앱 파이프라인 실행 결과를 TC 스튜디오 `results`로 자동 역반영.
- 앱 저장소의 옛 형식 md 9개(`## 테스트 단계` 형식, `parse_tc_blocks`가 0건으로 읽음) 일괄 변환 — Phase 4에서 선택 작업으로만 둠.

## 4. 위험과 대응

| 위험 | 대응 |
|---|---|
| 웹 스위트 동작이 바뀜 | `kind` 분기, 기존 웹 E2E 전부 통과를 완료 조건으로 |
| 기존 저장 데이터(results 없음) | 읽을 때 `results`가 없으면 `execution_result`로 채워 보여 주고, 저장 시에만 기록. 가져온 앱 스위트는 재가져오기 안내 |
| 중복 후보·커버리지가 플랫폼을 모름 | 공통 TC 하나 모델이라 영향 없음(케이스 수 그대로) |
| 웹 서버 꺼짐 | 앱 메뉴의 안내 카드 |
| 다른 저장소에 파일 쓰기 | xlsx 1개, 같은 이름 덮어쓰기 안 함(타임스탬프), 경로 미설정 시 비활성 |
