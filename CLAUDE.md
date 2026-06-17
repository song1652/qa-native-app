# QA Automation — App (Appium)

> 웹 QA(`qa-native`)와 **별개 프로젝트**. Android / iOS 앱 테스트 자동화.
> 파이프라인 철학은 qa-native와 동일하되, 드라이버·셀렉터·수집 방식이 다름.

## 절대 규칙
- `anthropic`, `langchain`, `openai` 등 외부 LLM SDK import 절대 금지
- 모든 단계 결과는 `state/pipeline.json`에 저장 후 다음 단계 진행
- **테스트 함수명**: `test_{english_snake_case}` (영문 snake_case)
- **파일명**: `tc_{번호}_{english_snake_case}.py`
- **테스트 파일은 자체 완결**: 드라이버 초기화 포함, 공유 헬퍼 금지

## 설정 파일

| 파일 | 용도 |
|------|------|
| `config/screens.json` | 화면 정의. precondition + actions (활성 앱 기준) |
| `config/devices.json` | 디바이스/에뮬레이터 Capabilities |
| `config/test_data.json` | 테스트 입력값 — 앱 패키지명, 계정 등 (활성 앱 기준) |
| `config/presets/{앱이름}/` | 앱별 설정 보관. 대시보드에서 선택 시 config/로 복사됨 |
| `config/presets/_template/` | 새 앱 추가용 예제 파일 (목록에 노출되지 않음) |

## 멀티앱 관리

새 앱 추가 절차:
1. `config/presets/앱이름/test_data.json` — 패키지명/번들ID 작성
2. `config/presets/앱이름/screens.json` — 테스트 화면 정의
3. `testcases/앱이름/tc_*.md` — TC 마크다운 작성
4. 대시보드 앱 드롭다운에서 선택 → 플랫폼 선택 → 전체 실행

앱 전환 API: `POST /api/switch_app {"app": "앱이름"}`
앱 목록 API: `GET /api/apps`

## 파이프라인

```
01_analyze → 02_generate → 03_lint → 05_execute → 06_heal (최대 3회)
```

대시보드 **▶ 전체 실행** 버튼으로 위 단계가 자동 순차 실행됨.
- 실패 없으면 heal 생략하고 즉시 완료
- heal 3회 실패 시 영상(`tests/reports/recordings/`) 자동 저장

## 실행 순서

```bash
# 환경 준비
ANDROID_HOME=~/Library/Android/sdk \
  ~/.nvm/versions/node/v20.20.2/bin/appium --address 0.0.0.0 --port 4723 &

# 대시보드 서버 (권장)
~/.pyenv/versions/3.12.9/bin/python agents/dashboard/serve.py

# 직접 실행 (Android)
python scripts/01_analyze.py --platform android --mode emulator
python scripts/05_execute.py --platform android

# 직접 실행 (iOS)
python scripts/01_analyze.py --platform ios --mode simulator
python scripts/05_execute.py --platform ios
```

## 디렉토리 구조

```
qa-native-app/
├── config/
│   ├── screens.json          # 활성 앱 화면 정의
│   ├── devices.json          # Appium Capabilities (공용)
│   ├── test_data.json        # 활성 앱 패키지명/계정
│   └── presets/
│       ├── _template/        # 새 앱 추가용 예제 (대시보드 미노출)
│       └── settings/         # Android Settings + iOS Preferences
├── scripts/
│   ├── drivers/
│   │   ├── android_driver.py
│   │   └── ios_driver.py
│   ├── 01_analyze.py         # page_source 기반 UI XML 수집
│   ├── 02_generate.py        # TC 마크다운 → pytest 코드 생성
│   ├── 03_lint.py            # flake8 린트
│   ├── 05_execute.py         # pytest 실행 + HTML 리포트 생성
│   ├── 06_heal.py            # 실패 TC 자동 패치
│   └── report_html.py        # HTML 리포트 빌더
├── testcases/
│   ├── settings/             # Android Settings TC (tc_*.md)
│   └── ios_test/             # iOS Settings TC (tc_*.md)
├── tests/
│   ├── generated/
│   │   ├── android/          # 생성된 Android pytest 파일
│   │   └── ios/              # 생성된 iOS pytest 파일
│   └── reports/
│       ├── report_android.html
│       └── report_ios.html
├── state/
│   └── pipeline.json         # 파이프라인 실행 상태 (active_app, platform 포함)
├── logs/                     # 단계별 실행 로그 (run_*.txt)
└── agents/
    ├── dashboard/
    │   └── serve.py          # 대시보드 서버 (포트 8767)
    └── lessons_learned.md
```

## 플랫폼 현황
- **Android**: UiAutomator2, 에뮬레이터(emulator-5554) — 운영 중
- **iOS**: XCUITest, iPhone 16 Simulator (iOS 26.5, UDID: 5666D9D8-91BC-453B-9A6F-556573EC5D3A) — 운영 중
- **Phase 3**: 실기기 + CI/CD 연동 (예정)

## 주요 환경 변수 / 경로
- Android SDK: `~/Library/Android/sdk/platform-tools/adb`
- Appium: `~/.nvm/versions/node/v20.20.2/bin/appium` (Node v20 필수)
- Python: `~/.pyenv/versions/3.12.9/bin/python`
- 대시보드: `http://localhost:8767`

## qa-native와 공유 vs 분리

| 공유 (철학·포맷만) | 새로 작성 |
|---|---|
| pipeline.json 스키마 구조 | 01_analyze.py (page_source 기반) |
| lessons_learned.md 포맷 | 드라이버 레이어 전체 |
| 파이프라인 단계 번호 | heal-patterns (앱 전용) |
| 03_lint.py (flake8) | 05_execute.py (Appium 드라이버) |
| report_html.py CSS/JS 스타일 | 앱 전용 artifact panel (screenshot/video) |
