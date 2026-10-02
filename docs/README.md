# 문서 안내

현재 제품 사용법과 화면 이미지를 모았습니다. 설치와 첫 실행은 온보딩, 화면별 조작은 사용자 가이드에서 확인하세요.

## 사용 가이드

- [QA Control Center 사용자 가이드](guides/USER_GUIDE.html): 기존 가이드를 확장한 상세 사용법. 시작 경로, 엑셀 매핑·초안 검토·내보내기, 화면 캡처 작성, 실행·재시도·증거 분석, 리포트·기록, 기기 설정과 오류 해결을 설명합니다.
- [온보딩](../ONBOARDING.md): 설치·환경 준비·첫 실행 절차

## 현재 화면과 주소

앱 대시보드 기본 주소는 `http://localhost:8767`입니다. `8766`은 별도 웹 참고 저장소의 포트입니다. 상단 파란 문서 체크 아이콘과 **QA Control Center** 제목은 대시보드로 이동하며, 실행 버튼은 **파이프라인**과 **빠른 실행** 화면에 있습니다. 메뉴 이동·다시 선택은 해당 화면 데이터를 갱신하고 선택한 주소는 새로고침·뒤로/앞으로 이동에도 유지됩니다.

다음 이미지는 2026-10-02 현재 제품의 실제 로컬 화면입니다. 촬영 시점의 기기명·파일명·결과 수는 사용 환경마다 달라집니다. [촬영 기준과 출처](images/user-guide/README.md)를 함께 확인하세요.

| 메뉴 | 주소 | 현재 화면 |
|---|---|---|
| 대시보드 | `/` | [대시보드](images/user-guide/dashboard.png) |
| TC 스튜디오 | `/tc-studio` | [TC 스튜디오](images/user-guide/tc-studio.png) |
| 화면 캡처로 작성 | `/?view=capture` | [캡처 작성](images/user-guide/capture.png) |
| 파이프라인 | `/?view=pipeline` | [파이프라인](images/user-guide/pipeline.png) |
| 빠른 실행 | `/?view=tests` | [빠른 실행](images/user-guide/quick-run.png) |
| 리포트 | `/?view=reports` | [목록과 미리보기](images/user-guide/reports.png) |
| 실행 기록 | `/?view=history` | [실행 기록](images/user-guide/history.png) |
| 환경 설정 | `/?view=config` | [환경 설정](images/user-guide/environment.png) |

엑셀 가져오기는 **TC 스튜디오 → 엑셀 가져오기**로 엽니다. 독립 사이드바 메뉴는 없으며 예전 `/?view=import`는 `/tc-studio?import=1`로 이동합니다. 리포트 체크박스는 삭제 대상을 선택하고 **열기**는 미리보기를 엽니다. 리포트 본문 상단에는 대시보드 링크·PDF 버튼이 없습니다.

## 화면 이미지와 촬영 기준

- [현재 제품 화면](images/user-guide/README.md): 현재 밝은 UI의 실제 전체 화면 캡처와 출처
- [환경 설정 이미지 설명](images/env-setup/README.md): 환경 설정 상태별 캡처와 실제 화면·브라우저 예시 상태 구분
