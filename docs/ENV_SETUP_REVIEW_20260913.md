# Environment Setup UI — 3인 에이전트 최종 검토 회의록

**일시**: 2026-09-13  
**참여**: PM · QA 엔지니어 · 개발자  
**검토 대상**: PRD v0.3, 인터랙티브 목업, 디자인 스펙

---

## 🚫 블로커 (착수 전 필수 해소)

### B1. `config/devices.json` 다중 디바이스 스키마 미정의 _(PM 발견)_

**문제**: 현재 `android.emulator`는 객체 1개이나, 목업은 AVD 2개·시뮬레이터 3개를 배열로 렌더링. "기본값" 뱃지 개념도 추가됨. `01_analyze`/`05_execute`가 이 스키마를 읽으므로 설계 없이 착수하면 M2 전체 재작업.  
**결정**: `android.emulator` → 배열 + `default: true` 필드로 전환. PRD §11에 마이그레이션 정책 추가.

### B2. Appium 중지에 Capture/파이프라인 가드 없음 _(PM, QA 공통 발견)_

**문제**: iOS 시뮬레이터 종료는 `is_capture_active()`로 막으면서, 훨씬 파괴적인 Appium 중지에 가드 없음. Appium을 죽이면 양쪽 세션이 동시에 orphan 발생.  
**결정**: `POST /api/env/appium/stop` 실패 코드에 `403 capture_session_active`, `409 pipeline_running` 추가. §13 카탈로그에도 추가.

### B3. `error` 상태 처리가 PRD↔스펙 정면 충돌 _(PM 발견)_

**문제**: PRD §7은 "error 유지 + 로그 + 재시도"인데, 디자인 스펙 전이표는 `error → stopped (자동, 1초)`로 1초 만에 사라짐. 구현자가 어느 쪽을 따라도 한쪽 문서와 어긋남.  
**결정**: **PRD §7을 정본**으로 삼음. 디자인 스펙에서 `error → stopped (자동, 1초)` 행 삭제. 사용자가 "다시 시도"를 클릭하거나 명시적으로 닫아야만 해소.

---

## ⚠️ 공통 수정 권고 (마일스톤 착수 전 반영)

### C1. 상태 모델 3값 → 5값 정정 _(PM 발견)_

PRD §5-1은 managed/external/stopped 3값인데 §10과 스펙 전이표는 `starting`, `error`를 추가로 사용. PRD 내부 모순.  
→ §5-1을 **5값** (stopped / starting / managed / external / error)으로 정정.

### C2. M1→M2→M3 릴리즈 의존성 미기술 _(PM 발견)_

"Appium 선행 게이팅"이 목업·스펙에만 있고 PRD §3·§4에 근거 없음. M2를 M1 없이 단독 릴리즈할 수 없는데 문서에 없음.  
→ §3 마일스톤 표에 "M2/M3는 M1 완료 후 릴리즈" 추가. §4 흐름도에 Appium 선행 조건 명시.

### C3. 재시작/재연결 버튼 API 미정의 _(QA, 개발자 공통 발견)_

목업·스펙에는 `↺ 재시작` (managed 카드), `↺ 재연결` (external 카드)이 있으나 PRD §6에 대응 엔드포인트 없음.  
→ 결정: **재시작** = `POST /api/env/appium/stop` → `POST /api/env/appium/start` 순차 호출, 클라이언트 처리. 별도 API 불필요.  
→ **재연결** = `GET /api/env/status` 즉시 1회 재호출. 라벨은 "상태 새로고침"으로 통일 (Capture Studio와 혼동 방지).

### C4. Android 에뮬레이터 중지 Capture 가드 누락 _(QA, PM 공통 발견)_

iOS에는 종료 시 `is_capture_active()` 가드가 있으나 Android에는 없음. Capture Studio Android 세션이 열린 상태에서 에뮬레이터를 강제 종료하면 세션 orphan.  
→ `POST /api/env/android/avd/stop` 실패 코드에 `403 capture_session_active` 추가.

### C5. `env_session.json` 스키마 누락 필드 _(QA, 개발자 공통 발견)_

`android.status`, `android.started_at`, `ios.status`, `ios.started_at`, `appium.status` 없음. §7 "부팅 중 이탈 복원"이 이 필드들에 의존하는데 스키마에 없음.

### C6. §12 재사용 맵 경로 오류 _(PM, 개발자 공통 발견)_

| PRD §12 기재 | 실제 위치 |
|---|---|
| `routes/pipeline.py` `is_capture_active()` | `agents/dashboard/utils/state.py:63` |
| `shared.py:38` `_find_adb_bin()` | `agents/dashboard/shared.py:63` |
| 신규 `utils/device_utils.py` | `utils/system.py` 확장으로 통합 (기존에 `check_android_devices()`, `check_ios_simulators()` 보유) |

### C7. DELETE body 비표준 _(개발자 발견)_

`DELETE /api/env/android/remove {avd}` 등 JSON body DELETE는 일부 HTTP 클라이언트에서 무시됨.  
→ `POST /api/env/android/remove`, `POST /api/env/ios/remove`로 변경.

### C8. 에뮬레이터 소유권 모델 비대칭 _(PM 발견)_

Appium: external 상태에서 SIGTERM 금지. 에뮬레이터: 소유권 무관 `adb emu kill` 허용. 사용자가 Android Studio로 띄운 에뮬레이터도 대시보드가 종료할 수 있음.  
→ MVP에서는 **의도된 결정**으로 명문화. §8에 "에뮬레이터 프로세스 소유권은 추적하지 않으며 항상 `adb emu kill`로 종료한다" 추가.

### C9. External Appium의 MJPEG 플래그 미검증 _(PM 발견)_

managed 카드에는 "MJPEG 플래그 ✓"가 있으나 external에는 없음. 플래그 없이 뜬 외부 서버가 US-2 사용자의 가장 흔한 미러링 실패 원인.  
→ external 상태에서도 기존 `/api/check/mjpeg` 재사용해 경고 배지 노출.

### C10. 복수 에뮬레이터 동시 시작 정책 미정의 _(QA, PM 공통 발견)_

목록에 AVD 여러 개가 있으나 동시 시작 시 행동이 미정의. PRD §16에 "단일 에뮬레이터 확정"이라고 했으나 UI가 모든 항목에 시작 버튼을 가짐.  
→ MVP 정책: **한 번에 하나만 실행 가능**. 하나가 실행/부팅 중일 때 다른 항목의 시작 버튼 비활성(409 already_running).

---

## ✅ 승인 항목

| 항목 | 담당 |
|---|---|
| US-1 해피패스 흐름 완결성 (목업 14화면 연결) | PM |
| US-2 External 인계 (SIGTERM 차단, pointer-events:none) | PM |
| Phase 3 실기기 분리 (안내 텍스트만, 조작 컨트롤 없음) | PM |
| 보안 제약 (화이트리스트, shell=False, UUID 검증) | PM, QA |
| 해피패스 §15-2 6개 항목 자동화 테스트 가능 | QA |
| `_find_adb_bin()` 패턴으로 Appium/emulator bin 탐색 추가 용이 | 개발자 |
| 기존 `check_appium_status()` 재사용으로 3값 판정 구현 가능 | 개발자 |
| M1 착수 블로커 없음 (스펙 수정 후) | 개발자 |
| 디자인 스펙 전이표 6열 구조 (From-To-트리거-조건-효과-API) | PM, 개발자 |

---

## 📋 PRD v0.4 업데이트 항목 (우선순위순)

| # | 항목 | 마일스톤 | 발견자 |
|---|---|---|---|
| 1 | devices.json 배열 스키마 + 마이그레이션 정책 | **M2 전 필수** | PM |
| 2 | Appium 중지 가드 (403/409) 추가 | **M1 필수** | PM, QA |
| 3 | error 상태 전이 충돌 해소 (PRD §7 정본) | **M1 필수** | PM |
| 4 | 5값 상태 모델 정정 | M1 | PM |
| 5 | M1→M2→M3 의존성 §3 명시 | M1 | PM |
| 6 | 재시작/재연결 API 결정 기재 | M1 | QA, Dev |
| 7 | Android 에뮬레이터 중지 Capture 가드 (403) | M2 | QA, PM |
| 8 | env_session.json 스키마 보강 | M1 | QA, Dev |
| 9 | §12 재사용 맵 경로 수정 + device_utils 통합 | M1 | PM, Dev |
| 10 | DELETE → POST 변경 | M1 | Dev |
| 11 | 에뮬레이터 소유권 모델 명문화 | M2 | PM |
| 12 | External MJPEG 경고 노출 | M1 | PM |
| 13 | 복수 에뮬레이터 동시 시작 차단 (409) | M2 | QA, PM |
| 14 | §15-1 KPI 측정 기준 구체화 | M1 릴리즈 전 | PM |
| 15 | 드라이버 확인 함수 DI 구조화 (테스트 격리) | M1 | QA |
| 16 | 타임아웃 모킹 포인트 추가 (테스트 전용 파라미터) | M2/M3 | QA |

---

## 다음 단계

1. **PRD v0.4 업데이트** — 위 블로커 3건 + 공통 권고 즉시 반영
2. **M1 착수** — `routes/env.py` 생성, Appium start/stop/status API
3. **목업 마이너 업데이트** — 삭제 확인 다이얼로그, iOS 타임아웃 화면 추가
