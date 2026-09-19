# Nova MCP Integration — 설계 문서

> 작성일: 2026-09-15
> 최종 업데이트: 2026-09-16 (에이전트 4종 리뷰 반영)
> 문서 성격: Nova MCP의 구조와 인터페이스를 설명하는 설계 자료. 동작의 최종 기준은 제품 코드와 API 테스트입니다.
> 관련 문서: `docs/ENV_SETUP_PRD.md`, `CLAUDE.md §Capture Studio`
> 디자인 목업: https://claude.ai/code/artifact/4d819f9b-382a-4f45-b3e1-720c9d9d8047

---

## 1. 개요

qa-native-app의 Capture Studio를 확장하여 nova MCP의 핵심 장점을 흡수한다.

**기존 강점 유지:**
- 완성된 QA 파이프라인 (analyze → generate → lint → execute → heal)
- TC 자산 관리 (Markdown, Locator registry, Healing)
- Excel Import, Run History, Dashboard

**신규 추가:**
- 브라우저에서 디바이스를 직접 클릭·조작하는 인터랙티브 미러
- 모든 자동화 흐름을 실시간으로 보여주는 Livetail 패널
- Claude Code / Claude Desktop이 디바이스를 직접 제어하는 MCP 서버

---

## 2. 목표 / 비목표

### 목표
- Capture Studio 3패널 레이아웃 (미러 | Hierarchy | Livetail)
- 미러 클릭 → 디바이스 실제 탭 (Android MJPEG 즉시 / iOS 1~2초)
- 스와이프: 드래그 제스처 → scroll API 전달
- Livetail: user·mcp·pipeline 이벤트 통합 실시간 스트림 (SSE)
- MCP 서버: 표준 MCP 프로토콜, Claude Code·Desktop 양쪽 지원
- MCP 툴 8종: screenshot, hierarchy, tap, scroll, input, back, screen_info, generate_test_case
- Android / iOS 동시 지원

### 비목표
- 외부 LLM SDK import (CLAUDE.md 규칙 준수)
- 별도 프로세스/포트의 MCP 서버 (기존 8767 포트 내 라우터로 구현)
- 새 탭 추가 (Capture Studio 탭 내 확장)
- 실기기 전용 기능 (에뮬레이터·시뮬레이터와 동일 코드 경로)
- iOS 자유 드래그 스와이프 (폴링 구조상 UX 불가 — 방향 버튼 유지)
- Claude Desktop 직접 연결 (stdio 브리지 필요 — Claude Code 단독 지원)
- 원격/팀 공유 MCP 접근 (인증·TLS 포함 별도 설계 필요)
- MCP를 통한 파이프라인 트리거 (execute/heal)
- Livetail 파일 영속/재생
- 멀티 디바이스 동시 MCP 세션
- WebView context MCP 조작

---

## 3. 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                  Capture Studio (확장)                  │
│                                                         │
│  [미러+컨트롤]  [Hierarchy]  [Livetail]                │
│       ↕                           ↑                     │
│  click→tap                  SSE 이벤트 수신             │
└───────┬─────────────────────────────┬───────────────────┘
        │                             │
        ▼                             │
┌──────────────────┐     ┌────────────────────┐
│  FastAPI 백엔드   │────▶│   Event Bus        │
│  (port 8767)     │     │  (asyncio Queue)   │
│                  │     │  모든 액션 emit     │
│ /capture/tap  ✅ │     └────────┬───────────┘
│ /capture/scroll✅│              │
│ /capture/screenshot✅           ▼
│ /livetail/stream  │     GET /livetail/stream
│   (신규 SSE)      │     (SSE, text/event-stream)
│ /mcp  (신규)      │
└──────────────────┘
        ▲
        │ MCP 프로토콜
┌───────┴──────────┐
│  Claude Code CLI │
│  Claude Desktop  │
└──────────────────┘
```

### 새로 만들 파일/모듈
| 경로 | 역할 |
|---|---|
| `agents/dashboard/routes/livetail.py` | SSE 스트림 + Event Bus |
| `agents/dashboard/routes/mcp.py` | MCP 서버 라우터 |
| `agents/dashboard/utils/event_bus.py` | 공유 asyncio Queue 싱글턴 |

### 기존 파일 수정
| 경로 | 변경 내용 |
|---|---|
| `agents/dashboard/serve.py` | livetail·mcp 라우터 등록 |
| `agents/dashboard/routes/capture.py` | 모든 액션에 event_bus.emit() 추가 |
| `agents/dashboard/routes/pipeline.py` | execute·heal 단계에 event_bus.emit() 추가 |
| `agents/dashboard/dashboard.html` | 3패널 레이아웃 + 인터랙티브 미러 + Livetail UI |

---

## 4. UI/UX 변경

### 4-1. Capture Studio 레이아웃

**현재:**
```
[ 세션 설정 ] → [ 미러 + Hierarchy 트리 + 액션 레코더 ]
```

**변경 후:**
```
[ 세션 설정 ] → [ 3패널 뷰 ]

┌──────────────┬─────────────────┬──────────────────────┐
│              │                 │ Livetail             │
│   미러 화면  │  Hierarchy 트리  │──────────────────────│
│  (클릭가능)  │  (기존 유지)    │ 22:45 👤 tap(540,960)│
│              │                 │ 22:45 🤖 screenshot  │
│              │                 │ 22:46 ⚙ pipeline    │
│              │                 │──────────────────────│
│ [Back][Home] │                 │ [👤][🤖][⚙] 필터   │
│ [⌨ 입력]   │                 │ [Export]             │
└──────────────┴─────────────────┴──────────────────────┘
│ 🔴 기록중: tap → scroll → tap ...          [TC 생성]  │
└──────────────────────────────────────────────────────┘
```

### 4-2. MCP 토글 (상단 상태 바)
```
[세션: Android · SM-G991] [MCP ● ON] [세션 종료]
```
- MCP OFF 상태에서도 인터랙티브 미러·Livetail 동작
- MCP ON 시 `/mcp` 엔드포인트 활성화 (Claude가 연결 가능)

### 4-3. 인터랙티브 미러 UX
- 일반 클릭: 탭
- 클릭 드래그 (0.3초 이상): 스와이프
- iOS: 탭 후 "처리 중..." 반투명 오버레이 표시 (1~2초)
- 탭 성공 시 Livetail에 즉시 기록

### 4-4. Livetail 로그 행 형식
```
HH:MM:SS  [아이콘] [source]  [type]  [요약]  [플랫폼]  [결과] [ms]
22:45:01   👤      user      tap     x=540,y=960  android  ✅  234ms
22:45:03   🤖      mcp       screenshot  —         android  ✅  89ms
22:46:00   ⚙       pipeline  execute  settings/tc1  android  ✅  3.2s
22:46:04   ⚙       pipeline  heal     settings/tc1  android  ⚠  retry
```

---

## 5. 인터랙티브 미러

### 5-1. 좌표 변환
```
클릭 좌표 (이미지 px) → 디바이스 좌표 (dp)

scale_x = device_width  / image_rendered_width
scale_y = device_height / image_rendered_height
device_x = click_x * scale_x
device_y = click_y * scale_y
```
디바이스 해상도는 세션 시작 시 `/capture/session` 응답의 `device_width`, `device_height`로 확보.

### 5-2. 스와이프 감지
- `mousedown` → `mousemove` → `mouseup` 시퀀스
- 이동 거리 < 10px: 탭으로 처리
- 이동 거리 ≥ 10px: 스와이프 → `POST /capture/scroll` with `{startX, startY, endX, endY}`

### 5-3. 플랫폼별 피드백
| | Android | iOS |
|---|---|---|
| 화면 갱신 | MJPEG 실시간 | 폴링 1.2s |
| 탭 후 반응 | 즉시 | 1~2초 오버레이 표시 |

---

## 6. Livetail

### 6-1. Event Bus (`utils/event_bus.py`)
```python
# asyncio Queue 싱글턴
# emit(source, type, platform, data, result, duration_ms)
# subscribe() → AsyncGenerator[Event]
```

### 6-2. SSE 엔드포인트
```
GET /livetail/stream
Content-Type: text/event-stream

data: {"ts":"22:45:01","source":"user","type":"tap","platform":"android",...}
```

### 6-3. 이벤트 emit 위치
| 위치 | 이벤트 |
|---|---|
| `capture.py` /capture/tap | user·tap |
| `capture.py` /capture/scroll | user·scroll |
| `capture.py` /capture/back | user·back |
| `capture.py` /capture/screenshot | user·screenshot |
| `mcp.py` 각 툴 | mcp·{tool_name} |
| `pipeline.py` execute 단계 | pipeline·execute |
| `pipeline.py` heal 단계 | pipeline·heal |

### 6-4. 프론트엔드
```javascript
const es = new EventSource('/livetail/stream');
es.onmessage = (e) => appendLivetailRow(JSON.parse(e.data));
```
필터 토글(user·mcp·pipeline)은 이미 수신된 행의 `display` CSS만 토글.

---

## 7. MCP 서버

### 7-1. 프로토콜
MCP over HTTP+SSE (표준 Model Context Protocol).
별도 라이브러리 없이 FastAPI로 직접 구현 — CLAUDE.md "외부 LLM SDK 금지" 규칙 준수.

### 7-2. 엔드포인트
```
POST /mcp          ← 툴 호출 (JSON-RPC 2.0)
GET  /mcp/sse      ← 서버→클라이언트 이벤트 스트림
```

### 7-3. MCP 툴 8종

| 툴명 | 파라미터 | 반환 | 내부 API |
|---|---|---|---|
| `device_screenshot` | — | base64 PNG | GET /capture/screenshot |
| `device_hierarchy` | — | XML 트리 | GET /capture/hierarchy |
| `device_tap` | x, y | ok/error | POST /capture/tap |
| `device_scroll` | direction, amount | ok/error | POST /capture/scroll |
| `device_input` | text | ok/error | POST /capture/input |
| `device_back` | — | ok/error | POST /capture/back |
| `device_get_screen_info` | — | hash, app_state | GET /capture/page_source_hash |
| `generate_test_case` | group, tc_id | 파일 경로 | POST /capture/generate_from_actions |

### 7-4. 연결 설정 (사용자 1회 설정)
```json
// Claude Code: .claude/settings.json mcpServers 섹션
// Claude Desktop: ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "qa-device": {
      "url": "http://localhost:8767/mcp"
    }
  }
}
```

### 7-5. 세션 가드
MCP 툴 호출 시 활성 Capture Studio 세션이 없으면 `session_not_active` 에러 반환.
기존 `is_capture_active()` 함수 재활용.

---

## 8. 구현 단계 (Phase)

> ⚠️ PM 리뷰 반영: MCP → Livetail 순서로 변경. 미러 탭은 이미 동작 중이므로 Phase 1은 좌표 정확도 수정에 집중.

### Phase 1 — 좌표 정확도 + 3패널 레이아웃 (0.5~1일)
- `capture.py:342-351` 응답에 `device_width`, `device_height` 추가 (1080 fallback 제거)
- `/capture/scroll` 좌표 파라미터 선택적 추가 (`{startX, startY, endX, endY}`)
- Capture Studio 3패널 레이아웃 CSS 변경 (`minmax(280px,320px) 1fr minmax(280px,360px)`)
- 스와이프 드래그 감지 + iOS 처리 중 오버레이
- Step/Locator 패널 → 미러 하단 accordion 이동
- 반응형: `@media(max-width:1200px)` Livetail 접힘, `@media(max-width:1000px)` 2패널+드로어

### Phase 2 — MCP 서버 (2~3일)
- `routes/mcp.py` JSON-RPC 2.0 + SSE 구현
- MCP 프로토콜 핸드셰이크: `initialize` / `initialized` / `tools/list` / `endpoint` SSE 이벤트
- 우선 4종: `device_tap`, `device_screenshot`, `device_hierarchy`, `generate_test_case`
- 나머지 4종: `device_scroll`, `device_input`, `device_back`, `device_get_screen_info`
- `serve.py` 라우터 등록 + MCP 토글 상태 4종 (OFF/대기중/ON/오류)
- 액션 레코드 `source: user|mcp` 필드 추가
- `device_input` emit 시 `is_secret` 마스킹 (`***`)
- Claude Code 연결 테스트 + ONBOARDING.md MCP 설정 섹션 추가

### Phase 3 — Livetail (1~2일)
- 기존 `/ws/timeline` + `broadcast_timeline_sync()` 확장 (신규 SSE Event Bus 없음)
- source별 아이콘·필터 (👤 user / 🤖 mcp / ⚙ pipeline)
- **레이아웃: 기존 3패널 유지 (Mirror | Hierarchy | Step+Locator)**
- Livetail은 세션 스트립 토글 버튼 → 오른쪽 슬라이드 패널 (Step+Locator 위를 덮음)
- 프론트 Livetail 패널: `.lt-row` 전용 클래스 (`.log-box` 재활용 금지)
- 메모리 버퍼 200행 + 신규 접속 시 replay
- 신규 JS: `static/livetail.js` 분리 (`dashboard.html` 인라인 증가 억제)
- 목업 참조: https://claude.ai/code/artifact/9d72a3b9-5d10-4ca3-96c5-7ba33bc3b748 (옵션 C)

---

## 9. 검증 기준

| 기능 | 검증 방법 |
|---|---|
| 인터랙티브 미러 | 브라우저 클릭 → 디바이스 화면 변화 확인 |
| 스와이프 | 드래그 → 앱 스크롤 확인 |
| Livetail 실시간 | 탭 후 1초 이내 로그 행 추가 확인 |
| 파이프라인 Livetail | execute 실행 시 Livetail에 ⚙ 행 표시 확인 |
| MCP Claude Code | `device_tap` 툴 호출 → 디바이스 탭 확인 |
| MCP Claude Desktop | 동일 |
| 세션 가드 | 세션 없을 때 MCP 호출 → error 반환 확인 |

---

## 10. 오픈 이슈 — 결정 현황

| # | 이슈 | 결정 |
|---|---|---|
| 1 | MCP SSE와 `/ws/timeline` WebSocket 공존 | ✅ 프로토콜 다름(SSE vs WS), 충돌 없음. 단 역할 분리 필요 → §11 참조 |
| 2 | Event Bus Queue 무한 증가 | ✅ Fan-out 패턴 + `maxsize=200` + overflow 시 oldest drop → §11 참조 |
| 3 | iOS 자유 드래그 UX | ✅ **비지원 확정** — 폴링 1.2s에서 드래그 피드백 불가. iOS는 방향 버튼 스크롤 유지 |
| 4 | MCP 인증 | ✅ 로컬 전용(`127.0.0.1` 고정), 인증 없음. MCP 토글 기본 OFF + 경고 표시 |
| 5 | Livetail 히스토리 | ✅ 세션 범위 메모리 버퍼 200행, 신규 접속 시 replay. 파일 영속 비목표 |
| 6 | `generate_test_case` 빈 액션 | ✅ 즉시 에러: `{"error":"session_actions_empty","message":"먼저 tap/scroll을 기록하세요"}` |

---

## 11. 에이전트 리뷰 결과 (2026-09-16)

> Developer · QA · Designer · PM 4종 리뷰 종합. 구현 착수 전 반드시 처리할 항목.

### 11-1. 구현 전 필수 결정 사항

**[PM] Livetail ↔ 기존 Action Timeline 관계 — 최우선 결정**

현재 `/ws/timeline` WebSocket + `broadcast_timeline_sync()` 5곳 emit이 이미 동작 중.
신규 SSE Event Bus(`utils/event_bus.py`)를 추가하면 완전 중복.

**결정 권고: Action Timeline을 Livetail로 흡수·확장. 전송은 기존 `/ws/timeline` 재사용. 신규 SSE/Event Bus 신설 취소.**
→ 오픈 이슈 #1·#2 소멸, Phase 2 공수 절반, `threading` → `asyncio` 브리지 재발명 불필요.

**[Dev] `/capture/scroll` 파라미터 스키마 통일**

현재 `direction: up|down` 전용. 설계 §5-2는 `{startX, startY, endX, endY}` 좌표 기반.
→ 기존 엔드포인트를 깨지 않고 좌표 파라미터를 선택적으로 추가하는 형태로 확장.

**[QA/Dev] `/capture/session` 응답에 `device_width/height` 추가**

현재 미포함 → 좌표 변환 시 `dashboard.html:4118-4130`의 1080 하드코딩 fallback 동작.
→ `capture.py:342-351` 응답에 `driver.get_window_size()` 결과 추가.

**[Dev] MCP 프로토콜 핸드셰이크 추가**

Phase 3 스코프에 명시 필요: `initialize` → `initialized` → `tools/list` 순서.
`GET /mcp/sse` 연결 직후 `endpoint` SSE 이벤트로 POST URL 전달.
JSON-RPC 표준 에러 코드: `-32601`, `-32700`, `-32600`.
`InitializeResult` capabilities: `{"tools": {}}` 최소 선언.

**[QA] `is_capture_active()` 로직 반전 — MCP 세션 가드**

기존 가드는 `True` 시 차단. MCP는 반대로 세션 있을 때 허용.
→ `if not is_capture_active(): return session_not_active` 로 명시.

### 11-2. 범위 조정 (비목표 추가)

```
비목표 (추가):
- iOS 자유 드래그 스와이프 (폴링 구조상 UX 불가)
- Claude Desktop 직접 연결 (stdio 브리지 필요, 이번 범위 제외 → Claude Code 단독)
- 원격/팀 공유 MCP 접근 (인증·TLS 포함 별도 설계)
- MCP를 통한 파이프라인 트리거 (execute/heal)
- Livetail 파일 영속/재생
- 멀티 디바이스 동시 MCP 세션
- WebView context MCP 조작
```

**Phase 순서 변경**: PM 권고에 따라 MCP를 Livetail보다 먼저 구현.

| 순서 | 내용 | 공수 |
|---|---|---|
| Phase 1 | 좌표 정확도 수정 + 좌표 스와이프 API + 3패널 레이아웃 | 0.5~1일 |
| Phase 2 | MCP 서버 (4종 우선: hierarchy/tap/screenshot/generate_test_case) | 2~3일 |
| Phase 3 | Livetail (기존 Action Timeline 확장) | 1~2일 |

### 11-3. 신규 발굴 이슈

**[PM] MCP 액션과 사람 액션 혼입**

MCP `device_tap` 호출이 사람의 녹화 세션 `session["actions"]`에 섞임 → TC 오염.
→ 액션 레코드에 `source: user|mcp` 필드 추가, TC 생성 시 필터 선택.

**[PM] 파이프라인 Livetail 이벤트 구조적 불가**

`pipeline.py:55,119` `is_capture_active()` 가드 → Capture 세션 활성 시 파이프라인 실행 차단.
§4-4의 `⚙ pipeline` 행은 Livetail 화면을 보는 동안 발생 불가.
→ §9 검증 항목 "파이프라인 Livetail" 제거, granularity를 "단계 시작/종료 + 최종 결과"로 낮춤.

**[PM] 비밀값 Livetail 누출**

`capture.py:415-417` `is_secret` 마스킹이 Livetail·MCP `device_input` 응답에 미적용.
→ `device_input` 이벤트 emit 시 `value_preview`에 `***` 처리 필수.

**[Designer] Step/Locator 패널 행선지 — ✅ 결정**

기존 3패널(Mirror | Hierarchy | Step+Locator) 레이아웃 완전 유지.
Livetail은 세션 바 토글 버튼으로 오른쪽에서 슬라이드 인 — 열리면 Step+Locator 패널 위를 덮음.
닫으면 기존 패널 복원. Livetail 버튼은 세션 스트립에 배치 (`lt-toggle-btn` 클래스).

**[Designer] 반응형 레이아웃**

13인치 MacBook(~1280px)에서 3패널 비좁음.
→ `@media(max-width:1200px)`: Livetail 기본 접힘, `@media(max-width:1000px)`: 2패널+드로어.

**[Designer] MCP 연결 대기 상태 추가**

기존 ON/OFF 2상태 외 "연결 대기 중"(warn 노란 pulse dot) 상태 추가 필요.
→ CSS `.dot.warn { background: var(--warn); animation: pulse-warn 1.5s infinite }` 신규.

**[Dev] dashboard.html 파일 분리**

현재 5390줄 → 3패널 추가 시 7000줄+.
→ 신규 기능은 `static/livetail.js`, `static/capture_mirror.js`로 분리, 기존 인라인 유지.

### 11-4. 수정된 검증 기준

| 기능 | 기준 |
|---|---|
| 좌표 정확도 | hierarchy 미로드 포함 20회 탭 → 20회 의도 요소 bounds 적중 |
| 탭 반응 | Android p95 < 500ms, iOS p95 < 2.5s |
| MCP 연결 | ONBOARDING.md 설정 블록 복사 붙여넣기 → 1회 성공 |
| TC 생성 | MCP 경로로 생성한 TC가 `05_execute` 첫 실행 pass |
| 회귀 | `py_compile scripts/*.py` + `02_generate --strict-locators` 양 플랫폼 통과 |
| 기존 Action Timeline | Livetail 작업 후 무손상 확인 |
| 비밀값 | `is_secret=true` 입력값이 Livetail·Export·MCP 응답에 미노출 |
