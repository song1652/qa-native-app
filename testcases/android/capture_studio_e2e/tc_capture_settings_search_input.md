# tc_capture_settings_search_input: 설정 검색창 텍스트 입력과 검증

## 플랫폼
Android

## TC 그룹
capture_studio_e2e

## 단계

1. 화면 탭
2. wait
3. "com.google.android.settings.intelligence:id/open_search_view_edit_text" 입력
4. wait
5. open_search_view_edit_text 텍스트 확인: "Bluetooth"

## 기대결과

1. 설정 검색 화면이 열린다.
2. 검색 화면이 안정적으로 표시된다.
3. 검색창에 Bluetooth가 입력된다.
4. 검색 결과가 표시될 때까지 기다린다.
5. 검색창에 Bluetooth가 표시된다.
