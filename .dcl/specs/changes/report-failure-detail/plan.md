# Plan: report-failure-detail

**Date**: 2026-06-17

## Intent
실패한 테스트 케이스의 HTML 결과지에 Steps / 기대결과 / 스크린샷 / 영상을 표시한다.

## Chosen Approach: conftest hook + report_html 확장
- pytest conftest.py의 `pytest_runtest_makereport` hook으로 실패 시 screenshot 자동 캡처
- screenshots.json에 nodeid → 경로 매핑 저장 → 05_execute.py가 errors[]에 주입
- report_html.py가 TC 마크다운 파싱해 steps/expected 채우고, case_row에 screenshot/video 렌더링

## Spec

### What
실패 케이스 상세(case-detail) 영역에:
- Steps: TC 마크다운 `### 단계` 항목 (순서 리스트)
- Expected: TC 마크다운 `### 기대결과` 항목
- Screenshot: 실패 시점 캡처 이미지 (base64 inline 또는 상대 경로)
- Video: 전체 런 영상 링크 (이미 있으면 케이스 상세에도 표시)

### Why
현재는 pytest 에러 메시지만 보여 실패 원인 파악이 어렵다.

### Success Criteria
- [ ] 실패 케이스 상세에 Steps 리스트가 표시된다
- [ ] 실패 케이스 상세에 기대결과 텍스트가 표시된다
- [ ] 실패 케이스 상세에 스크린샷 이미지가 표시된다 (파일 있을 때)
- [ ] 실패 케이스 상세에 영상 링크가 표시된다 (파일 있을 때)
- [ ] 기존 PASS 케이스 표시에 회귀 없음
- [ ] 정적 검증 통과 (mock 데이터로 HTML 생성 확인)

### Out of scope
- iOS 영상 녹화 구현
- 스크린샷 base64 embed (상대경로 href 사용)

## Tasks

### Task 1: pytest conftest.py 생성 (screenshot hook)
- Goal: 실패 시 driver.save_screenshot() 호출 → state/screenshots.json 저장
- Files: tests/conftest.py (신규)
- Done when: 파일 존재, hook 함수 포함

### Task 2: 05_execute.py — screenshots.json → errors[] 주입
- Goal: parse_junit_xml 이후 screenshots.json 읽어 errors[].screenshot 필드 추가
- Files: scripts/05_execute.py
- Done when: _inject_screenshots() 함수 추가, parse_junit_xml 호출 후 적용

### Task 3: report_html.py — TC 마크다운 파싱 + case_row 확장
- Goal: parse_pipeline_to_groups에서 TC 마크다운 읽어 steps/expected 채우기
        case_row에 screenshot img 태그 + video 링크 렌더링
- Files: scripts/report_html.py
- Done when: case_row에 screenshot/video 섹션 포함, steps/expected 실값 표시

### Task 4: 정적 검증 스크립트 + 확인
- Goal: mock pipeline.json으로 HTML 생성 후 구조 확인
- Files: scripts/verify_report.py (임시)
- Done when: HTML 파일 생성, case-detail에 필드 존재 확인
