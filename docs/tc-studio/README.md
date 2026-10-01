# TC 스튜디오 — 앱(iOS/Android) 지원 작업 안내

> **독자**: 이 폴더에서 새로 시작하는 Claude Code 세션과 작업자.
> 작성: 2026-10-01 (qa-native-fixed 세션에서 에이전트 4명 논의 후 정리)

## 한 줄 요약

웹 프로젝트(`qa-native-fixed`)에 있는 **TC 스튜디오를 코드 1벌로 유지**하면서, 앱 TC(공통 TC 하나 + Android/iOS 결과)를 다루는 **앱 스위트 모드**를 추가하고, 이 앱 대시보드에서는 **같은 화면을 메뉴로 띄워** 쓰며, 앱 TC는 **엑셀로 이 저장소의 Import Studio에 넘겨** md로 변환한다.

## 읽는 순서

1. [설계 — 무엇을 왜 이렇게 하는가](TC_STUDIO_APP_DESIGN.md): 결정, 근거(LODIS 실데이터), 데이터 모델, 거절한 안
2. [실행 계획 — 작업 목록](TC_STUDIO_APP_PLAN.md): Phase별 작업, 수정 파일, 테스트, 완료 기준, 체크박스

## 두 저장소에 걸친 작업이다

| 저장소 | 경로 | 이 작업에서 하는 일 |
|---|---|---|
| 웹 (TC 스튜디오 본체) | `/Users/junghoyoung/qa-native-fixed` | 앱 스위트 모드, 플랫폼별 결과, 임베드 모드, 앱으로 보내기 |
| 앱 (이 저장소) | `/Users/junghoyoung/qa-native-app` | 대시보드 "TC 스튜디오" 메뉴, Import Studio 보강 |

- 계획의 각 작업 머리에 **작업 위치**가 적혀 있다. `qa-native-fixed` 작업은 그 저장소의 `CLAUDE.md` 규칙(레지스트리 상수, `update_state`, lessons_learned 등)을 따른다.
- 사용자는 TC 스튜디오 코드를 **한 곳에서만** 관리하길 원한다. 이 저장소로 TC 스튜디오 코드를 복사하지 않는다.
- 두 저장소 모두 `main`에 직접 커밋하며, push는 사용자에게 확인받는다.

## 새 세션에서 이렇게 시작한다

이 저장소 폴더에서 Claude Code를 켜고:

```text
docs/tc-studio/README.md, TC_STUDIO_APP_DESIGN.md, TC_STUDIO_APP_PLAN.md를 읽고
실행 계획의 Phase 0부터 순서대로 진행해줘. 각 Phase가 끝나면 테스트 결과와 함께 보고하고,
계획의 '사용자 확인' 항목에서는 멈춰서 물어봐줘.
```

## 현재 상태 (2026-10-01 기준)

- 웹 TC 스튜디오: `qa-native-fixed` main `f4e7a6b`. 사용자 설명서 `doc/guides/tc-studio/TC_AUTHORING_USER_GUIDE.md`.
- 웹 대시보드: `http://localhost:8766/tc-studio` (`cd qa-native-fixed && python3 agents/dashboard/serve.py --port 8766`).
- 앱 대시보드: `http://localhost:8767` (이 저장소, FastAPI).
- 실데이터: 웹 TC 스튜디오에 LODIS 앱 TC 1,731건이 들어 있다(스위트 이름이 `LODIS______________230830_3__`로 깨진 채 — 이름 버그는 고쳐졌으니 재가져오기로 바로잡을 수 있다). 원본 `~/Downloads/LODIS_통합테스트_230830_3차.xlsx`.
- **알려진 버그(Phase 1에서 고침)**: 웹 TC 스튜디오가 Android/iOS 결과를 하나로 합쳐 저장하고, 엑셀로 다시 내보내면 두 열에 같은 값을 쓴다.
- 이 저장소 작업 트리에 정리되지 않은 변경이 있다(Phase 0).
