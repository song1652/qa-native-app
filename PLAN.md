# qa-native-app 개발 플랜

> 목표: Appium 기반 Android/iOS 앱 자동화 코드를 생성·실행해주는 파이프라인 완성
> 파이프라인: `01_analyze → 02_generate → 03_lint → 05_execute → 06_heal`

---

## Sprint 1 — Android TC 1개를 end-to-end로 실행

| # | 작업 | 담당 | 상태 |
|---|------|------|------|
| 1 | `01_analyze.py` import 경로 버그 수정 (`from scripts.drivers...` → ModuleNotFoundError) | app-developer | ✅ 완료 |
| 2 | `screens.json` login actions 보완 (ID/PW 입력 + 로그인 버튼 탭 시퀀스) | app-qa | ✅ 완료 |
| 3 | `test_data.json` credentials 채우기 (username/password) | app-qa | ⏭️ 앱 확정 시 |
| 4 | `01_analyze.py` 실행 → `pipeline.json` dom_info에 3개 화면 XML 수집 확인 | app-qa | ⏭️ 환경 필요 |
| 5 | `tests/generated/android/tc_001_login.py` 수작업 작성 (자체 완결, 드라이버 초기화 포함) | app-developer | ✅ 완료 |
| 6 | `05_execute.py --platform android --no-report` 실행 → TC 1개 실행 확인 | app-qa | ⬜ 대기 |

---

## Sprint 2 — 파이프라인 자동화 (02_generate, 03_lint)

| # | 작업 | 담당 | 상태 |
|---|------|------|------|
| 1 | TC 마크다운 3개 작성 (`testcases/tc_001_login.md`, `tc_002_file_list.md`, `tc_003_file_detail.md`) | app-qa | ✅ 완료 |
| 2 | `02_generate.py` 구현 — dom_info XML 파싱 → pytest 코드 자동 생성 | app-developer | ✅ 완료 |
| 3 | `03_lint.py` 구현 — flake8 subprocess 래퍼, 결과 pipeline.json 기록 | app-developer | ✅ 완료 |
| 4 | `01 → 02 → 03 → 05` 전체 파이프라인 연속 실행 검증 | app-qa | ⏭️ 환경 필요 |

---

## Sprint 3 — Self-heal + iOS 확장

| # | 작업 | 담당 | 상태 |
|---|------|------|------|
| 1 | `06_heal.py` 구현 — page_source XML 기반 heal (전략교체 fallback 포함) | app-developer | ✅ 완료 |
| 2 | heal 패턴 3건 이상 `agents/lessons_learned.md` 문서화 | app-qa | ✅ 완료 |
| 3 | `ios_driver.py` 보완 + iOS Simulator 환경 구축 | app-developer | ✅ 완료 |
| 4 | iOS TC 생성·실행 검증 | app-qa | ⏭️ 환경 필요 |

---

---

## Sprint 4 — 파이프라인 안정성·완성도 개선

| # | 작업 | 담당 | 상태 |
|---|------|------|------|
| 1 | `05_execute.py` pytest JUnit XML 파싱 → `execute_results.errors` 기록 (heal 연결 CRITICAL 수정) | app-developer | ✅ 완료 |
| 2 | `02_generate.py` WebDriverWait + EC 패턴 적용 (time.sleep 제거) | app-developer | ✅ 완료 |
| 3 | `report_html.py` + `05_execute.py --report` 연결 → `reports/report.html` 생성 | app-developer | ✅ 완료 |
| 4 | `06_heal.py` 다중 SEL 상수 일괄 heal 후 1회 pytest 재실행 | app-developer | ✅ 완료 |
| 5 | Sprint 4 전체 AC 정적 검증 (6개 항목 PASS) | app-qa | ✅ 완료 |

---

## 상태 범례
- ⬜ 대기
- 🔄 진행 중
- ✅ 완료
- ❌ 블로커
