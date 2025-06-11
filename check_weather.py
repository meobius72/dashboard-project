import sys
import math
from datetime import datetime, timedelta, timezone
import json
import requests

# app.py에서 KMAWeatherAPI 클래스 및 convert_gps_to_grid 함수를 임포트
# sys.path에 현재 디렉토리를 추가하여 app.py를 찾을 수 있도록 함
sys.path.append('.')
from app import KMAWeatherAPI

KMA_API_KEY = '6pbnk4lATQeW55OJQG0Hzw' # 사용자 제공 API 키

weather_api = KMAWeatherAPI(KMA_API_KEY)

# 하계동의 위경도 (참고용, 직접 사용하지 않음)
HAGYE_DONG_LATITUDE = 37.6365682
HAGYE_DONG_LONGITUDE = 127.0679542

# 엑셀 시트에서 확인된 하계동의 격자 좌표를 직접 사용
nx, ny = 62, 128

# 현재 시간을 기준으로 base_date 및 base_time 설정
current_time_utc = datetime.now(timezone.utc)
kst_offset = timedelta(hours=9)
current_time_kst = current_time_utc + kst_offset

base_date = current_time_kst.strftime('%Y%m%d')

# API 호출은 매시간 45분 이후 권장
if current_time_kst.minute < 45:
    base_time_dt = current_time_kst - timedelta(hours=1)
else:
    base_time_dt = current_time_kst

base_time = base_time_dt.strftime('%H%M')

# 시간을 30분 단위로 올림 (API 정책에 따름)
minute = int(base_time[2:4])
if minute >= 30:
    base_time = base_time[:2] + '30'
else:
    base_time = base_time[:2] + '00'

# 24시인 경우 00시로 조정
if base_time == '2400':
    base_time = '0000'

print(f"API 호출 파라미터: base_date={base_date}, base_time={base_time}, nx={nx}, ny={ny}")

# API 호출 및 응답 출력
response = weather_api.get_realtime_weather(latitude=HAGYE_DONG_LATITUDE, longitude=HAGYE_DONG_LONGITUDE)
print(json.dumps(response, indent=4, ensure_ascii=False)) 