# 전체 화면 재검토 기록

2026-10-02. 최초 완료 보고 후 사용자 피드백으로 화면 구성을 다시 검토하고 수정했다. 색상 변경만으로 목업 정합이 완료됐다고 판단했던 부분을 정정한다.

## 기준

- `mockups/index.html`에 연결된 36개 시안을 전부 범위에 포함했다.
- **대시보드는 이후 사용자가 제공한 통과율 추이 이미지와 환경 카드 이미지를 최종 기준으로 삼는다.** 기존 Main 시안과 달리 최근 실행 아래 그래프, 오른쪽 파이프라인 상태·환경·최근 로그를 배치했다.
- 독립 브라우저의 예시 상태는 화면 확인용이다. 실제 TC 반영·LLM 호출·기기 실행·Capture 종료를 하지 않았다.
- 예시 수치·파일명·기기명으로 제품 데이터를 대체하지 않는다. 없는 정보는 안내 또는 `—`로 표시한다.
- 비교 캡처는 1440×900. 모든 코드 수정은 앱 저장소의 작업 브랜치에서 수행했다.

## 대시보드 / Capture / 리포트

| 기준 | 수정 및 확인 | 남는 차이 |
|---|---|---|
| 사용자 대시보드 이미지 (Main 대체) | 요약 4카드, 최근 실행 6열, 실제 최근 10회 통과율 추이, 오른쪽 파이프라인 상태·환경·최근 로그. 1건/여러 건/빈 기록과 플랫폼 표시 필터 검증 | 웹의 등록 페이지는 앱의 생성 테스트로 표시. 앱에 없는 병렬 파이프라인·팀 토론 상태를 만들지 않음 |
| 사용자 환경 카드 이미지 | Appium 연결·주소, Android 에뮬레이터·실기기, iOS 시뮬레이터. 기존 환경 폴링 응답을 재사용 | 연결된 실제 이름·중지 상태를 표시. 예시 기기명 하드코딩 없음 |
| Capture | 기존 2열 세션 입력과 연결 상태, 단계 표시를 확인 | Android/iOS의 실제 입력 필드 및 세션 제한 유지 |
| CaptureWorkspace | 기기280 / Hierarchy300 / 상세 나머지 폭, 독립 카드, 세션 상태 바와 재연결·종료, 단계 표시, Locator 점수 | 실제 Hierarchy와 Locator 전략/승인/검증 기능은 유지. 기기 영상은 보존 자료 또는 브라우저 예시 상태로 비교 |
| CapturePreview | 1000px 모달·2열 코드·출처 요약·하단 닫기/기존 저장 연결, 저장 비활성 승계 | 코드 내용은 기존 미리보기 초안이며 실제 생성 결과로 바꾸지 않음 |
| Livetail | 우측 세로 패널을 콘텐츠 하단 가로 로그로 변경, 한 줄 필터·내보내기·하단 고정·닫기 | 기존 필터/스크롤고정/내보내기/WebSocket 버퍼 유지. 결과·소요 문구는 기존 추가정보로 유지 |
| ReportFail | 본문1240, 그룹 제목·필터 한 줄, 오류 요약·전체오류, 증거300px·이미지 최대420px, 상단 인쇄/대시보드 연결 | 원래 기록에 없는 기기·시도시간·태그를 임의로 만들지 않음 |
| ReportPass | 같은 틀·그룹·필터·통과 요약, 인쇄 스타일 확인 | 실제 테스트 수·스킵 건수 유지 |

대시보드 예시 1건 캡처: `/tmp/light-visual/overview-user-final-single.png`. Capture 4상태: `/tmp/mockup-review/`. 리포트: `/tmp/light-visual/report-layout-review.png`.

## TC 스튜디오 목업 재검토 (1440×900)

검토 기준: docs/design-refresh/mockups/Tc*.html 12종. 실제 화면 localhost:8767/tc-studio, Playwright Chromium. TC 목록과 수치는 복사된 실제 데이터이며 목업 숫자로 바꾸지 않았다. 검토 초안/진행중은 브라우저 메모리의 읽기 전용 fixture. 엑셀 가져오기 확정/TC저장·삭제/LLM생성/MD반영을 실행하지 않았다. MD 미리보기 요청은 pending preview run을 만들 수 있으나 실제 testcases 반영 없음.

## 수정 사항 및 증거

| 목업 | 확인/수정한 실제 화면 | 실제 PNG | 남는 차이와 이유 |
|---|---|---|---|
| TcGenerate | 420px 우측 카드, 검은 플랫폼 세그먼트, 상단 스위트 라벨, 밑줄 탭, 연결/규칙 편집 링크. 생성 버튼은 이전 y926에서 y851로 이동해 900px 안에 전체 노출 | /tmp/audit-tc/generate-final.png | 시트 이름 변경, 새 분류 입력/추가 버튼은 기존 기능을 보존해 작성 위치 카드가 목업보다 높음. 실제 선택한 스위트명·건수·내용은 데이터 그대로 |
| TcGenerating | 진행중 카드가 작성 규칙 아래에 묻히던 문제를 오른쪽 상단으로 변경; 진행 단계/취소 유지. 작업 상태 한국어 표시 | /tmp/audit-tc/generating-final.png | fixture에 소스와 로그를 새로 생성하지 않아 빈 수집 목록. 원래 단일 최근 작업 API라 목업의 현재 작업+지난 실패 작업을 동시에 합성하지 않음. 실제 생성 호출 안 함 |
| TcStudio | 중앙에 갇힌 필터를 전체폭으로, 계층 트리200/표/상세380 독립 카드. 표 기본은 ID·제목/우선순위/And/iOS/검토. 기존15열 모두 DOM보존, ‘추가 열 보기’로 원래 셀 편집 접근 | /tmp/audit-tc/library-detail-final.png | 기존 열 편집·드래그·가상스크롤을 유지하기 위해 추가 열 토글 제공. 목업6행 대신 실제11행. 실제 신규·검증 필터는 모두 유지 |
| TcDetailPanels | 상세의2열 폼(우선순위/검토, And/iOS), 편집/원문/이력 탭 보존 및 확인 | /tmp/audit-tc/detail-source-final.png /tmp/audit-tc/detail-history-final.png | 원본 TC ID·태그·메모·검증 필드는 기존기능으로 유지. 엑셀 출처라 원문 문서발췌 대신 파일/시트/행 표시. Figma 프레임 등 데이터 없는 상태를 임의 생성하지 않음 |
| TcReview | 2열의 상세카드 나열을3열 목록/선택상세/근거로 재배치. 요약·일괄승인 전체폭. 선택과 J/K 이동, 기존 승인·반려·재생성·중복처리 요소 유지 | /tmp/audit-tc/review.png | fixture초안1건, 원문없음. 기존 상세의 사전조건/우선순위·검증 정보 유지해서 목업 예시보다 카드 높이가 큼 |
| TcExport | 카드 헤더, 대상조건을 막대 그래프 대신 구분선 목록으로 변경, 기존 범위/무결성검사/그룹매핑 수정 보존 | /tmp/audit-tc/export.png | 목업의 플랫폼별 생성예정집계 테이블은 기존 eligibility API가 분기별 count만 반환하므로 플랫폼 수를 추측해서 표시하지 않음. 그룹 누락보정 입력을 유지 |
| TcMdPreview | 우측 카드 하단에 작게 붙던 미리보기를 전체폭으로 독립 표시, 내보내기 돌아가기. 기존 충돌선택/반영/롤백/파이프라인 연결 유지 | /tmp/audit-tc/md.png | 실제파일경로 길이·3개충돌 표시. 이미 반영된 TC의 파이프라인 바로가기는 기존 연계 기능으로 유지하고 보조버튼으로 표현 |
| TcImportModal | 모달1040→900px, 매핑 입력2열, 기존 파일/매핑/미리보기/반영 흐름 보존 | /tmp/audit-tc/import-mapping-final.png | 자동/수동 인식은 기존 select 유지(목업2라디오 카드와 다름). 현재 매핑 API가 열기호를 입력받는 구조여서 실제 헤더 dropdown으로 보이게 새기능 추가하지 않음. 기존 프로필 수정/삭제 버튼도 보존 |
| TcImportHistory | 가져오기 폼 아래 삽입되던 이력을 독립2열 목록/선택상세로 표시, ‘가져오기로 돌아가기’ 제공 | /tmp/audit-tc/history.png | 같은 modal을 재사용해 상단 제목은 엑셀가져오기, 내부 제목이 이력. 실제작업을 선택하기 전 상세 안내 표시. 반영·롤백은 실행하지 않음 |
| TcProfileEditor | 규칙 편집이 우측 카드 안에 길게 열리던 것을640px 모달로 이동. 이름/규칙/금지표현/예시, 닫기/취소/저장 유지 | /tmp/audit-tc/profile-final.png | 기본 프로필 저장명은 원래빈값(기본을 덮어쓰지 않는 기존처리) 유지. 내용은 실제규칙 |
| TcModalsA | 시트명/계층이동/삭제/미저장 확인의 공통 밝은 모달, 닫기/취소 보존 | /tmp/audit-tc/move-final.png /tmp/audit-tc/delete-final.png | 이동은 기존 결합경로 select+제목 input으로 유지(목업4분류 select는 새연동로직 필요). 복구가능 케이스삭제 문구와 스위트삭제 문구는 서로 다름 |
| TcModalsB | 연결설정/휴지통 모달 및 상세의 출처/이력 확인 | /tmp/audit-tc/connectors-final.png /tmp/audit-tc/trash-final.png | 실제 휴지통은 빈상태. 연결설정 입력/출처갱신은 실행하지 않음. 출처 변경 비교 데이터가 없어 변경비교상태는 소스만 점검 |

## 기능 보존
- API요청/저장 함수/폴링 유지. 원래 id/data-id/핸들러를 이동해서 사용.
- 원래 모든 표셀 유지. 기본 숨김 열은 명시적 추가열 토글로 접근.
- 기존 초안 카드 DOM은 모두 유지하고 선택카드만 표시. 목록클릭/J/K가 동일한 focus를 사용.
- 원래10 E2E는 1차 수정후10개 통과. 새2개 테스트는 프로필 열기·닫기/추가열 노출·값 보존/초안 선택과 승인버튼 접근을 검증. 최종 통과 결과는 root의 전체실행으로 확인.


## 페이지 목업 재감사 / 수정 (1440×900)

| 목업 | 실제 차이 및 수정 | 확인 / 남는 차이 |
|---|---|---|
| Pipeline | 플랫폼 독립행, 제목 없는 단계, 행별 상태 없음, 공유 grid 높이로 실행버튼 아래 밀림 → 제목 오른쪽 플랫폼, 독립2열, 단계머리·상태배지, 평면기기행 | 실제 5폴더/미연결에뮬레이터/활성 Capture 안내는 실데이터. 실행 미수행 |
| PipelineRunning | 동일 단계·로그 영역, 상태별 글자/색 배지 매핑 | 브라우저 상태 fixture에서 분석완료/생성중 표시. 실제 파이프라인 실행하지 않음 |
| QuickRun | 플랫폼이 기기위 별도행, 중첩카드 → 헤더플랫폼, 평면행, 420px 기기열, 자동복구 문구 | 기존 완료결과 자동복원은 유지. 실데이터 폴더수가 예시보다 많음 |
| RunEvidence | 작은 글자/배지/시도버튼 및 과도한 카드 → 글자·세그먼트·요약셀·배지·시도버튼 조정 | 기존 browser contract가 영상/로그/스크린샷 동시 노출 및 순서 요구. 목업의 탭 중심 구조로 숨기지 않음. 영상 native controls/TC내용도 기존기능 보존 |
| EvidenceOverlay | 배경 흰색, 960px, 영문 상태, 큰영상 → backdrop,1040px,한국어 상태,220×355영상 | native video controls 유지, 영상/로그/스크린샷 탭 기존기능 유지. 커스텀재생바 구현 없음 |
| Reports | 툴바 추가 카드,489px리스트,106px행/3버튼 → 단일툴바,440px리스트,60px행,더보기안에 열기/삭제 보존 | 표시전용 전체/Android/iOS 필터 추가. 미리보기 빈상태는 아직 열지 않아 정상. unknown리포트는 전체에만 |
| History | 리셋 독립행,분리pill필터,그룹버튼,날짜줄바꿈,소요열없음,진행바 → 헤더리셋,세그먼트,기존필터버튼 이용드롭다운,단일날짜,소요열,평면행 | 데이터/기존필터 클릭동작 유지 |
| Env | Appium 액션하단/기기중첩카드/실기기작은글자 → 헤더액션,평면기기행,기기별 상태문구/실기기행 정렬 | 활성 외부Appium/MJPEG경고는 실제 상태. 서버 재시작없음 |
| EnvAppiumStates | 5상태 기존행동 유지, 새 헤더·상태·오류배치 | stopped/starting/managed/external/error는 브라우저 fixture만; 장치/API mutation 없음 |
| EnvModals | WiFi/WDA440px,세로입력 →520px/17px제목/구분선/WiFi IP·port2열 | WiFi/WDA/add/log 모두 직접 열기 screenshot. submit하지 않음. 추가모달 설치기기목록은 실제 값 |

증거: `/tmp/audit-pages/` 수정 전, `/tmp/audit-pages-after/` 수정 후. 증거 modal 최근 결과 `/tmp/audit-pages/EvidenceOverlay-actual.png`, RunEvidence 동일폴더. 모든 screenshot viewport1440×900 (full_page 옵션 화면 본문스크롤은 앱내스크롤이므로 viewport유지).
테스트: test_observability_workspace_e2e 23 passed. 기대값은 MB/run→MB/회, FLAKY→불안정, CRASH→실패 지점만 변경, assertion 삭제없음.


## Import1–5 / Tokens / Components 목업 정합 점검

## 검증 범위
- Legacy import 호환 화면만 수정. 엑셀 가져오기 메뉴는 복원하지 않음.
- JS: `agents/dashboard/static/import-studio.js`, CSS 전달: `/tmp/import-refresh.css`.
- 스크린샷: `/tmp/light-visual/import-review-{1,2,3,4,5}.png`, 각 1440×900.
- 브라우저 JS 메모리에만 fixture 주입. import commit, 실제 TC 저장, API POST 실행 없음.
- fixture 3건/시트명/android/파일목록은 UI 확인용이며 제품 코드에는 입력하지 않음.

## 상태별 비교
| 시안 | 기존 차이 | 수정 | 의도적으로 유지하는 차이 |
|---|---|---|---|
| Import | 전체너비 파일카드, 반영대상 패널 없음, 늘어나는 단계선 | 파일/반영대상 2열, 플랫폼 선택 컨트롤 기존 handler 재사용, 설명·원형 단계·짧은 선 | 실제 파일 다중목록, 선택된 파일 안에 시트 체크박스 위치 유지 |
| Import2 | 선택파일/매핑/검증 3열, KPI 큰 숫자 | 매핑/검증 2열, 작은 한 줄 KPI, 행구분선·흰 입력창·대상 필드 mono | 지원 필드 8개(tags/group) 유지; 목업의 platform 매핑필드 미지원이므로 새로 만들지 않음. 기존 플랫폼선택을 매핑하단에도 유지 |
| Import3 | 기본 표·필터 구조는 부합 | 공통 단계바/설명/하단 액션카드 통일 | 실제 원문 TC 열 유지, 데이터 길이에 따른 줄높이 차이 |
| Import4 | 정책2개 좌우, 요약 아래 전체폭 | 정책 세로목록 + 반영요약 400px 2열, 한국어 정책명 | 기존 버튼 선택 handler 유지(라디오로 교체하지 않음), 실제 예상 건수·저장경로 유지 |
| Import5 | 중앙 큰 체크/빈 공간, 하단 재시작 | 좌측 820px 완료카드, 파일목록, 기존 파이프라인 화면이동·재시작 액션 | 원본 result가 count/files만 제공하므로 skip/error 건수 목업 수치 새로 만들지 않음 |

## 공통 토큰/Components 검토
- docs/design-refresh/tokens.css와 static/tokens.css diff 0 (동일).
- 버튼 기본 높이34, 모서리6, 배지4, 카드8, 폰트·색·대비 토큰 부합.
- 공통 확인 모달은 최초 점검에서 다음 차이를 발견했다: 폭480 vs440, h2/body/footer 패딩16 vs18~20, 확정버튼 모든 확인에 파랑. 위험 작업 종류별 구분이 없으므로 단순 CSS로 모든 확인버튼을 빨강으로 바꾸면 부적절. root가 별도 검토할 항목.
- 후속 수정: 확인 모달을 440px·18~20px 여백으로 맞추고, 삭제·종료·중지·초기화 확인만 위험 색상으로 구분했다. 기존 focus/cancel/resolve 동작은 유지했다.
- Components는 표시 가능한 부품명세이며 제품에 토스트 되돌리기/지연 타이머 등 새 기능 추가하지 않음.
- 상태 배지는 텍스트 함께 표시, import 정책 권장/주의·검증분류 문구 유지.

## 확인
- `node --check agents/dashboard/static/import-studio.js` 통과.
- 5개 상태 문서 가로폭1440, 표시 버튼/표머리 가로 overflow 0.
- 원본 소스/파일 API, 매핑/미리보기 요청순서, commitImportStudio 동작 변경 없음.


## 최종 검증

전체 통합 테스트와 검색 결과는 [VERIFICATION.md](VERIFICATION.md)에 기록한다.
