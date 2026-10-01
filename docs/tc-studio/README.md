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
3. [인수인계 — 다른 LLM에게 맡기는 법](HANDOFF.md): 프롬프트, 검토 체크리스트

## 일 맡기는 법

다른 LLM에게 맡길 때 쓸 프롬프트, Phase별 검토 체크리스트, 사용자 확인 지점의 답은 **[HANDOFF.md](HANDOFF.md)** 에 모두 있다.

## 현재 상태 (2026-10-01 기준)

- 참고 원본: 웹 TC 스튜디오 `qa-native-fixed` main `f4e7a6b`. 사용자 설명서 `doc/guides/tc-studio/TC_AUTHORING_USER_GUIDE.md`.
- 앱 대시보드: `http://localhost:8767` (이 저장소, FastAPI). TC 스튜디오 전용 화면: `http://localhost:8767/tc-studio`.
- 예시 엑셀(양식 참고용일 뿐, 특정 양식에 맞추지 않는다): `~/Downloads/야핏무브_Full.xlsx`(2줄 헤더 `환경` 아래 `And | iOS`, 전용 TC는 반대쪽 `NA`), `~/Downloads/LODIS_통합테스트_230830_3차.xlsx`(1줄 헤더 `Android | iOS`).
- 웹 원본의 알려진 버그: Android/iOS 결과를 하나로 합쳐 저장하고 내보낼 때 두 열에 같은 값을 쓴다. **이식본에서는 처음부터 플랫폼별로 저장한다**(웹은 고치지 않는다).
- **Phase 1~6 기능 이식 및 임시 데이터 검증 완료**(2026-10-01). 실제 Claude 호출과 실제 `testcases/` 반영은 사용자 결정 대기. 삭제된 TC 1개와 `-` 스크린샷은 출처 미상으로 보류(손대지 않음).
