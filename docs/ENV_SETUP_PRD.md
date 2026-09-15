# Environment Setup UI — PRD

**작성일**: 2026-09-12
**최종 수정**: 2026-09-15
**버전**: v1.0 (external Appium 중지 · iOS 시뮬레이터 비동기 부팅 · 배지 통일)
**상태**: M1·M2·M3 완료 (Appium + Android AVD + iOS Simulator 웹 E2E 실측 완료)
**리뷰 기록**: docs/ENV_SETUP_REVIEW_20260913.md
**담당**: QA Automation Platform

**변경 이력**
- 2026-09-15 (v1.0): **external Appium 중지 지원** — `POST /api/env/appium/stop`이 `external` 상태에서도 동작. `lsof -ti :<port>`로 PID 탐색 후 SIGTERM. **iOS 시뮬레이터 비동기 부팅** — `subprocess.run`(블로킹) → `subprocess.Popen`(비동기)으로 전환. API가 즉시 202 + `status: "starting"` 반환, 3초 폴링이 `simctl list`의 `Booted` 감지 → `running` 전환. 대시보드에서 "부팅 중..." 상태가 실제로 보임. **디바이스 배지 문구 통일** — iOS `Booted`→`실행 중`, `Shutdown`→`중지됨` (Android와 일치). §5-1 external 행 업데이트 (중지 가능으로 변경).
- 2026-09-15 (v0.9): **디바이스 최소 보유 정책** 신설 (§5-4). 가상 기기(emulator/simulator) 최소 1대 — 1대일 때 UI ✕ 버튼 `disabled` + 툴팁. 실기기(real_device) 0대 허용 — 마지막 1대 삭제 시 경고 다이얼로그. `envRemoveDevice()`를 `<dialog>` 패턴 + 한국어 에러 매핑으로 교체. Bug 수정: error code `"cannot remove last device"` → `"last_device"` (API 계약 준수), 빈 섹션 remove 요청 `400` → `404` 분리. 신규 API 테스트 10개 추가 (221개 통과).
- 2026-09-14 (v0.8 최신): 디자인 스펙 v0.8과 목업 v0.8을 기준으로 **환경 설정 페이지, 기기별 목록 행, Android/iOS 추가 모달, 자동 입력, 삭제 UI**를 반영했다. 시스템 AVD/Simulator 검색 API, Android 중복 AVD 409 및 MJPEG capability 자동 채움, iOS UDID 검증·중복 409·UDID 기반 부팅/종료를 완료했다. 실제 브라우저에서 Appium 시작, Android 시작/중지, iOS 부팅/종료를 검증했으며, 긴 `simctl` 명령 중에도 상태 조회가 멈추지 않도록 실행 중 명령 중복을 방지했다.
- 2026-09-14 (v0.8 중간 기록): F1·F3·F6과 US-3 API를 먼저 반영했다. 당시 UI 미구현 평가는 위 최신 변경 이력으로 대체됐다.
- 2026-09-13 (v0.7): 아키텍처 리뷰 7개 항목 반영. **F1** Appium을 디바이스 시작의 선행 조건에서 제외 (§4·§7). **F2** 터미널 0개 목표를 "최초 구축"과 "일상 사용"으로 분리 (§2·§15-1). **F3** Appium 바인딩 `0.0.0.0` → `127.0.0.1` (§1·§5-1·§14). **F4** 디바이스 식별 Known Limitation 신설 (§19). **F5** `devices.json` 원자적 저장을 Future Work로 기록 (§11). **F6** `is_capture_active(platform)` 플랫폼별 분리 (§8·§6·§7·§13). **F7** Phase 3 섹션에 별도 PRD 분리 예정 표기 (§16).
- 2026-09-13 (v0.6 유지): §4 사용자 흐름을 Android/iOS **병렬 분기** 구조로 정정. M2·M3가 사용자 진입 순서로 오독되던 문제 해소. §3 마일스톤 주석, §5-2·5-3 헤더, §7 Ready 판정 기준 동반 갱신.

---

## 1. 배경 및 목적

현재 Capture Studio와 파이프라인을 사용하려면 사용자가 터미널에서 직접 명령을 실행해야 합니다.

```bash
appium --address 127.0.0.1 --port 4723 --allow-insecure=uiautomator2:adb_screen_streaming
emulator -avd Pixel_7_Android15
xcrun simctl boot <udid>
```

이 진입 장벽을 없애고, **대시보드에서 모든 환경 준비를 마칠 수 있도록** 환경 설정 UI를 제공합니다. 또한 `config/devices.json`을 직접 편집하지 않고도 디바이스를 추가·삭제할 수 있어야 합니다.

---

## 2. 목표 · 페르소나 및 사용자 스토리

### 2-1. 목표 범위 정의 _(v0.7 신설, F2 해소)_

"터미널 명령 0개"는 **모든 상황에서 터미널이 필요 없다**는 뜻이 아니다. 두 단계를 분리해 정의한다.

| 단계 | 담당 | 터미널 사용 | 이 PRD의 범위 |
|---|---|---|---|
| **① 최초 개발 환경 구축** — Node.js·Appium 설치, `appium driver install uiautomator2/xcuitest`, Xcode Command Line Tools, Android SDK·AVD 생성 | 개발자 / 온보딩 담당자 | **필요** (1회성) | ❌ 범위 밖. 대시보드는 미설치를 **감지해 안내 메시지와 설치 명령을 표시**할 뿐 자동 설치하지 않는다 (§13 에러 카탈로그) |
| **② 구축 완료 후 일상 사용** — Appium 서버 시작·중지, 에뮬레이터/시뮬레이터 시작·종료, 디바이스 추가·삭제 | 비개발자 QA (US-1) | **0개** | ✅ 이 PRD가 달성하는 목표 |

> **KPI 해석 기준**: §15-1의 "터미널 명령 0개"는 ②구간만을 측정한다. ①을 포함해 측정하지 않는다.
>
> **비목표**: 대시보드가 `npm i -g appium`, `appium driver install`, `xcode-select --install`을 대신 실행하지 않는다. 권한·네트워크·전역 설치 실패 시 복구 경로가 대시보드 안에 없기 때문이며, 이는 Phase 4에서도 재검토하지 않는다.

### 2-2. 페르소나 및 사용자 스토리

**주 페르소나: 비개발자 QA (US-1 우선)**

**US-1** (주): 비개발자 QA로서, 터미널을 열지 않고 대시보드에서 Appium과 에뮬레이터를 시작해, Capture Studio로 바로 TC를 만들고 싶다.

**US-2**: QA 자동화 담당자로서, 내가 이미 터미널에서 띄운 Appium 서버를 대시보드가 죽이지 않고 "외부 실행 중"으로 인식하길 원한다.

**US-3**: QA 담당자로서, 에뮬레이터/시뮬레이터를 JSON 파일을 편집하지 않고 대시보드에서 추가·삭제하고 싶다.

---

## 3. 마일스톤 및 범위

| 마일스톤 | 범위 | 이유 | 선행 조건 |
|---|---|---|---|
| **M1 (P0)** | Appium 서버 시작/중지/상태(5값)/로그 + 바이너리 탐색 + 드라이버 설치 확인 | 실패 빈도 최상위, 플랫폼 무관. 기존 `/api/check/*` 확장으로 최소 변경 | — |
| **M2 (P1)** | Android AVD 목록·시작·중지 + 부팅 완료 판정 + 디바이스 추가/삭제 UI + `devices.json` 배열 마이그레이션 | Phase 1 (Android 에뮬레이터) 로드맵 우선 _(개발 순서이며 사용자는 Android/iOS를 어느 순서로든 독립 설정 가능)_ | **M1 완료 후 릴리즈** |
| **M3 (P2)** | iOS 시뮬레이터 목록·부팅·종료 + `devices.json` 반영 | Phase 2 _(개발 순서이며 사용자는 Android/iOS를 어느 순서로든 독립 설정 가능)_ | **M1 완료 후 릴리즈** |
| **Phase 3** | 실기기 감지·선택, WDA 자동화, AVD 생성 UI | 로드맵 순서 준수 | M3 완료 후 |

> **릴리즈 의존성** _(v0.7 정정, F1 해소)_: M2·M3는 M1 완료 후 릴리즈한다. 이유는 **디바이스 시작이 Appium을 필요로 해서가 아니라**, 디바이스를 띄워도 Appium 없이는 Capture Studio·파이프라인으로 이어지는 사용자 여정이 완결되지 않기 때문이다.
>
> ⚠️ **v0.6까지의 "Appium stopped → 디바이스 시작 버튼 비활성" 정책은 삭제되었다.** 에뮬레이터/시뮬레이터 시작은 Appium과 **완전히 독립**이며, Appium이 `stopped`/`error`여도 디바이스를 시작할 수 있다. Appium은 **Capture Studio 세션 시작과 파이프라인 실행**의 선행 조건일 뿐이다. 상세는 §4·§7 참조.
>
> **M2 → M3는 개발 마일스톤 순서일 뿐 사용자 진입 순서가 아니다.** 릴리즈 후 사용자는 Android만 설정해도, iOS만 설정해도 해당 플랫폼 파이프라인을 실행할 수 있다. 공통 선행 조건은 M1(Appium)뿐이다.

---

## 4. 사용자 흐름

```
대시보드 접속
  └─ 상단 환경 상태바: Appium ● / Android ● / iOS ●
       └─ "환경 설정" 탭 진입
            │
            ├─ ⓐ [M1] Appium 서버 섹션 ───────────┐
            │    ├─ 상태 표시 (managed / external  │
            │    │   / stopped / starting / error) │
            │    ├─ 시작 / 중지 / 상태 새로고침    │  세 섹션 모두
            │    └─ MJPEG 플래그 경고 (external)   │  서로 독립
            │                                       │  순서 무관
            ├─ ⓑ [M2] Android 에뮬레이터 섹션 ─────┤  동시 조작 가능
            │    ├─ 등록된 AVD 목록 + 시작/중지     │
            │    └─ "＋ 추가 / ✕ 삭제" UI           │
            │                                       │
            └─ ⓒ [M3] iOS 시뮬레이터 섹션 ─────────┘
                 ├─ 등록된 시뮬레이터 목록 + 부팅/종료
                 └─ "＋ 추가 / ✕ 삭제" UI
            │
            ▼  ⓐ Appium 준비  AND  (ⓑ OR ⓒ 중 하나 이상 준비)
       ③ 실행 게이트 → Capture Studio 세션 시작 / 파이프라인 실행
```

> **독립 시작 원칙** _(v0.7 정정, F1 해소)_
>
> **ⓐ·ⓑ·ⓒ 세 섹션은 서로 독립이며, Appium은 에뮬레이터/시뮬레이터 시작의 선행 조건이 아니다.**
>
> - Appium이 `stopped`·`starting`·`error` 상태여도 Android AVD를 시작할 수 있다.
> - Appium이 `stopped`·`starting`·`error` 상태여도 iOS 시뮬레이터를 부팅할 수 있다.
> - 에뮬레이터를 먼저 띄우고 Appium을 나중에 시작해도 되고, 그 반대도 된다.
>
> **근거**: `emulator -avd` 와 `xcrun simctl boot` 는 Appium 프로세스와 아무 의존 관계가 없는 독립 프로세스다. 에뮬레이터 콜드 부팅은 최대 3분이 걸리므로, 부팅을 Appium 시작 뒤로 직렬화하면 실제로 병렬 가능한 대기 시간을 사용자에게 순차로 부담시킨다. 게이팅은 사용자 시간을 늘릴 뿐 어떤 오류도 예방하지 않는다.
>
> **Appium이 실제로 선행 조건인 지점**: ③ 실행 게이트 하나뿐이다.
> - Capture Studio 세션 시작
> - 파이프라인(`01_analyze` ~ `06_heal`) 실행
>
> 이 두 진입점에서만 Appium `managed`/`external`을 요구하며, 미충족 시 해당 버튼을 비활성화하고 "환경 설정에서 Appium을 시작하세요" 안내를 표시한다.
>
> **플랫폼 병렬 원칙(v0.6 유지)**: ⓑ Android와 ⓒ iOS도 서로 독립이다. Android만 준비해도 Android 파이프라인이, iOS만 준비해도 iOS 파이프라인이 실행된다.

> ### US-3 달성 범위 — **API·UI 완료** _(v0.8 최신 실측)_
>
> | 계층 | 상태 | 근거 |
> |---|---|---|
> | 백엔드 API 4종 | ✅ 구현 완료 | `agents/dashboard/routes/env.py` — `/api/env/{android,ios}/{add,remove}` |
> | 원자적 저장 | ✅ 구현 완료 | `agents/dashboard/utils/state.py` `save_devices_json()` |
> | 시스템 기기 검색 | ✅ 구현 완료 | `/list_system_avds`, `/list_system_simulators`가 이름·버전·UDID 메타데이터를 제공 |
> | 대시보드 UI (추가 버튼·모달·✕ 삭제) | ✅ 구현 완료 | `dashboard.html`의 플랫폼별 목록 행과 추가 모달이 API를 직접 호출 |
> | 실제 웹 E2E | ✅ 완료 | Appium 및 실제 설치된 AVD/Simulator의 시작·상태 확인·종료 실측 |
>
> 따라서 US-3 사용자 스토리("JSON 파일을 편집하지 않고 대시보드에서 추가·삭제")와 일상 사용 구간의 **터미널 명령 0개** 목표를 달성했다. AVD/Simulator 자체 생성은 Android Studio/Xcode에서 수행하는 최초 구축 범위다.

---

## 5. 기능 상세

### 5-1. Appium 서버 관리 (M1)

**아키텍처 결정: 단일 Appium 서버 (확정)**

> **결정**: Appium 서버를 **1개만 운영**한다. Android와 iOS 세션을 같은 서버에서 처리한다.
>
> **근거**: Appium 3.x는 하나의 서버 인스턴스에서 UiAutomator2(Android)와 XCUITest(iOS) 드라이버를 동시에 로드·운용할 수 있다. 드라이버 간 세션 격리는 Appium 내부에서 처리된다.
>
> ```
> Appium 서버 (localhost:4723)
>   ├── UiAutomator2 드라이버  →  Android 에뮬레이터 세션
>   └── XCUITest 드라이버      →  iOS 시뮬레이터 세션
> ```
>
> **다중 서버 방식 미채택 이유**: 포트 충돌 관리, 이중 상태 관리, 구성 복잡도 증가 대비 MVP 단계에서 얻는 이점이 없음. 다중 에뮬레이터 동시 병렬 실행이 필요한 경우 Phase 3에서 재검토.

**5값 상태 모델** _(v0.4 정정: 3값 → 5값)_

| 상태 | 정의 | 버튼 |
|---|---|---|
| `stopped` (중지됨) | `/status` 실패 + PID 없음 | 시작 활성 |
| `starting` (시작 중) | subprocess spawn 완료, `/status` 200 대기 중 | 모든 버튼 잠김 |
| `managed` (관리 중) | 대시보드가 시작한 프로세스. PID 추적 중 | 중지·재시작 활성 |
| `external` (외부 실행 중) | `/status` 200이지만 대시보드 PID 아님 | **중지 활성** (lsof PID 탐색 후 SIGTERM), "상태 새로고침" 활성 |
| `error` (오류) | 타임아웃·비정상 종료 | "다시 시도" 버튼 + 로그 경로 표시 — **사용자 액션 없이 자동 해소되지 않음** |

> **external 중지 동작** _(v1.0 변경)_: `POST /api/env/appium/stop`은 `external` 상태에서도 동작한다. `lsof -ti :<port>`로 포트를 점유한 PID를 모두 탐색 후 SIGTERM. 5초 내 종료 미확인 시 504 `appium_stop_timeout`. Capture·파이프라인 가드는 동일하게 적용된다. _(구 정책 "외부 실행 중에서는 SIGTERM 금지"는 v1.0에서 폐지됨)_
>
> **error 상태 정책** _(v0.4 확정, B3 해소)_: 타임아웃·비정상 종료 후 `error` 상태는 사용자가 "다시 시도"를 클릭하거나 화면을 떠날 때까지 유지된다. 1초 후 자동 `stopped` 전이 없음 — 로그를 봐야 원인 파악이 가능하기 때문.
>
> **Appium 중지 가드** _(v0.4 추가 B2 해소 / v0.7 인자 명시 F6)_: `POST /api/env/appium/stop`은 Capture 세션 또는 파이프라인 실행 중 차단된다. **`is_capture_active()` — 인자 없이 호출해 플랫폼 무관 전체 확인** → 403 capture_session_active, `is_pipeline_active()` → 409 pipeline_running. Appium 서버는 Android·iOS 세션이 공유하는 단일 프로세스이므로 어느 플랫폼의 Capture 세션이든 하나라도 살아 있으면 중지를 차단한다 (§8 참조). 중지 버튼 클릭 전 프론트엔드도 `/api/env/status`로 상태 재확인 후 팝업 안내.
>
> **"재시작" 동작** _(v0.4 명시)_: 별도 `/restart` API 없음. `POST stop` → 완료 확인 → `POST start` 순차 호출. 클라이언트가 두 번 폴링해 상태 전이 감지.
>
> **"상태 새로고침" 동작** _(v0.4 명시, 기존 "재연결" 재명명)_: external 카드의 버튼명을 "상태 새로고침"으로 통일. `GET /api/env/status` 1회 즉시 호출 후 UI 갱신. Capture Studio의 "세션 재연결"과 혼동 방지.

**시작 명령** (필수 플래그 포함)

```bash
appium --address 127.0.0.1 --port 4723 \
  --allow-insecure=uiautomator2:adb_screen_streaming
```

> ⚠️ `--allow-insecure=uiautomator2:adb_screen_streaming` 없이 시작하면 Android MJPEG 미러링이 동작하지 않습니다. 이 플래그는 선택이 아니라 **필수**입니다.
>
> **바인딩 주소 `127.0.0.1` 확정** _(v0.7 정정, F3 해소)_: v0.6까지 기재된 `--address 0.0.0.0`은 Appium 서버를 LAN 전체에 노출시킨다. Appium은 인증이 없고 원격 코드 실행에 준하는 권한(앱 설치·파일 push/pull·셸 명령)을 열어주므로, 같은 네트워크의 누구나 조작할 수 있게 된다.
>
> | 항목 | 값 | 근거 |
> |---|---|---|
> | Appium 바인딩 | `127.0.0.1` | 대시보드·드라이버·Capture Studio가 모두 같은 머신(localhost)에서 접속. 외부 노출 이득 없음 |
> | 대시보드 바인딩 | `127.0.0.1` | §14 기존 정책과 동일 |
> | MJPEG 스트림(8093) | localhost 접근 | 대시보드가 프록시 |
>
> **원격 디바이스 팜이 필요해지면** `0.0.0.0`으로 되돌리는 것이 아니라 **별도 설계**가 필요하다 — 인증·TLS·네트워크 ACL·감사 로그가 함께 와야 하며 Phase 4 이후 주제다. 이 PRD 범위에서 `0.0.0.0` 바인딩은 금지한다.
>
> **드라이버 접속 URL 영향 없음**: `scripts/drivers/*.py`와 Capture Studio는 이미 `http://127.0.0.1:4723` / `http://localhost:4723`으로 접속하므로 이 변경으로 깨지는 소비자는 없다. 다만 **사용자가 터미널에서 `--address 0.0.0.0`으로 띄워 둔 external 서버도 그대로 인식**되어야 한다 — 대시보드는 `/status` 응답만 보고 판정하므로 external 감지 로직은 바인딩 주소와 무관하다.

**기능 목록**

| 항목 | 내용 |
|---|---|
| 상태 감지 | `GET /status` 200 여부 + PID 대조 → 3값 상태 판정 |
| 시작 | subprocess spawn → PID를 `state/env_session.json`에 저장 |
| 중지 | `managed` 상태에서만 SIGTERM. `external`이면 차단 |
| 비정상 종료 감지 | 3초 폴링 → PID 사라짐 감지 → 토스트 알림 + 로그 경로 표시 |
| 로그 | stdout을 `logs/appium_server.log`로 리다이렉트. `/api/env/appium/log`로 tail (최근 200줄) |
| 드라이버 확인 | `appium driver list --installed` → UiAutomator2 / XCUITest 설치 여부 표시 |
| 바이너리 탐색 | `shutil.which('appium')` 실패 시 `_find_appium_bin()` 후보 경로 순회. 미발견 시 설치 안내 |

### 5-2. Android 에뮬레이터 관리 (M2) — ⓑ 독립 경로

> **Appium 상태와 무관하게 동작한다** _(v0.7 정정, F1 해소)_. AVD 시작/중지 버튼은 Appium이 `stopped`·`error` 상태여도 활성이며, 잠금 뱃지를 표시하지 않는다. Android 섹션은 iOS 섹션과도 서로 독립이다.
>
> Appium 미실행 상태에서 에뮬레이터가 `running`이 되면, 대시보드는 차단 대신 **다음 액션 안내**를 노출한다 — "에뮬레이터 준비 완료. Capture Studio를 사용하려면 Appium을 시작하세요."

**등록된 AVD 목록 + 시작/중지**

| 항목 | 내용 |
|---|---|
| AVD 목록 | `config/devices.json`의 `android.emulator` 목록 표시 (기록된 것만) |
| 시작 | `_find_emulator_bin() + ['-avd', avd_name, '-no-snapshot-load']` |
| 부팅 완료 판정 | `adb -s <serial> shell getprop sys.boot_completed == 1` 3초 폴링, 타임아웃 180초 |
| 중지 | `adb -s <serial> emu kill` (serial 추적 필수). **가드: `is_capture_active("android")`** — Android Capture 세션만 확인하며 iOS 세션은 차단 사유가 아니다 _(v0.7, F6)_ |
| 바이너리 탐색 | `_find_emulator_bin()` — `$ANDROID_HOME/emulator/emulator` 등 후보 순회 |

**디바이스 추가/삭제 UI (US-3)**

- **추가 모달**: `emulator -list-avds` 결과로 드롭다운 자동 채우기 → 선택 시 OS 버전 자동 입력 → "등록" 클릭 → `config/devices.json` `android.emulator` 갱신
- **삭제**: 각 항목의 `✕` 버튼 → 확인 다이얼로그 → `config/devices.json`에서 제거
- **갱신 필드**: `avd`, `deviceName`, `platformVersion` — UI가 입력받는 것은 이 3개뿐
- **자동 채움 필드**: 신규 항목 등록 시 나머지는 §11 스키마 기본값으로 채운다 — `automationName: "UiAutomator2"`, `noReset: true`, `forceAppLaunch: true`, `shouldTerminateApp: true`, `mjpegServerPort: 8093`, `mjpegScalingFactor: 75`, `mjpegServerScreenshotQuality: 70`, `appPackage: ""`, `appActivity: ""`, `default: false`
- **UI 미노출 필드**: MJPEG caps 3종과 `appPackage`/`appActivity`는 모달에 노출하지 않는다. 조정이 필요하면 `devices.json`을 직접 편집한다 (M2 범위 밖)
- **`default` 전환**: 첫 항목은 자동으로 `default: true`. 이후 추가 항목은 `false`이며 목록에서 "기본으로 설정" 라디오로 전환한다. `default: true` 항목 삭제 시 남은 첫 항목이 승계하고, 마지막 1개 항목은 삭제할 수 없다 (400 last_device)
- **잠금**: 파이프라인 또는 Capture 세션 실행 중 `devices.json` 갱신 차단 + 안내 메시지

**실기기**: Phase 3 범위 (MVP에서는 "실기기는 Phase 3에서 지원 예정" 안내 텍스트만 표시)

### 5-3. iOS 시뮬레이터 관리 (M3) — ⓒ 독립 경로

> **Appium 상태와 무관하게 동작한다** _(v0.7 정정, F1 해소)_. 시뮬레이터 부팅/종료 버튼은 Appium이 `stopped`·`error` 상태여도 활성이다. iOS 섹션은 Android 섹션과도 서로 독립이다.

**등록된 시뮬레이터 목록 + 부팅/종료**

| 항목 | 내용 |
|---|---|
| 시뮬레이터 목록 | `config/devices.json`의 `ios.simulator` 목록 표시 |
| 부팅 | `subprocess.Popen(["xcrun", "simctl", "boot", udid])` — 비동기 실행, API 즉시 202 + `status: "starting"` 반환 _(v1.0 변경)_ |
| 부팅 완료 판정 | `xcrun simctl list devices --json` state == `Booted` 3초 폴링, 타임아웃 120초. "부팅 중..." 배지가 Booted 감지 시까지 유지됨 |
| 종료 | `xcrun simctl shutdown <udid>`. **가드: `is_capture_active("ios")`** — iOS Capture 세션만 확인하며 Android 세션은 차단 사유가 아니다 _(v0.7, F6)_ |

> **iOS XCUITest 세션 충돌**: 시뮬레이터 종료 버튼 클릭 시 Capture Studio **iOS** 세션 활성 여부 확인 → 활성이면 차단 + "Capture Studio 세션을 먼저 종료하세요" 안내. Android Capture 세션이 열려 있는 것만으로는 iOS 시뮬레이터 종료를 막지 않는다.

**디바이스 추가/삭제 UI (US-3)**

- **추가 모달**: `xcrun simctl list devices --json` 결과로 드롭다운 자동 채우기 → 선택 시 UDID 자동 입력 → "등록" 클릭 → `config/devices.json` `ios.simulator` 갱신
- **삭제**: 각 항목의 `✕` 버튼 → 확인 다이얼로그 → `config/devices.json`에서 제거
- **갱신 필드**: `deviceName`, `udid`, `platformVersion` — 나머지(`automationName: "XCUITest"`, `default`)는 §11 스키마 기본값으로 자동 채움. `default` 전환·삭제 규칙은 Android와 동일

**실기기**: Phase 3 범위

### 5-4. 디바이스 최소 보유 정책 _(v0.9 신설)_

섹션 성격에 따라 최소 보유 대수가 다르다. 근거는 **재등록 가능성의 비대칭**이다.

| 섹션 | 최소 대수 | 근거 |
|---|---|---|
| `android.emulator`, `ios.simulator` | **1대** | 항목은 시스템 검색 결과의 선택이다. 잘못된 항목은 "추가 후 삭제"로 무손실 교정 가능. 0대를 허용해 얻는 것이 없다 |
| `android.real_device`, `ios.real_device` | **0대** | 항목은 수기 입력이며 기기 미연결 시 재조회가 불가능하다. 0대를 막으면 잘못된 항목이 영구 고착되고, 실기기 미사용(Phase 3 이전)도 정상 상태다 |

**가상 기기 마지막 1대 — UI 비활성 + 툴팁**  
- ✕ 버튼을 `disabled` 처리하며 숨기지 않는다(기능 부재로 오인 방지)  
- 호버 시 툴팁: "마지막 기기입니다. 다른 기기를 먼저 추가하면 삭제할 수 있습니다."  
- 클릭 전에 이미 차단되므로 API `400 last_device`는 직접 API 호출 시에만 발생  

**실기기 마지막 1대 — 경고 다이얼로그 후 허용**  
- 확인 다이얼로그 제목: "마지막 실기기 삭제"  
- 본문: "{기기명}을(를) 삭제하면 {Android|iOS} 실기기 실행이 불가해집니다."  
- 삭제 후 섹션은 "등록된 실기기 없음 · 실기기 지원은 Phase 3 예정" 상태를 렌더한다  

**에러 코드 매핑 (UI 한국어 표시)**

| `error` 코드 | UI 표시 문구 |
|---|---|
| `last_device` | 마지막 기기는 삭제할 수 없습니다. 다른 기기를 먼저 추가하세요. |
| `capture_session_active` | Capture Studio 세션이 활성 상태입니다. 먼저 세션을 종료하세요. |
| `pipeline_running` | 파이프라인 실행 중에는 디바이스를 변경할 수 없습니다. |
| `device not found` | 이미 삭제된 기기입니다. 목록을 새로고침합니다. |

---

## 6. API 엔드포인트

> 네임스페이스: `/api/env/*` (기존 `/api/check/*`와 통일)
> 모든 응답: `{"ok": bool, "error": str|null, ...}` 기존 패턴 준수

### Appium (M1)

| 메서드 | 경로 | 요청 | 응답 (성공) | 실패 |
|---|---|---|---|---|
| `GET` | `/api/env/status` | — | `{ok, appium:{state,pid,port,version,drivers}, android:{...}, ios:{...}}` | 500 |
| `POST` | `/api/env/appium/start` | — | `{ok, pid, port}` 202 즉시 반환 | 409 already_running, 500 binary_not_found |
| `POST` | `/api/env/appium/stop` | — | `{ok}` | 403 capture_session_active, 403 external_process, 404 not_running, 409 pipeline_running, 500 |
| `GET` | `/api/env/appium/log` | `?lines=200` | `{ok, lines: [str]}` | 500 |

> `POST /api/env/appium/start`: subprocess spawn 후 **즉시 202 반환**. 클라이언트가 `/api/env/status`를 3초 폴링하여 `state: "managed"` 전환 감지.
>
> `POST /api/env/appium/stop`의 `403 capture_session_active`는 **`is_capture_active()` (인자 없음 = 전체 플랫폼)** 판정 결과다 _(v0.7, F6)_.

### Android (M2)

| 메서드 | 경로 | 요청 | 응답 (성공) | 실패 |
|---|---|---|---|---|
| `GET` | `/api/env/android/avds` | — | `{ok, avds: [{..., status, serial}]}` | 500 |
| `POST` | `/api/env/android/avd/start` | `{avd: str}` | `{ok, avd, status}` 202 | 409 already_running, 400 invalid_avd, 500 |
| `POST` | `/api/env/android/avd/stop` | `{avd: str}` | `{ok, status}` | 403 capture_session_active, 409 different_avd_running, 404 not_running, 500 |
| `GET` | `/api/env/android/list_system_avds` | — | `{ok, avds: [{avd, deviceName, platformVersion}]}` | 500 discovery_failed |
| `POST` | `/api/env/android/add` | `{mode:"emulator", deviceName, avd, platformVersion, default?}` | `{ok, entry}` | 400 invalid/discovery, 409 duplicate_avd |
| `POST` | `/api/env/android/remove` | `{mode, deviceName}` | `{ok: true}` | 400 last_device, 404 device not found |

> `avd` 파라미터는 `/api/env/android/list_system_avds` 결과 화이트리스트 대조 후 사용. `shell=False` + 리스트 인자 강제.
>
> **`POST /api/env/android/avd/start`에 Appium 상태 가드 없음** _(v0.7, F1)_. Appium이 `stopped`여도 202를 반환한다. `409 already_running`은 다른 **에뮬레이터**가 실행/부팅 중일 때만 발생한다.
>
> `POST /api/env/android/avd/stop`의 `403 capture_session_active`는 **`is_capture_active("android")`** 판정 결과다 — iOS Capture 세션은 이 API를 차단하지 않는다 _(v0.7, F6)_.

#### 디바이스 CRUD 계약 _(v0.8 최신 구현)_

> 가상 기기 추가는 시스템 검색 결과를 화이트리스트로 사용한다. Android는 `avd`, iOS는 `udid`가 중복 키이며 같은 값을 다시 등록하면 **409**로 파일을 변경하지 않는다. `platformVersion`은 검색 결과의 값을 저장한다. 첫 가상 기기는 자동으로 기본 기기가 된다.
>
> Android 에뮬레이터 등록 시 `UiAutomator2`, `noReset`, 앱 실행/종료 옵션과 MJPEG 포트·축소율·품질을 자동으로 채운다. MJPEG 포트는 기존 포트 다음 값으로 잡아 충돌을 피한다. add/remove는 해당 플랫폼 Capture 또는 파이프라인이 실행 중이면 설정 변경을 차단한다.

### iOS (M3)

| 메서드 | 경로 | 요청 | 응답 (성공) | 실패 |
|---|---|---|---|---|
| `GET` | `/api/env/ios/simulators` | — | `{ok, simulators: [{..., status, state}]}` | 500 |
| `POST` | `/api/env/ios/simulator/start` | `{udid: str}` | `{ok, simulator, udid, status}` 202 | 400 invalid_udid, 403 capture_session_active, 422 no_simulator_configured, 500 |
| `POST` | `/api/env/ios/simulator/stop` | `{udid: str}` | `{ok, status}` | 403 capture_session_active, 409 different_simulator_running, 500 |
| `GET` | `/api/env/ios/list_system_simulators` | — | `{ok, simulators: [{deviceName, platformVersion, udid, state}]}` | 500 discovery_failed |
| `POST` | `/api/env/ios/add` | `{mode:"simulator", deviceName, platformVersion, udid, default?}` | `{ok, entry}` | 400 invalid/discovery, 409 duplicate_udid/deviceName |
| `POST` | `/api/env/ios/remove` | `{mode, deviceName}` | `{ok: true}` | 400 last_device, 404 device not found |

> **경로명 정정** _(v0.8)_: v0.7의 `/simulator/boot`·`/simulator/shutdown`은 **구현되지 않았다**. 실제 경로는 Android(`/avd/start`·`/avd/stop`)와 대칭인 **`/simulator/start`·`/simulator/stop`**이다. 이 명명이 정본이며, 구 경로는 존재하지 않는다.
>
> **부팅 대상 식별** _(v0.8 최신)_: UI와 API는 `udid`를 정본으로 사용해 `xcrun simctl boot <udid>` / `shutdown <udid>`를 호출한다. 같은 이름의 Simulator가 여러 iOS 런타임에 있어도 선택한 한 대만 대상으로 한다. UUID 형식과 시스템 검색 화이트리스트를 등록 시 검증한다.
>
> **`POST /api/env/ios/simulator/start`에 Appium 상태 가드 없음** _(v0.7 F1 / v0.8 구현 확인)_. Appium이 `stopped`여도 202를 반환한다.
>
> `POST /api/env/ios/simulator/stop`의 `403 capture_session_active`는 **`is_capture_active("ios")`** 판정 결과다 — Android Capture 세션은 이 API를 차단하지 않는다 _(v0.7 F6 / v0.8 구현 확인)_.
>
> start/stop 계열 모두 `is_capture_active("android")` 또는 `is_capture_active("ios")`로 해당 플랫폼만 확인한다.

---

## 7. 상태 전이 규칙 _(v0.4 전체 재작성 — 5값 모델)_

### Appium 서버

| From | Trigger | Guard | To | Effect |
|---|---|---|---|---|
| `stopped` | ▶ 시작 버튼 클릭 | — | `starting` | subprocess spawn, 버튼 스피너 |
| `starting` | GET /status 200 + PID 일치 | 30초 이내 | `managed` | 중지·재시작 버튼 활성, 로그 표시 |
| `starting` | 30초 타임아웃 | — | `error` | 토스트, 로그 경로, 다시 시도 버튼 |
| `error` | 다시 시도 클릭 | — | `starting` | 재spawn |
| `managed` | ■ 중지 버튼 클릭 | `!is_capture_active() && !is_pipeline_active()` | `stopped` | SIGTERM, 버튼 초기화 |
| `managed` | ■ 중지 클릭 | `is_capture_active()` _(전체 플랫폼)_ | `managed` | 403, 팝업 안내 |
| `managed` | ■ 중지 클릭 | `is_pipeline_active()` | `managed` | 409, 팝업 안내 |
| `managed` | PID 소멸 감지 (폴링) | — | `error` | 토스트 "비정상 종료", 로그 경로 |
| `stopped` | GET /status 200 + PID 불일치 (폴링) | — | `external` | 안내 메시지, 중지 버튼 비활성 |
| `external` | ■ 중지 버튼 클릭 _(v1.0 신규)_ | `!is_capture_active() && !is_pipeline_active()` | `stopped` | lsof PID → SIGTERM, 버튼 초기화 |
| `external` | 중지 클릭 | `is_capture_active()` | `external` | 403, 팝업 안내 |
| `external` | 상태 새로고침 클릭 또는 폴링 | /status 실패 | `stopped` | 시작 버튼 복원 |
| **`error`** | **사용자 직접 해소 (다시 시도/탭 이탈)** | — | **`stopped`** | **로그 창 유지 — 1초 자동 해소 없음** |

### Android 에뮬레이터

| From | Trigger | Guard | To | Effect |
|---|---|---|---|---|
| `stopped` | ▶ 시작 클릭 | **Appium 상태 무관** _(v0.7, F1)_ · 다른 에뮬레이터 미실행 | `booting` | emulator spawn, 진행 바, 버튼 잠금 |
| `stopped` | ▶ 시작 클릭 | 다른 에뮬레이터 `running`/`booting` | `stopped` | 409 already_running, 안내 |
| `booting` | sys.boot_completed == 1 (폴링) | 180초 이내 | `running` | 중지 버튼 활성, serial 저장 |
| `booting` | 180초 타임아웃 | — | `error` | 빨강, 로그, 다시 시도 |
| `error` | 다시 시도 클릭 | — | `booting` | 재spawn |
| `running` | ■ 중지 클릭 | `!is_capture_active("android")` | `stopped` | adb emu kill, serial 제거 |
| `running` | ■ 중지 클릭 | `is_capture_active("android")` | `running` | 403, 팝업 안내 |
| any | Appium → stopped | — | **변화 없음** _(v0.7, F1)_ | 에뮬레이터 상태·버튼 모두 그대로. 잠금 뱃지 없음 |
| `booting` | 탭 이탈/새로고침 | — | `booting` | env_session.json 유지 → 복귀 시 스피너 복원 |

### iOS 시뮬레이터

| From | Trigger | Guard | To | Effect |
|---|---|---|---|---|
| `Shutdown` | ▶ 부팅 클릭 | **Appium 상태 무관** _(v0.7, F1)_ | `booting` | `Popen(simctl boot)` 즉시 반환, "부팅 중..." 배지 표시 _(v1.0: 비동기화)_ |
| `booting` | state == Booted (폴링) | 120초 이내 | `running` | 종료 버튼 활성, 배지 "실행 중" _(v1.0: "Booted"→"실행 중" 통일)_ |
| `booting` | 120초 타임아웃 | — | `error` | 빨강, 다시 시도 |
| `error` | 다시 시도 클릭 | — | `booting` | 재boot |
| `running` | ■ 종료 클릭 | `!is_capture_active("ios")` | `stopped` | xcrun simctl shutdown, 배지 "중지됨" _(v1.0: "Booted"/"Shutdown" → "실행 중"/"중지됨")_ |
| `running` | ■ 종료 클릭 | `is_capture_active("ios")` | `blocked` | 충돌 경고 화면 |
| `blocked` | 취소 클릭 | — | `running` | 목록 복귀, 변경 없음 |
| any | Appium → stopped | — | **변화 없음** _(v0.7, F1)_ | 시뮬레이터 상태·버튼 모두 그대로 |

**글로벌 규칙**
- 폴링 주기: 3초 (모든 상태 전이 감지)
- `error` 상태는 사용자 액션 없이 자동 해소되지 않음 _(v0.4 확정)_
- **에뮬레이터/시뮬레이터 시작은 Appium 상태와 독립이다** _(v0.7 정정, F1)_. v0.6의 "Appium `managed`/`external`일 때만 시작 버튼 활성" 규칙은 삭제됐다
- MVP: 에뮬레이터·시뮬레이터 동시 2개 이상 시작 불가 (409 already_running)
- **Android 섹션 · iOS 섹션 · Appium 섹션은 서로의 상태에 영향을 주지 않는다.** 세 섹션 간 게이팅은 존재하지 않으며, Appium 요구는 §7 하단 "실행 게이트"에서만 판정한다
- Capture 가드는 **플랫폼 인자를 받는다** _(v0.7, F6)_ — Appium 중지는 `is_capture_active()`, Android AVD 중지는 `is_capture_active("android")`, iOS 시뮬레이터 종료는 `is_capture_active("ios")` (§8 참조)

### 실행 게이트 판정 _(v0.7 개명 — 구 "환경 준비 완료(Ready) 판정", F1 해소)_

> **Ready는 "환경 설정 탭의 조작 가능 여부"가 아니라 "Capture Studio 세션 시작 / 파이프라인 실행 가능 여부"를 뜻한다.** 환경 설정 탭 안의 시작·중지 버튼은 Ready 판정과 무관하게 항상 조작 가능하다.

| 조건 | Android 실행 게이트 | iOS 실행 게이트 |
|---|---|---|
| Appium `managed`/`external` + Android 에뮬레이터 `running` | ✅ 통과 | ❌ iOS 디바이스 미준비 |
| Appium `managed`/`external` + iOS 시뮬레이터 `Booted` | ❌ Android 디바이스 미준비 | ✅ 통과 |
| Appium `managed`/`external` + 양쪽 모두 준비 | ✅ 통과 | ✅ 통과 |
| Appium `managed`/`external` + 디바이스 0개 | ❌ "디바이스를 하나 이상 시작하세요" | ❌ 동일 |
| **Appium `stopped`/`starting`/`error` + 디바이스 `running`** | ❌ **"Appium을 시작하세요"** — 단, **에뮬레이터는 계속 실행 중이며 중지 버튼도 활성** _(v0.7, F1)_ | ❌ 동일 |

> **판정 단위**: 실행 게이트는 **플랫폼 단위**로 평가한다. Android만 준비된 상태에서 iOS 파이프라인은 차단되지만 Android 파이프라인은 정상 실행된다. 상단 환경 상태바의 Appium ● / Android ● / iOS ● 는 이 플랫폼별 판정을 그대로 반영한다.
>
> **게이트 미충족 시 UI 동작** _(v0.7 명시)_: 환경 설정 탭의 어떤 컨트롤도 잠그지 않는다. 잠기는 것은 **Capture Studio 탭의 "세션 시작" 버튼**과 **파이프라인 탭의 "실행" 버튼** 두 개뿐이며, 각각 미충족 사유(Appium 미실행 / 디바이스 미준비)를 문구로 표시한다.

---

## 8. 프로세스 소유권 모델 _(v0.4 에뮬레이터 정책 추가)_

### Appium 소유권

```
대시보드 시작  →  PID 저장(state/env_session.json)  →  state: "managed"
외부 실행 감지 →  PID 없음 + /status 200           →  state: "external"  →  중지 버튼 비활성
중지됨         →  /status 실패 + PID 없음           →  state: "stopped"
```

**"외부 실행 중" 상태**: 대시보드는 SIGTERM을 금지하며 "상태 새로고침" 버튼으로 폴링만 재시도한다.  
**External + MJPEG 미확인**: `/api/check/mjpeg` 결과를 external 카드에도 노출해 `--allow-insecure` 플래그 누락을 경고한다.  
**대시보드 재시작 후 복구**: `env_session.json`의 PID 생존 여부로 `managed`/`stopped` 복원. `external` 복원은 폴링 첫 사이클에서 자동 감지.

### 에뮬레이터/시뮬레이터 소유권 _(v0.4 추가)_

> **의도된 결정**: 에뮬레이터·시뮬레이터는 Appium과 달리 소유권을 추적하지 않는다. 대시보드는 누가 시작했든 `adb -s <serial> emu kill` 및 `xcrun simctl shutdown <udid>`로 종료할 수 있다. 이는 USB 연결 에뮬레이터 등 외부에서 띄운 디바이스도 대시보드가 종료할 수 있음을 의미한다.
>
> 이 비대칭은 의도된 것이며 Phase 3(실기기 지원) 때 재검토한다.

**Android serial 추적 (단일 에뮬레이터 전제)**  
`emulator -avd <avd>` spawn 후 부팅 완료 판정 시점에 `adb devices`를 실행해 `emulator-` 접두어를 가진 첫 번째 serial을 저장. MVP는 단일 에뮬레이터이므로 이 단순화가 유효하다. 복수 에뮬레이터는 Phase 3. 외부 실행 에뮬레이터와의 serial 충돌 가능성은 §19 Known Limitation 참조.

### Capture 세션 가드 — 플랫폼별 분리 _(v0.7 신설, F6 해소)_

**문제**: v0.6까지 `is_capture_active()`는 플랫폼 구분 없는 단일 boolean이었다. 이 때문에 **iOS Capture 세션이 열려 있으면 무관한 Android 에뮬레이터 종료까지 차단**됐고, 그 반대도 마찬가지였다. Capture Studio 세션은 플랫폼별로 하나씩 존재할 수 있으므로 가드도 플랫폼을 알아야 한다.

**시그니처**

```
is_capture_active(platform: str | None = None) -> bool
```

| 인자 | 판정 대상 | 기본값 여부 |
|---|---|---|
| `None` (생략) | **모든 플랫폼** — Android·iOS 중 하나라도 활성이면 `True` | ✅ 기본값. 기존 호출부는 인자 없이 호출해도 v0.6과 동일하게 동작 (하위호환) |
| `"android"` | Android Capture 세션만 | — |
| `"ios"` | iOS Capture 세션만 | — |

**적용 규칙**

| 보호 대상 API | 호출 형태 | 근거 |
|---|---|---|
| `POST /api/env/appium/stop` | `is_capture_active()` | Appium 서버는 **단일 프로세스로 양 플랫폼 세션을 공유**한다(§5-1 아키텍처 결정). 어느 쪽 세션이든 살아 있으면 종료 시 orphan 발생 |
| `POST /api/env/android/avd/stop` | `is_capture_active("android")` | Android 에뮬레이터 종료는 iOS 세션에 아무 영향을 주지 않는다 |
| `POST /api/env/ios/simulator/stop` | `is_capture_active("ios")` | iOS 시뮬레이터 종료는 Android 세션에 아무 영향을 주지 않는다 |
| `POST /api/env/android/{add,remove}` | `is_capture_active("android")` | Android 설정 변경은 Android Capture 중 차단한다. 파이프라인도 별도 확인한다 |
| `POST /api/env/ios/{add,remove}` | `is_capture_active("ios")` | iOS 설정 변경은 iOS Capture 중 차단한다. 파이프라인도 별도 확인한다 |
| `POST /api/env/android/avd/start` · `/api/env/ios/simulator/start` | `is_capture_active("android")` / `("ios")` | 무관한 플랫폼 세션은 시작을 차단하지 않는다 |

**판정 근거 데이터**: `state/capture_session.json`. 세션 레코드의 플랫폼 필드(Android 세션은 `app_package`/`app_activity`, iOS 세션은 `bundle_id` 키를 사용 — CLAUDE.md Capture Studio 참조)로 플랫폼을 식별한다. 세션 파일에 플랫폼을 명시하는 필드가 없으면 **보수적으로 `True`를 반환**한다 (차단 쪽으로 기운다).

**하위호환**: 인자 없는 기존 호출부(`utils/state.py:63` 소비 지점)는 수정 없이 그대로 동작한다. 구현은 기본값 파라미터 추가이며 시그니처 파괴 변경이 아니다.

---

## 9. 디바이스 추가/삭제 UI 상세 (US-3)

### Android AVD 추가 모달

```
[ ＋ AVD 추가 ] 버튼 클릭 →

┌─────────────────────────────┐
│  Android 에뮬레이터 추가    │
│                             │
│  AVD 선택: [드롭다운 ▼]     │  ← emulator -list-avds 결과
│  (Pixel_7_Android15)        │
│                             │
│  이름:    [자동 채우기]      │
│  Android: [자동 채우기]      │
│                             │
│  [취소]           [등록]    │
└─────────────────────────────┘
```

### iOS 시뮬레이터 추가 모달

```
[ ＋ 시뮬레이터 추가 ] 버튼 클릭 →

┌─────────────────────────────┐
│  iOS 시뮬레이터 추가         │
│                             │
│  기기 선택: [드롭다운 ▼]    │  ← xcrun simctl list --json 결과
│  (iPhone 18 Pro)            │
│                             │
│  iOS:  [자동 채우기]         │
│  UDID: [자동 채우기]         │
│                             │
│  [취소]           [등록]    │
└─────────────────────────────┘
```

### 삭제

- 각 디바이스 카드 우측 `✕` 버튼
- 확인 다이얼로그: "Pixel_7_Android15을 목록에서 삭제하시겠습니까? (에뮬레이터 자체는 삭제되지 않습니다)"
- 파이프라인/Capture 세션 실행 중 → 잠금(423) + "실행이 완료된 후 변경하세요" 안내

---

## 10. 상태 표시 규칙

| 상태 | 색상 | 아이콘 | 버튼 활성 |
|---|---|---|---|
| 실행 중 (managed/running) | 초록 (#22c55e) | ● | 중지 (Appium: + 재시작). iOS: "실행 중", Android: "실행 중" _(v1.0: Booted→실행 중 통일)_ |
| 외부 실행 중 (external) | 청록 점선 (#06b6d4) | ◉ | **중지 가능** (빨간 테두리 버튼) + 상태 새로고침 _(v1.0: 중지 불가 → 중지 가능)_ |
| 시작 중 / 부팅 중 (starting/booting) | 노랑 (#eab308) | ◌ 스피너 | 모두 잠김 |
| 중지됨 / Shutdown (stopped) | 회색 (#6b7280) | ○ | 시작 / 부팅 |
| 오류 / 타임아웃 (error) | 빨강 (#ef4444) | ✕ | 다시 시도 + 로그 보기 |
| Capture 세션 충돌 (blocked) | 빨강 (#ef4444) | 차단됨 | Capture Studio 이동 + 취소 |
| ~~Appium 미실행 잠금 (locked)~~ | — | — | **v0.7에서 삭제** _(F1)_ — 디바이스 카드에 잠금 상태를 표시하지 않는다 |

> **`locked` 상태 삭제** _(v0.7, F1 해소)_: Appium 미실행은 더 이상 디바이스 컨트롤을 잠그지 않으므로 🔒 뱃지를 표시하지 않는다. 대신 **Capture Studio 탭의 "세션 시작" 버튼과 파이프라인 탭의 "실행" 버튼**에만 비활성 상태와 사유 문구를 적용한다(§7 실행 게이트).
>
> 디바이스 카드에는 잠금 대신 **다음 액션 안내**를 표시한다 — 에뮬레이터가 `running`인데 Appium이 `stopped`이면 "에뮬레이터 준비 완료. Capture Studio를 사용하려면 Appium을 시작하세요."

---

## 11. 프로세스 수명주기 및 상태 영속화

### `state/env_session.json` 스키마

```json
{
  "appium": {
    "pid": 12345,
    "port": 4723,
    "managed_by": "dashboard",
    "started_at": "2026-09-12T10:00:00",
    "status": "managed"
  },
  "android": {
    "avd": "Pixel_7_Android15",
    "pid": 23456,
    "serial": "emulator-5554",
    "status": "running",
    "started_at": "2026-09-12T10:02:00"
  },
  "ios": {
    "udid": "E73939EF-...",
    "deviceName": "iPhone 18 Pro",
    "status": "booted",
    "started_at": "2026-09-12T10:03:00"
  }
}
```

> `status` 필드는 대시보드 재시작 후 스피너 복원에 사용 (§7 "부팅 중 이탈 복원").  
> `started_at` 기반 스탈레 정책: **없음** (MVP). PID 생존 여부만으로 상태 복원. 24시간 초과 세션은 Phase 3에서 다룸.

**`config/devices.json` 스키마 변경** _(v0.4 추가 B1 해소 / v0.6 확정 — 키 명칭·케이스 규칙)_

#### 키 명칭 규칙 _(v0.6 확정, R3 해소)_

> **확정**: 디바이스 모드 키는 **단수형**을 사용한다 — `android.emulator`, `android.real_device`, `ios.simulator`, `ios.real_device`.
>
> **근거**: 이 키는 코드에서 `devices[platform][mode]` 형태로 `--mode` 인자와 1:1 대응해 조회된다. `--mode emulator`가 `emulators` 키를 찾는 불일치를 만들지 않기 위해 단수형을 유지한다.
>
> | 소비 지점 | 참조 |
> |---|---|
> | `scripts/drivers/android_driver.py:35` | `devices["android"][mode]` |
> | `scripts/02_generate.py:388` | `devices["android"][PLATFORM_MODE]` |
> | `scripts/02_generate.py:429` | `devices["ios"][PLATFORM_MODE]` |
> | `scripts/01_analyze.py:106` | `--mode emulator\|real_device\|simulator` choices |
> | `agents/dashboard/routes/*` | 대시보드 디바이스 조회 |
>
> v0.4~v0.5 초안의 `emulators`/`simulators`(복수)는 **오류**였다. 코드와 CLAUDE.md 모두 단수형을 쓴다. 이번 v0.6에서 PRD 전체를 단수형으로 정정한다.
>
> **변경되는 것은 값의 형태(단일 객체 → 배열)뿐이며, 키 이름은 그대로 유지된다.**

#### 케이스 규칙 _(v0.6 확정, R9 해소)_

> `devices.json`의 camelCase와 내부 state의 snake_case 혼용은 **실수가 아니라 의도된 역할 분리**다. 통일하지 않는다.
>
> | 대상 | 케이스 | 이유 |
> |---|---|---|
> | `config/devices.json` 필드 | **camelCase** | 값이 Appium capability 이름 그대로 드라이버에 전달됨. `deviceName`, `platformVersion`, `mjpegServerPort` 등은 Appium 프로토콜이 요구하는 철자이므로 변경 불가 |
> | `state/pipeline.json`, `state/capture_session.json` | **snake_case** | 제품 내부 state. Appium에 전달되지 않음 |
> | Python 변수·함수·API 요청 필드 | **snake_case** | PEP 8 |
>
> **예외 규칙**: `devices.json` 안에서도 Appium capability가 **아닌** 제품 전용 메타 필드는 snake_case를 쓴다 — 현재 `default`(bool) 하나뿐이며 Phase 3에서 `wifi_ip`, `team_id`가 추가된다. 즉 "Appium에 그대로 넘어가는 필드 = camelCase, 대시보드만 읽는 필드 = snake_case"가 판정 기준이다.
>
> 디바이스 항목을 caps로 만들 때는 제품 전용 메타 필드를 **제거한 뒤** Appium에 전달한다.

#### MJPEG caps 위치 _(v0.6 확정, R2 해소)_

> **확정**: MJPEG 관련 3개 capability(`mjpegServerPort`, `mjpegScalingFactor`, `mjpegServerScreenshotQuality`)는 **각 `android.emulator` 배열 항목 안에 flat하게** 둔다. 별도 중첩 객체(`mjpeg: {...}`)로 묶지 않는다.
>
> **근거**: 세 값은 Appium capability 그대로이므로 항목 전체를 `.copy()` 해서 caps로 넘기는 기존 코드 경로를 그대로 쓸 수 있다. 중첩하면 caps 조립 시 평탄화 로직이 추가로 필요하다.
>
> **현재 문제 (이중 분산)**: 같은 값이 두 곳에 있고 실제로는 devices.json이 무시되고 있다.
>
> | 위치 | 값 | 실제 동작 |
> |---|---|---|
> | `config/devices.json` L11–13 | 8093 / 75 / 70 | Capture Studio에서 **읽히지 않음** |
> | `agents/dashboard/routes/capture.py` L128–130 | 8093 / 75 / 70 | 하드코딩 값이 실제로 사용됨 |
>
> → **M2.0 마이그레이션에서 `capture.py` 하드코딩을 제거**하고 `devices.json`의 `default: true` 항목을 읽도록 변경한다 (아래 M2.0 항목 참조).

#### 스키마 (v0.6 확정형)

```json
{
  "android": {
    "emulator": [
      {
        "avd": "Pixel_7_Android15",
        "default": true,
        "deviceName": "Android Emulator",
        "platformVersion": "15.0",
        "automationName": "UiAutomator2",
        "noReset": true,
        "forceAppLaunch": true,
        "shouldTerminateApp": true,
        "mjpegServerPort": 8093,
        "mjpegScalingFactor": 75,
        "mjpegServerScreenshotQuality": 70,
        "appPackage": "",
        "appActivity": ""
      }
    ],
    "real_device": []
  },
  "ios": {
    "simulator": [
      {
        "udid": "E73939EF-741D-4A72-BEA7-97D31B15719A",
        "default": true,
        "deviceName": "iPhone 18 Pro",
        "platformVersion": "27.0",
        "automationName": "XCUITest"
      }
    ],
    "real_device": []
  }
}
```

**필드 정의 — `android.emulator[]`**

| 필드 | 케이스 | 필수 | 출처 / 의미 |
|---|---|---|---|
| `avd` | camel(고유명) | ✅ | AVD 이름. `emulator -list-avds` 화이트리스트 대조 대상. 배열 내 **유일 키** |
| `default` | snake | ✅ | 제품 전용 메타. `true`인 항목이 파이프라인·Capture 기본값. 배열 전체에서 **정확히 1개**만 `true` |
| `deviceName` | camel | ✅ | Appium capability |
| `platformVersion` | camel | ✅ | Appium capability |
| `automationName` | camel | ✅ | `UiAutomator2` 고정 |
| `noReset` | camel | ✅ | Appium capability |
| `forceAppLaunch` | camel | ✅ | Appium capability |
| `shouldTerminateApp` | camel | ✅ | Appium capability |
| `mjpegServerPort` | camel | ✅ | 기본 8093. 미러링 필수 |
| `mjpegScalingFactor` | camel | ✅ | 기본 75 |
| `mjpegServerScreenshotQuality` | camel | ✅ | 기본 70 |
| `appPackage` | camel | ⬜ | **선택적 오버라이드**. 빈 문자열이면 `test_data.json`의 값을 사용 |
| `appActivity` | camel | ⬜ | **선택적 오버라이드**. 빈 문자열이면 `test_data.json`의 값을 사용 |

> ⚠️ **`appPackage`/`appActivity` 우선순위 규칙** _(v0.6 신설)_: 현재 이 두 값의 source of truth는 `config/test_data.json`(`app.android.package` / `app.android.activity`)이며, `android_driver.py:37`과 `02_generate.py:390`이 그곳에서 읽는다. devices.json에 필드를 추가하는 것은 **디바이스별 오버라이드**를 위한 것이지 source of truth 이전이 아니다.
>
> **해석 순서**: `devices.json`의 값이 **비어 있지 않으면** 그 값을 쓰고, 비어 있으면 `test_data.json`을 쓴다. 신규 등록 항목의 기본값은 `""`이므로 기존 동작이 그대로 보존된다. UI의 디바이스 추가 모달은 이 두 필드를 **노출하지 않는다** (M2 범위 밖 — §5-2 갱신 필드 참조).

**필드 정의 — `ios.simulator[]`**

| 필드 | 케이스 | 필수 | 의미 |
|---|---|---|---|
| `udid` | camel | ✅ | 배열 내 **유일 키**. `^[0-9A-F-]{36}$` 검증 후 `xcrun simctl list` 대조 |
| `default` | snake | ✅ | 제품 전용 메타. 정확히 1개만 `true` |
| `deviceName` | camel | ✅ | Simulator 이름. XCUITest 세션에 필수 |
| `platformVersion` | camel | ✅ | Appium capability |
| `automationName` | camel | ✅ | `XCUITest` 고정 |

> `bundleId`는 devices.json이 아니라 `test_data.json`(`app.ios.bundle_id`)에서 읽는다 (`02_generate.py:431`). Android와 동일 원칙.

#### M2.0 마이그레이션 태스크 _(v0.6 신설)_

M2 착수 전 선행 작업. 순서대로 수행하며 각 단계 후 `python3 -m py_compile scripts/*.py` + `02_generate --strict-locators` 회귀 확인.

| # | 태스크 | 대상 파일 | 완료 조건 |
|---|---|---|---|
| **M2.0-1** | 단일 객체 → 배열 변환 스크립트. 기존 `emulator`/`simulator` 객체를 1개짜리 배열로 감싸고 `default: true` 부여. `real_device` 객체는 `udid`가 빈 문자열이면 `[]`로, 값이 있으면 1개짜리 배열로 변환 | `config/devices.json` | 변환 후 파일이 §11 스키마와 일치. 원본은 `config/devices.json.bak`으로 백업 |
| **M2.0-2** | 배열에서 `default: true` 항목을 반환하는 공용 리더 추가. 배열이 아닌 dict가 들어오면 그대로 반환하는 하위호환 분기 포함 | `agents/dashboard/utils/system.py` | 단일 함수로 4개 소비 지점이 모두 대체됨 |
| **M2.0-3** | 소비 지점 4곳을 공용 리더 호출로 교체 | `scripts/drivers/android_driver.py:35`, `scripts/02_generate.py:388`, `scripts/02_generate.py:429`, `agents/dashboard/routes/*` | `devices[platform][mode]` 직접 인덱싱이 코드베이스에서 0건 |
| **M2.0-4** | **`capture.py` MJPEG 하드코딩 제거** _(R2 해소)_. L128–130의 `75`/`70` 리터럴과 `mjpeg_port` 기본값 `8093`을 `devices.json`의 `default: true` 항목에서 읽도록 변경 | `agents/dashboard/routes/capture.py:128-130` | `grep -n "75\|70\|8093" capture.py`에 MJPEG 관련 리터럴 0건. devices.json에서 포트를 바꾸면 Capture Studio 미러링 포트가 실제로 따라 바뀜 |
| **M2.0-5** | 제품 전용 메타 필드(`default`) 제거 후 caps 조립. `default` 키가 Appium으로 전달되지 않음 | 공용 리더 | Appium 세션 시작 시 unknown capability 경고 없음 |

> **M2.0-4 검증 방법**: `devices.json`의 `mjpegServerPort`를 8093 → 8094로 임시 변경 → Capture Studio Android 세션 시작 → `mjpeg_url`이 `http://localhost:8094`로 반환되면 통과. 확인 후 8093으로 복구.

> **복수 에뮬레이터 동시 시작 정책**: MVP에서는 **한 번에 하나만** (`running` 또는 `booting` 상태의 에뮬레이터가 있으면 다른 항목의 `start` API가 `409 already_running` 반환).

### 대시보드 종료 시 정책

에뮬레이터/시뮬레이터는 **종료하지 않음** (재부팅 비용이 크므로). PID 정보는 파일에 유지. Appium도 종료하지 않고 다음 기동 시 `external`로 재인식. `serve.py`에 lifespan shutdown 훅 추가하여 `env_session.json` flush.

### subprocess stdout 처리

모든 long-running subprocess (Appium, 에뮬레이터)의 stdout은 **파일로 리다이렉트** (파이프 버퍼 블로킹 방지):
- Appium: `logs/appium_server.log`
- 에뮬레이터: `logs/android_emulator.log`

### `devices.json` 원자적 저장 정책 _(v0.7 F5 신설 → v0.8 확정, 부분 구현)_

> **v0.8 상태 변경**: US-3 디바이스 추가/삭제 API가 구현되면서 `devices.json` **쓰기 경로가 실제로 생겼다.** v0.7에서 "쓰기 경로가 없으므로 Future Work"로 미뤘던 근거가 소멸했으므로, 이 절을 Future Work에서 **확정 정책**으로 승격한다.
>
> 모든 `devices.json` 쓰기는 **반드시 `agents/dashboard/utils/state.py`의 `save_devices_json()`을 경유한다.** `config/devices.json`에 직접 `write_text()`하는 경로를 새로 만들지 않는다.

**저장 절차 (확정)**

1. 쓰기 **전** 스키마 검증 → 실패 시 `ValueError` → 라우터가 **400**으로 변환하고 **파일은 건드리지 않는다**
2. `config/devices.json.tmp`에 전량 기록
3. `Path.replace()`로 원자적 교체 — 같은 파일시스템이므로 `rename(2)` 원자성이 보장된다
4. 실패 시 원본 `devices.json`이 그대로 보존된다

**3개 항목 구현 현황**

| 항목 | 상태 | 내용 |
|---|---|---|
| **원자적 파일 교체** | ✅ **구현 완료** | `.json.tmp` 기록 → `Path.replace()` 교체. 저장 도중 프로세스가 죽어도 `devices.json`이 잘린 채 남지 않는다. 이 파일은 드라이버·`02_generate`·Capture Studio가 함께 읽는 단일 설정 파일이므로 손상 반경이 가장 크다 |
| **스키마 검증** | ⚠️ **부분 구현** | 각 플랫폼/모드 섹션에서 **`default: true` 2개 이상이면 `ValueError`** — 이 한 가지만 검증한다. **미구현**: 필수 필드 존재 여부, 유일 키(`avd`/`udid`) 중복 없음, `default: true`가 **정확히 1개**인지(현재는 0개도 통과) |
| **파일 잠금** | ⚠️ **부분 구현** | 저장 함수의 write/replace 구간은 `fcntl.flock`으로 보호한다. 다만 API의 load→modify→save 전체 트랜잭션을 잠그지는 않아 두 탭의 완전 동시 편집은 lost update 가능성이 남는다 |

> **`fsync` 적용 완료**: 임시 파일을 flush·`os.fsync()`한 뒤 `Path.replace()`로 교체한다. 저장 중 프로세스 종료와 전원 장애에 대한 내구성을 높인다.
>
> **백업 정책**: M2.0-1이 만드는 `config/devices.json.bak`은 **일회성 마이그레이션 백업**이며 매 저장 시 갱신하는 롤링 백업이 아니다. 롤링 백업 필요 여부는 위 3항목이 모두 완료된 후 재평가한다.
>
> **완료 기준**: 저장 중 강제 종료(SIGKILL) 후에도 `devices.json`이 항상 유효한 JSON이며 스키마를 만족한다. → 원자적 교체로 충족. 스키마 검증·파일 잠금 항목은 §15-7에서 추적한다.

---

## 12. 기존 자산 재사용 맵

신규 구현 전 반드시 확인. 중복 구현 금지.

| 기존 자산 | 실제 위치 _(v0.4 경로 정정)_ | 처리 방침 |
|---|---|---|
| Appium 상태 확인 | `routes/api.py` `/api/check/appium` | `/api/env/status` 내부에서 재사용 (기존 엔드포인트 유지) |
| MJPEG 포트 확인 | `routes/api.py` `/api/check/mjpeg` | 재사용. external 상태 카드에도 경고 노출 |
| Appium 상태 함수 | `utils/system.py:21` `check_appium_status()` | PID 대조 로직만 추가해 5값 상태 판정 |
| Capture 세션 가드 | `utils/state.py:63` `is_capture_active()` | **확장** _(v0.7, F6)_ — `platform: str \| None = None` 기본값 파라미터 추가. 인자 없는 기존 호출부는 수정 불필요. Appium 중지는 인자 없이, AVD 중지는 `"android"`, 시뮬레이터 종료는 `"ios"`로 호출 (§8) |
| 파이프라인 실행 가드 | `utils/state.py` `is_pipeline_active()` | Appium 중지·devices.json 갱신에 적용 |
| adb 바이너리 탐색 | `shared.py:63` `_find_adb_bin()` | 동일 패턴으로 `_find_emulator_bin()`, `_find_appium_bin()` 추가 |
| 디바이스 파싱 함수 | `utils/system.py` `check_android_devices()`, `check_ios_simulators()` | **`utils/device_utils.py` 신규 생성 불필요** — `utils/system.py` 확장 사용 |
| 로그 tail | `shared.py SCRIPT_MAP` + `/api/run_log` | Appium 로그에 동일 패턴 적용 |
| Appium 에러 메시지 | `routes/capture.py` | "터미널에서 appium 실행" 안내 → "환경 설정 패널에서 시작" 안내로 교체 |
| MJPEG caps 하드코딩 | `routes/capture.py:128-130` | **제거** — M2.0-4에서 `devices.json`의 `default: true` 항목을 읽도록 교체. 현재 devices.json 값이 무시되는 이중 분산 상태 |
| 디바이스 항목 리더 | — | **신규** — `utils/system.py`에 `default: true` 항목 반환 함수 추가 (M2.0-2). 4개 소비 지점이 공유 |
| 신규 라우터 | — | `routes/env.py` + `serve.py`에 `app.include_router(env_router, prefix="/api")` |

> ⚠️ `utils/device_utils.py` **신규 생성 금지** — 기능이 `utils/system.py`와 중복됨. 중복 구현 방지 원칙 적용.

---

## 13. 에러 처리 카탈로그

| 에러 원인 | 감지 방법 | UI 메시지 | 복구 액션 |
|---|---|---|---|
| `appium` 바이너리 없음 | `shutil.which` 실패 | "Appium이 설치되지 않았습니다. `npm i -g appium`을 실행하세요." | 설치 명령 복사 버튼 |
| 포트 4723 점유 (외부) | `/status` 200 + PID 불일치 | "외부에서 실행 중인 Appium을 감지했습니다." | 없음 (외부 종료 유도) |
| UiAutomator2 미설치 | `appium driver list --installed` | "UiAutomator2 드라이버가 없습니다. `appium driver install uiautomator2`" | 설치 명령 복사 |
| XCUITest 미설치 | 동일 | "XCUITest 드라이버가 없습니다. `appium driver install xcuitest`" | 설치 명령 복사 |
| `emulator` 바이너리 없음 | `_find_emulator_bin()` 실패 | "Android 에뮬레이터를 찾을 수 없습니다. ANDROID_HOME을 확인하세요." | — |
| AVD 목록 비어 있음 | `emulator -list-avds` 빈 결과 | "등록된 AVD가 없습니다. Android Studio > Virtual Device Manager에서 생성하세요." | — |
| 에뮬레이터 부팅 타임아웃 | 180초 초과 | "에뮬레이터 부팅 시간이 초과됐습니다." | 로그 보기 + 다시 시도 |
| `xcrun` 없음 | `shutil.which` 실패 | "Xcode Command Line Tools가 필요합니다. `xcode-select --install`" | 설치 명령 복사 |
| 시뮬레이터 부팅 타임아웃 | 120초 초과 | "시뮬레이터 부팅 시간이 초과됐습니다." | 로그 보기 + 다시 시도 |
| iOS Capture 세션 활성 중 시뮬레이터 종료 시도 | `is_capture_active("ios")` _(v0.7)_ | "iOS Capture Studio 세션이 활성 상태입니다. 먼저 세션을 종료하세요." | Capture Studio로 이동 |
| Android Capture 세션 활성 중 에뮬레이터 종료 시도 | `is_capture_active("android")` _(v0.7)_ | "Android Capture Studio 세션이 활성 상태입니다. 먼저 세션을 종료하세요." | Capture Studio로 이동 |
| Capture/파이프라인 실행 중 Appium 중지 시도 | `is_capture_active()` _(전체 플랫폼)_ / `is_pipeline_active()` | "Capture 세션 또는 파이프라인이 실행 중입니다. 먼저 종료하세요." | 해당 탭으로 이동 |
| `devices.json` 갱신 잠금 | `is_pipeline_active() or is_capture_active()` _(전체 플랫폼)_ | "파이프라인/Capture 세션 실행 중에는 디바이스를 변경할 수 없습니다." | — |
| Appium 미실행 상태에서 Capture 세션 시작 시도 _(v0.7, F1)_ | Appium `stopped`/`starting`/`error` | "Appium 서버가 실행 중이 아닙니다. 환경 설정에서 시작하세요." — **에뮬레이터는 종료하지 않는다** | 환경 설정 탭으로 이동 |

---

## 14. 보안 및 실행 제약

- **단일 사용자 로컬 환경 전제**: 대시보드는 `127.0.0.1` 바인딩 전제. 향후 `0.0.0.0` 변경 금지
- **Appium 서버도 `127.0.0.1` 바인딩** _(v0.7 신설, F3)_: 대시보드가 spawn하는 Appium은 `--address 127.0.0.1`로 시작한다. Appium은 인증이 없고 앱 설치·파일 push/pull·셸 실행 권한을 노출하므로 LAN 바인딩은 동일 네트워크의 임의 사용자에게 기기 제어권을 주는 것과 같다. 원격 디바이스 팜 요구가 생기면 `0.0.0.0` 복귀가 아니라 인증·TLS·ACL을 포함한 **별도 설계**로 다룬다 (Phase 4 이후)
- **인자 화이트리스트**: `avd` 이름은 `emulator -list-avds` 결과에 있는 값만 허용. `udid`는 UUID 형식 검증 후 `xcrun simctl list` 결과 대조
- **`shell=False` 강제**: 모든 subprocess는 리스트 인자 방식. 문자열 셸 명령 금지
- **파일 쓰기 제약**: `config/devices.json` 갱신은 파이프라인/Capture 세션 비활성 시에만
- **macOS 전용**: `xcrun`, `simctl`, iOS 관련 기능은 macOS 전용. Phase 3 CI/CD 연동 시 재검토

---

## 15. 성공 지표 및 완료 기준

### 15-1. 정량 KPI _(v0.4 측정 조건 구체화)_

| 지표 | 목표 | 측정 조건 |
|---|---|---|
| 대시보드 접속 → Capture 세션 시작까지 터미널 명령 수 | **0개** | **§2-1 ②구간(구축 완료 후 일상 사용)만 측정** _(v0.7 명확화, F2)_. ①최초 환경 구축(Appium·드라이버·Xcode CLT·Android SDK 설치, AVD 생성)은 개발자/온보딩 담당 몫이며 이 지표에 포함하지 않는다. 측정 시작 조건: `appium driver list --installed`에 uiautomator2(또는 xcuitest)가 보이고 AVD가 1개 이상 등록된 머신 |
| 동일 구간 소요 시간 | **5분 이내** | Appium 시작(~30초) + 에뮬레이터 스냅샷 부팅(~60초) 기준. 콜드 부팅(스냅샷 없음, ~3분) 포함 시 최대 5분. iOS 시뮬레이터는 Booted 상태 유지 가정 |
| Android 대시보드 기동 Appium으로 MJPEG 미러링 성공률 | **100%** | n=10회 시도. `--allow-insecure` 플래그 포함 검증 |
| 상태바 표시 ↔ 실제 상태 불일치 | **0건** | 시작/종료 각 10회 반복 |
| US-2 External 인계 정확도 | **100%** | 외부 Appium 감지 시 10회 중 10회 external로 표시, SIGTERM 0회 |
| US-3 JSON 미편집 디바이스 추가·삭제 성공률 | **100%** | 플랫폼별 추가 모달과 항목별 삭제 UI 구현. 브라우저 E2E로 검색·자동 입력·등록 계약·행 동작을 검증 (§4, §15-7) |

### 15-2. 해피패스 완료 기준

- [ ] 터미널 없이 대시보드에서 Appium 서버를 시작할 수 있다
- [ ] Appium 시작 후 Android MJPEG 미러링이 즉시 동작한다 (플래그 포함 검증)
- [ ] 등록된 AVD를 대시보드에서 시작하고 부팅 완료를 스피너로 확인할 수 있다
- [ ] 등록된 iOS 시뮬레이터를 대시보드에서 부팅하고 Booted 상태를 확인할 수 있다
- [ ] `devices.json`을 직접 편집하지 않고 UI에서 디바이스를 추가·삭제할 수 있다
- [ ] 환경 준비 완료 상태에서 Capture Studio 세션을 바로 시작할 수 있다

### 15-3. 실패 경로 완료 기준

- [ ] `appium` 미설치 시 크래시 없이 설치 안내 메시지를 표시한다
- [ ] 포트 4723이 외부 프로세스에 점유된 상태에서 "외부 실행 중"으로 인계하고 중지 버튼을 비활성화한다
- [ ] UiAutomator2/XCUITest 드라이버 미설치를 세션 시작 전에 감지해 표시한다
- [ ] 에뮬레이터 부팅이 180초를 초과하면 타임아웃 상태로 전이하고 로그 경로를 노출한다
- [ ] Capture Studio 세션 활성 중 시뮬레이터 종료를 차단하고 안내를 표시한다
- [ ] 파이프라인/Capture 실행 중 `devices.json` 갱신을 차단한다

### 15-4. 회귀 방지 기준

- [ ] 기존 `/api/check/appium`, `/api/check/mjpeg` 소비자가 깨지지 않는다
- [ ] `is_capture_active()` 가드가 계속 동작한다
- [ ] `config/devices.json` 자동 갱신 후 `02_generate --strict-locators`가 정상 동작한다
- [ ] 대시보드 재시작 후 `managed` 상태 Appium 프로세스를 중지할 수 있다
- [ ] 부팅 중 이탈(탭 닫기/새로고침) 후 재접속 시 `starting` 상태가 올바르게 복원된다 (`env_session.json` 기반)

### 15-5. v0.7 아키텍처 리뷰 반영 검증 기준 _(F1·F3·F6 코드 반영 판정 — v0.8 실측 반영)_

> **판정 범례**: ✅ 코드 실측으로 확인 · ⏳ 코드는 반영됐으나 **실기 런타임 검증 대기**(Appium 서버·디바이스 연결 필요) · ❌ 미충족

- [x] ✅ **F1** — Appium이 `stopped` 상태에서 Android AVD 시작 버튼이 활성이고, 클릭 시 202를 반환한다 — `routes/env.py` `post_avd_start()`에 Appium 상태 가드 **없음**. 부팅 완료는 ⏳ 실기 검증 대기
- [x] ✅ **F1** — Appium이 `stopped` 상태에서 iOS 시뮬레이터 시작 버튼이 활성이다 — `post_simulator_start()`에 Appium 상태 가드 **없음**. 부팅 완료는 ⏳ 실기 검증 대기
- [x] ✅ **F1** — Appium을 중지해도 이미 `running`인 에뮬레이터의 상태 표시와 중지 버튼이 유지된다 (잠금 뱃지 미표시) — `dashboard.html`에 디바이스 카드용 `locked` 뱃지 로직 **없음**
- [x] ✅ **F1** — Appium 미실행 시 비활성화되는 것은 파이프라인 실행 버튼(`dashboard.html` — `btn-run-all`·`btn-analyze`·`btn-generate`·`btn-lint`·`btn-execute`·`btn-heal`)과 Capture "세션 시작"(`cs-start-btn`) **뿐**이다. 디바이스 컨트롤은 게이팅되지 않는다
- [x] ✅ **F3** — 대시보드가 spawn하는 Appium 인자에 `--address 127.0.0.1`이 포함된다 — `routes/env.py:190`
- [x] ✅ **F3** — `agents/`·`scripts/`·`config/`에 `0.0.0.0` 바인딩 0건. 대시보드 자체도 `serve.py:61`에서 `host="127.0.0.1"`
- [ ] ⏳ **F3** — 127.0.0.1 바인딩 후에도 Android MJPEG 미러링과 iOS 스크린샷 폴링이 정상 동작한다 _(실기 런타임 검증 대기)_
- [x] ✅ **F6** — iOS Capture 세션 활성 중 **Android AVD 중지 성공** — `post_avd_stop()`이 `is_capture_active("android")` 사용
- [x] ✅ **F6** — Android Capture 세션 활성 중 **iOS 시뮬레이터 종료 성공** — `post_simulator_stop()`이 `is_capture_active("ios")` 사용
- [x] ✅ **F6** — 어느 플랫폼 세션이든 `POST /api/env/appium/stop`은 403 — 무인자 `is_capture_active()` 사용
- [x] ✅ **F6** — 무인자 호출부 하위호환 — `platform: str | None = None` 기본값. `routes/api.py:78`, `routes/pipeline.py:55,119`, `routes/capture.py` 6곳이 **수정 없이** 기존 동작 유지
- [x] ✅ **F6** — `capture_session.json`에 `platform` 필드가 없으면 보수적으로 `True` 반환 — `utils/state.py:90-91`
- [x] ✅ **F6** — start 계열도 `post_avd_start()`는 `is_capture_active("android")`, `post_simulator_start()`는 `is_capture_active("ios")`를 사용한다.

### 15-7. v0.8 구현 현황 및 잔여 항목

> 2026-09-14 최신 코드와 실제 브라우저/로컬 도구 실측 기준이다.

| # | 항목 | 우선순위 | 완료 기준 |
|---|---|---|---|
| **1** | ✅ **US-3 대시보드 UI** — 기기별 목록, 추가 모달, 삭제 확인 | **완료** | Android/iOS 브라우저 E2E 및 320px 모달 테스트 통과 |
| **2** | ✅ **add·remove 실행 가드** | **완료** | 플랫폼 Capture와 파이프라인 실행 중 변경 차단 |
| **3** | ✅ **add 유일 키 중복 검사** | **완료** | 동일 `avd`/`udid` 재등록 409, 파일 무변경 |
| **4** | ✅ **Android capability 자동 채움** | **완료** | UiAutomator2, 실행 옵션, MJPEG 3종, 버전 필드 저장 |
| **5** | ✅ **start 계열 Capture 가드 플랫폼 분리** | **완료** | Android/iOS가 해당 플랫폼 Capture만 확인 |
| **6** | **스키마 검증 보강** — 필수 필드 존재, 유일 키 중복, `default: true` **정확히 1개**(현재 0개도 통과) | **P2** | `save_devices_json()`이 세 조건 위반 시 `ValueError` |
| **7** | ✅ **`udid` UUID 형식 검증 + 화이트리스트 대조** | **완료** | 형식/검색 목록 불일치는 400, 중복은 409 |
| **8** | **`fcntl.flock` 파일 잠금** — read-modify-write 구간 보호 | **P3** | 탭 2개 동시 편집 시 lost update 없음 |
| **9** | ✅ **`fsync` 후 교체** | **완료** | tmp 파일 flush·`fsync` 후 `replace()` |
| **10** | ✅ **디바이스 최소 보유 정책 UI** — 가상 섹션 1대 시 ✕ `disabled`·툴팁, 실기기 경고 다이얼로그, 에러 한국어 매핑 | **완료** (v0.9) | API 테스트 10개 추가·221개 통과 |

### 15-6. v0.6 블로커 해소 검증 기준 _(M2.0 완료 판정)_

- [ ] **R3** — `grep -rn "emulators\|simulators" scripts/ agents/ config/ docs/ENV_SETUP_PRD.md`가 복수형 키 참조 0건 (API 경로명 `/api/env/ios/simulators`, `list_system_simulators`와 함수명 `check_ios_simulators()`는 devices.json 키가 아니므로 제외)
- [ ] **R3** — `devices[platform][mode]` 직접 인덱싱이 코드베이스에서 0건. 4개 소비 지점 전부 공용 리더 경유 (M2.0-3)
- [ ] **R3** — `--mode emulator`, `--mode simulator`, `--mode real_device` 3개 값이 배열 전환 후에도 모두 동작한다
- [ ] **R2** — `devices.json`의 `mjpegServerPort`를 8094로 바꾸면 Capture Studio Android 세션의 `mjpeg_url`이 `http://localhost:8094`로 반환된다 (하드코딩 제거 확인, M2.0-4)
- [ ] **R2** — `capture.py`에 MJPEG 관련 숫자 리터럴이 남아 있지 않다
- [ ] **R9** — `default`가 Appium caps에서 제거된 뒤 전달되어 unknown capability 경고가 발생하지 않는다 (M2.0-5)
- [ ] **R9** — `devices.json` 안의 Appium capability 필드가 전부 camelCase이고, 제품 전용 메타(`default`, `serial`, `connection`, `wifi_ip`, `team_id`)만 snake_case다
- [ ] 배열 전환 후 `python3 scripts/02_generate.py --platform android --strict-locators`와 `--platform ios --strict-locators`가 모두 성공한다

---

## 16. Phase 3 — 실기기 지원 _(초안, 별도 PRD로 분리 예정)_

> ### ⚠️ 이 섹션은 초안이며 별도 PRD로 분리됩니다 _(v0.7, F7)_
>
> **Phase 3 상세 스펙은 별도 문서(`docs/ENV_SETUP_PHASE3_PRD.md`, 작성 예정)를 참조하세요.** 아래 내용은 분리 전까지 유지되는 **초안**이며, 확정 스펙이 아닙니다.
>
> **분리하는 이유**: 이 PRD는 M1~M3(에뮬레이터·시뮬레이터)의 구현 계약 문서입니다. Phase 3는 성격이 다른 문제를 다룹니다 — WiFi ADB 페어링, WDA 빌드와 provisioning profile, Apple Developer Team ID 관리, 물리 기기 연결/분리 감지. 이 주제들은 각자 별도의 사용자 흐름·에러 카탈로그·보안 검토를 요구하며, 한 문서에 두면 M1~M3 구현자가 자신의 범위를 식별하기 어려워집니다. 현재 §16이 이 PRD 분량의 상당 부분을 차지하면서도 M1 착수에는 한 줄도 쓰이지 않는 상태입니다.
>
> **분리 시점**: M3 완료 후 Phase 3 착수 직전. 그 시점에 이 섹션을 신규 문서로 이관하고, 여기에는 링크만 남깁니다.
>
> **분리 전까지의 취급**:
> - 이 섹션의 내용은 **M1~M3 구현의 요구사항이 아닙니다**. 구현자는 §1~§15와 §19만 읽으면 됩니다.
> - 단 **§16-4 `devices.json` 스키마 확장은 예외**입니다 — M2.0-1 마이그레이션이 `real_device` 키를 배열로 함께 변환하므로, 그 부분만 지금 확정된 계약으로 취급합니다.
> - 실기기 관련 결정(WDA 빌드 방식, WiFi 페어링 UX 등)은 별도 PRD에서 재검토 대상이며, 이 초안을 근거로 확정 처리하지 않습니다.

---

> 이 섹션은 Phase 3 범위를 상세 스펙 수준으로 기술합니다.  
> Phase 1/2(에뮬레이터·시뮬레이터)가 완료된 후 착수합니다.

---

### 16-1. 추가 사용자 스토리

| ID | 스토리 | 완료 기준 |
|---|---|---|
| **US-4** | QA 엔지니어로서 USB로 연결된 Android 실기기를 대시보드에서 즉시 인식하고 Appium 세션을 시작할 수 있다 | `adb devices`에 보이는 즉시 대시보드에 표시 · Appium capability에 serial 자동 주입 |
| **US-5** | QA 엔지니어로서 WiFi로 연결된 Android 실기기를 페어링 코드 입력만으로 등록할 수 있다 | `adb pair` + `adb connect` 성공 후 목록 표시 · USB 없이 이후 재연결 가능 |
| **US-6** | QA 엔지니어로서 USB로 연결된 iOS 실기기에 WDA를 빌드·설치하고 Appium 세션을 시작할 수 있다 | WDA 빌드 진행 UI + 완료 후 세션 시작 버튼 활성 |

---

### 16-2. Android 실기기

#### 16-2-1. 디바이스 감지

```
adb devices -l
  → serial, transport_id, model, product, device 파싱
  → 4초 폴링 (에뮬레이터와 동일 인터벌)
  → 신규 serial 감지 시 목록 갱신
```

| 필드 | 출처 | 예시 |
|---|---|---|
| `serial` | `adb devices` | `R3CN70BFZLJ` (USB), `192.168.1.5:5555` (WiFi) |
| `model` | `adb -s <serial> shell getprop ro.product.model` | `Galaxy S24` |
| `version` | `adb -s <serial> shell getprop ro.build.version.release` | `14` |
| `connection` | serial에 `:` 포함 여부 | `usb` \| `wifi` |

**주의**: `serial`은 USB 연결에선 하드웨어 고정값이나, WiFi ADB는 `<IP>:<port>` 형식으로 IP 변경 시 달라집니다.  
→ WiFi 기기는 `serial + model`을 함께 저장해 재인식 시 매핑합니다.

#### 16-2-2. WiFi ADB 페어링 흐름 (Android 11+)

```
사용자: 기기에서 [개발자 옵션 → 무선 디버깅] 활성
        → [페어링 코드로 기기 페어링] 탭
        → IP:pairing_port와 6자리 코드 확인

대시보드: "WiFi 페어링" 모달
  1. IP 주소 + 페어링 포트 입력
  2. 6자리 코드 입력
  3. POST /api/env/android/real/pair {ip, pairing_port, code}
     → adb pair <ip>:<pairing_port> <code>
     → 성공 시: adb connect <ip>:<connect_port> (포트 자동 감지)
     → 목록 갱신
```

**Android ≤ 10**: USB로만 최초 인가 후 `adb tcpip 5555` → `adb connect <IP>:5555` 방식.  
Phase 3 MVP는 Android 11+ WiFi 페어링을 우선 지원하고, ≤ 10은 USB-only 안내 배너를 표시합니다.

#### 16-2-3. 상태 모델 (실기기)

에뮬레이터와 달리 "부팅" 단계가 없습니다. 기기는 이미 켜진 상태로 연결됩니다.

| 상태 | 의미 | 전이 조건 |
|---|---|---|
| `connected` | adb 인가 완료 · 사용 가능 | `adb devices`에 `device` 상태 |
| `unauthorized` | Trust 미승인 | `adb devices`에 `unauthorized` 상태 |
| `disconnected` | 케이블 분리 / WiFi 끊김 | serial이 `adb devices`에서 사라짐 |

`unauthorized` → 기기 화면의 "이 컴퓨터를 허용하시겠습니까?" 팝업 안내를 표시합니다.

---

### 16-3. iOS 실기기

#### 16-3-1. 디바이스 감지

```
xcrun xctrace list devices
  → "iPhone" / "iPad" 행 파싱 (Simulator 행 제외)
  → 예: iPhone 15 Pro (17.5) [ABC123DEF456...]
  → 4초 폴링
```

| 필드 | 출처 | 예시 |
|---|---|---|
| `udid` | xcrun 출력 `[…]` 부분 | `00008110-001A2B3C4D5E6F78` |
| `deviceName` | xcrun 출력 이름 | `iPhone 15 Pro` |
| `platformVersion` | xcrun 출력 버전 | `17.5` |
| `connection` | 항상 | `usb` (Phase 3 범위, WiFi는 미지원) |

`udid`는 기존 시뮬레이터와 동일하게 `^[0-9A-F-]{36}$` 정규식 검증 적용.

#### 16-3-2. WDA (WebDriverAgent) 설치 흐름

iOS 실기기는 시뮬레이터와 달리 WDA를 실기기에 빌드·설치해야 합니다.

```
기기 연결 감지
  → WDA 설치 여부 확인 (bundle ID: com.facebook.WebDriverAgentRunner)
  → 미설치: [WDA 설치] 버튼 활성
  → 클릭: POST /api/env/ios/real/wda/build {udid}
      xcodebuild
        -project WebDriverAgent.xcodeproj
        -scheme WebDriverAgentRunner
        -destination "id=<udid>"
        test
      → 진행 로그 스트리밍 (WebSocket)
      → 성공: wda_ready 상태
      → 실패: error + 로그 경로
```

**사전 조건**:
- Xcode 설치 (`xcode-select -p` 확인)
- Apple Developer Team ID 설정 (대시보드 설정 화면에서 입력)
- `WebDriverAgent` 저장소 클론 (`~/.appium/node_modules/...` 또는 사용자 지정 경로)

#### 16-3-3. 상태 모델 (iOS 실기기)

| 상태 | 의미 | 전이 |
|---|---|---|
| `connected` | 감지됨 · WDA 설치 여부 미확인 | USB 연결 즉시 |
| `trust_needed` | 기기에서 Trust 미승인 | xcrun에 감지되나 WDA 접근 불가 |
| `wda_needed` | WDA 미설치 | WDA 설치 버튼 활성 |
| `wda_building` | WDA 빌드/설치 중 | POST wda/build 후 |
| `ready` | WDA 설치 완료 · Appium 세션 시작 가능 | 빌드 성공 |
| `disconnected` | USB 분리 | xcrun 목록에서 사라짐 |

---

### 16-4. `devices.json` 스키마 확장 (Phase 3)

> **v0.6 정정**: 실기기 키는 `real`이 아니라 **`real_device`**다. 현재 `config/devices.json`이 이미 `android.real_device` / `ios.real_device`를 쓰고 있고, `01_analyze.py:106`의 `--mode` choices도 `emulator|real_device|simulator`다. `real`로 바꾸면 기존 `--mode real_device` 호출이 깨진다.
>
> 실기기 항목도 §11의 케이스 규칙을 그대로 따른다 — Appium에 전달되는 필드는 camelCase, 대시보드만 읽는 제품 전용 메타는 snake_case.

```json
{
  "android": {
    "emulator": [
      { "avd": "Pixel_7_Android15", "default": true, "deviceName": "Android Emulator", "platformVersion": "15.0", "automationName": "UiAutomator2" }
    ],
    "real_device": [
      {
        "udid": "R3CN70BFZLJ",
        "default": false,
        "deviceName": "Galaxy S24",
        "platformVersion": "14",
        "automationName": "UiAutomator2",
        "serial": "R3CN70BFZLJ",
        "connection": "usb"
      },
      {
        "udid": "192.168.1.5:5555",
        "default": false,
        "deviceName": "Pixel 8",
        "platformVersion": "14",
        "automationName": "UiAutomator2",
        "serial": "192.168.1.5:5555",
        "connection": "wifi",
        "wifi_ip": "192.168.1.5"
      }
    ]
  },
  "ios": {
    "simulator": [
      { "udid": "E73939EF-741D-4A72-BEA7-97D31B15719A", "default": true, "deviceName": "iPhone 18 Pro", "platformVersion": "27.0", "automationName": "XCUITest" }
    ],
    "real_device": [
      {
        "udid": "00008110-001A2B3C4D5E6F78",
        "default": false,
        "deviceName": "iPhone 15 Pro",
        "platformVersion": "17.5",
        "automationName": "XCUITest",
        "connection": "usb",
        "team_id": "ABCD1234EF"
      }
    ]
  }
}
```

**필드 정의 — `android.real_device[]`**

| 필드 | 케이스 | 필수 | 의미 |
|---|---|---|---|
| `udid` | camel | ✅ | Appium capability. Android에서는 serial과 동일 값. 배열 내 **유일 키** |
| `default` | snake | ✅ | 제품 전용 메타 |
| `deviceName` | camel | ✅ | Appium capability. `ro.product.model` 결과 |
| `platformVersion` | camel | ✅ | Appium capability. `ro.build.version.release` 결과 |
| `automationName` | camel | ✅ | `UiAutomator2` 고정 |
| `serial` | snake | ✅ | 제품 전용 메타. `adb -s <serial>` 호출용. `udid`와 값은 같지만 용도가 다르므로 별도 보관 |
| `connection` | snake | ✅ | 제품 전용 메타. `usb` \| `wifi`. 재연결 흐름 분기용 |
| `wifi_ip` | snake | ⬜ | 제품 전용 메타. `connection: "wifi"`일 때만. IP 변경 후 재페어링 안내용 |

**필드 정의 — `ios.real_device[]`**

| 필드 | 케이스 | 필수 | 의미 |
|---|---|---|---|
| `udid` | camel | ✅ | Appium capability. 배열 내 **유일 키**. `^[0-9A-F-]{36}$` 검증 |
| `default` | snake | ✅ | 제품 전용 메타 |
| `deviceName` | camel | ✅ | Appium capability |
| `platformVersion` | camel | ✅ | Appium capability |
| `automationName` | camel | ✅ | `XCUITest` 고정 |
| `connection` | snake | ✅ | 제품 전용 메타. Phase 3에서는 `usb` 고정 |
| `team_id` | snake | ⬜ | 제품 전용 메타. WDA 빌드용 Apple Developer Team ID. Appium caps 아님 |

> **`serial` vs `udid` 중복에 대하여**: Android 실기기에서 두 값은 같다. 그럼에도 분리하는 이유는 `udid`가 Appium caps로 그대로 전달되는 반면 `serial`은 `adb -s` 인자로만 쓰이기 때문이다. 한 필드를 두 용도로 쓰면 caps 조립 시 제품 전용 메타를 걸러내는 §11 규칙("Appium에 넘어가는 필드 = camelCase")이 무너진다.

**마이그레이션**: Phase 3 착수 시점에 `real_device`는 이미 M2.0-1에서 배열로 변환되어 있다(빈 배열 또는 1개 항목). Phase 3은 이 배열에 항목을 추가하는 흐름만 구현하며 키 이름 변경은 없다.

---

### 16-5. Phase 3 API 엔드포인트

| Method | 경로 | Body | 응답 | 비고 |
|---|---|---|---|---|
| `GET` | `/api/env/android/real/list` | — | `{ok, devices:[{serial,model,version,connection,status}]}` | 4초 폴링용 |
| `POST` | `/api/env/android/real/pair` | `{ip, pairing_port, code}` | `{ok, serial}` | 409 already_paired, 400 bad_code |
| `POST` | `/api/env/android/real/connect` | `{ip, port}` | `{ok, serial}` | WiFi 재연결 |
| `POST` | `/api/env/android/real/add` | `{serial, model, platformVersion, connection}` | `{ok}` | devices.json 등록 |
| `POST` | `/api/env/android/real/remove` | `{serial}` | `{ok}` | 404, 423 locked |
| `GET` | `/api/env/ios/real/list` | — | `{ok, devices:[{udid,deviceName,platformVersion,status}]}` | 4초 폴링용 |
| `POST` | `/api/env/ios/real/wda/build` | `{udid}` | `{ok}` 202 | 409 already_building, 500 xcode_not_found |
| `GET` | `/api/env/ios/real/wda/status` | — | `{ok, building, log_tail}` | 빌드 진행 확인 |
| `POST` | `/api/env/ios/real/add` | `{udid, deviceName, platformVersion, team_id?}` | `{ok}` | 409 already_exists |
| `POST` | `/api/env/ios/real/remove` | `{udid}` | `{ok}` | 404 |

> **보안**: `serial` 파라미터는 `^[A-Za-z0-9._:-]{4,64}$` 정규식 검증 + `/api/env/android/real/list` 결과 화이트리스트 대조. `udid`는 기존 UUID 검증 동일 적용.

---

### 16-6. 에러 카탈로그 (Phase 3 추가)

| 에러 코드 | 원인 | 표시 |
|---|---|---|
| `adb_pair_failed` | 잘못된 코드 / 포트 불일치 | "페어링 코드나 IP가 올바르지 않습니다" + 재시도 |
| `adb_unauthorized` | 기기에서 Trust 미승인 | "기기 화면에서 '허용'을 눌러주세요" 안내 + 5초 재폴링 |
| `xcode_not_found` | Xcode 미설치 | "Xcode가 설치되어 있지 않습니다. xcode-select --install" |
| `wda_build_failed` | xcodebuild 오류 | 로그 경로 + "Team ID 또는 provisioning profile을 확인하세요" |
| `team_id_missing` | iOS Team ID 미설정 | "대시보드 설정 → Apple Developer Team ID를 입력하세요" |
| `wifi_adb_legacy` | Android ≤ 10 연결 시도 | "Android 11 미만은 USB 연결 후 adb tcpip 5555 방식을 사용하세요" |

---

### 16-7. 제약 및 Phase 3 외 범위

| 항목 | Phase 3 포함 여부 | 비고 |
|---|---|---|
| Android USB 실기기 | ✅ | `adb devices` 자동 감지 |
| Android WiFi 실기기 (11+) | ✅ | 페어링 모달 포함 |
| Android WiFi 실기기 (≤10) | ❌ | USB-only 안내만 표시 |
| iOS USB 실기기 + WDA | ✅ | Team ID 필요 |
| iOS WiFi 실기기 | ❌ | Phase 4 후속 |
| Linux 러너 실기기 | ❌ | macOS 전용 (Phase 4) |
| AVD 생성 UI | ✅ | `emulator -list-avds` 드롭다운 |
| Appium 포트 설정 | ✅ | 4723 고정 → 설정 가능 |
| 환경 프리셋 저장 | ❌ | Phase 4 |
| 다중 에뮬레이터 동시 실행 | ❌ | Phase 4 (포트 분리 방식 재검토 필요) |
| CI/CD Linux 러너 | ❌ | Phase 4 |

---

### 16-8. 디자인 산출물 (Phase 3 목업)

Phase 3 실기기 화면은 인터랙티브 목업에 별도 섹션으로 추가됩니다.

| 화면 ID | 화면명 | 플랫폼 |
|---|---|---|
| `and-real-list` | Android 실기기 목록 (USB + WiFi) | Android |
| `and-real-wifi-pair` | WiFi 페어링 모달 | Android |
| `and-real-unauth` | Trust 미승인 안내 | Android |
| `ios-real-list` | iOS 실기기 목록 | iOS |
| `ios-real-wda` | WDA 빌드 진행 | iOS |
| `ios-real-trust` | Trust 안내 | iOS |

---

## 17. 관련 파일

| 파일 | 역할 |
|---|---|
| `agents/dashboard/routes/env.py` | 신규 — ENV API 라우터 |
| `agents/dashboard/serve.py` | `app.include_router(env_router)` 추가, lifespan shutdown 훅 추가 |
| `agents/dashboard/shared.py` | `_find_emulator_bin()`, `_find_appium_bin()` 추가 |
| `agents/dashboard/utils/system.py` | **확장** — `check_android_devices()`, `check_ios_simulators()` 기존 보유. adb/simctl 파싱 함수를 여기에 추가. `utils/device_utils.py` 신규 파일 생성 금지 |
| `agents/dashboard/dashboard.html` | 환경 설정 탭 UI |
| `state/env_session.json` | 신규 — 프로세스 상태 영속화 |
| `config/devices.json` | 디바이스 설정 (UI에서 갱신) |
| `logs/appium_server.log` | Appium stdout 리다이렉트 |
| `scripts/check_mjpeg.py` | 재사용 — 환경 점검 함수 |

---

## 18. 디자인 산출물

| 산출물 | URL | 설명 |
|---|---|---|
| **인터랙티브 목업** | https://claude.ai/code/artifact/466103b7-6be2-4811-b34e-f0c088462334 | **19화면** 클릭 프로토타입. Phase 1/2: Appium/Android/iOS 13화면. Phase 3: Android 실기기 3화면 (목록·WiFi 페어링·Trust 미승인) + iOS 실기기 3화면 (목록·WDA 빌드·Trust 안내) |
| **디자인 스펙 (목업 통합)** | https://claude.ai/code/artifact/55ba3c71-e480-4493-b60a-d0a2aad70fb1 | Figma 핸드오프 스타일. 7탭: Appium/Android/iOS/모달/상태 전이표/컴포넌트/**목업**. Phase 3 실기기 6화면 카드 인라인 삽입 |
| **SDLC TDD 개발 계획** | https://claude.ai/code/artifact/10daeb9e-4923-4dad-b641-9a90e8f02ae2 | **v1.3** — 최신 마일스톤과 P1 완료 상태를 반영한 개발 계획 |

> **아티팩트 버전 대응**: 목업 **v0.8**, 디자인 스펙 **v0.8**, SDLC 계획 **v1.3**을 기준으로 한다. 자동 접근이 제한될 때는 `docs/images/env-setup/`의 캡처를 재현 가능한 시각 기준으로 사용한다.

> **버전 대응**: 이 PRD는 v0.8 기준이다. 산출물이 업데이트될 때마다 위 URL은 동일 주소에 재배포된다.

---

## 19. Known Limitations _(v0.7 신설)_

MVP 범위에서 **의도적으로 남겨두는 한계**입니다. 버그가 아니라 알려진 제약이며, 각 항목에 완화 수단과 향후 개선 방향을 명시합니다.

### 19-1. 에뮬레이터 serial 식별 정확도 _(F4)_

**한계**: 대시보드는 `emulator -avd <avd>` spawn 후 `adb devices`에서 `emulator-` 접두어를 가진 **첫 번째 serial**을 자신이 띄운 에뮬레이터로 간주합니다(§8). 따라서 **대시보드 외부(Android Studio·터미널·다른 스크립트)에서 이미 실행 중인 에뮬레이터가 있으면 serial을 잘못 매핑할 수 있습니다.**

**영향**

| 시나리오 | 결과 |
|---|---|
| 외부 에뮬레이터 1대가 이미 실행 중인 상태에서 대시보드로 AVD 시작 | 중지 버튼이 **외부 에뮬레이터를 종료**할 수 있음 |
| 같은 상황에서 Appium 세션 시작 | 의도한 AVD가 아닌 기기에 앱이 설치·실행될 수 있음 |

**MVP 완화 수단**

1. **단일 에뮬레이터 정책** — 대시보드 기준 `running`/`booting` 상태가 하나라도 있으면 다른 시작 요청을 `409 already_running`으로 차단합니다(§7). 대시보드가 만드는 다중 에뮬레이터 상황은 발생하지 않습니다.
2. **§8 소유권 비대칭 명문화** — 에뮬레이터는 소유권을 추적하지 않으며 외부 실행 기기도 종료 가능함을 문서화했습니다. 이는 의도된 결정입니다.
3. **UI 안내** — 에뮬레이터 섹션에 "대시보드 밖에서 실행한 에뮬레이터가 있으면 먼저 종료하는 것을 권장합니다" 문구를 표시합니다.

> ⚠️ 위 1번은 **대시보드가 띄우는 에뮬레이터 개수**만 제한합니다. 외부에서 이미 떠 있는 에뮬레이터를 막지는 못하므로 한계가 완전히 사라지지는 않습니다.

**향후 개선 (Phase 3 또는 그 이전 소규모 개선)**

```
시작 전:  before = set(adb devices)           # 스냅샷
emulator -avd <avd> spawn
부팅 완료: after  = set(adb devices)
새 serial = after - before                    # 차집합
  ├─ 정확히 1개  → 그 serial을 확정 매핑
  ├─ 0개         → 타임아웃/실패로 처리
  └─ 2개 이상    → 사용자에게 선택 요청 (또는 매핑 포기 + 경고)
```

`adb devices` 목록의 **시작 전후 차이**로 매핑하면 외부 에뮬레이터가 몇 대 떠 있든 정확도가 유지됩니다. 구현 비용이 작으므로 M2 구현 중 여유가 있으면 앞당겨 반영할 수 있습니다. 단, 차집합이 2개 이상인 경우(동시에 다른 프로세스가 기기를 연결)는 여전히 모호하므로 완전한 해결책은 아닙니다.

**완전한 해결 방향 (Phase 3+)**: `emulator` 실행 시 `-port <N>`을 명시해 serial(`emulator-<N>`)을 **사전에 결정**하고, 포트 풀을 대시보드가 관리합니다. 다중 에뮬레이터 병렬 실행 설계와 함께 다뤄야 하므로 Phase 4 주제로 둡니다.

### 19-2. iOS 시뮬레이터 식별 _(v0.8 해결)_

iOS Simulator는 등록·부팅·종료 모두 UDID를 정본으로 사용한다. 같은 기기명이 여러 런타임에 있어도 선택한 Simulator 한 대만 조작한다. 부팅/종료 중에는 겹치는 `simctl list` 명령을 실행하지 않아 CoreSimulator 잠금으로 상태 조회가 멈추지 않는다.

### 19-3. 디바이스 CRUD의 `deviceName` 식별 _(v0.8 신설, US-3)_

`/api/env/{android,ios}/{add,remove}`는 항목을 **`deviceName`으로 지목**합니다(§6 CRUD 계약 정정). §11이 정의한 배열 내 유일 키(`avd`/`udid`)와 다릅니다.

| 한계 | 영향 |
|---|---|
| add는 `avd`/`udid` 중복을 409로 막는다 | 같은 시스템 기기를 두 번 등록할 수 없다 |
| remove는 아직 `deviceName` 일치 항목을 제거한다 | 서로 다른 시스템 기기에 같은 표시 이름을 수동 구성한 레거시 파일은 모호할 수 있다 |
| 가상 기기 마지막 1대 삭제 불가 (400 last_device, UI 비활성) | 의도된 동작 — §5-4 참조. 잘못된 항목은 "추가 후 삭제"로 교정 가능 |
| 실기기 마지막 1대 삭제 허용 (0대 허용) | 의도된 동작 — §5-4 참조. 기존 플레이스홀더 고착 문제 해소 |

**완화**: UI 등록은 시스템 검색의 표준 이름을 사용하고 `avd`/`udid` 중복을 차단한다. 향후 remove 요청도 `avd`/`udid` 정본으로 전환한다.

### 19-4. 기타 알려진 제약

| 항목 | 제약 | 참조 |
|---|---|---|
| 최초 환경 구축 자동화 | Appium·드라이버·Xcode CLT 설치는 자동화하지 않음. 감지·안내만 제공 | §2-1 비목표 |
| `devices.json` 동시 쓰기 | 원자적 교체·write 구간 `flock`·`fsync`는 구현 완료. load→modify→save 전체 트랜잭션 잠금은 없어 탭 2개 완전 동시 편집 시 lost update 가능 | §11, §15-7 항목 8 |
| `devices.json` 변경 잠금 | 플랫폼 Capture와 파이프라인 실행 중 add·remove 차단은 구현됨. 두 브라우저 탭의 완전 동시 쓰기 파일 잠금은 미구현 | §11, §15-7 항목 8 |
| 다중 에뮬레이터 동시 실행 | 미지원 (409 already_running) | §7, §16-7 |
| Appium 포트 | 4723 고정 | §16-7 (Phase 3에서 설정 가능화) |
| 세션 스탈레 판정 | `started_at` 기반 만료 없음. PID 생존 여부만 확인 | §11 |
| Linux 러너 | macOS 전용. iOS 기능은 Linux에서 동작하지 않음 | §14 |
