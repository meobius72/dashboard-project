import requests
from datetime import datetime, timedelta

# API endpoint for Short-Term Forecast (단기예보)
SERVICE_URL = 'http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst'
# Replace with your actual service key from data.go.kr
SERVICE_KEY = '6pbnk4lATQeW55OJQG0Hzw' # Provided API key

def get_base_datetime():
    now = datetime.now()
    
    # Short-term forecast base times (KST)
    base_times = [2, 5, 8, 11, 14, 17, 20, 23]
    
    current_hour_int = now.hour
    current_minute_int = now.minute

    target_date = now
    target_time_str = ""

    found_base_time = False
    for bt_hour in reversed(base_times):
        if (current_hour_int > bt_hour) or \
           (current_hour_int == bt_hour and current_minute_int >= 40):
            target_time_str = f"{bt_hour:02d}00"
            found_base_time = True
            break
    
    if not found_base_time:
        target_date = now - timedelta(days=1)
        target_time_str = "2300"

    base_date_str = target_date.strftime("%Y%m%d")
    
    return base_date_str, target_time_str

base_date, base_time = get_base_datetime()

# Example coordinates for Seoul
nx = 60
ny = 127

params = {
    'serviceKey': SERVICE_KEY,
    'pageNo': '1',
    'numOfRows': '10', # Limit rows for easier debugging
    'dataType': 'JSON',
    'base_date': base_date,
    'base_time': base_time,
    'nx': str(nx),
    'ny': str(ny)
}

try:
    response = requests.get(SERVICE_URL, params=params, timeout=10)
    response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
    
    print("--- Raw API Response Text ---")
    print(response.text)
    print("-----------------------------")

except requests.exceptions.HTTPError as e:
    print(f"HTTP Error: {e.response.status_code} {e.response.reason}")
    print(f"Response content: {e.response.text}")
except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}") 