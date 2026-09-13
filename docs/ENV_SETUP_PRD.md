# Environment Setup UI — PRD

**작성일**: 2026-09-12
**최종 수정**: 2026-09-13
**버전**: v0.5 (Phase 3 실기기 지원 스펙 추가 — Android USB/WiFi·iOS WDA)
**상태**: 구현 착수 가능 (M1)
**리뷰 기록**: docs/ENV_SETUP_REVIEW_20260913.md
**담당**: QA Automation Platform

---

## 1. 배경 및 목적

현재 Capture Studio와 파이프라인을 사용하려면 사용자가 터미널에서 직접 명령을 실행해야 합니다.

```bash
appium --address 0.0.0.0 --port 4723 --allow-insecure=uiautomator2:adb_screen_streaming
emulator -avd Pixel_7_Android15
xcrun simctl boot <udid>
```

이 진입 장벽을 없애고, **대시보드에서 모든 환경 준비를 마칠 수 있도록** 환경 설정 UI를 제공합니다. 또한 `config/devices.json`을 직접 편집하지 않고도 디바이스를 추가·삭제할 수 있어야 합니다.

---

## 2. 페르소나 및 사용자 스토리

### 주 페르소나: 비개발자 QA (US-1 우선)

**US-1** (주): 비개발자 QA로서, 터미널을 열지 않고 대시보드에서 Appium과 에뮬레이터를 시작해, Capture Studio로 바로 TC를 만들고 싶다.

**US-2**: QA 자동화 담당자로서, 내가 이미 터미널에서 띄운 Appium 서버를 대시보드가 죽이지 않고 "외부 실행 중"으로 인식하길 원한다.

**US-3**: QA 담당자로서, 에뮬레이터/시뮬레이터를 JSON 파일을 편집하지 않고 대시보드에서 추가·삭제하고 싶다.

---

## 3. 마일스톤 및 범위

| 마일스톤 | 범위 | 이유 | 선행 조건 |
|---|---|---|---|
| **M1 (P0)** | Appium 서버 시작/중지/상태(5값)/로그 + 바이너리 탐색 + 드라이버 설치 확인 | 실패 빈도 최상위, 플랫폼 무관. 기존 `/api/check/*` 확장으로 최소 변경 | — |
| **M2 (P1)** | Android AVD 목록·시작·중지 + 부팅 완료 판정 + 디바이스 추가/삭제 UI + `devices.json` 배열 마이그레이션 | Phase 1 (Android 에뮬레이터) 로드맵 우선 | **M1 완료 후 릴리즈** |
| **M3 (P2)** | iOS 시뮬레이터 목록·부팅·종료 + `devices.json` 반영 | Phase 2 | **M1 완료 후 릴리즈** |
| **Phase 3** | 실기기 감지·선택, WDA 자동화, AVD 생성 UI | 로드맵 순서 준수 | M3 완료 후 |

> **릴리즈 의존성**: Android/iOS 디바이스 시작 버튼은 Appium이 `managed` 또는 `external` 상태일 때만 활성화된다. M2·M3를 M1 없이 단독 릴리즈하면 디바이스 컨트롤이 항상 잠김 상태로 노출된다.

---

## 4. 사용자 흐름

```
대시보드 접속
  └─ 상단 환경 상태바: Appium ● / 에뮬레이터 ● / 시뮬레이터 ●
       └─ "환경 설정" 탭 진입
            ├─ [M1] Appium 서버 섹션
            │    ├─ 상태 표시 (관리 중 / 외부 실행 중 / 중지됨)
            │    ├─ 시작 / 중지 버튼 + 드라이버 설치 상태
            │    └─ 로그 확인 (최근 200줄)
            ├─ [M2] Android 섹션
            │    ├─ 등록된 AVD 목록 + 시작/중지 버튼
            │    └─ "＋ 추가 / ✕ 삭제" UI
            └─ [M3] iOS 섹션
                 ├─ 등록된 시뮬레이터 목록 + 부팅/종료 버튼
                 └─ "＋ 추가 / ✕ 삭제" UI
  └─ 환경 준비 완료 → Capture Studio 또는 파이프라인 실행
```

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
| `external` (외부 실행 중) | `/status` 200이지만 대시보드 PID 아님 | 중지 비활성, "상태 새로고침" 활성 |
| `error` (오류) | 타임아웃·비정상 종료 | "다시 시도" 버튼 + 로그 경로 표시 — **사용자 액션 없이 자동 해소되지 않음** |

> **중요**: "외부 실행 중" 상태에서는 절대 SIGTERM 금지. 사용자에게 터미널에서 직접 종료하도록 안내.
>
> **error 상태 정책** _(v0.4 확정, B3 해소)_: 타임아웃·비정상 종료 후 `error` 상태는 사용자가 "다시 시도"를 클릭하거나 화면을 떠날 때까지 유지된다. 1초 후 자동 `stopped` 전이 없음 — 로그를 봐야 원인 파악이 가능하기 때문.
>
> **Appium 중지 가드** _(v0.4 추가, B2 해소)_: `POST /api/env/appium/stop`은 Capture 세션 또는 파이프라인 실행 중 차단된다. `is_capture_active()` → 403 capture_session_active, `is_pipeline_active()` → 409 pipeline_running. 중지 버튼 클릭 전 프론트엔드도 `/api/env/status`로 상태 재확인 후 팝업 안내.
>
> **"재시작" 동작** _(v0.4 명시)_: 별도 `/restart` API 없음. `POST stop` → 완료 확인 → `POST start` 순차 호출. 클라이언트가 두 번 폴링해 상태 전이 감지.
>
> **"상태 새로고침" 동작** _(v0.4 명시, 기존 "재연결" 재명명)_: external 카드의 버튼명을 "상태 새로고침"으로 통일. `GET /api/env/status` 1회 즉시 호출 후 UI 갱신. Capture Studio의 "세션 재연결"과 혼동 방지.

**시작 명령** (필수 플래그 포함)

```bash
appium --address 0.0.0.0 --port 4723 \
  --allow-insecure=uiautomator2:adb_screen_streaming
```

> ⚠️ `--allow-insecure=uiautomator2:adb_screen_streaming` 없이 시작하면 Android MJPEG 미러링이 동작하지 않습니다. 이 플래그는 선택이 아니라 **필수**입니다.

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

### 5-2. Android 디바이스 관리 (M2)

**등록된 AVD 목록 + 시작/중지**

| 항목 | 내용 |
|---|---|
| AVD 목록 | `config/devices.json`의 `android.emulator` 목록 표시 (기록된 것만) |
| 시작 | `_find_emulator_bin() + ['-avd', avd_name, '-no-snapshot-load']` |
| 부팅 완료 판정 | `adb -s <serial> shell getprop sys.boot_completed == 1` 3초 폴링, 타임아웃 180초 |
| 중지 | `adb -s <serial> emu kill` (serial 추적 필수) |
| 바이너리 탐색 | `_find_emulator_bin()` — `$ANDROID_HOME/emulator/emulator` 등 후보 순회 |

**디바이스 추가/삭제 UI (US-3)**

- **추가 모달**: `emulator -list-avds` 결과로 드롭다운 자동 채우기 → 선택 시 OS 버전 자동 입력 → "등록" 클릭 → `config/devices.json` `android.emulator` 갱신
- **삭제**: 각 항목의 `✕` 버튼 → 확인 다이얼로그 → `config/devices.json`에서 제거
- **갱신 필드**: `avd`, `deviceName`, `platformVersion` (MJPEG caps는 고정값 유지)
- **잠금**: 파이프라인 또는 Capture 세션 실행 중 `devices.json` 갱신 차단 + 안내 메시지

**실기기**: Phase 3 범위 (MVP에서는 "실기기는 Phase 3에서 지원 예정" 안내 텍스트만 표시)

### 5-3. iOS 디바이스 관리 (M3)

**등록된 시뮬레이터 목록 + 부팅/종료**

| 항목 | 내용 |
|---|---|
| 시뮬레이터 목록 | `config/devices.json`의 `ios.simulator` 목록 표시 |
| 부팅 | `xcrun simctl boot <udid>` — 이미 Booted면 에러 무시하고 "실행 중"으로 표시 |
| 부팅 완료 판정 | `xcrun simctl list devices --json` state == `Booted` 3초 폴링, 타임아웃 120초 |
| 종료 | `xcrun simctl shutdown <udid>` |

> **iOS XCUITest 세션 충돌**: 시뮬레이터 종료 버튼 클릭 시 Capture Studio iOS 세션 활성 여부 확인 → 활성이면 차단 + "Capture Studio 세션을 먼저 종료하세요" 안내.

**디바이스 추가/삭제 UI (US-3)**

- **추가 모달**: `xcrun simctl list devices --json` 결과로 드롭다운 자동 채우기 → 선택 시 UDID 자동 입력 → "등록" 클릭 → `config/devices.json` `ios.simulator` 갱신
- **삭제**: 각 항목의 `✕` 버튼 → 확인 다이얼로그 → `config/devices.json`에서 제거
- **갱신 필드**: `deviceName`, `udid`, `platformVersion`

**실기기**: Phase 3 범위

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

### Android (M2)

| 메서드 | 경로 | 요청 | 응답 (성공) | 실패 |
|---|---|---|---|---|
| `GET` | `/api/env/android/avds` | — | `{ok, avds: [{name, status, serial}]}` | 500 binary_not_found |
| `POST` | `/api/env/android/avd/start` | `{avd: str}` | `{ok}` 202 | 409 already_running, 400 invalid_avd, 500 |
| `POST` | `/api/env/android/avd/stop` | `{serial: str}` | `{ok}` | 403 capture_session_active, 404 not_running, 423 pipeline_running, 500 |
| `GET` | `/api/env/android/list_system_avds` | — | `{ok, avds: [str]}` | `emulator -list-avds` 결과 |
| `POST` | `/api/env/android/add` | `{avd, deviceName, platformVersion}` | `{ok}` | 409 already_exists, 423 locked |
| `POST` | `/api/env/android/remove` | `{avd}` | `{ok}` | 404, 423 locked |

> `avd` 파라미터는 `/api/env/android/list_system_avds` 결과 화이트리스트 대조 후 사용. `shell=False` + 리스트 인자 강제.

### iOS (M3)

| 메서드 | 경로 | 요청 | 응답 (성공) | 실패 |
|---|---|---|---|---|
| `GET` | `/api/env/ios/simulators` | — | `{ok, simulators: [{name, udid, os, state}]}` | 500 xcrun_not_found |
| `POST` | `/api/env/ios/simulator/boot` | `{udid: str}` | `{ok}` 202 | 400 invalid_udid, 500 |
| `POST` | `/api/env/ios/simulator/shutdown` | `{udid: str}` | `{ok}` | 403 capture_session_active, 404, 500 |
| `GET` | `/api/env/ios/list_system_simulators` | — | `{ok, simulators: [{name, udid, os}]}` | `xcrun simctl list --json` 결과 |
| `POST` | `/api/env/ios/add` | `{deviceName, udid, platformVersion}` | `{ok}` | 409, 423 locked |
| `POST` | `/api/env/ios/remove` | `{udid}` | `{ok}` | 404, 423 locked |

> `udid`는 UUID 형식 검증(`^[0-9A-F-]{36}$`) 후 `list_system_simulators` 화이트리스트 대조.

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
| `managed` | ■ 중지 클릭 | `is_capture_active()` | `managed` | 403, 팝업 안내 |
| `managed` | ■ 중지 클릭 | `is_pipeline_active()` | `managed` | 409, 팝업 안내 |
| `managed` | PID 소멸 감지 (폴링) | — | `error` | 토스트 "비정상 종료", 로그 경로 |
| `stopped` | GET /status 200 + PID 불일치 (폴링) | — | `external` | 안내 메시지, 중지 버튼 비활성 |
| `external` | 상태 새로고침 클릭 또는 폴링 | /status 실패 | `stopped` | 시작 버튼 복원 |
| **`error`** | **사용자 직접 해소 (다시 시도/탭 이탈)** | — | **`stopped`** | **로그 창 유지 — 1초 자동 해소 없음** |

### Android 에뮬레이터

| From | Trigger | Guard | To | Effect |
|---|---|---|---|---|
| `stopped` | ▶ 시작 클릭 | Appium `managed`/`external` | `booting` | emulator spawn, 진행 바, 버튼 잠금 |
| `stopped` | ▶ 시작 클릭 | Appium `stopped` | `stopped` | 버튼 비활성 (잠금 유지, 안내 표시) |
| `booting` | sys.boot_completed == 1 (폴링) | 180초 이내 | `running` | 중지 버튼 활성, serial 저장 |
| `booting` | 180초 타임아웃 | — | `error` | 빨강, 로그, 다시 시도 |
| `error` | 다시 시도 클릭 | — | `booting` | 재spawn |
| `running` | ■ 중지 클릭 | `!is_capture_active()` | `stopped` | adb emu kill, serial 제거 |
| `running` | ■ 중지 클릭 | `is_capture_active()` | `running` | 403, 팝업 안내 |
| any | Appium → stopped | — | `stopped (잠김)` | 시작 버튼 비활성, 잠금 뱃지 |
| `booting` | 탭 이탈/새로고침 | — | `booting` | env_session.json 유지 → 복귀 시 스피너 복원 |

### iOS 시뮬레이터

| From | Trigger | Guard | To | Effect |
|---|---|---|---|---|
| `Shutdown` | ▶ 부팅 클릭 | Appium `managed`/`external` | `booting` | xcrun simctl boot, 버튼 잠금 |
| `booting` | state == Booted (폴링) | 120초 이내 | `Booted` | 종료 버튼 활성 |
| `booting` | 120초 타임아웃 | — | `error` | 빨강, 다시 시도 |
| `error` | 다시 시도 클릭 | — | `booting` | 재boot |
| `Booted` | ■ 종료 클릭 | `!is_capture_active()` | `Shutdown` | xcrun simctl shutdown |
| `Booted` | ■ 종료 클릭 | `is_capture_active()` | `blocked` | 충돌 경고 화면 |
| `blocked` | 취소 클릭 | — | `Booted` | 목록 복귀, 변경 없음 |

**글로벌 규칙**
- 폴링 주기: 3초 (모든 상태 전이 감지)
- `error` 상태는 사용자 액션 없이 자동 해소되지 않음 _(v0.4 확정)_
- Android/iOS 시작 버튼은 Appium이 `managed` 또는 `external`일 때만 활성
- MVP: 에뮬레이터·시뮬레이터 동시 2개 이상 시작 불가 (409 already_running)

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
`emulator -avd <avd>` spawn 후 부팅 완료 판정 시점에 `adb devices`를 실행해 `emulator-` 접두어를 가진 첫 번째 serial을 저장. MVP는 단일 에뮬레이터이므로 이 단순화가 유효하다. 복수 에뮬레이터는 Phase 3.

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
| 실행 중 / Booted (managed) | 초록 (#22c55e) | ● | 중지 (Appium: + 재시작) |
| 외부 실행 중 (external) | 청록 점선 (#06b6d4) | ◉ | 상태 새로고침 (중지 불가) |
| 시작 중 / 부팅 중 (starting/booting) | 노랑 (#eab308) | ◌ 스피너 | 모두 잠김 |
| 중지됨 / Shutdown (stopped) | 회색 (#6b7280) | ○ | 시작 / 부팅 |
| 오류 / 타임아웃 (error) | 빨강 (#ef4444) | ✕ | 다시 시도 + 로그 보기 |
| Capture 세션 충돌 (blocked) | 빨강 (#ef4444) | 차단됨 | Capture Studio 이동 + 취소 |
| Appium 미실행 잠금 (locked) | 회색 (#6b7280) | 🔒 | 없음 |

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

**`config/devices.json` 스키마 변경** _(v0.4 추가, B1 해소)_

```json
{
  "android": {
    "emulators": [
      {
        "avd": "Pixel_7_Android15",
        "deviceName": "Pixel 7",
        "platformVersion": "15.0",
        "default": true
      },
      {
        "avd": "Pixel_4_Android12",
        "deviceName": "Pixel 4",
        "platformVersion": "12.0",
        "default": false
      }
    ]
  },
  "ios": {
    "simulators": [
      {
        "deviceName": "iPhone 18 Pro",
        "udid": "A1B2C3D4-...",
        "platformVersion": "27.0",
        "default": true
      }
    ]
  }
}
```

> **마이그레이션**: 기존 단일 객체 → 배열 전환. `01_analyze`/`05_execute`/드라이버는 `default: true` 항목을 읽도록 업데이트.  
> **복수 에뮬레이터 동시 시작 정책**: MVP에서는 **한 번에 하나만** (`running` 또는 `booting` 상태의 에뮬레이터가 있으면 다른 항목의 `start` API가 `409 already_running` 반환).

### 대시보드 종료 시 정책

에뮬레이터/시뮬레이터는 **종료하지 않음** (재부팅 비용이 크므로). PID 정보는 파일에 유지. Appium도 종료하지 않고 다음 기동 시 `external`로 재인식. `serve.py`에 lifespan shutdown 훅 추가하여 `env_session.json` flush.

### subprocess stdout 처리

모든 long-running subprocess (Appium, 에뮬레이터)의 stdout은 **파일로 리다이렉트** (파이프 버퍼 블로킹 방지):
- Appium: `logs/appium_server.log`
- 에뮬레이터: `logs/android_emulator.log`

---

## 12. 기존 자산 재사용 맵

신규 구현 전 반드시 확인. 중복 구현 금지.

| 기존 자산 | 실제 위치 _(v0.4 경로 정정)_ | 처리 방침 |
|---|---|---|
| Appium 상태 확인 | `routes/api.py` `/api/check/appium` | `/api/env/status` 내부에서 재사용 (기존 엔드포인트 유지) |
| MJPEG 포트 확인 | `routes/api.py` `/api/check/mjpeg` | 재사용. external 상태 카드에도 경고 노출 |
| Appium 상태 함수 | `utils/system.py:21` `check_appium_status()` | PID 대조 로직만 추가해 5값 상태 판정 |
| Capture 세션 가드 | `utils/state.py:63` `is_capture_active()` | Appium 중지·에뮬레이터 중지·devices.json 갱신에 적용 |
| 파이프라인 실행 가드 | `utils/state.py` `is_pipeline_active()` | Appium 중지·devices.json 갱신에 적용 |
| adb 바이너리 탐색 | `shared.py:63` `_find_adb_bin()` | 동일 패턴으로 `_find_emulator_bin()`, `_find_appium_bin()` 추가 |
| 디바이스 파싱 함수 | `utils/system.py` `check_android_devices()`, `check_ios_simulators()` | **`utils/device_utils.py` 신규 생성 불필요** — `utils/system.py` 확장 사용 |
| 로그 tail | `shared.py SCRIPT_MAP` + `/api/run_log` | Appium 로그에 동일 패턴 적용 |
| Appium 에러 메시지 | `routes/capture.py` | "터미널에서 appium 실행" 안내 → "환경 설정 패널에서 시작" 안내로 교체 |
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
| Capture 세션 활성 중 iOS 종료 시도 | `is_capture_active()` | "Capture Studio 세션이 활성 상태입니다. 먼저 세션을 종료하세요." | Capture Studio로 이동 |
| Capture 세션 활성 중 Android 에뮬레이터 종료 시도 | `is_capture_active()` | "Android Capture Studio 세션이 활성 상태입니다. 먼저 세션을 종료하세요." | Capture Studio로 이동 |
| Capture/파이프라인 실행 중 Appium 중지 시도 | `is_capture_active()` / `is_pipeline_active()` | "Capture 세션 또는 파이프라인이 실행 중입니다. 먼저 종료하세요." | 해당 탭으로 이동 |
| `devices.json` 갱신 잠금 | `is_pipeline_active() or is_capture_active()` | "파이프라인/Capture 세션 실행 중에는 디바이스를 변경할 수 없습니다." | — |

---

## 14. 보안 및 실행 제약

- **단일 사용자 로컬 환경 전제**: 대시보드는 `127.0.0.1` 바인딩 전제. 향후 `0.0.0.0` 변경 금지
- **인자 화이트리스트**: `avd` 이름은 `emulator -list-avds` 결과에 있는 값만 허용. `udid`는 UUID 형식 검증 후 `xcrun simctl list` 결과 대조
- **`shell=False` 강제**: 모든 subprocess는 리스트 인자 방식. 문자열 셸 명령 금지
- **파일 쓰기 제약**: `config/devices.json` 갱신은 파이프라인/Capture 세션 비활성 시에만
- **macOS 전용**: `xcrun`, `simctl`, iOS 관련 기능은 macOS 전용. Phase 3 CI/CD 연동 시 재검토

---

## 15. 성공 지표 및 완료 기준

### 15-1. 정량 KPI _(v0.4 측정 조건 구체화)_

| 지표 | 목표 | 측정 조건 |
|---|---|---|
| 대시보드 접속 → Capture 세션 시작까지 터미널 명령 수 | **0개** | Appium 미설치·드라이버 미설치 상태 제외. 환경이 처음 갖춰진 직후 기준 |
| 동일 구간 소요 시간 | **5분 이내** | Appium 시작(~30초) + 에뮬레이터 스냅샷 부팅(~60초) 기준. 콜드 부팅(스냅샷 없음, ~3분) 포함 시 최대 5분. iOS 시뮬레이터는 Booted 상태 유지 가정 |
| Android 대시보드 기동 Appium으로 MJPEG 미러링 성공률 | **100%** | n=10회 시도. `--allow-insecure` 플래그 포함 검증 |
| 상태바 표시 ↔ 실제 상태 불일치 | **0건** | 시작/종료 각 10회 반복 |
| US-2 External 인계 정확도 | **100%** | 외부 Appium 감지 시 10회 중 10회 external로 표시, SIGTERM 0회 |
| US-3 JSON 미편집 디바이스 추가·삭제 성공률 | **100%** | UI 모달로 추가 5회, 삭제 5회 |

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

---

## 16. Phase 3 — 실기기 지원 상세 스펙

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

```json
{
  "android": {
    "emulator": [
      { "avd": "Pixel_7_Android15", "deviceName": "Pixel 7", "platformVersion": "15.0", "default": true }
    ],
    "real": [
      {
        "serial": "R3CN70BFZLJ",
        "model": "Galaxy S24",
        "platformVersion": "14",
        "connection": "usb",
        "default": false
      },
      {
        "serial": "192.168.1.5:5555",
        "model": "Pixel 8",
        "platformVersion": "14",
        "connection": "wifi",
        "wifi_ip": "192.168.1.5",
        "default": false
      }
    ]
  },
  "ios": {
    "simulator": [
      { "bundle_id": "com.example.app", "device_name": "iPhone 16 Pro", "platform_version": "18.0", "default": true }
    ],
    "real": [
      {
        "udid": "00008110-001A2B3C4D5E6F78",
        "deviceName": "iPhone 15 Pro",
        "platformVersion": "17.5",
        "team_id": "ABCD1234EF",
        "default": false
      }
    ]
  }
}
```

**마이그레이션**: `real` 키가 없는 기존 파일은 `real: []`로 자동 초기화. 기존 `emulator`/`simulator` 배열은 그대로 유지.

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

> **버전 대응**: 이 PRD v0.4 기준. 목업/스펙이 업데이트될 때마다 위 URL은 동일 주소에 재배포됩니다.
