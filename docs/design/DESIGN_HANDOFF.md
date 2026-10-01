# 대시보드 디자인 개편 — 다른 LLM에게 맡기는 법

> 이 문서는 **사람(작업 지시자)** 이 읽고, 아래 프롬프트를 복사해 다른 LLM(코딩 에이전트)에게 붙여 넣는 용도다.
> 작성: 2026-10-02 · 시안: 밝은 테마(A안) 36장 확정 · 원본 캔버스: https://claude.ai/artifact/XvGF3Gvyaw8M9uYQiFcbqe

## 1. 한눈에 보기

| 항목 | 내용 |
|---|---|
| 무엇을 | 앱 대시보드(8767)와 TC 스튜디오, 리포트 페이지의 **겉모습만** 시안대로 바꾼다. 보라·글로우 다크 테마 → 차분한 밝은 테마 |
| 하지 않는 것 | 기능·API·데이터 흐름 변경. 새 기능 추가. 다크 테마 |
| 저장소 | `/Users/junghoyoung/qa-native-app` (이 저장소에만 쓴다) |
| 시안 HTML | `docs/design/mockups/NN_이름.html` — 브라우저로 바로 열린다. **모든 색·크기·간격 값이 inline style에 그대로 있다** |
| 시안 스크린샷 | `docs/design/screenshots/NN_이름.jpg` (1440 폭) |
| 토큰 | `docs/design/tokens.css` — CSS 변수. 그대로 가져다 쓴다 |

캔버스 링크는 사람이 보는 용도다. LLM은 저장소 안 파일(`mockups/`, `screenshots/`, `tokens.css`)만 근거로 쓴다.

## 2. 맡기기 전에 사람이 할 일

1. **TC 스튜디오 이식 작업을 먼저 끝낸다.** 지금(2026-10-02) 대시보드 파일에 커밋 안 된 수정이 있다(`dashboard.css`, `dashboard.html`, `tc-studio/*` 등). 그 작업이 커밋되고 `git status`가 깨끗해진 뒤에 디자인 작업을 시작한다. 같은 파일을 두 작업이 동시에 고치면 충돌한다.
2. 아래 5장의 "사용자 확인" 3가지를 미리 정해 두면 LLM이 멈추지 않는다.
3. 한 번에 **Phase 1개**씩 맡기고, 끝나면 4장 체크리스트로 확인한다.

## 3. 프롬프트

### 3.1 공통 규칙 — 모든 프롬프트 맨 앞에 붙인다

```text
[작업 규칙 — 반드시 지켜]
- 저장소: /Users/junghoyoung/qa-native-app. 먼저 CLAUDE.md와 docs/design/DESIGN_HANDOFF.md를 읽어.
- 목표: 화면의 겉모습만 docs/design/mockups/의 시안과 같게 바꾼다. 기능·API·데이터·동작은 바꾸지 마.
- 근거: docs/design/mockups/NN_*.html(값은 inline style에 있음)과 docs/design/screenshots/NN_*.jpg.
  시안과 다르게 해야 하면 이유를 보고에 적어.
- 색은 docs/design/tokens.css의 CSS 변수만 써. 컴포넌트 CSS에 hex를 새로 쓰지 마.
- JS와 테스트가 쓰는 id·class·data-* 속성·onclick 이름은 바꾸지 마. 모양 때문에 class를 더해야 하면 "추가"만 해.
- 금지: 보라색, 그라데이션, 글로우, 반투명 유리 효과, 이모지 아이콘(🤖🍎📡🔨⚠️ 등), 대문자 영어 라벨(PASS RATE 등).
  상태는 항상 색 + 글자로 보여 줘.
- 새 npm/pip 의존성 추가 금지. 글꼴은 Google Fonts <link> 하나만 허용(오프라인이면 system-ui로 동작).
- 파이썬을 고치면 8767 대시보드를 재시작해:
  kill $(lsof -tiTCP:8767 -sTCP:LISTEN); nohup python3 agents/dashboard/serve.py >/tmp/dash8767.log 2>&1 &
- 화면을 고쳤으면 반드시 직접 확인해: Playwright로 http://localhost:8767 (TC 스튜디오는 /tc-studio)을
  1440x900으로 열어 스크린샷을 찍고, 같은 번호의 docs/design/screenshots 이미지와 나란히 비교해.
  버튼·배지·표 머리 글자가 두 줄로 쪼개지거나, 칸 밖으로 넘치거나, 가로 스크롤이 생기면 고쳐.
- 테스트: python3 -m pytest tests/unit tests/dashboard -q 가 통과해야 한다. 디자인 때문에 깨진 테스트는
  "모양에 대한 기대값"일 때만 고치고, 고친 테스트와 이유를 보고에 적어.
- 사용자 데이터(state/, testcases/, import/)를 건드리지 마.
- 커밋: Phase 단위, 한국어 conventional commit (예: "style(dashboard): ..."). git push는 하지 마.
- /Users/junghoyoung/qa-native-fixed 저장소는 건드리지 마.
- docs/design/DESIGN_HANDOFF.md 5장의 "사용자 확인" 항목은 적힌 결정대로 하고, 결정이 비어 있으면 멈추고 물어봐.
- 보고는 한국어로 짧고 쉽게.
```

### 3.2 Phase 하나를 맡길 때

`N`만 바꿔서 쓴다. D0부터 순서대로.

```text
(3.1 공통 규칙)

docs/design/DESIGN_HANDOFF.md 6장의 Phase DN만 진행해줘. 끝나면 멈춰.
보고 형식:
1) 바꾼 화면과 파일 (한 줄씩)
2) 시안 대비 확인: 화면별로 "내 스크린샷 경로 ↔ 시안 번호", 남은 차이
3) 테스트 결과 (명령과 마지막 줄)
4) 커밋 목록 (git log --oneline)
5) 시안과 다르게 한 점과 이유
```

### 3.3 끊겼다가 이어갈 때

```text
(3.1 공통 규칙)

docs/design/DESIGN_HANDOFF.md 6장의 체크박스, git log --oneline -20, git status를 보고
어디까지 했는지 먼저 알려줘. 반쯤 된 Phase만 마저 끝내고 멈춰.
```

## 4. 검토 체크리스트 (사람용)

**모든 Phase 공통**
- [ ] 바뀐 화면을 브라우저(1440 폭)로 열어 같은 번호 시안 스크린샷과 비교했다. 글자 쪼개짐·넘침이 없다.
- [ ] `python3 -m pytest tests/unit tests/dashboard -q` 통과.
- [ ] 버튼을 몇 개 눌러 기능이 그대로 동작한다(탭 전환, 모달 열기·닫기, 실행 버튼).
- [ ] `git diff`에 `.py`의 동작 로직 변경이 없다(리포트 페이지 D8 제외).
- [ ] 새로 추가된 hex가 없다: `git diff -U0 | grep '^+' | grep -E '#[0-9A-Fa-f]{6}' | grep -v tokens.css` 결과가 비어 있다.
- [ ] 이모지·보라색이 남아 있지 않다(해당 Phase 화면 기준).

**Phase별**: 6장 각 Phase의 "완료 기준"을 확인한다.

## 5. 사용자 확인 (미리 정해 두기)

| 항목 | 질문 | 결정 |
|---|---|---|
| 메뉴 이름 | Import Studio → **엑셀 가져오기**, Capture Studio → **화면 캡처로 작성**, Dashboard → 대시보드, 리포트 목록 → 리포트, 실행 히스토리 → 실행 기록으로 바꿀까? | (비어 있음 — 정해 주세요. 시안은 바꾼 이름) |
| 글꼴 | IBM Plex Sans KR + JetBrains Mono를 Google Fonts에서 불러올까, 시스템 글꼴만 쓸까? | (비어 있음) |
| 리포트 페이지 구조 | D8에서 오류 요약을 맨 위로, 시도(1·2·3차)별 증거 버튼을 추가하는 **마크업 변경**까지 할까, 색·글자만 바꿀까? | (비어 있음) |

## 6. Phase (순서대로)

각 Phase는 커밋 1개 이상. 끝난 항목은 `[x]`로 바꿔 같은 커밋에 넣는다.

### D0 — 토큰과 글꼴
- [ ] `docs/design/tokens.css` 내용을 `agents/dashboard/static/tokens.css`로 복사하고 `dashboard.html`, `tc_studio.html`에서 가장 먼저 불러온다.
- [ ] `dashboard.css`의 `:root` 변수(`--bg`, `--surface`, `--accent` 등, 현재 3~9행)를 새 토큰으로 바꾸고, 직접 쓴 색(약 245곳)을 변수로 교체한다. 보라·그라데이션·글로우·반투명 배경 제거.
- [ ] `body`는 `var(--bg)`, 글꼴 `var(--font-sans)`.
- 완료 기준: 모든 화면이 밝은 바탕이 된다(배치는 아직 옛날 그대로여도 됨). `grep -cE '#[0-9A-Fa-f]{6}|rgba?\(' agents/dashboard/static/dashboard.css`가 크게 줄었다(남은 것은 이유가 있는 것만).

### D1 — 공통 셸과 부품 (시안 `02_Components`, 모든 화면의 상단 바·사이드바)
- [ ] 상단 바: 로고 + `QA Control Center` + 상태 한 줄(Appium·기기) + 오른쪽 `파이프라인 실행`. `LIVE` 알약·`자동화: ADB`·`executed` 배지 제거(정보는 상태 줄 글자로).
- [ ] 사이드바: 그룹(개요/TC 작성/실행/결과) + 맨 아래 `환경 설정`. 선택 항목은 `--accent-bg` 바탕 + `--accent` 글자. 메뉴 이름은 5장 결정대로.
- [ ] 공통 클래스: 버튼(주/보조/위험/비활성), 입력·선택, 전환 버튼(segmented), 배지, 탭, 단계 표시, 카드·섹션, 표, 알림 배너 4종, 토스트, 빈 상태, 불러오는 중(스켈레톤), 오류 상태, 모달(배경 막 포함).
- 완료 기준: 공통 클래스가 `dashboard.css` 한 곳에 있고, 버튼·배지 글자가 줄바꿈되지 않는다(`white-space: nowrap`).

### D2 — 대시보드 · 실행 기록 · 리포트 목록 (`03_Main`, `31_History`, `30_Reports`)
- 코드: `dashboard.html` `#view-overview` · `#view-history` · `#view-reports`, `static/reports.js`, `static/dashboard-init.js`
- [ ] 대시보드: 요약 4칸을 한 줄 띠로, 최근 실행은 표, 오른쪽에 환경·최근 로그. 원형 그래프 제거.
- [ ] 실행 기록: 요약 띠 + 필터(유형·플랫폼·그룹) + 표.
- [ ] 리포트 목록: 왼쪽 목록(체크박스·이름 Mono·시간·크기·새 탭) + 오른쪽 미리보기.

### D3 — 파이프라인 · 빠른 실행 · 실행 증거 (`25`~`29`)
- 코드: `#view-pipeline`, `#view-tests`, `static/execution.js`, `static/quick-run.js`, `static/observability.js`, `#ev-detail-overlay`
- [ ] 플랫폼 큰 카드(🤖/🍎) → `Android | iOS` 전환 버튼.
- [ ] 단계 5개 목록 + 상태 배지(대기/실행 중/완료/실패) + 진행 막대(`26_PipelineRunning`).
- [ ] 실행 결과 증거(`28_RunEvidence`): TC 목록 + 시도 버튼 + 영상/스크린샷/시스템 로그 탭 + 실패 지점 표시 + 로그 필터·검색. 오버레이(`29`)도 같은 모양.

### D4 — 엑셀 가져오기 5단계 (`16`~`20`)
- 코드: `#view-import`, `static/import-studio.js`
- [ ] 단계 표시, 파일 카드, 열 매핑 표, 검증 결과, 미리보기 필터+표, 반영 정책 라디오 카드, 완료 화면.

### D5 — 화면 캡처 (`21`~`24`)
- 코드: `#view-capture`(`#cs-setup`, `#cs-workspace`, `#cs-preview-modal`), `static/capture-*.js`, `#csLtOverlay`
- [ ] 세션 정보 바, 3열(기기 화면 280 · Hierarchy 300 · 나머지), 선택 요소·Step 추가·검증, 상세·Locator 후보(위아래 배치), 동작 기록, 저장 줄.
- [ ] Livetail 패널, TC 미리보기 모달.
- 완료 기준: 실제 Android 세션으로 열어 미러링·트리·Step 추가가 그대로 동작(기기가 없으면 사람에게 확인 요청).

### D6 — 환경 설정 (`34`~`36`)
- 코드: `#view-config`, `static/environment.js`, `static/environment-devices.js`, 모달 `#env-add-modal`, `#env-appium-log-modal`, `#env-wifi-pair-modal`, `#env-wda-build-modal`
- [ ] Appium 카드(상태 5종: 중지됨·시작 중·실행 중(관리)·실행 중(외부)·오류), 기기 4묶음 2열, 빈 목록 상태, 모달 4종. Appium 로그는 접어 둔다.

### D7 — TC 스튜디오 (`04`~`15`)
- 코드: `agents/dashboard/tc_studio.html`, `static/tc-studio/tc-studio.css`, `reference-layout.css`, `reference-variables.css`, `standalone.css`, `static/tc-studio/*.js`
- [ ] 4개 탭(기획 정보·생성 / 라이브러리 / 초안 검토 / 내보내기)과 상단 스위트 선택.
- [ ] 라이브러리: 계층 트리 200 · 표 · 상세 380, 필터 줄, `And·iOS 결과가 다른 것만`, 일괄 변경 바(자주 쓰는 3개 + ⋯ 더보기), And/iOS 결과 배지와 N/A(점선).
- [ ] 모달: 엑셀 가져오기, 이력, 작성 규칙 편집, 시트 이름·이동·스위트 삭제·저장 안 함, 휴지통·연결 설정·출처 변경.
- 완료 기준: `tests/dashboard/test_tc_studio_e2e.py` 통과.

### D8 — 리포트 페이지 (`32_ReportFail`, `33_ReportPass`)
- 코드: `scripts/report_html.py` (`report_css` :442, `case_row` :332, `build_group_section` :400, `report_js` :566)
- [ ] 밝은 테마, 한국어 라벨(테스트 리포트·전체·통과·실패·건너뜀·통과율, 사전 조건·단계·기대 결과·오류), 그룹 이름 원래 폴더 이름 그대로.
- [ ] 5장 결정이 "구조 변경"이면: 오류 요약을 펼친 케이스 맨 위로, 시도별 증거 버튼(`state/runs/{run_id}/artifacts/.../attemptN/`), 원본 오류는 접기.
- 완료 기준: `tests/unit/test_report_html_markdown.py` 통과. 실패가 있는 run으로 리포트를 새로 만들어 브라우저에서 확인.

### D9 — 마무리
- [ ] 이모지·보라색·대문자 영어 라벨 잔존 검사: `grep -rnE '🤖|🍎|📡|🔨|⚠️|#8b5cf6|PASS RATE' agents/dashboard scripts/report_html.py`
- [ ] 전체 테스트, 36개 시안 화면 전부 스크린샷 비교, `docs/USER_GUIDE.html`의 화면 캡처 이미지가 있으면 새 화면으로 교체 여부를 사람에게 묻기.
- [ ] 결과 보고 후 push 여부는 사람에게 묻는다.

## 7. 시안 목록

| 파일 | 화면 |
|---|---|
| `01_Tokens` | 디자인 토큰 |
| `02_Components` | 공통 부품 |
| `03_Main` | 대시보드 |
| `04_TcGenerate` | TC 스튜디오 ① 기획 정보·생성 |
| `05_TcGenerating` | ① 초안 생성 중 / 일부 실패 |
| `06_TcStudio` | ② 라이브러리 (트리·필터·일괄 변경·상세) |
| `07_TcDetailPanels` | ② 상세 패널 — 편집·원문·이력 |
| `08_TcReview` | ③ 초안 검토 |
| `09_TcExport` | ④ 내보내기 |
| `10_TcMdPreview` | ④ md 변경 미리보기 |
| `11_TcImportModal` | 엑셀 → 라이브러리 가져오기 모달 |
| `12_TcImportHistory` | 가져오기·md 반영 이력 |
| `13_TcProfileEditor` | 작성 규칙 편집 |
| `14_TcModalsA` | 시트 이름·이동·스위트 삭제·저장 안 함 |
| `15_TcModalsB` | 휴지통·연결 설정·출처 변경 |
| `16_Import` | 엑셀 가져오기 1 파일·시트 선택 |
| `17_Import2` | 2 열 매핑 |
| `18_Import3` | 3 미리보기 |
| `19_Import4` | 4 안전한 반영 |
| `20_Import5` | 5 완료 |
| `21_Capture` | 화면 캡처 1 세션 설정 |
| `22_CaptureWorkspace` | 2–4 작업 공간 |
| `23_CapturePreview` | TC 미리보기 (md · pytest) |
| `24_Livetail` | Livetail 실시간 기록 |
| `25_Pipeline` | 파이프라인 — 설정 |
| `26_PipelineRunning` | 파이프라인 — 실행 중 |
| `27_QuickRun` | 빠른 실행 — 설정 |
| `28_RunEvidence` | 실행 결과 — 증거 |
| `29_EvidenceOverlay` | 증거 상세 오버레이 |
| `30_Reports` | 리포트 목록 |
| `31_History` | 실행 기록 |
| `32_ReportFail` | 리포트 페이지 (새 탭) — 실패 |
| `33_ReportPass` | 리포트 페이지 (새 탭) — 통과 |
| `34_Env` | 환경 설정 |
| `35_EnvAppiumStates` | Appium 상태 5종 · 빈 기기 목록 |
| `36_EnvModals` | 기기 추가·Appium 로그·Wi-Fi 페어링·WDA 빌드 |

시안 속 데이터: 기기·실행 기록·리포트 이름·실패 화면은 2026-10-01 실제 값이다. 가져오기 건수·초안 수 등은 예시이며, `[파일 이름]`처럼 대괄호는 실제 값이 들어갈 자리다.
