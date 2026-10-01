# 앱 대시보드 디자인 교체 — 인수인계

> **독자**: 이 작업을 이어받는 LLM(Claude Code 또는 다른 모델)과 작업자.
> **작성**: 2026-10-02 · **저장소**: `/Users/junghoyoung/qa-native-app` (main)
> **한 줄 요약**: 앱 대시보드(8767)의 모든 화면, TC 스튜디오, 리포트 HTML을 **보라색 어두운 테마 → 밝은 테마**로 바꾼다. **기능·동작은 바꾸지 않는다.**

## 0. 먼저 읽을 것

| 순서 | 파일 | 내용 |
|---|---|---|
| 1 | 이 문서 | 목표, 규칙, 화면↔코드 대응, 작업 순서, 검증 |
| 2 | [`mockups/index.html`](mockups/index.html) | **디자인 시안 36장 목록.** 각 화면은 단독 HTML이라 브라우저로 열 수 있고, 소스(인라인 스타일)가 곧 명세다. 사이드바 링크로 화면 사이를 이동할 수 있다 |
| 3 | [`tokens.css`](tokens.css) | 새 색·글꼴·크기 변수. 그대로 붙여 쓴다 |
| 4 | 저장소 [`CLAUDE.md`](../../CLAUDE.md) | 저장소 공통 규칙 (devices.json 쓰기 경로, Capture 가드, Appium 바인딩 등) |

디자인 원본은 claude.ai 디자인 캔버스다 — `https://claude.ai/artifact/XvGF3Gvyaw8M9uYQiFcbqe`. **다른 사람·모델은 열 수 없을 수 있다.** 그래서 같은 내용을 `mockups/`에 파일로 넣었다. 링크가 안 열리면 `mockups/`만 기준으로 삼는다. 웹 저장소(`qa-native-fixed`)도 같은 가이드로 별도 진행 중이다 — 색·부품 규칙이 같다.

## 1. 디자인 가이드 (요약 — 상세는 `mockups/Tokens.html`, `mockups/Components.html`)

**색** — `tokens.css` 변수만 쓴다. 컴포넌트 안에 hex를 쓰지 않는다.

| 쓰임 | 변수 | 값 |
|---|---|---|
| 페이지 바탕 / 카드 / 표 머리 | `--bg` / `--surface` / `--surface-sub` | `#F5F6F8` / `#FFFFFF` / `#F0F2F5` |
| 선 / 입력 테두리 | `--border` / `--border-input` | `#E2E5EA` / `#8B93A1` |
| 글자 본문 / 보조 / 힌트 | `--text` / `--text-2` / `--text-3` | `#111827` / `#4B5563` / `#6B7280` |
| 강조(주 버튼·링크·선택) | `--accent` / `--accent-bg` | `#1F4FD1` / `#E8EEFC` |
| 통과 / 실패 / 주의 | `--pass(-bg)` / `--fail(-bg)` / `--warn(-bg)` | `#15803D` / `#B91C1C` / `#92400E` (+ 연한 배경) |
| 로그 | `--log-bg` | `#F8F9FB` |

**글꼴** — 본문 IBM Plex Sans KR, 숫자·ID·시간·경로·로그 JetBrains Mono (Google Fonts, 오프라인이면 system-ui). 크기: 화면 제목 22/600, 모달·상세 제목 17/600, 카드 제목 15/600, 본문 14, 보조 13, 라벨 12.

**배치** — 상단 바 56px(흰색, 아래 선) · 왼쪽 사이드바 232px(흰색) · 본문 여백 `28px 32px` · 카드 안 16px · 섹션 사이 20px. 모서리: 배지 4 / 버튼·입력 6 / 카드 8 / 모달 10. 그림자는 모달·토스트만. 버튼·입력 높이 34~36px, 주 실행 버튼 44px.

**부품 규칙**
- 주 버튼(파란 채움)은 **화면에서 다음에 누를 것 하나만**. 나머지는 흰 바탕 + 테두리.
- 비활성 버튼은 `title`로 이유를 알린다.
- 상태 배지는 항상 **글자**를 함께(통과·실패·중단·실행 중·기본·결과 다름…). 색만으로 구분하지 않는다. 앱 TC의 And/iOS 결과에서 대상이 아닌 쪽은 점선 테두리 `N/A`.
- 세그먼트(필터 토글, `Android | iOS` 등)는 선택된 칸만 검은 채움(`#111827`). 플랫폼 선택용 큰 카드(🤖/🍎)는 세그먼트로 바꾼다.
- 버튼·배지·표 머리 글자는 줄바꿈하지 않는다(`white-space: nowrap`). 좁으면 배치를 바꾼다.
- 되돌릴 수 없는 작업(삭제, 세션 종료, Appium 중지 등)은 브라우저 `confirm()` 대신 **화면 안 대화창**(`mockups/Components.html`의 확인 모달).
- 빈 상태는 제목 + 한 줄 설명 + 다음 행동 버튼(`Components.html`).

**금지** — 보라색·그라데이션·글로우·유리(`backdrop-filter`, 반투명) 효과 · 이모지 아이콘(🤖🍎📡🔨⚠️📝✅❌⏱⬅ 등) · 영어 대문자 라벨(`PASS RATE`, `TOTAL`, `FIRST PASS`, `CAPTURE STUDIO` → `통과율`, `전체`, `첫 시도 통과`, 제목은 한국어) · 색으로만 상태 구분.

**메뉴 구성(사이드바)** — 개요: 대시보드 / TC 작성: TC 스튜디오, 엑셀 가져오기, 화면 캡처로 작성 / 실행: 파이프라인, 빠른 실행 / 결과: 리포트, 실행 기록 / 맨 아래: 환경 설정. (옛 이름: Dashboard, Import Studio, Capture Studio, 파이프라인 실행, 리포트 목록, 실행 히스토리.) 상단 바: 제품명 · Appium·기기 상태 문구 · 오른쪽 `파이프라인 실행` 버튼. 지금의 `LIVE`, `자동화: ADB`, `executed` 알약은 상태 문구로 바꾼다.

## 2. 지켜야 할 것 (절대)

1. **동작을 바꾸지 않는다.** API 호출, 상태 전이(Appium 5상태 등), 폴링, 저장 로직, Capture 세션·MJPEG·Livetail WebSocket은 그대로. 바뀌는 것은 마크업 구조·클래스·CSS·문구뿐.
2. **`id`, `data-id`, `data-view`, `aria-*`, `role`, `onclick` 함수 이름은 유지한다.** TC 스튜디오 JS에 `data-id`가 약 250개 있고 E2E 테스트가 이것으로 요소를 찾는다. 대시보드 JS는 `getElementById`로 `env-*`, `cs-*`, `obs-*`, `ev-*` id를 찾는다. 바꿔야 하면 테스트를 같은 커밋에서 고친다.
3. **테스트를 약하게 고치지 않는다.** 문구가 바뀌어 기대값을 고치는 것은 되지만, 검사 줄을 지우거나 `skip`하지 않는다.
4. 목업에 없는 상태가 코드에 있으면 **가장 가까운 목업의 부품을 조합**해 그린다. 새 색·새 부품을 만들지 않는다.
5. 목업 숫자·이름(그룹명, 건수, `[파일 이름]` 같은 대괄호)은 예시다. 실제 화면은 데이터 그대로.
6. 커밋은 단계(아래 4절)마다, 한국어 conventional commit(`style(dashboard): …`). **push는 사용자에게 확인받는다.**
7. 기능 버그를 발견하면 고치되 디자인 커밋과 섞지 않는다(별도 커밋). `agents/lessons_learned.md`에는 기록하지 않는다(파이프라인 힐링 전용).
8. `/Users/junghoyoung/qa-native-fixed`(웹 저장소)는 건드리지 않는다.

## 3. 화면 ↔ 목업 ↔ 코드

| 화면 | 목업 (`mockups/…html`) | 바꿀 코드 |
|---|---|---|
| 공통 틀(상단 바·사이드바) | 모든 화면 공통 | `agents/dashboard/dashboard.html`(상단 바, 사이드바와 `#tc-studio-root`), `static/dashboard-shell.js`(`selectView`, 뷰 전환) |
| 토큰·공통 부품 | `Tokens`, `Components` | `static/dashboard.css`(818줄, `:root` 3~9행이 보라 테마, 직접 쓴 색 약 245곳), 새 파일 `static/tokens.css` |
| 대시보드 | `Main` | `dashboard.html` `#view-overview`, `static/dashboard-shell.js`, `static/dashboard-init.js` |
| 엑셀 가져오기 1~5단계 | `Import`, `Import2`~`Import5` | `dashboard.html` `#view-import`, `static/import-studio.js` |
| 화면 캡처 | `Capture`, `CaptureWorkspace`, `CapturePreview`, `Livetail` | `dashboard.html` `#view-capture`(`#cs-setup`, `#cs-workspace`, `#cs-preview-modal`, `#csLtOverlay`), `static/capture-studio.js`, `capture-actions.js`, `capture-inspector.js`, `capture-livetail.js` |
| 파이프라인 | `Pipeline`, `PipelineRunning` | `dashboard.html` `#view-pipeline`, `static/execution.js` |
| 빠른 실행 · 실행 증거 | `QuickRun`, `RunEvidence`, `EvidenceOverlay` | `dashboard.html` `#view-tests`, `#ev-detail-overlay`, `static/quick-run.js`, `static/observability.js` |
| 리포트 목록 | `Reports` | `dashboard.html` `#view-reports`, `static/reports.js` |
| 실행 기록 | `History` | `dashboard.html` `#view-history`, `static/dashboard-init.js` |
| 환경 설정 | `Env`, `EnvAppiumStates`, `EnvModals` | `dashboard.html` `#view-config`·`#env-add-modal`·`#env-appium-log-modal`·`#env-wifi-pair-modal`·`#env-wda-build-modal`, `static/environment.js`, `static/environment-devices.js` |
| TC 스튜디오 ①~④ | `TcGenerate`, `TcGenerating`, `TcStudio`, `TcDetailPanels`, `TcReview`, `TcExport`, `TcMdPreview` | `dashboard.html`의 `#tc-studio-root`, `static/tc-studio/*.js`, `static/tc-studio/tc-studio.css` |
| TC 스튜디오 모달 | `TcImportModal`, `TcImportHistory`, `TcProfileEditor`, `TcModalsA`, `TcModalsB` | 같은 폴더의 `import.js`, `main.js`, `generate.js`, `connectors.js`, `library.js`, `detail.js`, `export.js` |
| 리포트 HTML (새 탭) | `ReportFail`, `ReportPass` | `scripts/report_html.py`(798줄, `report_css()` :442, `case_row()` :332, `build_group_section()` :400, `report_js()` :566) — 실행이 `tests/reports/`에 만드는 독립 HTML |

참고: 경로는 `agents/dashboard/` 아래(리포트 생성기 제외). `dashboard.html`에 인라인 `style=`이 195곳, JS에도 있다(`capture-inspector.js` 14곳, `capture-actions.js` 12곳, `environment-devices.js` 11곳, `dashboard-shell.js` 11곳 등). 인라인 색은 클래스로 옮기거나 토큰 변수로 바꾼다.

**TC 스튜디오 전용 메모**
- 지금은 탭이 번호 원(①②③④) 스테퍼다. 목업은 **밑줄 탭**(`기획 정보 · 생성 / 라이브러리 N / 초안 검토 N / 내보내기`)이다. 목업을 따른다. `data-id="nav-tab-*"`는 유지.
- 라이브러리: 계층 트리 200 · 표 · 상세 380. 일괄 변경 바는 자주 쓰는 3개(실행 결과·검토 상태·계층 이동) + `⋯` 더보기(우선순위·승인·반려·복제·삭제). 앱 스위트는 결과 열이 `And | iOS` 2칸, `And·iOS 결과가 다른 것만` 필터 유지.
- 표·트리·상세 패널의 기능(셀 편집, 끌어다 놓기, 가상 스크롤)은 그대로 두고 색·선·글꼴만 바꾼다.

**리포트 HTML 메모** — `ReportFail` 목업대로: 펼친 실패 TC 맨 위에 사람이 읽는 오류 요약(원본 오류는 `전체 오류 보기`로 접기), 오른쪽에 **시도별 증거**(1차·2차·3차 버튼 + 스크린샷 + 영상·시스템 로그). 시도별 파일은 `state/runs/{run_id}/artifacts/{node}/attempt{n}/`(`manifest.json`)에 이미 있다 — 데이터는 읽기만 한다.

## 4. 작업 순서

각 단계: 목업 확인 → 코드 수정 → 관련 테스트 → 서버 재시작(파이썬을 고쳤을 때) → 브라우저에서 목업과 나란히 비교 → 커밋.

- [ ] **1. 토큰·글꼴 교체** — `tokens.css`를 `static/tokens.css`로 두고 `dashboard.html`에서 가장 먼저 불러온다. `dashboard.css` `:root`와 `tc-studio.css`의 옛 변수 이름을 새 변수에 연결(또는 사용처 일괄 교체). 글꼴 `<link>`를 IBM Plex Sans KR + JetBrains Mono로(지금 TC 스튜디오는 Inter·Outfit). `body` 배경 그라데이션 제거. 이 단계만으로 화면이 대략 밝아져야 한다.
- [ ] **2. 공통 틀** — 상단 바·사이드바를 목업대로(`dashboard.html` 하나). 메뉴 묶음·이름 변경(1절). 활성 메뉴는 `--accent-bg` 배경.
- [ ] **3. 공통 부품** — 버튼·배지·입력·표·카드·세그먼트·단계 표시·알림 배너·토스트·빈 상태·불러오는 중·오류·확인 대화(`dashboard.css`). 글로우·`backdrop-filter`·빛나는 애니메이션 제거(필요한 회전·페이드만 남김). `confirm()` 사용처를 화면 안 대화창으로.
- [ ] **4. 화면별** — 대시보드 → 파이프라인(설정·실행 중) → 빠른 실행·실행 증거·증거 오버레이 → 리포트 목록 → 실행 기록 → 엑셀 가져오기 5단계 → 화면 캡처(설정·작업 공간·미리보기·Livetail) → 환경 설정(Appium 5상태·모달 4종). 화면마다 1커밋.
- [ ] **5. TC 스튜디오** — `tc-studio.css` 변수 교체 → 상단(제목·스위트·탭) → 라이브러리 → 생성 → 검토 → 내보내기 → 모달. 2~3커밋으로 나눈다.
- [ ] **6. 리포트 HTML** — `report_html.py`의 CSS와 마크업. 3절 리포트 메모대로.
- [ ] **7. 마무리** — 전체 테스트, `docs/guides/USER_GUIDE.html`에 화면 캡처가 있으면 새 화면으로 교체할지 사용자에게 묻기, 남은 옛 색·이모지 검색.

## 5. 검증

```bash
cd /Users/junghoyoung/qa-native-app
# 전체 단위·대시보드 테스트 (.venv 사용 — 시스템 python에는 selenium이 없어 2개 파일이 수집 오류)
.venv/bin/python -m pytest tests/unit tests/dashboard -q -W ignore -p no:cacheprovider
# 대시보드 서버 재시작 (파이썬 수정 시. JS·CSS는 새로고침)
kill $(lsof -tiTCP:8767 -sTCP:LISTEN); nohup python3 agents/dashboard/serve.py >/tmp/dash8767.log 2>&1 &
# 남은 옛 테마 색·효과 찾기 (0건이 목표)
grep -rniE "8b5cf6|7c3aed|a78bfa|c4b5fd|a855f7|#08071b|#0d1117|rgba\(139, ?92, ?246|rgba\(140, ?120, ?220|rgba\(18, ?16, ?42|rgba\(28, ?24, ?60|linear-gradient|radial-gradient|backdrop-filter|PASS RATE|FIRST PASS" agents/dashboard/static agents/dashboard/dashboard.html agents/dashboard/tc_studio.html scripts/report_html.py
# 남은 이모지 아이콘 찾기 (0건이 목표)
grep -rnE "🤖|🍎|📡|🔨|⚠️|📝|✅|❌|⏱|⬅|👤|⚙️|🔄|🔌" agents/dashboard/static agents/dashboard/dashboard.html agents/dashboard/tc_studio.html scripts/report_html.py
```

- 테스트 기준: **564건 중 563건 통과, 1건 실패(`test_dashboard_assets.py::test_dashboard_document_loads_external_assets_instead_of_inline_bundles` — 디자인 작업 전부터 실패, 미커밋 작업 영향 추정. 디자인 작업 범위가 아니면 그대로 두고 보고)** (2026-10-02, 디자인 작업 전). 이 수보다 통과가 줄면 안 된다.
- TC 스튜디오 E2E(`tests/dashboard/test_tc_studio_e2e.py`)는 `data-id`로 요소를 찾는다. 2절 2번 규칙. 화면 자산 검사는 `tests/dashboard/test_dashboard_assets.py`, `test_tc_studio_assets.py`(파일·링크 존재 확인)와 `test_observability_workspace_e2e.py`.
- 시각 확인: Playwright로 1440×900 화면을 찍어 같은 이름의 목업과 비교한다. 예: `mockups/QuickRun.html` ↔ `http://localhost:8767/`에서 사이드바 `빠른 실행`(`selectView('tests', …)`). TC 스튜디오는 `http://localhost:8767/tc-studio`. 버튼·배지·표 머리 글자 줄바꿈, 칸 넘침, 가로 스크롤이 없어야 한다.
- 화면 캡처 작업 공간은 Appium + Android 에뮬레이터가 있어야 열린다. 없으면 세션 설정 화면까지만 확인하고 사용자에게 알린다.
- 리포트 HTML은 빠른 실행 1회 후 `tests/reports/`에 생긴 파일을 열어 `ReportPass`/`ReportFail`과 비교한다. 실패 사례는 기존 실패 run(`state/runs/run_android_20261001_220632_572`)의 리포트를 `scripts/report_html.py`로 다시 만들어 본다(원본 파일은 덮어쓰지 않는다).

## 6. 완료 정의

- 4절 체크박스 전부 완료, 전체 테스트 통과(기대값 갱신은 근거와 함께).
- 5절 옛 색·이모지 검색 0건.
- 모든 화면이 같은 틀(상단 바·사이드바·제목 위치)을 쓰고, 목업과 나란히 봤을 때 색·글꼴·간격·부품이 같다.
- 범위 밖: `qa-native-fixed` 저장소(웹 대시보드는 같은 가이드로 별도 진행), 기능 추가, 다크 테마.

## 7. 새 세션 시작 문구 (복사해서 붙여 넣기)

```text
/Users/junghoyoung/qa-native-app 저장소에서 작업해 줘.

[작업]
앱 QA 대시보드(agents/dashboard)의 모든 화면, TC 스튜디오, 실행이 만드는 리포트 HTML을
지금의 보라색 어두운 테마에서 "밝은 테마" 디자인으로 바꾸는 작업이야.
기능과 동작은 바꾸지 말고 디자인(마크업 구조, 클래스, CSS, 문구)만 바꿔.

[먼저 읽을 것 — 순서대로]
1. docs/design-refresh/HANDOFF.md  ← 인수인계 문서. 처음부터 끝까지 읽어.
2. docs/design-refresh/mockups/index.html  ← 디자인 시안 36장 목록.
   각 화면은 단독 HTML이고, 소스(인라인 스타일)가 곧 디자인 명세야.
3. docs/design-refresh/tokens.css  ← 새 색·글꼴·크기 변수.
4. 저장소 루트 CLAUDE.md  ← 저장소 공통 규칙.

[지켜야 할 것]
- 동작(API 호출, 상태 처리, 폴링, 저장, Capture 세션·Livetail)은 그대로 둬.
- id, data-id, data-view, aria-*, role, onclick 함수 이름은 유지해. TC 스튜디오 E2E 테스트가 data-id로 요소를 찾아.
- 테스트를 약하게 고치지 마. 문구가 바뀌어 기대값을 고치는 건 괜찮지만, 검사 줄 삭제나 skip은 안 돼.
- 목업에 없는 상태는 가장 가까운 목업의 부품을 조합해서 그려. 새 색이나 새 부품은 만들지 마.
- 금지: 보라색, 그라데이션, 글로우, 반투명 유리 효과, 이모지 아이콘,
  영어 대문자 라벨(PASS RATE, FIRST PASS 등 → 통과율, 첫 시도 통과), 색으로만 상태 구분.
- /Users/junghoyoung/qa-native-fixed 저장소는 건드리지 마.

[진행 방법]
- HANDOFF.md 4절의 작업 순서 1단계(토큰·글꼴 교체)부터 차례로 진행해.
- 단계마다 목업과 실제 화면을 Playwright 스크린샷(1440×900)으로 나란히 비교해 확인해.
  글자가 두 줄로 쪼개지거나 칸 밖으로 넘치면 고쳐.
  대시보드 서버: python3 agents/dashboard/serve.py (포트 8767, 파이썬을 고치면 재시작)
- 단계마다 테스트를 돌려: .venv/bin/python -m pytest tests/unit tests/dashboard -q -W ignore -p no:cacheprovider
  (기준: HANDOFF.md 5절의 통과 건수)
- 단계가 끝나면 커밋하고, 무엇을 바꿨는지와 테스트 결과를 짧게 보고한 뒤 다음 단계로 넘어가.
- push는 하지 말고 나한테 먼저 물어봐.
- 마지막에 HANDOFF.md 5절의 "옛 테마 색 찾기"와 "이모지 찾기" 결과가 0건인지 확인해.

[보고]
설명은 한국어로 쉽고 짧게 해 줘.
```
