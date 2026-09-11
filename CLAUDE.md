# QA Automation — Native App 작업 가이드

이 저장소는 웹 QA 프로젝트와 분리된 Appium 기반 Android/iOS 네이티브 앱 자동화 프로젝트입니다.

## 핵심 원칙

- 외부 LLM SDK(`anthropic`, `langchain`, `openai` 등)를 제품 코드에 import하지 않습니다.
- 파이프라인 단계 결과는 `state/pipeline.json`에 기록합니다.
- 테스트 함수명은 `test_{english_snake_case}`를 사용합니다.
- 생성 테스트 파일은 드라이버 초기화까지 포함하는 자체 완결 형태를 유지합니다.
- locator의 기준값은 `config/locators.json`에서 관리합니다. 생성된 `.py` 파일은 산출물입니다.
- Android와 iOS UI hierarchy snapshot은 동일한 화면명 아래에서도 플랫폼별로 분리합니다.

## 파이프라인

```text
01_analyze → 02_generate → 03_lint → 05_execute → 06_heal
```

- `01_analyze.py`: Appium native hierarchy와 감지된 WebView DOM을 분리 수집
- `02_generate.py`: native 우선·선택적 Playwright WebView pytest 생성
- `03_lint.py`: 생성 코드 flake8 검사
- `05_execute.py`: pytest/Appium 실행 및 리포트 저장
- `06_heal.py`: 실패 직전 최신 hierarchy를 다시 수집하고 유일 후보만 healing

대시보드의 전체 실행은 위 순서의 단일 파이프라인입니다. 제품에는 단일/병렬 실행 유형을 별도로 노출하지 않습니다.

플랫폼별 TC 입력과 생성 코드는 다음 경로를 사용합니다.

```text
testcases/android/{group}/ → tests/generated/android/{group}/
testcases/ios/{group}/     → tests/generated/ios/{group}/
```

대시보드에서 Android를 선택하면 `testcases/android`만, iOS를 선택하면 `testcases/ios`만 실행 대상으로 노출합니다. 플랫폼 루트는 생성 결과에 다시 중첩하지 않습니다.

## Excel Import Studio

- 흐름: `파일·시트 선택 → 열 매핑 → 미리보기 → 안전한 반영 → 완료`
- 입력 파일은 `import/*.xlsx`에 두며 원본을 수정하지 않습니다.
- 파일을 선택한 뒤 카드 내부에서 하나 이상의 시트를 선택해야 합니다.
- 필수 매핑은 `tc_id`, `title`, `precondition`, `steps`, `expected`입니다.
- 선택한 Excel 열 매핑은 `scripts/import_excel.py` 변환에 실제로 전달되어야 합니다.
- `/api/import/preview`는 현재 매핑과 플랫폼을 기준으로 상태 집계와 전체 TC 상세 데이터를 반환하며, 열 매핑 화면 변경 시 다시 호출합니다.
- 미리보기 단계는 `전체/추가/업데이트/충돌/오류/동일` 필터와 전체 TC 상세 테이블을 제공하며 열 매핑 화면에는 중복 미니 테이블을 노출하지 않습니다.
- Android는 `testcases/android/{sheet}/`, iOS는 `testcases/ios/{sheet}/`에 별도 Markdown을 생성합니다.
- 단, 시트명 자체가 `android` 또는 `ios`이면 같은 OS에만 반영하고 플랫폼 루트 바로 아래에 생성하여 중첩 플랫폼 폴더를 만들지 않습니다.
- 두 플랫폼을 선택하면 플랫폼별 파일을 각각 생성하고 각 Markdown의 `## 플랫폼`에는 하나의 OS만 기록합니다.
- 파일명 충돌은 시트별 하위 폴더로 방지합니다.
- 안전한 반영의 기본 정책은 `skip-conflict`이며 기존 Markdown을 보존합니다. 명시적으로 `overwrite`를 선택하면 동일 경로 파일을 덮어씁니다.

## Locator 작업 규칙

1. Appium Inspector 또는 native hierarchy에서 요소 속성을 확인합니다.
2. 확인한 플랫폼별 locator를 `config/locators.json`에 저장합니다.
3. strict 생성으로 registry 누락을 차단합니다.
4. 실패 시 `06_heal.py`가 locator surface에 따라 native XML 또는 WebView DOM에서 후보를 찾습니다.
5. 후보가 유일하고 신뢰도가 높을 때만 registry를 갱신합니다.
6. 후보가 모호하거나 snapshot이 없으면 자동 변경하지 않고 실패 상태로 남깁니다.

```bash
python scripts/02_generate.py --platform android --strict-locators
python scripts/02_generate.py --platform ios --strict-locators
```

상세 healing 정책은 [docs/LOCATOR_HEALING.md](docs/LOCATOR_HEALING.md)에 있습니다.

## 설정 파일

| 파일 | 역할 |
|---|---|
| `config/test_data.json` | 앱 package/activity, bundle ID, 테스트 데이터 |
| `config/devices.json` | Android/iOS capability |
| `config/screens.json` | 분석 화면과 진입 action |
| `config/locators.json` | 플랫폼별 target locator registry |
| `config/jira_config.json` | 이 제품 전용 Jira 프로젝트/이슈 설정 |

`config/locators.json` target key는 `{tc_slug}.{selector_key}` 형식입니다. entry의 `surface`는 `auto`(native 우선), `native`, `webview` 중 하나이며 WebView locator는 `webview` 객체에 별도로 둡니다. WebView가 감지되지 않으면 Playwright를 시작하지 않으며, CDP 미지원 WebView는 Appium context로 실행합니다.

대시보드 전체 실행이 healing 3회 후에도 실패하면 `scripts/jira_reporter.py`가 이 프로젝트의 Jira 설정으로 Bug를 생성하고 스크린샷/영상을 첨부합니다. `JIRA_TOKEN`이 없으면 Jira 보고만 건너뛰며 테스트 결과는 유지합니다. Jira 설정은 다른 제품과 공유하지 않습니다.

## 실행 명령

```bash
appium --address 0.0.0.0 --port 4723
python agents/dashboard/serve.py

# Android
python scripts/01_analyze.py --platform android --mode emulator
python scripts/02_generate.py --platform android --strict-locators
python scripts/03_lint.py --platform android
python scripts/05_execute.py --platform android

# iOS
python scripts/01_analyze.py --platform ios --mode simulator
python scripts/02_generate.py --platform ios --strict-locators
python scripts/03_lint.py --platform ios
python scripts/05_execute.py --platform ios
```

## 디렉토리 규칙

```text
config/locators.json       # locator source of truth
config/{devices,screens,test_data}.json
scripts/                   # 분석·생성·린트·실행·힐링
import/                    # Import Studio Excel 입력
testcases/{android,ios}/   # OS별 입력 TC Markdown
tests/generated/{android,ios}/ # OS별 생성 코드
tests/reports/             # 실행 리포트
state/pipeline.json        # 실행 상태와 snapshot
logs/                      # 단계별 로그
docs/LOCATOR_HEALING.md    # healing 정책
```

## 변경 시 검증

```bash
python3 -m py_compile scripts/*.py
python3 scripts/02_generate.py --platform android --strict-locators
python3 scripts/02_generate.py --platform ios --strict-locators
git diff --check
```

실제 Appium 실행은 연결된 서버와 디바이스가 있을 때 별도로 수행합니다.
