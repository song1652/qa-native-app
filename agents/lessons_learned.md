# Lessons Learned — App QA

> 앱 테스트 자동화 과정에서 발견된 패턴과 교훈을 기록합니다.
> 코드 패치 전 반드시 이 파일을 확인하세요.

## Appium / Android


<!-- 패턴 발견 시 아래 형식으로 추가 -->
<!-- ### [오류 유형] 제목
**문제**: 무슨 오류가 났는가
**원인**: 왜 났는가
**해결**: 어떻게 고쳤는가
**적용 범위**: 어떤 상황에서 동일하게 적용되는가 -->

### [Locator Heal] ACCESSIBILITY_ID → ID 전환 패턴

**문제**: `AppiumBy.ACCESSIBILITY_ID, SEL_USERNAME_FIELD` 형태로 요소를 탐색할 때 `NoSuchElementException` 발생. `tc_001_login.py`의 `test_login_success`에서 최초 확인.

**원인**: Android 앱이 View에 `contentDescription` 속성을 설정하지 않은 경우 ACCESSIBILITY_ID 탐색이 실패한다. 로그인 화면의 username/password 필드처럼 입력 위젯은 `contentDescription`보다 `resource-id`(`com.example:id/username_field` 형태)만 가지는 경우가 많다.

**해결**: `06_heal.py`의 `HEAL_STRATEGIES = ["ACCESSIBILITY_ID", "ID", "XPATH"]` 순서에 따라 자동 전환. `_replace_strategy_in_source()`가 소스 내 `AppiumBy.ACCESSIBILITY_ID, SEL_USERNAME_FIELD`를 `AppiumBy.ID, SEL_USERNAME_FIELD`로 교체한 뒤 pytest 재실행으로 통과 여부 확인.

**적용 범위**: 생성된 TC 파일(`tests/generated/android/`) 전체. `contentDescription`이 없는 EditText, Button, TextView 위젯에 동일하게 적용.

---

### [Locator Heal] ID → XPATH 전환 패턴 (최후 수단)

**문제**: ACCESSIBILITY_ID 전환 실패 후 ID 전략으로도 `NoSuchElementException`이 계속 발생. `06_heal.py`의 두 번째 heal 시도에서 확인.

**원인**: resource-id가 앱 빌드 환경이나 프로드가 기트 variant(`debug`/`release`)에 따라 달라지거나, 요소에 id가 아예 없는 경우. 특히 서드파티 라이브러리 컴포넌트나 동적으로 추가된 View는 resource-id를 갖지 않는다.

**해결**: `HEAL_STRATEGIES`의 마지막 전략인 `XPATH`로 전환. `_replace_strategy_in_source()`가 `AppiumBy.ID`를 `AppiumBy.XPATH`로 교체. XPATH 전략 적용 시 SEL 상수값(`username_field`)은 XPath 표현식(`//android.widget.EditText[@index='0']` 등)으로 수동 수정 필요 — heal 자동화 범위 밖이므로 수동 개입 후 재실행.

**적용 범위**: 모든 heal 자동화 대상 TC. XPATH 전환 후에도 실패 시 `heal_results.failed`에 기록되며 수동 디버깅 필요.

---

### [Selector Target] screens.json placeholder가 실제 resource-id와 불일치

**문제**: `01_analyze.py`의 `navigate_to_screen()`에서 `_find_element(driver, "username_field")` 호출 시 `NoSuchElementException` 발생. `config/screens.json`의 `target` 값이 실제 앱 resource-id와 다를 때 발생.

**원인**: `screens.json`의 `target` 필드(`username_field`, `login_button`, `nav_files` 등)는 코드 생성 단계의 placeholder다. `_find_element()`는 콜론(`:`) 포함 여부로 전략을 분기하는데(`com.example:id/foo` → `AppiumBy.ID`, 그 외 → `AppiumBy.ACCESSIBILITY_ID`), placeholder는 콜론이 없으므로 ACCESSIBILITY_ID로 탐색한다. 실제 앱 요소에 `contentDescription`이 없으면 탐색 실패.

**해결**: `adb shell uiautomator dump`로 실제 XML을 덤프한 뒤 resource-id 확인. `screens.json`의 `target`을 `com.directcloud:id/input_username` 형태의 실제 resource-id로 교체. 교체 후 `01_analyze.py --screen login`으로 단일 화면 재수집 가능.

**적용 범위**: `screens.json` 초기 설정 시 전 항목. `01_analyze.py`와 `06_heal.py` 모두 영향받음. TC 생성 전 반드시 placeholder를 실제값으로 검증해야 함.

---

### [Timing] 화면 로딩 전 탐색 시도로 인한 false NoSuchElementException

**문제**: `01_analyze.py`의 `collect_screen_xml()`에서 `navigate_to_screen()` 직후 `driver.page_source` 호출 시 이전 화면의 XML이 반환되거나, 전환 직후 `find_element`가 `NoSuchElementException` 발생.

**원인**: `navigate_to_screen()`의 마지막 action(예: `tap login_button`) 실행 직후 화면 전환 애니메이션이 완료되기 전에 다음 요소 탐색을 시도. `collect_screen_xml()`의 `time.sleep(1)` 대기는 화면 전환 속도에 따라 부족할 수 있으며, 특히 에뮬레이터가 느릴 때 문제.

**해결**: `time.sleep(1)` 값을 화면 특성에 맞게 조정하거나, `WebDriverWait`를 사용해 특정 요소가 나타날 때까지 명시적 대기로 전환. 로그인 → 파일 목록 전환처럼 네트워크 요청이 수반되는 화면은 `sleep(3)` 이상 필요. `heal`에서는 이 오류가 `NoSuchElementException`으로 기록되므로 heal 시도 전 timing 문제인지 먼저 확인.

**적용 범위**: `01_analyze.py`의 모든 화면 수집 단계. 에뮬레이터 환경에서 특히 빈번. 실기기는 더 빠르므로 sleep 값을 환경별로 분리 관리 권장.

## iOS

<!-- iOS 관련 패턴은 여기에 추가 -->

## 공통

<!-- 플랫폼 공통 패턴 -->
