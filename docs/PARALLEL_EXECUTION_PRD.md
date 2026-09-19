# 실기기 병렬 테스트 실행 — PRD

| 항목 | 값 |
|---|---|
| 문서 버전 | v0.7 (초안) |
| 작성일 | 2026-09-16 |
| 상태 | 스펙 확정 대기 — 구현 미착수 |
| v0.7 변경 | **F-2 스크린샷 경합 항목 무효화** — [EXECUTION_OBSERVABILITY_PRD.md](EXECUTION_OBSERVABILITY_PRD.md) v0.13에서 `tests/conftest.py`의 legacy 스크린샷 훅과 `state/screenshots.json`을 완전히 제거. 실패 스크린샷이 이제 run_id로 이미 격리된 `state/runs/{run_id}/artifacts/`에만 저장되므로 §6-3의 관련 코드 계획은 건너뛰어도 됨 (§4 F-2, §6-3 인라인 안내 참고) |
| v0.2 변경 | **범위 축소** — 파이프라인 실행 탭 병렬화 제외, 빠른 실행 탭 전용으로 확정 (§2-5) |
| v0.3 변경 | **동일 타입 그룹 정책 확정** (§2-2) — 실기기끼리·에뮬레이터끼리만 병렬, 혼합 금지. 에뮬레이터 병렬은 영구 제외에서 **M2로 연기**(§2-3 선행 조건) |
| v0.6 변경 | **§6-3 코드 예시 수정** (개발자 검토 반영) — 경로 재바인딩을 `main()`으로 이동, conftest는 훅 내부 동적 조회. `STATE_DIR` 동반 재바인딩 누락과 **스크린샷 PNG 경로 충돌**(F-2 신규 항목)을 함께 반영 |
| v0.5 변경 | **Android + iOS 동시 실행 영구 제외 최종 확정** (§2-4) — 한 run 혼합·플랫폼별 독립 run 동시 진행 **모두 제외**, 별도 검토 안 함. v0.4에서 검토했던 (B) 지지안과 그에 딸린 Q-5·Q-6·전방호환 설계를 철회 |
| 관련 문서 | [ENV_SETUP_PRD.md](ENV_SETUP_PRD.md) §16 (Phase 3 실기기), [LOCATOR_HEALING.md](LOCATOR_HEALING.md) |
| 선행 조건 | ENV_SETUP_PRD M2.0 마이그레이션 완료 (`devices.json` 배열 스키마) |

---

## 1. 배경 및 목적

### 1-1. 현재 상태

대시보드의 두 실행 경로 모두 **디바이스 1개 · 순차 실행**입니다.

| 경로 | 엔드포인트 | 디바이스 선택 | 실행 형태 |
|---|---|---|---|
| 파이프라인 실행 탭 | `POST /api/run_all` | 라디오 1개 (`_selectedDevice`) | TC 폴더를 12초 간격으로 순차 실행 |
| 빠른 실행 탭 | `POST /api/run_test` | 라디오 1개 (`_selectedDevice`) | 테스트 파일/폴더 1건 실행 |

`agents/dashboard/dashboard.html:1959`의 `_selectedDevice`는 단일 객체이며, `getSelectedDeviceParams()`가 `{mode, device_udid}` 한 쌍만 반환합니다.

### 1-2. 문제

실기기 3대를 USB로 연결해 둔 환경에서 같은 회귀 TC 세트를 돌리려면 QA가 대시보드에서 디바이스를 바꿔가며 3번 실행해야 합니다. TC 폴더 하나가 약 8분이면 3대 검증에 24분 + 조작 대기 시간이 듭니다. 기기별 결과 비교도 리포트 파일을 수동으로 대조해야 합니다.

### 1-3. 목적

**빠른 실행 탭에서, 연결된 Android 실기기 여러 대에 같은 테스트 세트를 동시에 실행하고 디바이스별 결과를 한 화면에서 비교한다.**

기대 효과:
- 실행 시간: N대 검증 시 순차 대비 약 1/N (N ≤ 3 기준)
- 기기별 차이(해상도·OS 버전·벤더 스킨) 발생 TC를 한 번의 실행으로 식별

### 1-4. 비목적 (이 기능이 해결하지 않는 것)

- 테스트 1건의 실행 속도 개선 — TC 분할·샤딩은 다루지 않습니다
- 파이프라인 실행 탭의 변경 — 코드 생성 흐름은 현행 유지 (§2-5)
- CI/CD 연동 — 대시보드 UI 경로만 다룹니다
- 디바이스 팜·원격 실행 — `--address 127.0.0.1` 고정 정책 유지 (ENV_SETUP_PRD §14)

---

## 2. 범위

### 2-1. 포함

| 항목 | 값 |
|---|---|
| 플랫폼 | Android |
| 디바이스 모드 | **동일 타입 그룹 내에서만 병렬** — 실기기끼리 또는 에뮬레이터끼리. **혼합 금지** (§2-2) |
| 모드별 지원 시점 | M1: `real_device` · M2: `emulator` (선행 조건 있음) |
| 동시 실행 수 | 기본 최대 3대 (설정으로 상향 가능, 하드 상한 4) |
| 병렬 대상 단계 | `execute` (05_execute.py) **만** |
| 실행 경로 | **빠른 실행 탭 전용** — 파이프라인 실행 탭은 순차 유지 |

### 2-2. 동일 타입 그룹 정책 _(확정)_

**한 번의 병렬 실행에 참여하는 디바이스는 모두 같은 `mode`여야 합니다.**

| 조합 | 허용 | 비고 |
|---|---|---|
| 실기기 + 실기기 | ✅ | M1 |
| 에뮬레이터 + 에뮬레이터 | ✅ | M2 — §2-3 선행 조건 해소 후 |
| 실기기 + 에뮬레이터 | ❌ | `400 mixed_device_mode` |
| Android + iOS | ❌ | `400 invalid_platform`. **영구 제외** — 한 run 혼합도, 플랫폼별 독립 run 동시 진행도 지원하지 않습니다 (§2-4) |

**혼합을 금지하는 이유**

1. **자원 모델이 다릅니다.** 에뮬레이터는 호스트 CPU/RAM을 공유하므로 동시 실행 수가 호스트 성능에 종속되고, 실기기는 USB 대역폭과 adb 커넥션에 종속됩니다. 두 종류를 섞으면 "최대 3대" 같은 단일 상한이 의미를 잃습니다.
2. **결과 비교의 전제가 깨집니다.** 병렬 실행의 핵심 가치는 §7-3의 기기 종속 실패 식별입니다. 에뮬레이터와 실기기는 성능·입력 지연·벤더 스킨이 근본적으로 달라, 둘 사이의 결과 차이는 "기기 종속 버그"가 아니라 "환경 종류 차이"로 나옵니다. 비교 매트릭스의 신호가 노이즈가 됩니다.
3. **포트 할당 규칙이 다릅니다.** 에뮬레이터는 `systemPort`에 더해 `mjpegServerPort`까지 슬롯별로 분리해야 하고, 실기기는 `mjpegServerPort`를 갖지 않습니다 (§6-4). 한 요청 안에서 두 규칙을 분기시키면 할당기가 불필요하게 복잡해집니다.

### 2-3. 에뮬레이터 병렬 선행 조건 _(M2)_

에뮬레이터끼리의 병렬은 정책상 허용이지만, 아래 3건이 해소되기 전에는 구현하지 않습니다.

| # | 항목 | 현재 상태 |
|---|---|---|
| E-1 | `mjpegServerPort` 슬롯별 분리 | `config/devices.json`의 emulator 항목에 `mjpegServerPort: 8093`이 flat하게 고정. MJPEG 서버는 호스트의 단일 포트를 점유하므로 2대가 동시에 8093을 요구해 충돌합니다. `systemPort`와 동일하게 **런타임 슬롯 주입**으로 전환 필요 (8093 + slot) |
| E-2 | 다중 에뮬레이터 serial 식별 | `/api/devices`가 `emulator-` 접두사로 **첫 매칭 1개만** 가져옵니다 (`pipeline.py:69`). 2대 이상을 구분하지 못해 선택 UI에 제대로 뜨지 않습니다 |
| E-3 | 다중 AVD 동시 부팅 | `POST /api/env/android/avd/start`가 다른 에뮬레이터 실행 중이면 `409 already_running`을 반환합니다 (ENV_SETUP_PRD §6). 2대 이상 동시 부팅을 허용하도록 가드 완화 + `devices.json`에 AVD 항목 2개 이상 등록 필요 |

E-1은 `config/devices.json` 스키마와 Capture Studio 미러링에 함께 걸리고(`capture.py:128-130` MJPEG 하드코딩 — ENV_SETUP_PRD M2.0-4가 이미 다루는 항목), E-3은 ENV_SETUP_PRD의 에뮬레이터 상태 모델 변경을 동반합니다. **두 PRD의 조율이 필요하므로 M1과 분리합니다.**

### 2-4. Android + iOS 동시 실행 — ❌ 영구 제외 _(v0.5 최종 확정)_

**한 번의 실행은 언제나 단일 플랫폼입니다.** 아래 두 형태 모두 제외하며, 후속 마일스톤·별도 안건으로도 다루지 않습니다.

| 형태 | 판정 |
|---|---|
| (A) 한 run 안에 Android + iOS 디바이스 혼합 | ❌ 영구 제외 — `400 invalid_platform` |
| (B) Android run과 iOS run을 각각 독립 run_id로 동시 진행 | ❌ 범위 제외 — 별도 검토하지 않음 |

**근거**

1. **(A)는 비교 매트릭스의 공통 축이 없습니다.** 병렬 실행의 핵심 가치는 §7-3의 TC × 디바이스 매트릭스로 기기 종속 실패를 찾는 것인데, 두 플랫폼은 TC 파일 자체가 분리돼 있습니다 — `testcases/android/{group}/` vs `testcases/ios/{group}/`, `tests/generated/android/` vs `tests/generated/ios/`. 공유 TC가 0건이므로 매트릭스는 겹치지 않는 두 블록을 나란히 붙인 모양이 됩니다. 한 run으로 묶어서 얻는 분석적 이득이 없습니다.
2. **플랫폼은 이 제품 전반의 최상위 파티션입니다.** `config/locators.json`이 `targets.{tc_slug}.{selector_key}.{platform}` 구조로 갈리고(`06_heal.py:517`, `06_heal.py:556`), TC 입력·생성 코드·리포트 경로가 모두 플랫폼으로 먼저 나뉩니다. 실행 단위가 이 파티션을 가로지를 이유가 없습니다.
3. **(B)는 검증 신뢰도 리스크가 이득보다 큽니다.** 같은 Mac 호스트에서 iOS Simulator와 Android 세션이 동시에 돌면 CPU·메모리 경합으로 타이밍 민감 TC(`WebDriverWait`, `_time.sleep` 기반 대기)가 flaky해질 수 있고, 그때 "앱 버그"와 "동시 실행 부작용"을 구분할 방법이 없습니다. QA가 결과를 신뢰할 수 없는 실행 모드는 QA 자동화 도구에서 이득이 아닙니다.
4. **범위 규율.** 이 PRD의 "병렬"은 *같은 TC를 여러 기기에* 돌리는 것입니다. (B)는 *다른 TC를 다른 플랫폼에* 돌리는 별개 축이며, M1이 아직 미구현(F-1·F-2 블로커 미해소)인 상태에서 축을 늘리지 않습니다.

**구현 지침**: `_running` 키·`index.json`·`last_parallel_run`을 플랫폼 동시성 대비로 미리 일반화하지 마세요. 쓰지 않을 유연성은 비용입니다. C-4(동시 병렬 run 1개)는 플랫폼 구분 없는 전역 제약으로 구현합니다.

### 2-5. 제외 — 근거 포함

| 제외 항목 | 근거 |
|---|---|
| **파이프라인 실행 탭 병렬** | 파이프라인 탭의 주된 용도는 `analyze → generate → lint`로 **테스트 코드를 만들어내는 것**이고, `execute`는 생성 결과가 돌아가는지 확인하는 검증 성격입니다. 코드 생성 3단계는 디바이스와 무관해 병렬화할 대상이 아니며(동일 경로 동시 쓰기), 남는 `execute` 1단계만 병렬화하면 빠른 실행 탭과 기능이 중복됩니다. 회귀 세트를 여러 기기에 돌리는 실제 수요는 **이미 생성된 코드를 실행하는** 빠른 실행 탭에 있습니다. 파이프라인 탭은 기존 단일 디바이스 순차 실행을 그대로 유지합니다. |
| **에뮬레이터 + 실기기 혼합** | §2-2 참조. 자원 모델·결과 비교 전제·포트 할당 규칙이 모두 다릅니다. 영구 제외이며 후속 마일스톤에서도 다루지 않습니다. |
| **에뮬레이터 병렬 (M1 한정)** | 정책상 허용이나 §2-3의 E-1 ~ E-3 해소가 선행되어야 합니다. **M2로 연기**이며 영구 제외가 아닙니다. |
| **iOS 병렬 (시뮬레이터)** | XCUITest는 시뮬레이터당 세션 1개만 허용합니다 (CLAUDE.md 명시). 시뮬레이터 2대 병렬은 `wdaLocalPort` 분리 + 시뮬레이터별 WDA 빌드가 선행되어야 하며, 별도 검토 대상입니다. |
| **iOS 병렬 (실기기)** | WDA provisioning profile·Team ID 관리가 ENV_SETUP_PRD §16-3에서 아직 초안 상태입니다. 선행 스펙 미확정. |
| **`analyze` / `generate` / `lint` 병렬** | `02_generate.py`는 `tests/generated/{platform}/{group}/*.py`에 씁니다. N개 프로세스가 동일 경로에 동시 쓰기 → 파일 손상. 이 단계들은 **디바이스와 무관한 산출물**이므로 애초에 병렬 실행 대상이 아닙니다. |
| **`heal` 병렬** | `06_heal.py`는 `config/locators.json`(`save_registry`, 06_heal.py:525/563)과 생성 `.py` 파일(06_heal.py:651)을 직접 rewrite합니다. 병렬 healing은 registry 경합과 서로 다른 기기 기준 locator의 덮어쓰기를 유발합니다. M1에서 병렬 실행 시 heal은 **비활성**이며, M2에서 순차 fallback으로 재도입합니다. |
| **pytest-xdist 도입** | 미설치 상태이며, 디바이스별로 `DEVICE_UDID`·`systemPort` 등 **프로세스 단위 환경변수**가 달라야 합니다. xdist worker는 환경변수를 공유하므로 적합하지 않습니다. 프로세스 레벨 병렬(디바이스당 `05_execute.py` 1개)을 채택합니다. |
| **Android + iOS 동시 실행 (한 run 혼합 · 플랫폼별 독립 run 동시 진행 모두)** | §2-4 참조. **영구 제외 — 후속 마일스톤에서도 다루지 않습니다.** 한 번의 실행은 언제나 단일 플랫폼입니다. |

---

## 3. 사용자 스토리

| ID | 스토리 | 완료 기준 |
|---|---|---|
| **PS-1** | QA 엔지니어로서 빠른 실행 탭의 실기기 목록에서 **여러 대를 체크박스로 선택**할 수 있다 | 빠른 실행 탭 실기기 카드가 체크박스로 전환 · 다중 선택 상태 유지 · 에뮬레이터 카드와 파이프라인 탭 피커는 단일 선택(라디오) 유지 |
| **PS-2** | QA 엔지니어로서 **빠른 실행 탭에서** 선택한 실기기들에 같은 테스트 폴더를 동시에 실행할 수 있다 | 1회 클릭으로 N개 프로세스 시작 · 각 프로세스가 지정한 udid의 기기에서만 동작 |
| **PS-3** | QA 엔지니어로서 실행 중 **디바이스별 진행 상황을 실시간으로** 볼 수 있다 | 디바이스별 카드에 상태(대기/실행 중/성공/실패)·경과 시간·현재 테스트명 표시 |
| **PS-4** | QA 엔지니어로서 실행 후 **디바이스별 결과를 나란히 비교**할 수 있다 | 디바이스별 pass/fail 집계 + 전체 디바이스에서 실패한 TC와 일부 디바이스에서만 실패한 TC 구분 표시 |
| **PS-5** | QA 엔지니어로서 **특정 디바이스 1대만 취소**하거나 전체를 취소할 수 있다 | 디바이스 카드의 취소 버튼 · 전체 취소 버튼 · 취소된 기기 외 나머지는 계속 실행 |
| **PS-6** | QA 엔지니어로서 **디바이스별 상세 로그**를 개별로 열어볼 수 있다 | 디바이스 카드 클릭 → 해당 기기 로그만 표시 |
| **PS-7** | QA 엔지니어로서 **에뮬레이터와 실기기를 실수로 섞어 실행하지 않는다** | 한쪽 선택 시 다른 섹션이 비활성화되고 사유가 표시됨 · 선택이 말없이 사라지지 않음 · API 직접 호출 시 `400 mixed_device_mode` |

---

## 4. 선행 기술 이슈 — 구현 전 반드시 해소

병렬 실행을 얹기 전에 현재 코드의 다음 항목이 먼저 수정되어야 합니다. **이 중 F-1·F-2는 병렬 실행의 정합성을 직접 깨뜨리는 블로커입니다.**

### F-1. UiAutomator2 `systemPort` 미할당 — 🔴 블로커

저장소 전체에 `systemPort` 캡이 **존재하지 않습니다** (`scripts/`, `config/devices.json`, 생성 코드 전부 확인). UiAutomator2 드라이버는 미지정 시 기본 포트 8200을 사용하며, 동일 Appium 서버에서 2개 세션이 동시에 8200을 요구하면 두 번째 세션이 초기화 실패합니다.

**해결 방향**: 디바이스 슬롯별 `systemPort` 동적 할당 (§6-3).
`systemPort`는 Appium 정식 cap이므로 camelCase이며, `_NON_APPIUM_KEYS` 필터(`02_generate.py:398`)에 걸리지 않고 그대로 caps에 전달됩니다. `devices.json`에 고정값으로 박지 않고 **런타임 주입**합니다 — 고정하면 같은 기기를 다른 슬롯에서 쓸 때 재충돌합니다.

### F-2. 공유 산출물 경로 경합 — 🔴 블로커

`05_execute.py`가 쓰는 경로가 전부 고정입니다.

| 경로 | 위치 | 병렬 시 문제 |
|---|---|---|
| `state/pytest_report.xml` | `05_execute.py:38` | 마지막 완료 프로세스가 덮어씀 |
| `state/pytest_report.json` | `05_execute.py:39` | 동일 |
| `state/pipeline.json` | `05_execute.py:36` | `load_state()` → 수정 → `save_state()` read-modify-write 경합. `execute_results`가 1개 기기 것만 남음 |
| ~~`state/screenshots.json`~~ | ~~`tests/conftest.py:13`~~ | **(2026-09-17 제거됨)** legacy 캡처 훅과 함께 삭제. 실패 스크린샷은 `state/runs/{run_id}/artifacts/...`에만 저장되며 run_id가 이미 격리 단위라 경합 없음 |
| ~~`reports/screenshots/{platform}/{nodeid}.png`~~ | ~~`tests/conftest.py:60-63`~~ | **(2026-09-17 제거됨)** 위와 동일 이유로 해당 없음 |
| `logs/run_execute.txt` | `shared.py` `SCRIPT_MAP` | 여러 프로세스 stdout이 한 파일에 섞임 |

**해결 방향**: 런별·디바이스별 출력 네임스페이스 (§6-2) + 스크린샷 디렉토리에 udid 세그먼트 추가.

**구현 가이드 (§6-3에 코드 포함)**

- `05_execute.py`: 경로 상수 재바인딩을 **모듈 레벨이 아니라 `main()` 첫 부분**에서 수행합니다. `STATE_FILE`만이 아니라 **`STATE_DIR`까지 함께** 재바인딩해야 합니다 — `save_state()`가 `STATE_DIR.mkdir()` 후 `STATE_FILE`에 쓰므로(`05_execute.py:104-106`) 둘이 어긋나면 write가 실패합니다.
- `tests/conftest.py`: `SCREENSHOTS_JSON` 모듈 상수를 없애고 **훅 내부에서 `QA_RUN_DIR`을 매번 읽는** 헬퍼로 전환합니다.
- 두 파일 모두 `QA_RUN_DIR` 미설정 시 기존 `state/` 경로로 폴백해야 합니다 (CLI 직접 실행 보존).

### F-3. `_running` 슬롯 충돌 — 🟠 필수

`shared.py`의 `_running: dict[str, Popen]`이 `_running["execute"]` 단일 슬롯입니다 (`pipeline.py:193`). N개 프로세스가 같은 키에 덮어써 취소·상태조회가 마지막 1개만 가리킵니다. `/api/cancel`도 `step` 문자열만 받습니다 (`pipeline.py:496`).

### F-4. 디바이스 가드가 udid를 검증하지 않음 — 🟠 필수

`05_execute.py:53 check_android_device()`는 `adb devices`에 **아무 기기나 1대라도** 있으면 통과합니다. `--udid`로 지정한 기기가 실제로 연결되어 있는지 확인하지 않아, 케이블이 빠진 기기에 대해서도 실행을 시작하고 Appium 세션 생성 단계에서야 실패합니다.

### F-5. `/api/devices`의 실기기 `connected` 판정 오류 — 🟠 필수

`pipeline.py:82`:

```python
connected = udid in connected_serials if udid else bool(
    next((s for s in connected_serials if not s.startswith("emulator-")), "")
)
```

`udid`가 빈 문자열인 실기기 항목은 **아무 실기기나 하나 붙어 있으면 연결됨으로 표시**됩니다. 실기기 2대 이상 환경에서 오판을 일으킵니다. 병렬 선택 UI의 입력이 되는 값이므로 `udid` 필수화가 필요합니다.

### F-6. `02_generate.py --device-udid`가 동작하지 않음 — 🟡 정리

`02_generate.py:1009`에 `--device-udid` 인자가 선언되어 있으나 `args.device_udid`를 읽는 코드가 **없습니다**. `pipeline.py:251`이 이 인자를 전달하지만 조용히 무시됩니다.

현재 실제 동작하는 경로는 생성 코드 템플릿에 내장된 `_get_device()`의 `os.environ.get("DEVICE_UDID")` 조회(`02_generate.py:386`)입니다. 병렬 실행이 의존하는 경로가 이쪽이므로 **env var 경로를 정본으로 확정**하고 `--device-udid` 인자는 제거합니다.

### F-7. 생성 코드 템플릿 2종의 분기 — 🟡 정리

| 생성원 | `_get_device` 형태 | udid 오버라이드 |
|---|---|---|
| `02_generate.py` (`02_generate.py:384`) | 템플릿에 `os.environ.get("DEVICE_UDID")` 내장 | 자체 처리 |
| Capture Studio (`CAPTURE_TEMPLATE_VERSION = 2`) | env 조회 없음 (`tc_settings_battery.py:26`) | `tests/generated/conftest.py`의 monkeypatch에 의존 |

두 경로 모두 `tests/generated/conftest.py`의 패치가 있으면 동작하지만, **`systemPort` 주입 지점을 conftest 한 곳으로 통일**하면 Capture Studio 템플릿을 건드리지 않고 두 계열을 동시에 지원할 수 있습니다. → conftest 단일 주입 채택 (§6-3).

---

## 5. 실행 아키텍처

### 5-1. 병렬 모델: 프로세스 레벨 fan-out

```
대시보드
  └─ POST /api/run_parallel
       └─ asyncio.gather / ThreadPool (N ≤ 3)
            ├─ Popen: 05_execute.py --platform android --mode real_device --udid A
            │           env: DEVICE_UDID=A  DEVICE_SYSTEM_PORT=8200  QA_RUN_DIR=.../A
            ├─ Popen: 05_execute.py ... --udid B
            │           env: DEVICE_UDID=B  DEVICE_SYSTEM_PORT=8210  QA_RUN_DIR=.../B
            └─ Popen: 05_execute.py ... --udid C
                        env: DEVICE_UDID=C  DEVICE_SYSTEM_PORT=8220  QA_RUN_DIR=.../C
                                    │
                        단일 Appium 서버 (127.0.0.1:4723) — 세션 3개 동시 유지
```

Appium 서버는 1개를 그대로 유지합니다. 서버 인스턴스를 늘리지 않는 이유: ENV_SETUP_PRD의 Appium 5값 상태 모델(`stopped`/`starting`/`managed`/`external`/`error`)이 단일 서버를 전제로 하며, 서버 다중화는 그 상태 모델 전체를 다시 설계해야 합니다. UiAutomator2는 세션별 `systemPort`만 분리하면 단일 서버에서 병렬 세션을 지원합니다.

### 5-2. 두 탭의 역할 분리

| 탭 | 주 용도 | 실행 형태 | 이 PRD의 변경 |
|---|---|---|---|
| 파이프라인 실행 | `analyze → generate → lint`로 **테스트 코드를 생성**하고, `execute`로 생성 결과를 1회 검증 | 디바이스 1대 · 순차 | **변경 없음** |
| 빠른 실행 | **이미 생성된 코드**를 반복 실행 (회귀 확인) | 실기기 2대 이상 선택 시 병렬 | 병렬 추가 |

파이프라인 탭을 병렬 대상에서 제외하는 이유는 §2-5 첫 행에 있습니다. 요약하면, 그 탭에서 병렬화 가능한 단계는 `execute` 하나뿐이고 그것은 빠른 실행 탭이 이미 담당하는 일입니다. 같은 기능을 두 탭에 중복 구현하면 진행 UI·결과 집계·취소 로직을 두 벌 유지해야 합니다.

**기기별 locator 차이에 대한 전제**: `analyze`는 파이프라인 탭에서 기준 디바이스 1대의 hierarchy만 수집하며, `config/locators.json`은 기기 독립적인 것이 전제입니다. 기기별로 locator가 갈리는 상황은 **병렬 실행이 찾아내야 할 버그**이지 자동으로 흡수할 대상이 아닙니다 (Q-3).

### 5-3. 동시 실행 수 제한

기본 3, 하드 상한 4. 근거:
- 단일 Appium 서버의 UiAutomator2 세션 동시 유지는 실측 검증이 필요한 영역이며, CLAUDE.md가 이미 "3개 이상 순차 실행 시 3번째 이후 세션 초기화 실패"를 기록하고 있습니다
- `adb` 서버가 다수 기기에 동시 명령을 보낼 때의 안정성도 미검증

상한 초과 요청 시 **큐잉하지 않고 400으로 거부**합니다 — 큐잉은 "동시 실행"이라는 기능 정의를 흐리고 진행 UI를 복잡하게 만듭니다.

---

## 6. 기술 요구사항 — 백엔드

### 6-1. 신규/변경 엔드포인트

#### `POST /api/run_parallel`

요청:
```json
{
  "platform": "android",
  "mode": "real_device",
  "devices": ["HA1XM5MS", "R3CN70BFZLJ"],
  "test_folder": "settings",
  "test_file": null,
  "heal": false
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `platform` | `"android"` | android 고정 |
| `mode` | `"real_device"` \| `"emulator"` | **요청당 단일값.** 이 요청의 모든 디바이스가 이 모드에 속해야 합니다. M1은 `real_device`만 허용, `emulator`는 M2부터 |
| `devices` | `string[]` | udid/serial 배열. 1~4개. 중복 불가. **전원이 `mode`에 해당하는 항목**이어야 함 |
| `test_folder` / `test_file` | `string?` | 둘 중 하나 필수. 기존 `/api/run_test`와 동일한 경로 검증 |
| `heal` | `bool` | M1은 `false` 강제. `true` 전달 시 400 |

이 엔드포인트는 **빠른 실행 탭 전용**이며 `05_execute.py`만 호출합니다. 파이프라인 단계(`analyze`/`generate`/`lint`/`heal`)는 다루지 않습니다.

응답 `202`:
```json
{
  "ok": true,
  "run_id": "par_android_20260916_204512",
  "devices": [
    {"udid": "HA1XM5MS",    "deviceName": "Lenovo TB320FC", "system_port": 8200, "log": "parallel/par_android_20260916_204512/HA1XM5MS.txt"},
    {"udid": "R3CN70BFZLJ", "deviceName": "Galaxy S24",     "system_port": 8210, "log": "parallel/par_android_20260916_204512/R3CN70BFZLJ.txt"}
  ]
}
```

**`mode`는 요청 본문에서 단일 스칼라입니다.** 디바이스마다 mode를 싣는 구조(`[{udid, mode}, ...]`)를 채택하지 않는 이유는, 그 구조 자체가 혼합 요청을 표현 가능하게 만들어 검증으로만 막아야 하기 때문입니다. 스키마 수준에서 혼합이 불가능하도록 단일 `mode` + udid 배열로 고정합니다.

검증 순서(첫 실패에서 중단):

1. `platform != "android"` → `400 invalid_platform`
2. `mode`가 `"real_device"`/`"emulator"` 외 → `400 invalid_mode`
3. `mode == "emulator"` 이고 M2 미완료 → `400 emulator_parallel_not_ready` (§2-3 선행 조건 안내 포함)
4. `len(devices) < 1` → `400 no_device_selected`
5. `len(devices) > 4` → `400 max_parallel_exceeded`
6. 중복 udid → `400 duplicate_device`
7. **모드 일치 검증** — 각 udid를 `config/devices.json`에서 조회해 소속 모드를 판정하고, `mode`와 다른 항목이 하나라도 있으면 → `400 mixed_device_mode` (위반 udid와 그 실제 모드를 응답에 포함). serial 형태로도 교차 확인합니다: `emulator-` 접두사 serial이 `mode="real_device"` 요청에 섞이면 동일하게 거부
8. `adb devices`에 없는 udid → `409 device_not_connected` (누락 udid 목록 포함)
9. `is_capture_active("android")` → `409 capture_session_active`
10. 진행 중 병렬 run 존재 → `409 parallel_run_active`
11. 경로 검증: 기존 `/api/run_test`의 `..`·절대경로·`tests/generated/{platform}` 하위 여부 검사 재사용

7번은 UI가 이미 상호 배타 선택(§7-1)을 강제하므로 정상 경로에서는 발생하지 않습니다. API 직접 호출과 UI 상태 꼬임에 대한 서버 측 방어선입니다.

#### `GET /api/parallel/{run_id}`

```json
{
  "ok": true,
  "run_id": "par_android_20260916_204512",
  "status": "running",
  "started_at": "2026-09-16T20:45:12",
  "finished_at": null,
  "devices": [
    {
      "udid": "HA1XM5MS", "deviceName": "Lenovo TB320FC",
      "status": "running", "returncode": null,
      "summary": {"total": 12, "passed": 7, "failed": 1},
      "current_test": "tests/generated/android/settings/tc_settings_battery.py::test_open_battery",
      "elapsed_sec": 143
    }
  ],
  "aggregate": {
    "total_devices": 2, "completed": 0, "failed_devices": 0,
    "common_failures": [], "device_specific_failures": []
  }
}
```

`status` 값: `pending` / `running` / `passed` / `failed` / `cancelled` / `error`

#### `POST /api/parallel/{run_id}/cancel`

```json
{ "udid": "HA1XM5MS" }
```
`udid` 생략 시 전체 취소. 기존 `/api/cancel`의 `os.killpg(os.getpgid(pid), 15)` 방식을 재사용합니다 (`pipeline.py:505` — `preexec_fn=os.setsid`로 프로세스 그룹이 이미 분리되어 있음).

#### `GET /api/parallel/{run_id}/log?udid=...`

기존 `/api/run_log` 응답 형태(`{ok, log, done, exit_code, result}`)를 유지하되 디바이스 스코프로 반환합니다.

#### `GET /api/devices` — 변경

실기기 항목에 udid 없을 때의 fallback 제거 (F-5). `udid`가 빈 항목은 `connected: false` + `"needs_udid": true`로 반환하고, UI가 "udid 미등록 — ENV Setup에서 등록 필요"로 안내합니다.

### 6-2. 출력 네임스페이스

```text
state/parallel/{run_id}/
  index.json                       # 집계 상태 — 진행 UI의 단일 소스
  {udid}/
    pipeline.json                  # 05_execute.py의 state 파일
    pytest_report.json
    pytest_report.xml
    screenshots.json
logs/parallel/{run_id}/
  {udid}.txt
tests/reports/
  report_android_{stamp}.html      # 기존 경로 유지 (stamp가 ms 단위라 충돌 없음)
  compare_{run_id}.html            # M2 — 디바이스 비교 리포트
```

`udid`는 경로 세그먼트가 되므로 `[^A-Za-z0-9._:-]`를 `_`로 치환해 sanitize합니다 (WiFi ADB serial `192.168.1.5:5555` 형태 대비).

`index.json` 스키마:
```json
{
  "run_id": "par_android_20260916_204512",
  "platform": "android",
  "mode": "real_device",
  "target": {"test_folder": "settings"},
  "started_at": "2026-09-16T20:45:12",
  "finished_at": null,
  "status": "running",
  "devices": [
    {"udid": "HA1XM5MS", "deviceName": "Lenovo TB320FC", "system_port": 8200,
     "pid": 48213, "status": "running", "returncode": null,
     "started_at": "2026-09-16T20:45:13", "finished_at": null}
  ]
}
```

`index.json` 쓰기는 `save_devices_json()`과 동일한 원자적 교체 패턴을 따릅니다 — `.json.tmp` 기록 후 `Path.replace()`. 쓰기 주체는 대시보드 프로세스 하나이므로 파일 락은 불필요하지만, 대시보드 내부에서는 `threading.Lock`으로 직렬화합니다.

### 6-3. 환경변수 계약 — 신규

기존 `DEVICE_MODE` / `DEVICE_UDID` 계약을 확장합니다.

| 환경변수 | 소비 지점 | 설명 |
|---|---|---|
| `DEVICE_MODE` | `tests/generated/conftest.py`, 생성 코드 `_get_device` | 기존 |
| `DEVICE_UDID` | 동일 | 기존 |
| **`DEVICE_SYSTEM_PORT`** | `tests/generated/conftest.py` | UiAutomator2 세션 포트. conftest가 `_get_device` 반환 dict에 `systemPort`로 주입 |
| **`QA_RUN_DIR`** | `05_execute.py`, `tests/conftest.py` | 산출물 루트. 미설정 시 기존 `state/` 경로로 폴백 |

**폴백이 필수**입니다 — CLI에서 `python scripts/05_execute.py --platform android`를 직접 실행하는 기존 워크플로(CLAUDE.md "실행 명령")가 깨지면 안 됩니다.

#### `05_execute.py` — 경로 재바인딩은 `main()` 첫 부분에서

```python
# 모듈 레벨: 폴백 경로로 그대로 둔다 (기존 코드 유지)
STATE_DIR        = ROOT / "state"
STATE_FILE       = STATE_DIR / "pipeline.json"
JUNIT_XML        = STATE_DIR / "pytest_report.xml"
JSON_REPORT      = STATE_DIR / "pytest_report.json"
SCREENSHOTS_JSON = STATE_DIR / "screenshots.json"


def _resolve_run_dir() -> Path:
    raw = os.environ.get("QA_RUN_DIR", "").strip()
    if not raw:
        return STATE_DIR
    run_dir = Path(raw)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    run_dir.mkdir(parents=True, exist_ok=True)   # 반드시 생성 — 아래 write가 의존
    return run_dir


def main():
    global STATE_DIR, STATE_FILE, JUNIT_XML, JSON_REPORT, SCREENSHOTS_JSON
    STATE_DIR        = _resolve_run_dir()        # ← main() 첫 줄
    STATE_FILE       = STATE_DIR / "pipeline.json"
    JUNIT_XML        = STATE_DIR / "pytest_report.xml"
    JSON_REPORT      = STATE_DIR / "pytest_report.json"
    SCREENSHOTS_JSON = STATE_DIR / "screenshots.json"
    ...
```

**왜 모듈 레벨이 아니라 `main()`인가** — 환경변수 가시성 문제는 아닙니다. `05_execute.py`는 항상 `Popen(..., env=run_env)`로 기동되는 독립 프로세스이고 어디서도 모듈로 import되지 않으므로(`shared.py:195`·`pipeline.py:447`가 스크립트 경로로만 참조), 자식 프로세스는 **import 시점에 이미 `QA_RUN_DIR`을 봅니다**. 실제 이유는 다음 셋입니다.

1. **선언 순서 함정.** 모듈 레벨 상수가 헬퍼 함수보다 위에 오면 `NameError`가 납니다. 상수 블록과 함수 정의의 상대 위치에 정합성이 묶이는 코드는 리팩터링에 취약합니다.
2. **`mkdir` 부수효과의 위치.** `_resolve_run_dir()`은 디렉토리를 생성합니다. import만으로 파일시스템을 건드리면 `--help`나 인자 검증 실패 시에도 빈 디렉토리가 생깁니다.
3. **`STATE_DIR` 자체를 함께 재바인딩해야 합니다.** 현재 `save_state()`가 `STATE_DIR.mkdir(...)` 후 `STATE_FILE`에 씁니다 (`05_execute.py:104-106`). `STATE_FILE`만 run dir로 옮기고 `STATE_DIR`을 그대로 두면 **mkdir 대상과 쓰기 대상이 어긋나** run dir이 없을 때 write가 실패합니다. 한 곳에서 같이 묶어야 빠뜨리지 않습니다.

#### `tests/conftest.py` — 훅 내부에서 동적 결정 _(2026-09-17 무효화 — 아래 참고)_

> **무효화 안내**: 이 하위 섹션(`_screenshots_json()`, `_load_screenshots()`/`_save_screenshots()`, 다음 하위 섹션의 `_screenshots_dir()` 포함)이 다루는 `state/screenshots.json`과 `reports/screenshots/{platform}/{nodeid}.png`는 [EXECUTION_OBSERVABILITY_PRD.md](EXECUTION_OBSERVABILITY_PRD.md) v0.13에서 `tests/conftest.py`의 legacy 캡처 훅과 함께 **완전히 제거**되었습니다. 실패 스크린샷은 이제 `state/runs/{run_id}/artifacts/{node_slug}/attempt{n}/screenshot.png`에만 저장되며, `run_id`가 이미 실행 단위로 고유하므로 **이 F-2 경합 자체가 더 이상 존재하지 않습니다** — 별도 udid 세그먼트 분리가 필요 없습니다. 이 PRD를 실제로 구현할 때는 아래 두 코드 블록을 건너뛰고, `state/pytest_report.*`·`state/pipeline.json`·`logs/run_execute.txt` 경합만 §6-3의 나머지 부분대로 처리하세요.

상수 방식 대신 훅이 호출될 때마다 읽습니다. (참고용으로 남긴 원안 — 위 안내 참고)

```python
def _run_dir() -> Path:
    raw = os.environ.get("QA_RUN_DIR", "").strip()
    if not raw:
        return ROOT / "state"
    d = Path(raw)
    return d if d.is_absolute() else ROOT / d


def _screenshots_json() -> Path:
    return _run_dir() / "screenshots.json"
```

`_load_screenshots()` / `_save_screenshots()`가 모듈 상수 `SCREENSHOTS_JSON` 대신 `_screenshots_json()`을 호출하도록 바꿉니다. pytest는 conftest를 여러 경로에서 재사용하고 import 시점이 실행 컨텍스트에 따라 달라질 수 있으므로, 상수로 굳히지 않는 편이 안전합니다.

#### 스크린샷 PNG 경로도 run별로 분리 — F-2에 누락돼 있던 항목

`_save_screenshots()`만 고치면 **매핑 JSON은 격리되지만 PNG 파일 자체는 여전히 충돌합니다.** `_screenshots_dir()`이 `reports/screenshots/{platform}/`을 반환하고 파일명이 `item.nodeid`에서 파생되므로(`tests/conftest.py:60-63`), 같은 TC를 2대에서 병렬 실행하면 **동일한 `safe_name.png`에 양쪽이 덮어씁니다.** 실패 스크린샷이 어느 기기 것인지 알 수 없게 됩니다.

```python
def _screenshots_dir(nodeid: str) -> Path:
    ...
    d = ROOT / "reports" / "screenshots" / platform
    udid = os.environ.get("DEVICE_UDID", "").strip()
    if udid:
        d = d / _sanitize(udid)      # 병렬 실행 시 기기별 분리
    d.mkdir(parents=True, exist_ok=True)
    return d
```

`_sanitize()`는 §6-2의 udid 경로 치환 규칙(`[^A-Za-z0-9._:-]` → `_`)을 재사용합니다. `DEVICE_UDID`가 없으면 기존 경로 그대로이므로 단일 실행 워크플로는 영향받지 않습니다.

### 6-4. 포트 할당

```
슬롯 i (0-based):  systemPort = 8200 + (i * 10)
```

| 슬롯 | systemPort | 예약 범위 |
|---|---|---|
| 0 | 8200 | 8200–8209 |
| 1 | 8210 | 8210–8219 |
| 2 | 8220 | 8220–8229 |
| 3 | 8230 | 8230–8239 |

10 간격을 두는 이유: UiAutomator2가 `systemPort` 외에 보조 포트를 인접 범위에서 쓸 수 있고, 향후 `chromedriverPort`(WebView TC) 추가 여지를 남기기 위함입니다.

**모드별 할당 대상이 다릅니다** — 이것이 §2-2에서 혼합을 금지하는 세 번째 근거입니다.

| 모드 | `systemPort` | `mjpegServerPort` |
|---|---|---|
| `real_device` (M1) | 8200 + slot×10 | 할당 안 함 — 실기기 caps에 없음 |
| `emulator` (M2) | 8200 + slot×10 | 8093 + slot — `devices.json`의 고정값을 런타임에 덮어씀 (§2-3 E-1) |

요청당 `mode`가 단일값이므로 할당기는 한 번에 한 규칙만 적용합니다.

실행 시작 전 각 포트가 이미 점유되었는지 확인(`lsof -ti :<port>`)하고, 점유 시 다음 사용 가능 슬롯으로 이동합니다. 4슬롯 모두 점유되면 `409 no_free_port`.

### 6-5. `_running` 구조 변경 (F-3)

키를 `parallel:{run_id}:{udid}`로 사용합니다. 기존 `execute`·`test:{platform}:{file}` 키 체계와 네임스페이스가 겹치지 않아 하위호환됩니다. `/api/cancel`의 기존 동작은 그대로 둡니다.

### 6-6. 디바이스 가드 강화 (F-4)

`05_execute.py`의 `check_android_device()`가 `--udid` 지정 시 해당 serial이 `adb devices`에 `device` 상태로 존재하는지 확인하도록 변경합니다. 미연결 시 `[05_execute] ERROR: device {udid} not connected` 출력 후 exit 1.

### 6-7. Livetail 연동

`pipeline.py`의 기존 `broadcast_timeline_sync` 패턴을 따릅니다. 병렬 이벤트에는 `udid`·`run_id`를 추가합니다.

```json
{"type": "parallel_device_start",    "source": "pipeline", "run_id": "...", "udid": "...", "deviceName": "..."}
{"type": "parallel_device_complete", "source": "pipeline", "run_id": "...", "udid": "...", "ok": true, "returncode": 0}
{"type": "parallel_run_complete",    "source": "pipeline", "run_id": "...", "summary": {...}}
```

---

## 7. 기술 요구사항 — 프론트엔드

### 7-1. 디바이스 선택 UI 변경 — 빠른 실행 탭만

`dashboard.html`의 디바이스 피커는 `_renderDeviceList(containerId, ...)`로 두 탭이 같은 함수를 공유합니다 (`pipeline-device-list` / `quick-device-list`). **다중 선택은 `quick-device-list`에만 적용**하고 `pipeline-device-list`는 현행 단일 선택을 유지합니다. 렌더 함수에 `multiSelect` 플래그를 추가해 분기합니다.

선택 상태도 분리합니다: 기존 `_selectedDevice`(단일 객체)는 파이프라인 탭용으로 유지하고, 빠른 실행 탭용 `_quickSelectedDevices`(배열)를 신설합니다. 이렇게 하면 파이프라인 탭 코드 경로는 손대지 않습니다.

#### 상호 배타 선택 — 그룹 잠금

§2-2의 동일 타입 그룹 정책을 **UI에서 먼저 강제**합니다. 한 섹션에서 디바이스를 선택하면 다른 섹션 전체가 비활성화됩니다.

| 현재 선택 | 에뮬레이터 섹션 | 실기기 섹션 |
|---|---|---|
| 없음 | 활성 | 활성 |
| 에뮬레이터 1대 | 활성 | **비활성 (dimmed)** |
| 실기기 1대 이상 | **비활성 (dimmed)** | 활성 |

비활성 섹션은 `opacity: .4` + `pointer-events: none`으로 처리하고, 섹션 헤더에 해제 안내와 버튼을 둡니다. **선택을 조용히 갈아치우지 않습니다** — 실기기 2대를 고른 상태에서 에뮬레이터를 클릭했을 때 실기기 선택이 말없이 사라지면 사용자가 무엇을 실행하는지 오인합니다.

| 섹션 | 컨트롤 | 동작 |
|---|---|---|
| 에뮬레이터 | M1: 라디오(현행) · M2: 체크박스 | M2부터 0~4개 선택 |
| 시뮬레이터 (iOS) | 라디오 (현행 유지) | 병렬 대상 아님 |
| 실기기 | **체크박스** | 0~4개 선택. 2개 이상이면 병렬 |

토글 스위치("병렬 실행 모드")를 별도로 두지 **않습니다**. 2개 이상 체크하면 병렬, 1개면 단일입니다. 모드 토글은 상태를 하나 더 만들고 "토글은 켰는데 1대만 선택" 같은 무의미한 조합을 허용합니다.

```
에뮬레이터                                     ⓘ 실기기 선택 중 — [선택 해제]
┌──────────────────────────────────────────────┐
│ ○  Android Emulator                          │   ← dimmed, 클릭 불가
│    Pixel_7_Android15 · Android 15            │
└──────────────────────────────────────────────┘

실기기                          [전체 선택]  2 / 3대 선택
┌──────────────────────────────────────────────┐
│ ☑  Lenovo TB320FC                   연결됨   │
│    HA1XM5MS · Android 15                     │
├──────────────────────────────────────────────┤
│ ☑  Galaxy S24                       연결됨   │
│    R3CN70BFZLJ · Android 14                  │
├──────────────────────────────────────────────┤
│ ☐  Pixel 8                          미연결   │
│    (udid 미등록 — ENV Setup에서 등록)         │
└──────────────────────────────────────────────┘
```

`[전체 선택]`은 **해당 섹션 안에서만** 동작합니다. 연결된 항목만 선택하며 상한 4대를 넘지 않습니다.

실행 버튼 라벨이 선택 상태를 반영합니다: `실행` → `실기기 2대 병렬 실행`.

`getSelectedDeviceParams()`는 그대로 유지합니다. 빠른 실행 탭에서 2개 이상 체크한 경우에만 `getQuickSelection()`이 `{mode: "real_device", udids: ["HA1XM5MS", "R3CN70BFZLJ"]}`를 반환하고 `/api/run_parallel`로 라우팅합니다. 1개 이하 선택 시 기존 `/api/run_test`를 그대로 호출합니다 — **단일 디바이스 실행 경로와 파이프라인 탭은 코드 변경 없이 보존**됩니다.

`mode`는 선택된 카드들에서 **파생**되며 별도 상태로 저장하지 않습니다. 그룹 잠금이 이미 단일 모드를 보장하므로, 선택 배열의 첫 항목 `mode`가 곧 요청의 `mode`입니다.

### 7-2. 병렬 진행 상태 UI (빠른 실행 탭)

실행 중에는 로그 영역 상단에 디바이스별 진행 카드를 가로로 배치합니다.

```
┌─ Lenovo TB320FC ──────────┐  ┌─ Galaxy S24 ──────────────┐
│ ● 실행 중          02:23  │  │ ✓ 완료             01:58  │
│ ████████████░░░░░░  7/12  │  │ ████████████████  12/12   │
│ tc_settings_battery       │  │ 12 passed · 0 failed      │
│                    [취소] │  │              [로그 보기]  │
└───────────────────────────┘  └───────────────────────────┘
```

- 폴링 주기 2초 (`GET /api/parallel/{run_id}`). 기존 `/api/run_log` 폴링 주기와 일관
- 카드 클릭 → 해당 디바이스 로그를 로그 패널에 표시
- 좁은 화면에서는 세로 스택

### 7-3. 결과 비교 뷰 (M2)

실행 완료 후 TC × 디바이스 매트릭스를 표시합니다.

```
TC                                  Lenovo TB320FC   Galaxy S24   Pixel 8
tc_settings_battery                      ✓               ✓            ✓
tc_settings_location                     ✓               ✗            ✓   ← 기기 종속
tc_settings_search_input                 ✗               ✗            ✗   ← 공통 실패
```

- **공통 실패** (전 기기 실패): 테스트/앱 문제 가능성 → 우선 조사 대상
- **기기 종속 실패** (일부만 실패): 해상도·OS 버전·벤더 스킨 차이 가능성

이 구분이 병렬 실행의 핵심 가치이므로 M2의 필수 산출물입니다.

---

## 8. 데이터 구조 변경 요약

| 파일 | 변경 |
|---|---|
| `config/devices.json` | 스키마 변경 **없음**. `android.real_device[]`에 항목을 추가하고 각 항목의 `udid`를 채우면 됩니다. `systemPort`는 런타임 주입이므로 저장하지 않습니다 |
| `state/parallel/{run_id}/index.json` | 신규 |
| `state/parallel/{run_id}/{udid}/*.json\|xml` | 신규 (기존 `state/*` 파일의 디바이스별 사본) |
| `logs/parallel/{run_id}/{udid}.txt` | 신규 |
| `state/pipeline.json` | 병렬 실행 중에는 쓰지 않음. 마지막 병렬 run 참조만 기록: `{"last_parallel_run": "par_android_..."}` |

`state/parallel/` 보존 정책: 최근 20개 run만 유지하고 오래된 디렉토리는 새 run 시작 시 정리합니다.

---

## 9. 제약 조건

| # | 제약 | 처리 |
|---|---|---|
| C-0 | 빠른 실행 탭에서만 병렬 가능 | 파이프라인 실행 탭 UI는 단일 선택 유지. `/api/run_all`은 변경 없음 |
| C-1 | **동일 타입 그룹 내에서만 병렬** — 에뮬↔실기기 혼합 금지 | UI 그룹 잠금(§7-1) + API `400 mixed_device_mode`(§6-1 검증 7번) 이중 방어 |
| C-1b | M1은 `real_device`만 | `mode == "emulator"` → `400 emulator_parallel_not_ready`. M2에서 해제 |
| C-2 | Android 전용 | `platform != "android"` → `400 invalid_platform` |
| C-3 | 최대 4대 | `400 max_parallel_exceeded` |
| C-4 | 동시 병렬 run 1개 (플랫폼 구분 없는 전역 제약) | `409 parallel_run_active` |
| C-5 | Capture Studio(android) 세션 중 실행 불가 | 기존 `is_capture_active("android")` 가드 재사용 |
| C-6 | Appium 서버 실행 중이어야 함 | `05_execute.py`의 기존 `check_appium_server()` |
| C-7 | 병렬 실행 중 heal 비활성 | M1. `heal: true` → 400 |
| C-8 | 각 실기기 항목에 `udid` 필수 | 빈 udid 항목은 선택 불가 |
| C-9 | `pytest-rerunfailures` 재시도는 디바이스별 독립 | 기존 `--reruns 2 --reruns-delay 5` 유지. 한 기기의 재시도가 다른 기기에 영향 없음 |
| C-10 | Jira 리포트는 병렬 실행에서 자동 생성 안 함 | `jira_reporter.py`가 `state/pipeline.json` 단일 파일을 읽으므로 병렬 결과와 맞지 않음. M2에서 집계 기반 단일 이슈 생성으로 재설계. 파이프라인 탭의 기존 Jira 자동 보고는 그대로 동작 |

---

## 10. 에러 카탈로그

| 코드 | HTTP | 메시지 | 복구 |
|---|---|---|---|
| `mixed_device_mode` | 400 | 에뮬레이터와 실기기를 함께 실행할 수 없습니다. 같은 종류끼리만 선택하세요 ({위반 udid}: {실제 mode}) | 한 종류만 선택 |
| `invalid_mode` | 400 | 지원하지 않는 디바이스 모드입니다 | — |
| `emulator_parallel_not_ready` | 400 | 에뮬레이터 병렬 실행은 아직 지원하지 않습니다 (M2 예정) | 실기기 선택 |
| `invalid_platform` | 400 | 병렬 실행은 Android만 지원합니다 | — |
| `no_device_selected` | 400 | 디바이스를 1대 이상 선택하세요 | — |
| `max_parallel_exceeded` | 400 | 최대 4대까지 동시 실행할 수 있습니다 | 선택 축소 |
| `duplicate_device` | 400 | 같은 디바이스를 중복 선택했습니다 | — |
| `heal_not_supported_parallel` | 400 | 병렬 실행에서는 자동 healing을 사용할 수 없습니다 | heal 해제 |
| `device_not_connected` | 409 | 연결되지 않은 디바이스: {udid 목록} | 케이블 확인 후 재시도 |
| `capture_session_active` | 409 | Capture Studio 세션이 실행 중입니다 | Capture 종료 |
| `parallel_run_active` | 409 | 이미 병렬 실행이 진행 중입니다 ({run_id}) | 완료 대기 또는 취소 |
| `no_free_port` | 409 | 사용 가능한 systemPort가 없습니다 | 잔여 Appium 세션 정리 |
| `run_not_found` | 404 | run_id를 찾을 수 없습니다 | — |

**부분 실패 정책**: 3대 중 1대가 세션 생성에 실패해도 나머지 2대는 계속 실행합니다. 해당 디바이스만 `status: "error"`로 표시하고 전체 run은 `failed`로 종료합니다. 전체 중단은 하지 않습니다 — 2대분 결과도 가치가 있습니다.

---

## 11. 마일스톤

### M0 — 선행 이슈 해소 (병렬 기능 없음)

§4의 F-1 ~ F-7을 처리합니다. **이 단계만으로도 단일 실행의 정합성이 개선되므로 독립적으로 배포 가능합니다.**

- [ ] F-1: `DEVICE_SYSTEM_PORT` → `tests/generated/conftest.py`에서 `systemPort` 주입
- [ ] F-2: `QA_RUN_DIR` 환경변수 + `05_execute.py`·`tests/conftest.py` 경로 폴백 (§6-3 코드 참조 — `main()` 재바인딩 · `STATE_DIR` 동반 변경 · 훅 내부 동적 조회)
- [ ] F-2: 스크린샷 PNG 디렉토리에 udid 세그먼트 추가 (`_screenshots_dir()`)
- [ ] F-4: `check_android_device(udid)` udid 검증
- [ ] F-5: `/api/devices` 실기기 `connected` fallback 제거, `needs_udid` 필드 추가
- [ ] F-6: `02_generate.py --device-udid` 인자 제거, `pipeline.py`의 전달부 제거
- [ ] 회귀: `python3 -m py_compile scripts/*.py` · `02_generate --strict-locators` (android/ios) · 기존 단일 실행 경로 동작 확인

### M1 — 빠른 실행 탭 병렬 (핵심 기능)

- [ ] `POST /api/run_parallel` — `05_execute.py` N개 fan-out
- [ ] F-3: `_running` 키 `parallel:{run_id}:{udid}`
- [ ] 포트 할당기 (§6-4)
- [ ] `state/parallel/{run_id}/` 출력 네임스페이스 + `index.json`
- [ ] `GET /api/parallel/{run_id}` · `/log` · `/cancel`
- [ ] 빠른 실행 탭 실기기 체크박스 다중 선택 UI (PS-1) — 파이프라인 탭 피커는 미변경
- [ ] **그룹 잠금 UI** — 에뮬레이터/실기기 상호 배타 선택 (§7-1)
- [ ] **`mixed_device_mode` 서버 검증** (§6-1 검증 7번) — UI 우회 호출 방어
- [ ] 디바이스별 진행 카드 (PS-3)
- [ ] 디바이스별 취소 / 전체 취소 (PS-5)
- [ ] 디바이스별 로그 열람 (PS-6)
- [ ] Livetail 이벤트 3종

**완료 판정**:
1. 실기기 2대 연결 상태에서 같은 TC 폴더를 병렬 실행 → 두 기기 모두 세션 생성 성공
2. 각 기기의 로그·리포트가 독립 저장되고 교차 오염 없음
3. 총 소요 시간이 순차 실행의 60% 이하
4. 파이프라인 실행 탭이 기존과 동일하게 동작 (회귀 없음)
5. 에뮬레이터 + 실기기 혼합 선택이 UI에서 불가능하고, API 직접 호출 시 `400 mixed_device_mode` 반환

### M2 — 결과 비교 · 에뮬레이터 병렬 · healing 복귀

- [ ] TC × 디바이스 비교 매트릭스 (PS-4)
- [ ] 공통 실패 / 기기 종속 실패 분류
- [ ] `tests/reports/compare_{run_id}.html`
- [ ] **에뮬레이터 병렬 해금** — §2-3의 E-1(`mjpegServerPort` 슬롯 주입) · E-2(다중 emulator serial 식별) · E-3(다중 AVD 동시 부팅) 해소 후 `emulator_parallel_not_ready` 가드 제거
- [ ] 에뮬레이터 섹션 체크박스 전환 (그룹 잠금 로직은 M1에서 이미 완성)
- [ ] heal 순차 fallback: 병렬 execute 완료 후 **기준 디바이스 1대에서만** heal 실행 → 재실행은 다시 병렬
- [ ] Jira 리포트 집계 재설계 (C-10)

**완료 판정**: 기기 종속 실패가 매트릭스에서 시각적으로 구분됨. 에뮬레이터 2대 병렬 실행 시 MJPEG 포트 충돌 없음. heal이 `config/locators.json`을 경합 없이 갱신.

> E-1 ~ E-3은 ENV_SETUP_PRD의 에뮬레이터 상태 모델·`devices.json` 스키마와 겹칩니다. M2 착수 전 두 PRD 조율이 필요합니다 (특히 E-3은 `POST /api/env/android/avd/start`의 `409 already_running` 가드 완화를 요구).

> **파이프라인 탭 병렬화는 이 로드맵에 없습니다.** 향후 재검토가 필요해지는 조건은 하나뿐입니다 — 빠른 실행 탭 병렬이 정착한 뒤에도 "코드 생성 직후 여러 기기에서 곧바로 검증"하는 수요가 반복해서 관찰될 때. 그 전까지는 §2-5의 제외 결정을 유지합니다.

---

## 12. CLAUDE.md 스펙 변경 필요 항목

### 변경 1 — "파이프라인" 섹션

**현재**:
> 대시보드의 전체 실행은 위 순서의 단일 파이프라인입니다. 제품에는 단일/병렬 실행 유형을 별도로 노출하지 않습니다.

**변경안**:
> 대시보드의 전체 실행(파이프라인 실행 탭)은 위 순서의 **단일 디바이스 순차 파이프라인**이며, 여기에 병렬 실행 유형을 노출하지 않습니다.
>
> **빠른 실행 탭만 예외입니다.** 이미 생성된 테스트를 여러 Android 디바이스에서 반복 실행하는 용도이므로, 2대 이상 선택하면 `05_execute.py`를 디바이스별로 병렬 실행합니다. 사용자가 실행 유형을 토글로 고르지 않으며 선택한 디바이스 수로 결정됩니다 — 1대면 단일, 2대 이상이면 병렬(최대 4대).
>
> **병렬 실행은 동일 타입 그룹 안에서만 가능합니다.** 실기기는 실기기끼리, 에뮬레이터는 에뮬레이터끼리만 묶이며 **에뮬레이터와 실기기를 섞어서 실행할 수 없습니다.** UI는 한쪽을 선택하면 다른 쪽 섹션을 비활성화하고, API는 혼합 요청에 `400 mixed_device_mode`를 반환합니다. iOS(시뮬레이터·실기기)는 병렬 대상이 아닙니다.
>
> 상세: [docs/PARALLEL_EXECUTION_PRD.md](docs/PARALLEL_EXECUTION_PRD.md)

변경 시점: **M1 완료 후**. M0까지는 현재 문장이 사실이므로 수정하지 않습니다.

이 변경은 기존 원칙을 뒤집는 것이 아니라 **적용 범위를 명시하는 것**입니다. "파이프라인은 단일 순차"라는 원래 규칙은 그대로 유지됩니다.

### 변경 2 — "설정 파일" 표의 `config/devices.json` 행에 추가

> **병렬 실행**: `android.real_device[]`의 각 항목은 `udid`가 필수입니다. 빈 `udid` 항목은 병렬 선택 목록에 표시되지 않습니다. `systemPort`는 `devices.json`에 저장하지 않으며 실행 시 슬롯별로 주입됩니다 (8200 + slot×10). 에뮬레이터 병렬(M2)에서는 `mjpegServerPort`도 같은 방식으로 슬롯 주입되므로, emulator 항목의 고정 `mjpegServerPort: 8093`은 기본값 역할만 합니다.

### 변경 3 — "연속 Appium 세션 주의사항" 섹션에 추가

> **빠른 실행 탭 병렬 실행 시**: 각 디바이스 프로세스는 독립된 `systemPort`(8200 + slot×10)를 사용하므로 세션끼리 간섭하지 않습니다. 단 동시 실행 상한은 4대이며 기본값은 3대입니다. 4대 초과 요청은 큐잉되지 않고 거부됩니다.

### 변경 4 — "디렉토리 규칙"에 추가

```text
state/parallel/{run_id}/     # 병렬 실행 디바이스별 산출물
logs/parallel/{run_id}/      # 병렬 실행 디바이스별 로그
```

### 변경 5 — "실행 명령"에 추가

```bash
# 특정 디바이스 지정 실행 (병렬 실행이 내부적으로 사용하는 형태)
DEVICE_SYSTEM_PORT=8210 QA_RUN_DIR=state/parallel/par_xxx/R3CN70BFZLJ \
  python scripts/05_execute.py --platform android --mode real_device --udid R3CN70BFZLJ
```

### 변경 없음 확인

- **외부 LLM SDK 금지**: 이 기능은 `asyncio`·`subprocess`·표준 라이브러리만 사용합니다. 위반 없음
- **자체 완결 생성 파일 원칙**: 생성 코드는 수정하지 않습니다. `systemPort` 주입은 `tests/generated/conftest.py`에서만 일어납니다
- **`config/locators.json` source of truth**: 병렬 실행은 registry를 읽기만 합니다. 쓰기는 heal뿐이며 M2까지 비활성. 파이프라인 탭의 heal은 순차 단일 디바이스이므로 현행 그대로 동작
- **Appium `--address 127.0.0.1` 고정**: 단일 로컬 서버 유지. 변경 없음

---

## 13. 열린 질문 — 확정 필요

| # | 질문 | 결정 필요 시점 |
|---|---|---|
| Q-1 | 실기기 2대 이상을 실제로 확보했는가? 현재 `devices.json`의 `android.real_device[]`에는 `Lenovo TB320FC` 1대뿐입니다. **검증 없이 M1을 완료 판정할 수 없습니다** | M1 착수 전 |
| Q-2 | 단일 Appium 서버에서 UiAutomator2 세션 3개 동시 유지가 실제로 안정적인가? 불안정하면 서버 다중화(포트 4723/4733/4743)가 필요하고, 이는 ENV_SETUP_PRD의 Appium 상태 모델 재설계를 동반합니다 | M1 초반 — 2대 실측 후 |
| Q-3 | 기기별로 locator가 갈릴 때(벤더 스킨) 어떻게 처리하는가? 현재 `config/locators.json`은 플랫폼별 분리만 지원하고 기기별 분리는 없습니다. 실측에서 빈도가 확인되면 §5-2의 "기기 독립 전제"를 재검토합니다 | M2 |
| Q-4 | 동시 실행 기본값 3이 적절한가? Q-2 실측 결과에 따라 조정 | M1 종료 |

---

## 14. 성공 지표

| 지표 | 목표 | 측정 |
|---|---|---|
| 실행 시간 단축 | 2대 병렬이 순차 대비 60% 이하 | 동일 TC 폴더 실행 시간 비교 |
| 세션 생성 성공률 | 병렬 세션 생성 성공 95% 이상 | 10회 반복 실행 중 세션 초기화 실패 횟수 |
| 결과 격리 | 디바이스별 리포트 교차 오염 0건 | `state/parallel/{run_id}/{udid}/pipeline.json`의 `execute_results`가 해당 기기 결과만 포함 |
| 기기 종속 실패 식별 | 비교 매트릭스에서 구분 가능 | M2 수동 확인 |
| 파이프라인 탭 회귀 | 0건 | 병렬 기능 추가 전후로 `/api/run_all` 동작 동일 |
