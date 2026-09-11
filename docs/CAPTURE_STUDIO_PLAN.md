# Capture Studio 구현 플랜

**기준 PRD**: Element-first Capture Studio (Notion · 섹션 1–21)
**최종 업데이트**: 2026-09-11

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

### 후속 범위 (iOS·후속 기능)

- iOS Simulator (MJPEG 미지원 → 별도 방식 결정 필요)
- Swipe 및 복합 제스처
- 부분 재녹화
- 실패 TC에서 Capture Studio 재확인 화면으로 이동
- 실제 디바이스와 원격 디바이스 팜
- ws-scrcpy 전환 (H.264 WebCodecs, 지연 <100ms)

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

Healing 재확인은 7단계 별도 화면 또는 Locator 검토(4단계) 재진입으로 처리합니다 (와이어프레임 확정 후 결정).

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
| 방식 | Appium UiAutomator2 내장 MJPEG |
| 브라우저 표시 | `<img src="http://localhost:8093/">` |
| capability | `mjpegServerPort=8093`, `mjpegScalingFactor=75`, `mjpegServerScreenshotQuality=70` |
| Appium 서버 플래그 | `--allow-insecure=adb_screen_streaming` |
| 후속 범위 | ws-scrcpy (Node.js, H.264 WebCodecs, <100ms) |
| iOS | 후속 범위 (MJPEG 미지원, 별도 방식 결정 필요) |

### 서버 아키텍처

- 기존 `serve.py` (BaseHTTPRequestHandler) → **FastAPI + Uvicorn** 교체
- WebSocket 엔드포인트(`@app.websocket`)로 실시간 Action Timeline 업데이트
- 기존 `/api/*` REST 엔드포인트를 FastAPI로 이관 (하위 호환 유지)
- Capture Studio 전용 엔드포인트:
  - `POST /capture/session` — 세션 시작/재연결
  - `POST /capture/tap` — Tap 실행 및 기록
  - `POST /capture/input` — Input 실행 및 기록
  - `GET /capture/hierarchy` — 현재 hierarchy/DOM 수집
  - `POST /capture/save` — TC·registry 저장

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

| 전략 | 별점 | 근거 |
|---|---|---|
| `data-testid` / `resource-id` | ★★★★★ | 테스트 전용 식별자 |
| `accessibility id` / `aria-label` | ★★★★☆ | 접근성 표준, 안정적 |
| `role + name` 조합 | ★★★☆☆ | 구조적이나 텍스트 의존 |
| CSS selector / 안정적 text | ★★☆☆☆ | 텍스트 변경에 취약 |
| XPath | ★☆☆☆☆ | 최후 수단, 구조 변경에 취약 |

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
| P0 | Appium 서버 `--allow-insecure=adb_screen_streaming` 환경 확인 | ⬜ |
| P0 | `serve.py` → FastAPI 전환 일정 확정 (기존 엔드포인트 하위 호환 유지) | ⬜ |
| P0 | Capture Studio 세션과 파이프라인 실행 세션 충돌 방지 UX 확정 | ⬜ |
| P1 | Action Timeline 재실행 범위 확인 (전체 처음부터만 MVP 지원) | ⬜ |
| P1 | Healing 재확인 뷰 와이어프레임 확정 (별도 화면 vs Locator 검토 재진입) | ⬜ |
| P2 | TC 그룹명 기본값 정책 확정 (앱 이름 자동 vs 사용자 필수 입력) | ⬜ |
| P2 | Capture Studio 생성 pytest와 conftest.py 의존성 호환성 검증 | ⬜ |

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

### Phase 0 — 기반 준비 (P0 체크리스트 완료 필요)

**Task 0-1: FastAPI 전환**
- `agents/dashboard/serve.py` → FastAPI + Uvicorn 교체
- 기존 `/api/*` 엔드포인트 하위 호환 이관
- WebSocket 엔드포인트 뼈대 추가 (`/ws/timeline`)
- 완료 기준: 기존 대시보드 기능 그대로 동작, WebSocket 연결 확인

**Task 0-2: 세션 충돌 방지 UX**
- `state/capture_session.json` 스키마 정의
- 대시보드 상태바에 "Capture 세션 실행 중" 표시
- 파이프라인 실행 중 Capture Studio 진입 차단 UI

**Task 0-3: 환경 확인 스크립트**
- Appium MJPEG 스트리밍 동작 확인 스크립트 (`scripts/check_mjpeg.py`)
- `--allow-insecure=adb_screen_streaming` 플래그 안내 문서 갱신

---

### Phase 1 — 세션 설정 화면 (1단계)

**Task 1-1: Capture Studio 진입점**
- 대시보드에 "Capture Studio" 탭/버튼 추가
- OS(Android/iOS), 실행 대상(Emulator/실제), 앱 설정(package/activity) 입력 폼
- 연결 확인 후에만 "세션 시작" 활성화

**Task 1-2: Appium 세션 시작 API**
- `POST /capture/session` 구현
- Appium 드라이버 시작 → `state/capture_session.json`에 `session_id` 저장
- MJPEG 포트 반환

---

### Phase 2 — 화면 탐색 (2단계)

**Task 2-1: MJPEG 미러링 패널**
- `<img src="http://localhost:8093/">` 표시
- 클릭 시 좌표 캡처 → 좌표-노드 매핑 API 호출

**Task 2-2: 좌표-노드 매핑 API**
- `POST /capture/hierarchy` — page_source XML 파싱
- 좌표 보정 → bounds 필터링 → 최소 면적 노드 반환
- 부모/자식 전환 응답 포함

**Task 2-3: hierarchy/DOM 트리 패널**
- Native hierarchy 트리 렌더링 (좌우 양방향 강조)
- WebView 감지 시 DOM 탭 활성화
- WebView 미감지 시 "Native만 사용" 안내

**Task 2-4: 선택 요소 상세 패널**
- 속성(text, resource-id, accessibility, bounds) 표시
- Locator 후보 목록 + 별점 (★ 기반 전략 신뢰도)
- 중복 후보 시 일치 요소 수 표시

---

### Phase 3 — 동작 기록 (3단계)

**Task 3-1: 녹화 컨트롤**
- 녹화 시작 / 일시정지 / 종료 버튼
- 30분 비활동 자동 종료 타이머

**Task 3-2: Tap API**
- `POST /capture/tap` — Appium driver.click() 실행
- 클릭 전후 screenshot + snapshot 저장
- actions.json 항목 추가

**Task 3-3: Input API**
- `POST /capture/input` — 일반값 / 비밀값(마스킹) 구분
- actions.json에 입력 데이터 키 저장 (원문 미저장)

**Task 3-4: Back / Context switch API**
- Back: `driver.back()`
- Context switch: `driver.switch_to.context()` + 전환 로그 기록

**Task 3-5: Action Timeline WebSocket**
- `/ws/timeline` — 각 action 완료 시 브라우저에 실시간 push
- 로그 삭제 / 재정렬 API

---

### Phase 4 — Locator 검토 (4단계)

**Task 4-1: Locator 후보 검증 API**
- 각 후보 strategy+value로 `find_elements()` 실행
- 일치 개수 반환 → 1이면 "유일", 2+이면 "중복"

**Task 4-2: 승인 UI**
- 후보별 승인/거부 버튼
- 승인 항목만 `locators.json` 반영 대상으로 표시

---

### Phase 5 — Step 편집 (5단계)

**Task 5-1: Step 초안 생성**
- actions.json에서 사람이 읽을 수 있는 Step 문구 생성
- 사용자 편집 가능

**Task 5-2: 기대 결과 입력**
- 각 Step에 기대 결과 텍스트 입력
- 기대 결과 없는 Step: "품질 낮음" 경고 표시

---

### Phase 6 — 미리보기 (6단계)

**Task 6-1: Markdown TC 미리보기**
- actions.json + step 편집 결과로 Markdown 초안 렌더링
- `testcases/{platform}/{group}/tc_*.md` 경로 표시

**Task 6-2: pytest 미리보기**
- `02_generate.py` 로직으로 pytest 코드 미리보기 (파일 미저장)
- registry 누락 항목 있으면 "생성 불가" 경고

---

### Phase 7 — 저장 및 생성 (7단계)

**Task 7-1: 저장 API**
- `POST /capture/save` 구현
- Markdown TC 저장 (`testcases/`)
- `screens.json`, `locators.json` 갱신
- 기존 파일 충돌: 덮어쓰기 / 새 ID 선택
- 저장 성공 후 "코드 생성 / 빠른 실행 / TC 열기" 버튼 제공

**Task 7-2: 코드 생성 실행**
- `02_generate.py --strict-locators --platform {os}` subprocess 실행
- 결과를 대시보드 스타일 리포트로 표시

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
