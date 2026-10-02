# 현재 제품 화면

2026-10-02에 `main`의 실제 `agents/dashboard/serve.py`(http://localhost:8767/)에서 촬영한 밝은 UI입니다. 브라우저 폭 1440px, 높이 1000px, 배율 1로 전체 페이지를 저장했습니다. 주요 화면은 `main`의 밝은 UI를 기준으로 촬영했고, Capture 실행 대상 정책 변경 뒤 관련 화면을 같은 날 다시 촬영했습니다.

| 파일 | 화면 |
|---|---|
| [dashboard.png](dashboard.png) | 대시보드와 통과·주의·실패 범례 |
| [pipeline.png](pipeline.png) | 파이프라인 설정과 기기 선택 |
| [quick-run.png](quick-run.png) | 빠른 실행과 생성된 테스트 선택 |
| [quick-run-result.png](quick-run-result.png) | 저장된 11:08 실행 결과의 TC 목록과 증거(실제 실패 영상) |
| [reports.png](reports.png) | 리포트 목록과 저장된 실행 결과 미리보기 |
| [history.png](history.png) | 실행 기록 |
| [environment.png](environment.png) | Appium·Android·iOS 환경 설정 |
| [capture.png](capture.png) | 화면 캡처로 작성 |
| [capture-emulator-unavailable.png](capture-emulator-unavailable.png) | 설명용 상태 예시: 에뮬레이터가 꺼지고 실기기만 연결된 경우 시작 차단 |
| [tc-studio.png](tc-studio.png) | TC 스튜디오 기획 정보·생성 |
| [tc-library.png](tc-library.png) | TC 스튜디오 라이브러리 |
| [tc-review.png](tc-review.png) | TC 스튜디오 초안 검토 |
| [tc-export.png](tc-export.png) | TC 스튜디오 내보내기 |

현재 저장된 결과와 조회된 환경 상태를 그대로 표시했습니다. 리포트 미리보기는 2026-10-02 11:08 실행의 실제 저장 결과(3건 중 1건 통과, 2건 실패)입니다. 이 캡처를 위해 테스트 실행, TC 생성·저장·삭제, 기기 시작·종료를 하지 않았습니다. 실행 기록은 브라우저의 로컬 저장 이력에 따라 비어 있을 수 있습니다.

화면의 기기명·파일명·상태·결과 수는 촬영 시점의 값이며 사용 환경마다 달라집니다.

`capture-emulator-unavailable.png`만 브라우저 기기 목록 응답과 상단 기기 표시를 설명용 데이터로 바꾼 상태 예시입니다. 가상 기기를 실제로 종료하거나 실기기에 세션을 연결하지 않았습니다. 환경 확인은 현재 UI로 수행했고, 세션 시작 버튼의 비활성화와 안내를 확인했습니다. 나머지 제품 화면 이미지는 실제 조회 상태입니다.
