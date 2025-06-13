# 대시보드 디자인 개선 체크리스트

## 1. HTML 구조 및 스타일 변경

[X] templates/index.html 파일의 전체 HTML 구조를 새로운 디자인 예시 코드로 교체
[X] Tailwind CSS 및 Font Awesome 라이브러리 링크 추가
[X] 제공된 CSS 스타일을 templates/index.html에 통합

## 2. 백엔드 데이터 통합

- [X] 기존 Flask 백엔드에서 제공되는 동적 데이터 (`weather_data`, `notices`, `current_video_id`, `refresh_interval`)를 새로운 프론트엔드 구조에 맞게 통합
    - [X] `hourly-weather` 및 `weekly-weather`에 날씨 데이터 동적으로 렌더링
    - [X] 공지사항 탭 (`ts-content`, `aviation-alert-content`, `aviation-notice-content`)에 공지사항 데이터 동적으로 렌더링

## 3. JavaScript 로직 조정

- [X] `updateTime`, `switchNoticeTab`, `switchWeatherTab`, `getWeatherIcon` 등 기존 JavaScript 함수를 새 HTML 구조에 맞게 수정 및 조정
- [X] 동영상 플레이어 (`youtube-player` iframe) 설정 및 제어 로직 통합

## 4. 추가 기능 및 확인

- [X] `0.0°C` 온도 표시 문제에 대한 사용자 피드백 확인 및 필요 시 조정
- [X] 최종적으로 모든 기능이 새로운 디자인에서 올바르게 작동하는지 확인 및 테스트

## 5. 추가 변경 사항

- [X] 공지사항 링크 색상 흰색으로 변경 및 밑줄 제거 (CSS) 