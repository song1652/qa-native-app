# Locator Healing 운영 정책

## 목적

네이티브 앱의 UI 구조가 변경되어 생성된 locator가 실패했을 때, 사용자가 매번 GUI Appium Inspector를 조작하지 않아도 최신 native hierarchy를 기준으로 안전하게 locator를 갱신합니다.

기준은 GUI 화면이 아니라 Appium이 제공하는 `page_source` XML입니다. Appium Inspector가 보여주는 native hierarchy와 같은 계층 정보를 자동 수집해 사용합니다.

## 전체 흐름

```text
테스트 실패
  ↓
06_heal.py 시작
  ↓
01_analyze.py를 통해 최신 page_source 수집
  ↓
resource-id/content-desc/name/label/value/hint/text 후보 추출
  ↓
원래 locator와 후보의 유사도·속성·플랫폼 비교
  ↓
유일하고 신뢰도 높은 후보인가?
  ├─ 예 → config/locators.json 갱신 → 재생성 시 반영
  └─ 아니오 → 자동 변경하지 않고 heal 실패 기록
```

새 snapshot 수집이 불가능하면 기존 `state/pipeline.json` snapshot을 사용할 수 있지만, 오래된 화면일 수 있으므로 결과를 확정하지 못하면 실패로 처리합니다.

## Locator source of truth

`config/locators.json`이 생성과 healing의 기준입니다.

```json
{
  "schema_version": 1,
  "targets": {
    "login.username_field": {
      "android": {"strategy": "ID", "value": "com.example:id/username"},
      "ios": {"strategy": "ACCESSIBILITY_ID", "value": "username"}
    }
  }
}
```

생성된 `tests/generated/**/*.py`는 산출물입니다. healing 결과를 산출물에만 반영하지 않고 registry를 갱신한 뒤 다시 생성해야 다음 실행에도 유지됩니다.

## 후보 탐색 규칙

### Android

1. `resource-id` → `AppiumBy.ID`
2. `content-desc` → `AppiumBy.ACCESSIBILITY_ID`
3. 필요한 경우 UiAutomator 전략
4. XPath는 마지막 수단

### iOS

1. `name` 또는 `label` → `AppiumBy.ACCESSIBILITY_ID`
2. `value`/predicate 또는 class chain
3. XPath는 마지막 수단

`text`, `value`, `hint`처럼 표시 문자열만 일치하는 후보는 안정성이 낮습니다. 동일 문자열을 가진 요소가 둘 이상이면 자동 선택하지 않습니다.

## 자동 반영 조건

- 현재 플랫폼의 snapshot이어야 합니다.
- 후보 속성값이 비어 있지 않아야 합니다.
- 원래 locator와 후보가 정확히 일치하거나 충분히 강한 유사도를 가져야 합니다.
- 최고 후보가 하나뿐이어야 합니다.
- 같은 값이라도 서로 다른 native 속성에 매칭되면 모호한 것으로 취급합니다.
- 생성된 코드에 `target_ref`가 있어 registry 항목과 연결되어야 합니다.

조건을 만족하지 못하면 임의로 XPath를 만들거나 첫 번째 요소를 선택하지 않습니다.

## 실패 시 확인할 항목

1. Appium 서버가 `http://localhost:4723/status`에서 응답하는지 확인합니다.
2. Android 디바이스 또는 iOS 시뮬레이터가 연결/부팅되었는지 확인합니다.
3. `state/pipeline.json`의 `dom_info`에 현재 플랫폼 XML이 있는지 확인합니다.
4. `logs/run_heal*.txt`에서 snapshot 수집 및 후보 매칭 결과를 확인합니다.
5. Appium Inspector로 실제 화면을 직접 확인하고 `config/locators.json`을 수정합니다.
6. strict 생성으로 다시 생성합니다.

```bash
python scripts/02_generate.py --platform android --strict-locators
python scripts/02_generate.py --platform ios --strict-locators
```

## 운영상 주의사항

- healing은 테스트의 기대 동작을 수정하지 않고 locator만 갱신합니다.
- 여러 요소가 같은 텍스트를 가지는 화면에서는 accessibility ID, resource ID, predicate 등 더 안정적인 식별자를 Inspector에서 확인해야 합니다.
- 화면 이동 action이 바뀐 경우 locator healing만으로 해결하지 말고 `config/screens.json`도 함께 수정합니다.
- locator 변경 이력은 `config/locators.json`의 diff와 `agents/lessons_learned.md`를 함께 확인합니다.
