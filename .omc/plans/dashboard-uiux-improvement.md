# Dashboard UI/UX 개선 기획서

**상태**: pending approval  
**작성일**: 2026-06-17  
**대상 파일**: `agents/dashboard/serve.py`

---

## 요구사항 요약

사용자 핵심 고통점: **스텝 실행 후 "다음 단계를 실행해야 하는지 멈춰야 하는지" 시스템이 알려주지 않음**

현재 문제:
- 6개 버튼이 동등하게 나열되어 전체 파이프라인 흐름/현재 위치 파악 어려움
- 스텝 완료 후 다음 액션을 사용자가 직접 판단해야 함
- 로그 박스 180px 고정 → 디버깅 시 불편
- `04_approve.py` 미구현이지만 버튼이 활성화되어 오류 발생

---

## 개선 우선순위

| 우선순위 | 기능 | 근거 |
|--------|------|------|
| 1 | 다음 액션 가이드 배너 | 핵심 고통점 직접 해결 |
| 2 | 파이프라인 진행률 인디케이터 | 전체 흐름 가시성 |
| 3 | 로그 확장/축소 토글 + 결과 요약 | 디버깅 편의성 |
| 4 | approve 버튼 disabled 처리 | 혼란 방지 |

---

## 기능 1: 다음 액션 가이드 배너

### 동작 명세

**성공(exit_code === 0):**
- 초록 배너: "완료. 다음: [다음스텝명] 실행하세요"
- 다음 스텝 버튼에 `suggested` CSS 클래스 (금색 테두리 + subtle pulse)
- heal(마지막) 성공 시: "파이프라인 완료. 리포트를 확인하세요"

**실패(exit_code !== 0):**
- 빨간 배너, 스텝별 분기:
  - `analyze` 실패: "Appium 연결 또는 디바이스 상태를 확인하세요. 재실행 권장."
  - `generate` 실패: "TC 마크다운 또는 screens.json 설정을 확인하세요."
  - `lint` 실패: "생성된 코드에 문법 오류. 수정 후 lint 재실행 or heal 실행."
  - `approve` 실패: "QA 승인 거부. 코드 검토 후 generate부터 재실행."
  - `execute` 실패: "테스트 실패 발생. 아래 실패 목록 확인. heal 실행으로 자동 패치 시도 가능."
  - `heal` 실패: "자동 패치 실패. 수동 수정 필요."
- execute 실패 시 heal 버튼에 `suggested` 표시

**소멸 조건:**
- 다음 스텝 시작 시 자동 소멸
- 닫기(X) 클릭 시 소멸

**approve 건너뛰기:**
- lint 성공 시 가이드: "다음: 테스트 실행 (approve 단계 건너뜀)"

### 구현 위치
- `agents/dashboard/serve.py:472-475` — 가이드 배너 HTML 삽입 (`.steps` 닫는 div 뒤, `.log-wrap` 앞)
- `agents/dashboard/serve.py:609-621` — `finishStep()` 함수에 가이드 로직 추가
- `agents/dashboard/serve.py:529-534` 부근 — 가이드 메시지 맵핑 객체 선언
- `agents/dashboard/serve.py:260-268` 부근 — `.suggested` 버튼 스타일 추가

### 수용 기준
- [ ] `finishStep()` 호출 후 1초 이내 가이드 배너 표시
- [ ] exit_code === 0 → 배너에 다음 스텝명 포함
- [ ] exit_code !== 0 → 스텝별 권장 액션 텍스트 포함
- [ ] 다음 스텝 버튼에 `suggested` 클래스 추가됨
- [ ] 배너 닫기(X) 클릭 시 소멸
- [ ] 새 스텝 시작 시 이전 배너 자동 소멸
- [ ] lint 성공 → 가이드가 execute를 안내함 (approve 건너뜀)
- [ ] heal 성공 → "파이프라인 완료" 메시지

---

## 기능 2: 파이프라인 진행률 인디케이터

### 동작 명세
- 6개 원형 노드 + 연결 라인으로 구성된 수평 바 (높이 약 40px)
- 위치: `platform-selector` 아래, `.steps` 위
- 노드 상태: idle(회색) / running(파란 펄스) / done(초록) / failed(빨강) / skipped(점선 회색)
- 연결 라인: 완료 구간 초록, 미완료 회색
- 우측 끝에 "N/6 완료" 텍스트
- approve 노드는 항상 skipped 스타일
- `pipeline.json`의 `last_completed_steps[]` 배열로 새로고침 후 복원

### 구현 위치
- `agents/dashboard/serve.py:389-392` — 인디케이터 HTML 삽입
- `agents/dashboard/serve.py:198-351` 내 style 블록 — 인디케이터 CSS 추가
- script 블록 내 — `updateProgressIndicator()` 함수 신규 작성
- `agents/dashboard/serve.py:972` 부근 — `save_state()` 호출 시 `last_completed_steps` 배열 업데이트

### 수용 기준
- [ ] 로드 시 6노드 수평 인디케이터 표시
- [ ] 스텝 실행 중 → 해당 노드 pulse
- [ ] 스텝 done → 노드 초록 + 연결 라인 초록 + "N/6 완료" 갱신
- [ ] 스텝 failed → 해당 노드 빨강
- [ ] approve 노드 항상 skipped 스타일(점선)
- [ ] 페이지 새로고침 후 진행 상태 복원

---

## 기능 3: 로그 확장/축소 + 스텝 결과 요약

### 로그 확장/축소
- 기본: 180px, "확장" 클릭 → 500px, 버튼 텍스트 "축소"로 변경
- `.log-header` 우측 "지우기" 옆에 토글 버튼 배치 (`agents/dashboard/serve.py:477`)

### 스텝 결과 요약 카드
- 스텝 완료 시 로그 박스 상단 1줄 요약:
  - analyze: "소요 Ns | 수집 화면: N개"
  - generate: "소요 Ns | 생성 파일: N개"
  - lint: "소요 Ns | 통과: N/N"
  - execute: "소요 Ns | 통과: N/N | 실패: N"
  - heal: "소요 Ns | 패치: N/N"
- 소요시간: `runStep()` 시작 시 `Date.now()` 기록, `finishStep()` 시 계산
- 새 스텝 시작 시 이전 요약 교체

### 수용 기준
- [ ] 로그 박스 헤더에 확장/축소 토글 버튼 존재
- [ ] 확장 → 500px, 축소 → 180px
- [ ] 스텝 완료 후 소요시간 "Ns" 형태 표시
- [ ] execute 완료 → 통과/실패 건수 요약 포함
- [ ] generate 완료 → 생성 파일 수 표시
- [ ] 새 스텝 시작 → 이전 요약 교체

---

## 기능 4: approve 버튼 disabled 처리

### 동작 명세
- approve 버튼: `disabled` 속성 + "(준비중)" 텍스트 또는 뱃지
- `step-num` 노드에 점선 테두리 스타일
- 클릭 시 서버 요청 없음

### 구현 위치
- `agents/dashboard/serve.py:435-441` — approve 버튼 HTML 수정

### 수용 기준
- [ ] approve 버튼 클릭 불가 (disabled)
- [ ] "(준비중)" 텍스트 표시
- [ ] 클릭 시 서버 요청 없음
- [ ] lint 성공 → 가이드가 approve 건너뛰고 execute 안내

---

## 리스크 및 완화책

| 리스크 | 영향 | 완화책 |
|--------|------|--------|
| 인라인 HTML 비대화 (1025줄 이상) | 유지보수 어려움 | 이번 완료 후 HTML/CSS/JS 별도 파일 분리를 Phase 2에 편입 |
| 가이드 메시지가 실제 패턴과 불일치 | 잘못된 안내 | 가이드 메시지를 JS 객체 한 곳에서 관리, 향후 서버 API 기반 확장 가능하게 설계 |
| 진행률 새로고침 후 유실 | 맥락 상실 | `pipeline.json`에 `last_completed_steps[]` 배열 필드 추가 |
| 로그 확장 시 레이아웃 불균형 | 시각적 깨짐 | `max-height: 500px` 상한 유지 + 스크롤 |

---

## 검증 체크리스트 (app-qa 전달용)

### 가이드 배너
- [ ] analyze exit 0 → 배너에 "다음: 코드 생성" 포함
- [ ] execute exit ≠ 0 → 배너에 "heal 실행" 권장 포함
- [ ] heal 성공 → "파이프라인 완료" 표시
- [ ] 배너 X 클릭 → 소멸
- [ ] 다음 스텝 시작 → 배너 자동 소멸

### 진행률 인디케이터
- [ ] 초기: 6노드 idle(회색)
- [ ] 실행 중: 해당 노드 pulse
- [ ] 완료: 초록 노드 + "N/6 완료" 갱신
- [ ] 새로고침 후 상태 복원

### 로그 확장
- [ ] 기본 180px (개발자 도구 Computed 확인)
- [ ] 확장 → 500px
- [ ] 축소 → 180px

### 결과 요약
- [ ] execute 완료 → "통과: X/Y | 실패: Z" 표시
- [ ] generate 완료 → 생성 파일 수 표시

### approve 비활성화
- [ ] 버튼 클릭 불가
- [ ] "(준비중)" 표시
- [ ] lint 성공 → execute 안내

### 회귀 테스트
- [ ] 기존 스텝 실행/취소/로그 폴링 정상
- [ ] 플랫폼 전환 후 가이드 정상
- [ ] 동시 2개 스텝 실행 거부 유지
- [ ] Appium 미기동 상태에서도 대시보드 렌더링 정상

---

## 구현 노트 (app-developer 전달용)

1. 단일 파일 `agents/dashboard/serve.py` 내에서 모든 변경
2. 구현 권장 순서: 가이드 배너 → approve disabled → 로그 확장 → 진행률 인디케이터 → 결과 요약
3. `pipeline.json`에 `last_completed_steps: []` 배열 필드 추가 (`save_state()` 시점에 기록)
4. 가이드 메시지는 JS 객체로 한 곳에서 선언 (유지보수 용이)
5. 인라인 HTML 비대화는 이번 구현 후 별도 리팩토링으로 분리
