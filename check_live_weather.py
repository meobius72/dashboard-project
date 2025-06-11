import sys
import math
from datetime import datetime, timedelta, timezone
import json
import requests

sys.path.append('.')
from app import KMAWeatherAPI, convert_gps_to_grid # convert_gps_to_grid는 사용하지 않지만 호환성을 위해 유지

KMA_API_KEY = '6pbnk4lATQeW55OJQG0Hzw' # 사용자 제공 API 키

weather_api = KMAWeatherAPI(KMA_API_KEY)

# 엑셀 시트에서 확인된 하계동의 격자 좌표를 직접 사용
nx, ny = 62, 128

# KMAWeatherAPI._get_base_date_time() 함수를 직접 호출하여 base_date와 base_time 가져오기
base_date, base_time = weather_api._get_base_date_time()

print(f"API 호출 파라미터: base_date={base_date}, base_time={base_time}, nx={nx}, ny={ny}")

# API 호출 및 응답 출력
# get_realtime_weather 함수가 base_date, base_time을 내부적으로 처리하므로, 여기서는 직접 전달하지 않음
response = weather_api.get_realtime_weather(latitude=37.6365682, longitude=127.0679542) # 실제 위경도 전달
print(json.dumps(response, indent=4, ensure_ascii=False)) 