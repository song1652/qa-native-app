# PRD — Element-first Capture Studio

## 1. 제품 정의

Capture Studio는 사용자가 실제 Android/iOS 앱 화면의 요소를 선택하고 조작하는 과정을 기록하여, 검증 가능한 locator와 테스트 Step을 만드는 반수동 테스트 제작 도구다.

제품의 중심은 문서 입력이 아니라 **요소 선택과 실제 조작 증거 수집**이다. 목적, 사전조건, 기대 결과는 기록된 동작을 테스트 케이스로 완성하기 위한 보조 정보로 다룬다.

## 2. 해결할 문제

- 앱의 UI hierarchy나 WebView DOM을 모르면 신뢰할 수 있는 자동화 코드를 만들기 어렵다.
- Appium Inspector에서 요소를 찾고 코드와 TC에 다시 옮기는 작업은 반복적이다.
- 사람이 단말을 직접 터치하면 어떤 요소가 실행되었는지 정확한 자동화 근거가 남지 않는다.
- 실패 후 locator를 복구하려면 최초 요소의 속성, context와 화면 snapshot이 필요하다.

## 3. 목표

- Capture Studio의 미러링 화면에서 선택한 요소를 UI hierarchy 또는 DOM 노드와 연결한다.
- 선택 요소의 locator 후보를 생성하고 실제 세션에서 유일성을 검증한다.
- 클릭, 입력, 스와이프, 뒤로 가기와 context 전환을 순서대로 로그에 쌓는다.
- 기록된 요소와 동작으로 테스트 Step 초안을 생성한다.
- 사용자가 기대 결과와 검증 요소를 보완한 뒤 TC Markdown과 pytest 코드를 생성한다.
- 실행 실패 시 최초 capture evidence를 locator healing의 기준으로 사용한다.

## 4. 비목표

- 사용자의 업무 의도나 기대 결과를 확인 없이 확정하지 않는다.
- 좌표만으로 영구 테스트 코드를 만들지 않는다.
- 모호한 locator를 자동 승인하지 않는다.
- WebView가 없는 화면에서 Playwright를 시작하지 않는다.
- 일반적인 원격 디바이스 팜을 1차 범위에 포함하지 않는다.

## 5. 핵심 사용자 흐름

1. OS, 디바이스와 앱을 선택하고 Appium 세션을 시작한다.
2. Native UI hierarchy를 수집하고 실제 WebView가 있으면 DOM도 수집한다.
3. 사용자가 Capture Studio의 디바이스 화면에서 요소를 선택한다.
4. 시스템이 좌표와 hierarchy/DOM 노드를 연결하고 요소를 강조한다.
5. locator 후보, 일치 개수와 안정성을 표시한다.
6. 사용자가 클릭 또는 입력을 실행하면 Appium/Playwright 명령으로 전달한다.
7. 실행 전후 snapshot, screenshot, context와 결과를 Action Timeline에 기록한다.
8. 시스템이 로그를 테스트 Step 초안으로 변환한다.
9. 사용자가 기대 결과와 검증할 요소를 지정한다.
10. locator 검토 후 TC Markdown, `screens.json`, `locators.json`과 pytest 코드를 생성한다.

## 6. 기능 요구사항

### FR-1 세션과 화면 구조

- 최초 context는 `NATIVE_APP`이어야 한다.
- Native 화면은 Appium `page_source` 기반 UI hierarchy를 표시해야 한다.
- 실제 WebView context가 감지된 경우에만 WebView DOM 탭을 활성화해야 한다.
- 화면 snapshot과 구조 데이터는 동일 시점 ID로 연결해야 한다.

### FR-2 요소 선택

- 미러링 화면의 클릭 좌표와 겹치는 가장 구체적인 요소를 선택해야 한다.
- 화면과 hierarchy/DOM에서 같은 요소를 양방향 강조해야 한다.
- class/tag, text, accessibility, resource ID, bounds와 context를 보여줘야 한다.
- 부모·자식 후보가 겹치면 사용자가 원하는 노드를 변경할 수 있어야 한다.

### FR-3 Locator 검증

- Android는 resource ID/accessibility, iOS는 accessibility/predicate/class chain을 우선한다.
- WebView는 test id, role/name, label, 안정적인 CSS 순으로 후보를 제시한다.
- 후보별 일치 개수, surface, strategy, value와 안정성을 표시해야 한다.
- 유일하지 않은 후보는 승인 전까지 코드 생성 대상에서 제외해야 한다.

### FR-4 동작 로그

- tap, long press, input, clear, swipe, back, context switch와 assertion을 기록해야 한다.
- 로그에는 시간, action, context, target reference, locator, 실행 전후 snapshot과 성공 여부가 포함되어야 한다.
- 입력 비밀값은 원문을 저장하지 않고 데이터 키와 마스킹 값만 표시해야 한다.
- 로그 항목은 삭제, 재정렬, 재실행할 수 있어야 한다.

### FR-5 Step과 기대 결과

- 각 action log로 사람이 읽을 수 있는 테스트 Step을 자동 생성해야 한다.
- 사용자는 Step 문구를 수정하고 기대 결과를 추가할 수 있어야 한다.
- 기대 결과는 화면 변화 또는 사용자가 선택한 검증 요소와 연결할 수 있어야 한다.
- 기대 결과 미입력 상태에서도 capture를 계속할 수 있지만 최종 저장 시 경고해야 한다.

### FR-6 저장과 생성

- 한 Markdown 파일에는 TC 하나만 저장해야 한다.
- 승인된 locator만 `config/locators.json`에 반영해야 한다.
- 플랫폼과 그룹에 따라 `testcases/{platform}/{group}`에 저장해야 한다.
- 기존 strict locator 코드 생성기를 사용해야 한다.

### FR-7 Healing

- 실패 locator와 최초 capture snapshot을 같은 surface 안에서 비교해야 한다.
- 신뢰도 높고 유일한 후보만 자동 healing 대상으로 허용해야 한다.
- 모호한 후보는 Capture Studio의 재확인 목록으로 보내야 한다.
- 3회 실패 시 Jira 정책에 따라 로그, screenshot, 영상과 후보 비교를 첨부해야 한다.

## 7. 화면 우선순위

1. 실제 디바이스 화면과 선택 요소 강조
2. UI hierarchy/WebView DOM과 선택 요소 상세
3. 실시간 Action Timeline
4. Locator 후보 및 승인 상태
5. Step/기대 결과 편집
6. TC와 코드 미리보기

## 8. 데이터 산출물

- Capture session: `state/captures/{session_id}`
- TC Markdown: `testcases/{platform}/{group}/tc_*.md`
- 화면 정의: `config/screens.json`
- Locator registry: `config/locators.json`
- 생성 코드: `tests/generated/{platform}/{group}/tc_*.py`

## 9. 성공 기준

- 사용자가 Inspector와 코드를 오가지 않고 요소를 선택하여 TC 한 건을 만들 수 있다.
- 모든 실행 Step에 요소, context와 전후 snapshot 근거가 남는다.
- 선택 요소의 locator가 실제 세션에서 유일하게 검색된다.
- Native-only 앱은 UI hierarchy만으로 완성되며 WebView 도구가 실행되지 않는다.
- Hybrid 앱은 Native/WebView 전환이 로그와 생성 코드에 동일하게 반영된다.
- 생성 결과가 기존 lint, 실행, 리포트와 healing 파이프라인을 통과한다.

## 10. MVP

- Android Emulator
- Native UI hierarchy 및 Android WebView DOM
- 요소 선택, 탭, 입력, 뒤로 가기, context 전환
- Action Timeline과 locator 승인
- Step 초안 및 기대 결과 입력
- Markdown, registry와 pytest 생성

