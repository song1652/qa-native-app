# 문서 안내

현재 제품 사용법과 화면 이미지를 모았습니다. 설치와 첫 실행은 온보딩, 화면별 조작은 사용자 가이드에서 확인하세요.

## 사용 가이드

- [QA Control Center 사용자 가이드](guides/USER_GUIDE.html): 기존 가이드를 확장한 상세 사용법. 시작 경로, 엑셀 매핑·초안 검토·내보내기, 화면 캡처 작성, 오류별 재시도·알림·증거 분석, 리포트·기록, 기기 설정과 오류 해결을 설명합니다.
- [온보딩](../ONBOARDING.md): 설치·환경 준비·첫 실행 절차

## 현재 화면과 주소

앱 대시보드 기본 주소는 `http://localhost:8767`입니다. `8766`은 별도 웹 참고 저장소의 포트입니다. 상단 파란 문서 체크 아이콘과 **QA Control Center** 제목은 대시보드로 이동하며, 실행 버튼은 **파이프라인**과 **빠른 실행** 화면에 있습니다. 오류가 있으면 공통 헤더의 **알림**에서 원인과 다음 조치를 확인합니다. 메뉴 이동·다시 선택은 해당 화면 데이터를 갱신하고 선택한 주소는 새로고침·뒤로/앞으로 이동에도 유지됩니다.

주요 화면은 2026-10-02의 실제 로컬 캡처이며, 대시보드·실행 기록과 오류 알림 패널은 2026-10-03에 촬영했습니다. 이전 전체 화면에는 새 알림 표시가 없을 수 있습니다. 촬영 시점의 기기명·파일명·결과 수는 사용 환경마다 달라집니다. [촬영 기준과 출처](images/user-guide/README.md)를 함께 확인하세요.

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
| 오류 알림 | 공통 헤더의 **알림** | [현재 알림 패널](images/user-guide/recovery-notices.png) |

엑셀 가져오기는 **TC 스튜디오 → 엑셀 가져오기**로 엽니다. 독립 사이드바 메뉴는 없으며 예전 `/?view=import`는 `/tc-studio?import=1`로 이동합니다. 리포트 체크박스는 삭제 대상을 선택하고 **열기**는 미리보기를 엽니다. 리포트 본문 상단에는 대시보드 링크·PDF 버튼이 없습니다.

## 운영 안정화 범위

현재 사용 가이드는 **1·2·3차 안정화가 누적 적용된 main**의 정책을 설명합니다.

| 단계 | 주요 변경 | 변경 커밋 |
|---|---|---|
| 1차 | 실행 충돌 방지, 취소 후 종료 확인, 실행별 결과·복구 변경 관리 | `2574027` |
| 2차 | 서버 재시작 후 실행 추적, 단계 시간 제한, Capture 연결 대기·상태 저장 | `fc5ff33` |
| 3차 | 오류별 읽기 재시도, 복구 검증 실패 시 중단, 대응 알림, 실패 기록 보존 | `505aa09` |

다른 저장소에 동일한 작업을 적용할 때는 **현재 main의 1·2·3차 변경을 모두 비교**합니다. 3차 커밋 하나만 적용하면 1·2차 변경은 포함되지 않습니다. 포트·기기·앱·Jira 설정과 로컬 실행 자료는 대상 프로젝트의 설정을 유지합니다.

- [실행 충돌·자동 복구](guides/USER_GUIDE.html#pipeline-recovery-policy)
- [재시작·시간 초과 대응](guides/USER_GUIDE.html#pipeline-restart-timeout)
- [오류별 재시도·알림](guides/USER_GUIDE.html#error-retry-notices)
- [실행 기록·보존](guides/USER_GUIDE.html#quickrun-retention-links)

## 화면 이미지와 촬영 기준

- [현재 제품 화면](images/user-guide/README.md): 밝은 UI의 실제 전체 화면·알림 패널 캡처와 촬영 시점·출처
