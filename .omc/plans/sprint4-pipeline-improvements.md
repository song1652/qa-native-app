# Sprint 4 — 파이프라인 개선 플랜

**상태**: pending approval  
**작성일**: 2026-06-17  
**범위**: 기존 01~06 파이프라인 전체 안정성·완성도 향상

---

## Requirements Summary

코드 분석 결과 다음 4개 영역에 개선이 필요하다:

1. **[CRITICAL] 05_execute → 06_heal 연결 단절**: `execute_results.errors` 형식 불일치로 heal이 실제로 트리거되지 않음
2. **[HIGH] 생성된 테스트의 명시적 wait 부재**: `time.sleep` 고정 대기로 불안정한 테스트 발생
3. **[HIGH] report_html.py 파이프라인 미연결**: HTML 리포트가 실제로 생성되지 않음
4. **[MEDIUM] 06_heal 다중 SEL 재시도 미지원**: 단일 heal 후 재실행 없음

---

## Acceptance Criteria

| # | 기준 | 검증 방법 |
|---|------|-----------|
| AC-1 | `05_execute.py` 실행 후 `pipeline.json`의 `execute_results.errors`에 실패한 테스트 파일 경로와 오류 메시지가 기록된다 | `pipeline.json` 직접 확인 |
| AC-2 | `06_heal.py` 실행 시 `execute_results.errors`가 비어있지 않으면 heal 루프가 실제로 동작한다 | `06_heal.py` 단위 테스트 (mock pytest 출력) |
| AC-3 | `02_generate.py`가 생성하는 테스트 코드에 `WebDriverWait` + `EC.presence_of_element_located` 패턴이 포함된다 | 생성된 .py 파일 grep |
| AC-4 | `05_execute.py --report` 실행 후 `reports/report.html` 파일이 생성된다 | 파일 존재 확인 |
| AC-5 | `06_heal.py`가 같은 테스트 파일에서 SEL 상수가 여러 개 실패할 때 모두 heal 시도 후 1회 재실행한다 | 코드 리뷰 + `python -m py_compile` |
| AC-6 | 모든 수정 파일이 `flake8` + `py_compile` 통과 | `03_lint.py` 실행 또는 직접 확인 |

---

## Implementation Steps

### Task 1 — 05_execute.py: pytest 결과 파싱 → pipeline.json 기록 [CRITICAL]

**파일**: `scripts/05_execute.py`  
**문제**: pytest를 subprocess로 실행한 뒤 exit code만 저장하고 실패 테스트 목록을 `execute_results.errors`에 넣지 않음  
**수정**:

```
1. pytest 실행 시 --tb=line --json-report --json-report-file=state/pytest_report.json 추가
   (pytest-json-report 패키지 사용, 없으면 xml: --junit-xml=state/pytest_report.xml)
2. 실행 후 JSON/XML 파싱하여 실패 테스트 추출
3. pipeline.json execute_results 구조:
   {
     "exit_code": <int>,
     "errors": [
       {"file": "tests/generated/android/tc_001_login.py", "error": "AssertionError: ..."}
     ],
     "passed": ["tests/generated/android/tc_002_file_list.py"],
     "summary": {"total": 3, "passed": 2, "failed": 1}
   }
```

**주의**: pytest-json-report가 없을 경우 `--junit-xml` fallback 사용. 두 경우 모두 지원.

---

### Task 2 — 02_generate.py: 명시적 wait 패턴 적용 [HIGH]

**파일**: `scripts/02_generate.py`  
**문제**: 생성 코드가 `time.sleep(1)` 고정 대기만 사용  
**수정**:

```
1. _generate_test_body() 내 tap/input_text 액션 코드 생성 시:
   - 기존: driver.find_element(...).click()
   - 변경: WebDriverWait(driver, 10).until(EC.presence_of_element_located((...)))
           element.click()

2. import 블록에 자동 추가:
   from selenium.webdriver.support.ui import WebDriverWait
   from selenium.webdriver.support import expected_conditions as EC

3. 기존 time.sleep(1) → 제거 (setup_method의 앱 시작 대기만 유지)
```

---

### Task 3 — report_html.py 파이프라인 연결 [HIGH]

**파일**: `scripts/05_execute.py`, `scripts/report_html.py`  
**문제**: `report_html.py`가 독립 모듈로 존재하나 호출되지 않음  
**수정**:

```
1. report_html.py에 parse_pipeline_to_groups(pipeline_state) 함수 추가:
   - pipeline.json의 execute_results + dom_info를 읽어 groups_data 생성
   - 화면별로 그룹핑: login / file_list / file_detail

2. 05_execute.py에 --report 플래그 추가:
   - 실행 후 parse_pipeline_to_groups() 호출
   - build_report() 호출 → reports/report.html 저장
   - pipeline.json에 report_path 기록

3. reports/ 디렉토리 자동 생성
```

---

### Task 4 — 06_heal.py: 다중 SEL 재시도 루프 [MEDIUM]

**파일**: `scripts/06_heal.py`  
**문제**: 단일 SEL 상수 heal 후 테스트 재실행 없음; 같은 파일에 실패 SEL이 여러 개면 첫 번째만 heal됨  
**수정**:

```
1. heal_file_xml() 내 루프를 "모든 SEL_* 상수 시도"로 변경:
   - 현재: 첫 번째 SEL 상수 heal → 즉시 pytest 재실행
   - 변경: 모든 SEL 상수에 대해 best-match 탐색 → 전부 적용 → 1회 pytest 재실행

2. 중간 pytest 재실행 제거 (불필요한 실행 감소)

3. 최종 결과를 배열로 lessons_learned에 기록:
   heal_results = [
     {"sel_const": "SEL_USERNAME_FIELD", "healed": True, ...},
     {"sel_const": "SEL_PASSWORD_FIELD", "healed": True, ...},
   ]
```

---

## Risk & Mitigations

| 위험 | 대응 |
|------|------|
| pytest-json-report 패키지 미설치 | junit-xml fallback 경로 구현, requirements.txt에 추가 |
| WebDriverWait import로 기존 생성 파일 깨짐 | 새로 generate할 때만 적용; 기존 파일은 재생성 시 갱신 |
| 06_heal 다중 SEL 적용 중 일부 실패 시 파일 오염 | heal 전 backup 복사본 유지, 전체 실패 시 backup 복원 |
| report_html 그룹 파싱 스키마 불일치 | parse_pipeline_to_groups()에 방어적 .get() 사용 |

---

## Verification Steps

```bash
# 1. Task 1 검증 — execute_results 구조 확인
python -c "
import json; s = json.load(open('state/pipeline.json'))
errs = s.get('execute_results', {}).get('errors', [])
assert isinstance(errs, list), 'errors must be list'
print('AC-1 PASS:', errs)
"

# 2. Task 2 검증 — 생성 코드에 WebDriverWait 포함 확인
python scripts/02_generate.py --platform android
grep -r "WebDriverWait" tests/generated/android/ && echo "AC-3 PASS"

# 3. Task 3 검증 — 리포트 파일 생성 확인
python scripts/05_execute.py --platform android --no-report --dry-run  # 서버 없이
ls reports/report.html && echo "AC-4 PASS"  # --report 플래그 시

# 4. Task 4 검증 — py_compile + flake8
python -m py_compile scripts/06_heal.py && echo "compile OK"
python -m flake8 scripts/06_heal.py && echo "lint OK"
```

---

## Sprint 4 작업 테이블

| # | 작업 | 담당 | 우선순위 | 상태 |
|---|------|------|----------|------|
| 1 | `05_execute.py` pytest 결과 파싱 → `execute_results.errors` 기록 | app-developer | CRITICAL | ⬜ |
| 2 | `02_generate.py` WebDriverWait 패턴 적용 | app-developer | HIGH | ⬜ |
| 3 | `report_html.py` + `05_execute.py` 연결 | app-developer | HIGH | ⬜ |
| 4 | `06_heal.py` 다중 SEL 재시도 루프 | app-developer | MEDIUM | ⬜ |
| 5 | 전체 AC 검증 | app-qa | - | ⬜ |

**예상 소요**: Task 1~4 병렬 불가 (공유 파일 없음 — 병렬 가능), Task 5는 4 완료 후 순차
