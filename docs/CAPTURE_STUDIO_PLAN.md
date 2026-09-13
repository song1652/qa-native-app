# Capture Studio 구현 플랜

**기준 PRD**: Element-first Capture Studio (Notion · 섹션 1–21)
**최종 업데이트**: 2026-09-12

---

## 1. 목적

Capture Studio는 QA 담당자가 실제 Android/iOS 앱 화면의 요소를 선택하고 조작하는 과정을 기록하여 검증 가능한 Locator와 테스트 Step을 만드는 반수동 제작 화면입니다.

핵심: **요소 선택과 실제 조작 증거 수집** → Markdown TC + Locator registry + pytest 생성.

---

## 2. 범위

### 1차 MVP (Android Emulator)

- Appium 및 Android 디바이스 연결 확인
- MJPEG 스트리밍으로 앱 화면 표시
- Native hierarchy와 감지된 WebView DOM 조회
- 현재 context 자동 인식 및 수동 전환
- Tap, Input, Back, Context switch 기록
- 선택 요소의 Locator 후보와 별점 안정성 표시
- 테스트 Step 초안과 기대 결과 작성
- Markdown TC, `screens.json`, `locators.json` 미리보기
- 사용자 승인 후 저장 및 기존 `02_generate.py --strict-locators` 실행

### 후속 범위

- Swipe 및 복합 제스처 (현재: swipe API 있음, 녹화·재생은 후속)
- 부분 재녹화
- 실제 디바이스와 원격 디바이스 팜
- ws-scrcpy 전환 (H.264 WebCodecs, 지연 <100ms)
- iOS Hybrid WebView context (현재 Native only)

---

## 3. 핵심 사용자 흐름 (7단계)

```
1. 세션 설정     — OS·디바이스·앱 선택, Appium 세션 시작
2. 화면 탐색     — 미러링 + hierarchy/DOM 조회, 요소 선택
3. 동작 기록     — 녹화 중 Tap/Input/Back/Context 전환 실행
4. Locator 검토  — 후보·별점·중복 여부 확인, 사용자 승인
5. Step 편집     — 초안 수정, 기대 결과 입력
6. 미리보기      — Markdown TC + pytest 코드 나란히 표시
7. 저장 및 생성  — registry·TC 저장 → 02_generate.py 실행
```

Healing 재확인은 Locator 검토(4단계) 재진입 방식으로 구현되었습니다. 실패 TC 목록에서 "재확인" 버튼을 누르면 해당 TC의 Locator 검토 화면으로 이동합니다.

---

## 4. 화면 정보 구조

### 기본 레이아웃

```
┌────────────────────────────────────────────────────────────────────┐
│ 세션/Context 상태 (상태바)                 녹화 · 일시정지 · 종료  │
├─────────────────┬────────────────────────┬─────────────────────────┤
│ MJPEG 미러링    │ Native / WebView 트리  │ 선택 요소 상세          │
│ (localhost:8093)│ 검색 · Inspect         │ Locator 후보 · 별점     │
├─────────────────┴────────────────────────┴─────────────────────────┤
│ Action Timeline: 01 Tap · 02 Input · 03 Context switch · 04 Assert │
├──────────────────────────────────┬─────────────────────────────────┤
│ Markdown TC 미리보기             │ 생성 코드 미리보기              │
└──────────────────────────────────┴─────────────────────────────────┘
```

---

## 5. 기술 아키텍처

### 화면 미러링 (MVP)

| 항목 | 값 |
|---|---|
| 항목 | Android | iOS |
|---|---|---|
| 방식 | Appium UiAutomator2 내장 MJPEG | XCUITest + `/capture/screenshot` polling |
| 브라우저 표시 | `<img src="http://localhost:8093/">` | 1.2초 간격 `<img>` src 교체 |
| capability | `mjpegServerPort=8093`, `mjpegScalingFactor=75` | `screenshot_mode: poll` |
| Appium 서버 플래그 | `--allow-insecure=uiautomator2:adb_screen_streaming` | 불필요 |
| WDA 안정화 대기 | — | 폴링 25회 실패 후 에러 (약 30초 여유) |
| 후속 범위 | ws-scrcpy (H.264, <100ms) | — |

### 서버 아키텍처

- **FastAPI + Uvicorn** (Phase 0에서 전환 완료)
- WebSocket 엔드포인트(`/ws/timeline`) 뼈대 구현
- 기존 `/api/*` REST 엔드포인트 하위 호환 이관 완료
- Capture Studio 전용 엔드포인트 (구현 완료):
  - `POST /capture/session` — 세션 시작/재연결 (Android: MJPEG, iOS: poll 분기)
  - `POST /capture/tap` — Tap 실행 및 기록
  - `POST /capture/back` — Back 실행 (완료 후 hierarchy 자동 새로고침)
  - `POST /capture/scroll` — Swipe 실행
  - `GET /capture/hierarchy` — 현재 page_source hierarchy 수집
  - `GET /capture/screenshot` — iOS용 단일 스크린샷 (poll 방식)
  - `GET /capture/page_source_hash` — page_source MD5 (8자 hex), 화면 전환 감지용
  - `POST /capture/generate_from_actions` — actions 배열 → 자체 완결형 pytest 코드
  - `POST /capture/end_session` — 세션 종료

### Appium 세션 관리

- Capture Studio 세션 시작 → `state/capture_session.json`에 `session_id` 저장
- FastAPI 서버가 `session_id`로 기존 Appium 세션에 attach (기존 파이프라인 스크립트와 분리)
- 세션 종료: "저장 및 생성" 완료 후 명시적 종료 **또는** 비활동 30분 자동 종료
- **Capture Studio 세션과 파이프라인 실행 세션은 동시에 존재 불가** → 대시보드에 상태 표시

### 좌표-노드 매핑 알고리즘

```
브라우저 클릭 좌표
  → 미러링 화면 스케일 보정 (display_width / img_width)
  → 디바이스 실제 좌표
  → page_source XML 파싱 → 모든 노드 bounds 추출
  → 실제 좌표를 포함하는 노드 목록 필터링
  → 가장 작은 면적(가장 구체적) 노드 기본 선택
  → 부모/자식 전환 UI 제공
  → hierarchy 수집은 클릭 직후, 화면 변화 감지 시 자동 재수집
```

---

## 6. Locator 정책

### 우선순위 및 별점

**Android:**
| 전략 | 별점 | 근거 |
|---|---|---|
| `resource-id` (앱 고유) | ★★★★★ | 테스트 전용 식별자 |
| `accessibility id` / `content-desc` | ★★★★☆ | 접근성 표준, 안정적 |
| `text` (안정적 문자열) | ★★★☆☆ | 텍스트 변경에 취약 |
| `class name` | ★★☆☆☆ | 같은 클래스 다수 존재 가능 |
| XPath | ★☆☆☆☆ | 최후 수단 |

**iOS:**
| 전략 | 별점 | 근거 |
|---|---|---|
| `accessibility id` (`label` 우선, `name` 차선) | ★★★★★ | XCUITest 표준, `_ios_tap()` 자동 스크롤 지원 |
| `predicate string` | ★★★☆☆ | 복합 조건, 유일성 높음 |
| `class chain` | ★★☆☆☆ | 구조 의존 |
| XPath | ★☆☆☆☆ | 최후 수단 |

> iOS `label` vs `name`: `label`은 사람이 읽는 텍스트(예: '스크린 타임'), `name`은 bundle-ID 스타일(예: 'com.apple.settings'). XCUITest에서 `_ios_tap()` 자동 스크롤은 `label` 기준으로 동작하므로 `label`을 우선 사용합니다.

### 승인 조건

- 동일 후보가 화면 내에서 유일하게 검색될 것
- 중복 시: 일치 요소 수와 후보 비교 표시 → 사용자 선택
- 승인된 항목만 `config/locators.json` 반영

---

## 7. 저장 데이터

### 세션 원본 (`state/captures/{session_id}/`)

```
state/captures/{session_id}/
├─ session.json
├─ actions.json
├─ native/
│  ├─ 0001.xml
│  └─ 0001.png
└─ webview/
   ├─ 0002.html
   └─ 0002.png
```

### actions.json 최소 필드

```json
{
  "index": 1,
  "action": "tap",
  "surface": "native",
  "context": "NATIVE_APP",
  "screen": "settings_main",
  "target_ref": "Settings_main.search_button",
  "snapshot_id": "0001",
  "locator": {
    "strategy": "accessibility id",
    "value": "Search"
  }
}
```

### 최종 승인 시 갱신 대상

```
testcases/{platform}/{group}/tc_*.md
config/screens.json
config/locators.json
tests/generated/{platform}/{group}/tc_*.py
```

---

## 8. Native/WebView 판단 규칙

- 세션 시작은 항상 Native context
- context 목록에 실제 WebView가 있을 때만 WebView UI 활성화
- 사용자가 WebView 내부 요소 선택 시 DOM locator 저장
- WebView 탈출 동작은 명시적인 `NATIVE_APP` 복귀 단계로 기록
- Android Chromium WebView: CDP 가능 시 CDP 사용, 불가 시 Appium WebView context
- iOS: 후속 범위 (Appium context 기반 기본값)

---

## 9. Action Timeline

기록 대상 (MVP):
- Tap, Input, Clear, Back, Context switch, Assertion

각 로그 포함 정보:
- 순서와 실행 시간
- Action과 결과 상태
- Platform, Surface와 Context
- Screen과 Target reference
- Locator (전략, 값)
- 실행 전후 Snapshot ID
- Screenshot
- 입력 데이터 키

비밀값: 원문 저장 없음, 사용자가 Input마다 보안 토글로 지정.
재실행: Appium 세션을 처음 단계부터 순차 재생.

---

## 10. Step과 기대 결과

- Action Timeline에서 Step 초안 자동 생성
- 사용자가 Step 문구 수정 가능
- 기대 결과 미입력 상태로 Capture 계속 가능
  - 최종 저장 시 경고 표시 + 저장 허용
  - 생성된 TC에 **`품질 낮음` 태그** 부여

---

## 11. Healing 연계

1. 실행 실패 → 마지막 성공 Snapshot과 실패 직전 Snapshot 비교
2. 최초 Capture evidence와 현재 요소를 같은 Surface 안에서 비교
3. 신뢰도 높고 유일한 후보만 자동 반영
4. 모호하거나 Context 달라진 경우 → Capture Studio **재확인 목록** 으로 전달
5. 사용자가 새 요소 선택 → Registry 갱신 + 코드 재생성
6. 3회 실패 시 Jira에 로그·Screenshot·영상·후보 비교 첨부

---

## 12. 주요 상태 및 메시지

| 상태 | 처리 |
|---|---|
| Appium 미기동 | 세션 시작 비활성화, 설정 화면 링크 |
| 디바이스 없음 | 대상 선택 비활성화, 재조회 제공 |
| WebView 없음 | "Native만 사용합니다" 명시 |
| Locator 유일 | 승인 가능 |
| Locator 중복 | 일치 요소 수와 후보 비교 표시 |
| Snapshot 오래됨 | 재수집 전 저장 비활성화 |
| 세션 시간 초과 | 30분 비활동 자동 종료, 기록 유지 |
| 세션 종료됨 | 기록 유지 + 재연결 제공 |
| 파이프라인 실행 중 | Capture Studio 비활성 (동시 사용 불가) |
| 저장 성공 | 코드 생성 / 빠른 실행 / TC 열기 제공 |

---

## 13. 구현 전 해결 체크리스트 (PRD 섹션 21)

| 우선순위 | 항목 | 상태 |
|---|---|---|
| P0 | Appium 서버 `--allow-insecure=adb_screen_streaming` 환경 확인 | ✅ |
| P0 | `serve.py` → FastAPI 전환 일정 확정 (기존 엔드포인트 하위 호환 유지) | ✅ |
| P0 | Capture Studio 세션과 파이프라인 실행 세션 충돌 방지 UX 확정 | ✅ |
| P1 | Action Timeline 재실행 범위 확인 (전체 처음부터만 MVP 지원) | ⬜ |
| P1 | Healing 재확인 뷰 와이어프레임 확정 (별도 화면 vs Locator 검토 재진입) | ✅ Locator 검토 재진입 방식으로 구현 |
| P2 | TC 그룹명 기본값 정책 확정 (앱 이름 자동 vs 사용자 필수 입력) | ⬜ |
| P2 | Capture Studio 생성 pytest와 conftest.py 의존성 호환성 검증 | ✅ 자체 완결형으로 conftest 불필요 |

---

## 14. 완료 기준

- 사용자가 Appium Inspector와 코드를 오가지 않고 요소를 선택하여 TC 한 건을 만들 수 있다
- 모든 실행 Step에 요소, Context와 전후 Snapshot 근거가 남는다
- 승인된 Locator가 실제 세션에서 유일하게 검색된다
- Native-only 앱은 UI hierarchy만으로 완성되고 WebView 도구가 실행되지 않는다
- Android Hybrid 앱은 Native/WebView 전환이 로그와 생성 코드에 동일하게 반영된다 (iOS Hybrid는 후속 범위)
- 생성된 Markdown은 파일 하나당 TC 하나 원칙을 지킨다
- 생성 결과가 기존 Lint, 실행, 리포트와 Healing 파이프라인과 호환된다
- 실행은 대시보드에서 수동으로 트리거하며 Capture Studio가 자동 실행하지 않는다

---

## 15. 구현 태스크 분해

### Phase 0 — 기반 준비 ✅ 완료

**Task 0-1: FastAPI 전환** ✅
- `agents/dashboard/serve.py` → FastAPI + Uvicorn 교체 완료
- 기존 `/api/*` 엔드포인트 하위 호환 이관 완료
- WebSocket 엔드포인트 뼈대 추가 (`/ws/timeline`) 완료

**Task 0-2: 세션 충돌 방지 UX** ✅
- `state/capture_session.json` 스키마 정의 완료
- 대시보드 상태바에 "Capture 세션 실행 중" 표시 완료
- 파이프라인 실행 중 Capture Studio 진입 차단 UI 완료

**Task 0-3: 환경 확인 스크립트** ✅
- Appium MJPEG 스트리밍 환경 확인 완료
- `--allow-insecure=uiautomator2:adb_screen_streaming` 플래그 (Appium 3.x) 문서 반영

---

### Phase 1 — 세션 설정 화면 (1단계) ✅ 완료

**Task 1-1: Capture Studio 진입점** ✅
- 대시보드에 "Capture Studio" 탭/버튼 추가 완료
- OS(Android/iOS), 실행 대상(Emulator/실제), 앱 설정(`app_package`/`app_activity`) 입력 폼 완료
- 연결 확인 후에만 "세션 시작" 활성화 완료

**Task 1-2: Appium 세션 시작 API** ✅
- `POST /capture/session` 구현 완료
- Appium 드라이버 시작 → `state/capture_session.json`에 `session_id` 저장 완료
- MJPEG 포트 반환 완료
- `/capture/generate_from_actions` 엔드포인트: actions 배열 → 자체 완결형 pytest 코드 생성 완료
- 세션 key: `app_package` / `app_activity` (구버전 `app_pkg` 사용 금지)

---

### Phase 2 — 화면 탐색 (2단계) ✅ 완료

**Task 2-1: 미러링 패널** ✅
- Android: `<img src="http://localhost:8093/">` MJPEG 스트리밍
- iOS: 1.2초 polling + img src 교체

**Task 2-2: 화면 전환 자동 감지** ✅
- `csStartScreenWatcher()` — 4초 간격 `/capture/page_source_hash` 폴링
- hash 변경 감지 → 3초 쿨다운 후 `csRefreshHierarchy()` 자동 호출

**Task 2-3: hierarchy/DOM 트리 패널** ✅
- Native hierarchy XML 파싱 → 트리 렌더링
- 노드 클릭 → 속성 및 Locator 후보 상세 패널

**Task 2-4: 선택 요소 상세 패널** ✅
- 속성(text, resource-id/label, accessibility, bounds) 표시
- Locator 후보 목록 + ★ 별점 (Android/iOS 전략별 우선순위)
- Android: resource-id(앱 고유) 최우선 / iOS: label 기반 accessibility-id 최우선

---

### Phase 3 — 동작 기록 (3단계) ✅ 완료

**Task 3-1: 녹화 컨트롤** ✅ (세션 시작 = 기록 시작)

**Task 3-2: Tap API** ✅
- 미러링 클릭 → 좌표 변환 → `POST /capture/tap` → Appium click 실행
- back 버튼: `POST /capture/back` → 실행 후 1.2초 뒤 hierarchy 자동 새로고침

**Task 3-3: Scroll API** ✅
- `POST /capture/scroll` — swipe 실행

**Task 3-4: "직접 Step 추가" 패널** ✅
- tap / back / scroll / wait / assert 타입 직접 입력 추가
- iOS: `accessibility-id` tap → `_ios_tap(label)` 코드 생성 (mobile:scroll 자동 스크롤 포함)

**Action Timeline 갱신**: 각 액션의 fetch `.then()` 에서 직접 업데이트 (WebSocket 불필요 — 모든 액션이 사용자 트리거이므로 request-response 패턴으로 충분)

---

### Phase 4 — Locator 검토 (4단계) ✅ 완료

**Task 4-1: Locator 후보 카드** ✅
- 전략·값·별점 표시 (Android/iOS 플랫폼별 우선순위 분기)
- iOS: `_csBestLocator()` 에서 `label` 우선 선택 (`name` 차선)

**Task 4-2: 승인 UI** ✅
- 후보 카드 클릭 → 승인 → actions에 반영

**Task 4-3: Healing 재진입** ✅
- 실패 TC "Locator 재확인" 버튼 → Capture Studio 4단계 재진입
- `csOpenHealReview()`: 세션 있으면 csMirrorConnect + csRefreshHierarchy 자동 호출

---

### Phase 5 — Step 편집 (5단계) ✅ 부분 완료

**Task 5-1: tc_group / tc_id 설정** ✅
- tc_group → 폴더명 (`tests/generated/{platform}/{tc_group}/`)
- tc_id → 파일명 (`{tc_id}.py`)
- 같은 그룹에 여러 TC 누적 가능 → 대시보드 리포트에 그룹별 집계

**Task 5-2: 기대 결과 입력** ⬜ (각 Step별 기대 결과 텍스트 입력 UI 미구현)

---

### Phase 6 — 미리보기 (6단계) ✅ 완료

**Task 6-1: 생성 코드 미리보기** ✅
- `POST /capture/generate_from_actions` (dry-run 없이 직접 생성)
- 자체 완결형: `_build_driver()` + `_el()` + `_ios_tap()` (iOS) + test class

---

### Phase 7 — 저장 및 생성 (7단계) ✅ 완료

**Task 7-1: 코드 저장** ✅
- "저장 및 생성" 버튼 → `/capture/generate_from_actions` → pytest 파일 저장
- `tests/generated/{platform}/{tc_group}/{tc_id}.py`
- 저장 성공 후 "실행" / "파일 열기" 버튼 제공

**Task 7-2: Markdown TC / locators.json 갱신** ⬜ (코드만 저장, MD·registry 자동 갱신 미구현)

---

### Phase 8 — 검증

**Task 8-1: 정적 검증**
- `python3 -m py_compile agents/dashboard/serve.py`
- mock session으로 `/capture/*` 엔드포인트 smoke test

**Task 8-2: 통합 검증**
- Android Emulator + Settings 앱으로 TC 1건 end-to-end 생성
- 생성된 Markdown이 기존 lint, execute, report 파이프라인과 호환 확인

---

## 16. 디자인 원칙

- 기존 QA Control Center의 어두운 보라색 디자인 토큰 사용
- 사용자가 선택한 요소와 현재 Context를 항상 명확히 표시
- 디바이스 화면과 Action Timeline이 Locator 상세보다 시각적으로 우선
- 색상만으로 상태를 전달하지 않고 텍스트와 아이콘을 함께 사용
- 모호한 후보, 오래된 Snapshot과 연결 실패를 숨기지 않음
- 사용자 기록이 유실되지 않도록 재연결과 저장 실패 상태를 지원

---

## 17. 관련 파일

| 파일 | 역할 |
|---|---|
| `agents/dashboard/serve.py` | FastAPI 서버 (교체 대상) |
| `agents/dashboard/dashboard.html` | 대시보드 프론트엔드 |
| `state/capture_session.json` | Capture 세션 상태 |
| `state/captures/{session_id}/` | 세션 원본 데이터 |
| `config/locators.json` | Locator registry |
| `config/screens.json` | 화면 정의 |
| `scripts/02_generate.py` | pytest 코드 생성기 |
| `docs/LOCATOR_HEALING.md` | Healing 정책 |

---

## 18. 현재 알려진 제약사항

| 항목 | 내용 |
|---|---|
| Android MJPEG | 포트 8093 사용. Appium 서버에 `--allow-insecure=uiautomator2:adb_screen_streaming` 플래그 필요 (Appium 3.x) |
| iOS XCUITest 세션 충돌 | 시뮬레이터당 XCUITest 세션 1개 제한. Capture Studio iOS 세션 열린 채 iOS pytest TC 동시 실행 불가. 충돌 시 "🔄 세션 재연결" 버튼으로 복구 |
| iOS 미러링 지연 | screenshot polling 방식 (1.2초 간격) — MJPEG보다 지연 큼 |
| 세션 동시 사용 불가 | Capture Studio 세션과 파이프라인 실행 세션은 동시에 존재할 수 없음 |
| 자체 완결 코드 생성 | 생성된 pytest 파일은 `_build_driver()` + `_el()` + class 구조로 완결. conftest 공유 fixture 사용 금지 |
| iOS `_ios_tap()` | accessibility-id tap만 자동 스크롤 지원. xpath/id tap은 기존 `_el().click()` 방식 사용 |
| TC 파일 덮어쓰기 | 같은 `tc_id`로 생성 시 기존 파일 덮어씀. 의도적 버전 관리 필요 시 tc_id를 달리 지정 |
| Step별 기대 결과 | 현재 기대 결과 UI 미구현. assert 타입 액션으로 검증 로직 추가 필요 |
