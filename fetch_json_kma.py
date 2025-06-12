import requests
import json
from datetime import datetime, timedelta

# API endpoint for Short-Term Forecast (단기예보)
SERVICE_URL = 'http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst'
# Replace with your actual service key from data.go.kr
SERVICE_KEY = '6pbnk4lATQeW55OJQG0Hzw' # PLEASE REPLACE THIS WITH YOUR ACTUAL API KEY

def get_base_datetime():
    now = datetime.now()
    
    # Short-term forecast base times (KST)
    # Valid base times are 0200, 0500, 0800, 1100, 1400, 1700, 2000, 2300
    base_times = [2, 5, 8, 11, 14, 17, 20, 23]
    
    current_hour_int = now.hour
    current_minute_int = now.minute

    target_date = now
    target_time_str = ""

    found_base_time = False
    for bt_hour in reversed(base_times):
        # KMA data is typically available around 40 minutes after announcement.
        # So we consider the base time valid if current time is at least 40 minutes after it.
        if (current_hour_int > bt_hour) or \
           (current_hour_int == bt_hour and current_minute_int >= 40):
            target_time_str = f"{bt_hour:02d}00"
            found_base_time = True
            break
    
    if not found_base_time:
        # If no base_time found for today (e.g., before 02:40), use 2300 from yesterday
        target_date = now - timedelta(days=1)
        target_time_str = "2300"

    base_date_str = target_date.strftime("%Y%m%d")
    
    return base_date_str, target_time_str

base_date, base_time = get_base_datetime()

# Example coordinates for Seoul (you might need to adjust these based on your target area)
nx = 60
ny = 127

params = {
    'serviceKey': SERVICE_KEY,
    'pageNo': '1',
    'numOfRows': '1000', # Increase if more data is needed
    'dataType': 'JSON',
    'base_date': base_date,
    'base_time': base_time,
    'nx': str(nx),
    'ny': str(ny)
}

try:
    response = requests.get(SERVICE_URL, params=params, timeout=10)
    response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
    
    json_response = response.json()
    print(json.dumps(json_response, indent=4, ensure_ascii=False))

except requests.exceptions.HTTPError as e:
    print(f"HTTP Error: {e.response.status_code} {e.response.reason} - {e.response.text}")
except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")
except json.JSONDecodeError:
    print("Failed to parse API response as JSON.") 