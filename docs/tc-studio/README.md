# TC 스튜디오 — 앱(iOS/Android) 이식 작업 안내

> **독자**: 이 폴더에서 새로 시작하는 Claude Code 세션과 작업자.
> 작성: 2026-10-01 · 개정: 2026-10-01(방향 변경 — 웹 저장소 수정 금지, 이 저장소로 이식)

## 한 줄 요약

웹 프로젝트(`qa-native-fixed`)의 **TC 스튜디오를 참고해 이 저장소(qa-native-app)에 직접 만든다.** 기획서·URL·Confluence·Figma를 넣으면 LLM이 TC 초안을 만들고, 엑셀을 가져오고, TC 라이브러리에서 관리하며, 앱 TC는 **And/iOS 결과를 비교**할 수 있다. 승인한 TC는 `testcases/{android,ios}/` md로 내보내 기존 파이프라인이 그대로 읽는다.

> **핵심 요구: And와 iOS 결과를 비교할 수 있으면 된다.** AUTO 열은 쓰지 않는다.

## 절대 규칙

- **`/Users/junghoyoung/qa-native-fixed`는 읽기 전용 참고 자료다.** 파일 수정·커밋·push·서버(8766) 재시작 모두 금지.
- 웹 코드를 참고할 때는 기준 커밋 **`f4e7a6b`** 를 읽는다(`git -C ../qa-native-fixed show f4e7a6b:<경로>`). 이식 후 웹 쪽 변경은 자동으로 따라오지 않는다.
- 이 저장소는 `main`에 직접 커밋하며, push는 사용자에게 확인받는다.
- LLM은 웹과 같이 `claude -p` CLI를 subprocess로 호출한다. LLM SDK(`anthropic` 등) import 금지(이 저장소 `CLAUDE.md` 핵심 원칙).

## 읽는 순서

1. [설계 — 무엇을 왜 이렇게 하는가](TC_STUDIO_APP_DESIGN.md): 결정, 이식 방식, 데이터 모델, 범위
2. [실행 계획 — 작업 목록](TC_STUDIO_APP_PLAN.md): Phase별 작업, 수정 파일, 테스트, 완료 기준, 체크박스

## 새 세션에서 이렇게 시작한다

```text
docs/tc-studio/README.md, TC_STUDIO_APP_DESIGN.md, TC_STUDIO_APP_PLAN.md를 읽고
실행 계획의 Phase 0부터 순서대로 진행해줘.
- qa-native-fixed는 읽기만 하고 절대 수정·커밋하지 마.
- 계획의 '사용자 확인' 항목에서는 멈추고 물어봐.
- 끝난 항목은 PLAN 체크박스를 체크하고 커밋에 포함해줘.
- 각 Phase가 끝나면 테스트 결과와 함께 짧게 보고하고, 다음 Phase 전에 확인받아.
- 파이썬을 고치면 8767 앱 대시보드를 재시작해. push는 물어보고 해.
```

이어서 할 때: "PLAN 체크박스와 git log로 진행 위치를 확인하고 남은 작업부터 이어서 해줘. 규칙은 README와 PLAN의 Global Constraints대로."

## 현재 상태 (2026-10-01 기준)

- 참고 원본: 웹 TC 스튜디오 `qa-native-fixed` main `f4e7a6b`. 사용자 설명서 `doc/guides/tc-studio/TC_AUTHORING_USER_GUIDE.md`.
- 앱 대시보드: `http://localhost:8767` (이 저장소, FastAPI).
- 예시 엑셀(양식 참고용일 뿐, 특정 양식에 맞추지 않는다): `~/Downloads/야핏무브_Full.xlsx`(2줄 헤더 `환경` 아래 `And | iOS`, 전용 TC는 반대쪽 `NA`), `~/Downloads/LODIS_통합테스트_230830_3차.xlsx`(1줄 헤더 `Android | iOS`).
- 웹 원본의 알려진 버그: Android/iOS 결과를 하나로 합쳐 저장하고 내보낼 때 두 열에 같은 값을 쓴다. **이식본에서는 처음부터 플랫폼별로 저장한다**(웹은 고치지 않는다).
- 이 저장소 작업 트리에 정리되지 않은 변경이 있다(Phase 0).
