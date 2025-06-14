import requests
# import math # math 모듈은 현재 사용되지 않으므로 제거합니다.
from flask import Flask, render_template, jsonify, request
from scrape_notices import scrape_kotsa_notices, scrape_kaa_notices
from datetime import datetime, timedelta, timezone
import json
from collections import Counter
import threading
import time
import sqlite3
from flask_cors import CORS
import io
import pandas as pd
from bs4 import BeautifulSoup
import urllib.parse

app = Flask(__name__)
CORS(app) # 모든 경로에 대해 CORS 허용

print("Hello, from Flask app startup!") # 테스트를 위한 출력

# YouTube 동영상 ID 목록
YOUTUBE_VIDEO_IDS = [
    "dQw4w9WgXcQ", # Rick Astley - Never Gonna Give You Up
    "JGwWNGJdvx8", # Imagine Dragons - Believer
    "kJQP7kiw5Fk"  # Luis Fonsi - Despacito
]
current_youtube_index = 0

# 화면 갱신 주기 설정 (초 단위, 기본값 5분 = 300초)
REFRESH_INTERVAL = 300

# Database configuration
DATABASE_FILE = 'weather_forecasts.db'

# 기상청 API 설정
WEATHER_API_KEY = "PcVFXfWoNUlki9AS6y8ODPyW2KZKyHfrGdy6rFnMUNIBZxhC2+KnUUekPDtfSBCRBWfR/G+9UpcQwuHBZFR+Xw==" # URL 인코딩 제거
WEATHER_API_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
WEATHER_NX = "55"  # 경기기계공업고등학교 X좌표
WEATHER_NY = "127"  # 경기기계공업고등학교 Y좌표

# 날씨 카테고리 매핑
CATEGORY_MAPPING = {
    "TMP": "기온", "UUU": "풍속(동서)", "VVV": "풍속(남북)", "VEC": "풍향", "WSD": "풍속",
    "SKY": "하늘상태", "PTY": "강수형태", "POP": "강수확률", "RN1": "1시간 강수량", "REH": "습도",
    "WAV": "파고", "PCP": "1시간 강수량", "SNO": "1시간 신적설"
}

# PTY (강수형태) 매핑
PTY_MAP = {
    "0": "없음", "1": "비", "2": "비/눈", "3": "눈",
    "4": "소나기", "5": "빗방울", "6": "빗방울/눈날림", "7": "눈날림"
}

# SKY (하늘상태) 매핑
SKY_MAP = {
    "1": "맑음", "3": "구름많음", "4": "흐림"
}

# 안전한 int 변환 도우미 함수
def safe_int_conversion(value, default=0):
    print(f"[DEBUG] safe_int_conversion input: '{value}', type: {type(value)}")
    if value is None:
        print(f"[DEBUG] safe_int_conversion output: {default}")
        return default
    s_value = str(value).strip()
    try:
        result = int(float(s_value)) # float로 먼저 변환하여 소수점 있는 문자열도 처리
        print(f"[DEBUG] safe_int_conversion output: {result}")
        return result
    except ValueError:
        print(f"[DEBUG] safe_int_conversion output (ValueError): {default}")
        return default

# 안전한 float 변환 도우미 함수
def safe_float_conversion(value, default=0.0):
    print(f"[DEBUG] safe_float_conversion input: '{value}', type: {type(value)}")
    if value is None:
        print(f"[DEBUG] safe_float_conversion output: {default}")
        return default
    s_value = str(value).strip()
    if s_value == "" or s_value == "강수없음" or s_value == "1mm 미만":
        print(f"[DEBUG] safe_float_conversion output (special string): {default}")
        return default
    # 'mm' 문자열이 포함된 경우 제거
    if "mm" in s_value:
        s_value = s_value.replace("mm", "")
    try:
        result = float(s_value)
        print(f"[DEBUG] safe_float_conversion output: {result}")
        return result
    except ValueError:
        print(f"[DEBUG] safe_float_conversion output (ValueError): {default}")
        return default

def init_db():
    with app.app_context():
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        # Create table for short-term forecasts
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS short_term_forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                base_date TEXT NOT NULL,
                base_time TEXT NOT NULL,
                forecast_date TEXT NOT NULL,
                forecast_time TEXT NOT NULL,
                nx INTEGER NOT NULL,
                ny INTEGER NOT NULL,
                category TEXT NOT NULL,
                fcst_value TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(base_date, base_time, forecast_date, forecast_time, nx, ny, category)
            )
        ''')
        conn.commit()
        conn.close()
        print("Database initialized.")

def insert_forecast_data(data):
    with app.app_context():
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        try:
            if data and data.get("forecasts"):
                base_reference_time = data.get("base_reference_time")
                base_date = base_reference_time.split(' ')[0].replace('-', '')
                base_time = base_reference_time.split(' ')[1].replace(':', '')
                nx = data["location"]["grid_x"]
                ny = data["location"]["grid_y"]

                for forecast_item in data["forecasts"]:
                    forecast_date_str = forecast_item["date"]
                    forecast_time_str = forecast_item["time"]
                    for category, fcst_value in forecast_item["weather"].items():
                        # SKY 및 PTY 카테고리의 경우 숫자로 변환하여 저장
                        if category in ["SKY", "PTY"]:
                            fcst_value = safe_int_conversion(fcst_value)
                        cursor.execute('''
                            INSERT OR REPLACE INTO short_term_forecasts
                            (base_date, base_time, forecast_date, forecast_time, nx, ny, category, fcst_value)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''',
                        (base_date, base_time, forecast_date_str, forecast_time_str, nx, ny, category, str(fcst_value)))
                conn.commit()
                print("Forecast data inserted/updated into DB.")
            else:
                print("No forecast data to insert.")
        except sqlite3.Error as e:
            print(f"Database error during insertion: {e}")
        finally:
            conn.close()

def get_latest_forecasts_from_db(nx, ny):
    with app.app_context():
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        # Get the latest base_date and base_time for the given nx, ny
        cursor.execute('''
            SELECT base_date, base_time FROM short_term_forecasts
            WHERE nx = ? AND ny = ?
            ORDER BY base_date DESC, base_time DESC
            LIMIT 1
        ''', (nx, ny))
        latest_base = cursor.fetchone()
        
        if not latest_base:
            conn.close()
            return None
            
        base_date, base_time = latest_base

        # Fetch all forecast items for this latest base_date and base_time, and nx, ny
        cursor.execute('''
            SELECT forecast_date, forecast_time, category, fcst_value
            FROM short_term_forecasts
            WHERE base_date = ? AND base_time = ? AND nx = ? AND ny = ?
            ORDER BY forecast_date ASC, forecast_time ASC
        ''', (base_date, base_time, nx, ny))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return None

        # Reconstruct the data into the desired format
        location_info = {"latitude": None, "longitude": None, "grid_x": nx, "grid_y": ny}
        base_reference_time = f"{base_date[:4]}-{base_date[4:6]}-{base_date[6:]} {base_time[:2]}:{base_time[2:]}"
        
        forecasts_by_time = {}
        for row in rows:
            fcst_date, fcst_time, category, fcst_value = row
            forecast_datetime_str = f"{fcst_date}{fcst_time}"
            if forecast_datetime_str not in forecasts_by_time:
                forecasts_by_time[forecast_datetime_str] = {
                    "date": fcst_date,
                    "time": fcst_time,
                    "weather": {}
                }
            forecasts_by_time[forecast_datetime_str]["weather"][category] = fcst_value

        # PTY (강수형태) 매핑 (from KMAWeatherAPI)
        # 이 함수 내에 PTY_MAP을 다시 정의하는 것이 올바릅니다.
        pty_map = {
            "0": "없음", "1": "비", "2": "비/눈", "3": "눈",
            "4": "소나기", "5": "빗방울", "6": "빗방울/눈날림", "7": "눈날림"
        }

        # SKY_MAP 내용 디버깅
        print(f"[DEBUG] SKY_MAP content: {SKY_MAP}")

        formatted_forecasts = []
        for dt_str in sorted(forecasts_by_time.keys()):
            forecast_item = forecasts_by_time[dt_str]
            weather_data = forecast_item["weather"]

            print(f"[DEBUG] Processing forecast_item for time: {dt_str}")
            print(f"[DEBUG] Raw weather_data for {dt_str}: {weather_data}")

            # 각 카테고리별 원본 값 디버깅 출력
            print(f"[DEBUG] Raw TMP: {weather_data.get('TMP')}")
            print(f"[DEBUG] Raw REH: {weather_data.get('REH')}")
            print(f"[DEBUG] Raw PCP: {weather_data.get('PCP')}")
            print(f"[DEBUG] Raw VEC: {weather_data.get('VEC')}")
            print(f"[DEBUG] Raw WSD: {weather_data.get('WSD')}")
            print(f"[DEBUG] Raw PTY: {weather_data.get('PTY')}")
            print(f"[DEBUG] Raw SKY: {weather_data.get('SKY')}")
            print(f"[DEBUG] Raw POP: {weather_data.get('POP')}")

            temperature_c = safe_float_conversion(weather_data.get("TMP"))
            precipitation_mm = safe_float_conversion(weather_data.get("PCP"))

            # SKY 매핑 디버깅 추가 및 적용
            raw_sky_value = weather_data.get("SKY")
            converted_sky_value = safe_int_conversion(raw_sky_value)
            sky_map_key = str(converted_sky_value)
            mapped_sky_value = SKY_MAP.get(sky_map_key, "정보 없음")
            print(f"[DEBUG] SKY Mapping Trace - Raw: {raw_sky_value} (type: {type(raw_sky_value)}), Converted: {converted_sky_value} (type: {type(converted_sky_value)}), Map Key: \'{sky_map_key}\' (type: {type(sky_map_key)}), Mapped: {mapped_sky_value}")

            # PTY 매핑 디버깅 추가 및 적용
            raw_pty_value = weather_data.get("PTY")
            converted_pty_value = safe_int_conversion(raw_pty_value)
            pty_map_key = str(converted_pty_value)
            mapped_pty_value = pty_map.get(pty_map_key, "정보 없음")
            print(f"[DEBUG] PTY Mapping Trace - Raw: {raw_pty_value} (type: {type(raw_pty_value)}), Converted: {converted_pty_value} (type: {type(converted_pty_value)}), Map Key: \'{pty_map_key}\' (type: {type(pty_map_key)}), Mapped: {mapped_pty_value}")

            humidity_percent = safe_float_conversion(weather_data.get("REH"))
            wind_direction_deg = safe_float_conversion(weather_data.get("VEC"))
            wind_speed_ms = safe_float_conversion(weather_data.get("WSD"))
            pop_percent = safe_int_conversion(weather_data.get("POP"))
            sky_status = mapped_sky_value

            formatted_forecast = {
                "location": location_info,
                "forecast_time": f"{forecast_item['date'][:4]}-{forecast_item['date'][4:6]}-{forecast_item['date'][6:]} {forecast_item['time'][:2]}:{forecast_item['time'][2:]}",
                "weather": {
                    "temperature_celsius": temperature_c,
                    "humidity_percent": humidity_percent,
                    "precipitation_mm": precipitation_mm,
                    "precipitation_type": mapped_pty_value,
                    "precipitation_type_code": converted_pty_value,
                    "wind_direction_deg": wind_direction_deg,
                    "wind_speed_ms": wind_speed_ms,
                    "sky_condition": sky_status,
                    "sky_status_code": converted_sky_value,
                    "precipitation_probability": pop_percent
                }
            }
            formatted_forecasts.append(formatted_forecast)

        # 현재 시간 이후 10시간 예측 필터링
        current_kst = datetime.now(timezone(timedelta(hours=9)))
        print(f"[DEBUG] Current KST for filtering: {current_kst.strftime('%Y-%m-%d %H:%M:%S')}")
        filtered_forecasts = []
        unique_forecast_datetimes = set() # Store (date, hour) to ensure unique hourly forecasts

        for forecast in formatted_forecasts:
            fcst_dt_str = forecast["forecast_time"]
            try:
                fcst_dt = datetime.strptime(fcst_dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=9)))
            except ValueError:
                print(f"[DEBUG] 날씨 예측 시간 파싱 오류: {fcst_dt_str}")
                continue
            print(f"[DEBUG] Comparing fcst_dt: {fcst_dt.strftime('%Y-%m-%d %H:%M:%S')} with current_kst: {current_kst.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"[DEBUG] Check condition: fcst_dt >= current_kst -> {fcst_dt >= current_kst}")
            print(f"[DEBUG] Check condition: (fcst_dt.date(), fcst_dt.hour) not in unique_forecast_datetimes -> {(fcst_dt.date(), fcst_dt.hour) not in unique_forecast_datetimes}")

            # 현재 시각보다 같거나 미래인 예측만 포함
            # 그리고 이미 추가된 시간대의 예측이 아니라면 추가 (중복 방지)
            # 날짜를 포함하여 비교함으로써 자정을 넘어서는 예측도 올바르게 필터링
            if fcst_dt >= current_kst and (fcst_dt.date(), fcst_dt.hour) not in unique_forecast_datetimes:
                filtered_forecasts.append(forecast)
                unique_forecast_datetimes.add((fcst_dt.date(), fcst_dt.hour))
            
            if len(filtered_forecasts) >= 10:
                break
        
        # 시간 순서대로 정렬 (날짜 변경도 고려)
        filtered_forecasts.sort(key=lambda x: datetime.strptime(x["forecast_time"], "%Y-%m-%d %H:%M"))

        print(f"Filtered forecasts count: {len(filtered_forecasts)}")
        for fcst in filtered_forecasts:
            print(f"[DEBUG] Final Filtered Forecast - Time: {fcst["forecast_time"]}, Sky: {fcst["weather"]["sky_condition"]}")

        return {
            "location": location_info,
            "base_reference_time": base_reference_time,
            "forecasts": filtered_forecasts, # 필터링된 예측 데이터 반환
            "message": "날씨 정보 조회 성공"
        }

@app.route('/')
def index():
    # 날씨 정보 가져오기
    weather_data = get_latest_forecasts_from_db(WEATHER_NX, WEATHER_NY) # get_weather_data에서 get_latest_forecasts_from_db로 변경
    print(f"[DEBUG] Final weather_data before rendering template: {weather_data}") # 템플릿 렌더링 전 weather_data 출력
    
    # 기존 공지사항 및 YouTube 데이터 가져오기
    kotsa_notices = scrape_kotsa_notices() # 최신 3개만 가져옴
    kaa_notices = scrape_kaa_notices() # 알림 3개, 일반 3개 가져옴

    return render_template('index.html',
                           current_video_id=YOUTUBE_VIDEO_IDS[current_youtube_index],
                           kotsa_notices=kotsa_notices,
                           kaa_notices=kaa_notices,
                           weather_data=weather_data) # weather_data 전달

@app.route('/get_notices')
def get_notices():
    kotsa_notices = scrape_kotsa_notices() # 최신 3개만 가져옴
    kaa_notices = scrape_kaa_notices() # 알림 3개, 일반 3개 가져옴
    return jsonify({
        "kotsa_notices": kotsa_notices,
        "kaa_notices": kaa_notices
    })

@app.route('/next_video')
def next_video():
    global current_youtube_index
    current_youtube_index = (current_youtube_index + 1) % len(YOUTUBE_VIDEO_IDS)
    return jsonify({"video_id": YOUTUBE_VIDEO_IDS[current_youtube_index]})

@app.route('/prev_video')
def prev_video():
    global current_youtube_index
    current_youtube_index = (current_youtube_index - 1 + len(YOUTUBE_VIDEO_IDS)) % len(YOUTUBE_VIDEO_IDS)
    return jsonify({"video_id": YOUTUBE_VIDEO_IDS[current_youtube_index]})

@app.route('/set_refresh_interval', methods=['POST'])
def set_refresh_interval():
    global REFRESH_INTERVAL
    data = request.get_json()
    new_interval = data.get('interval')
    if new_interval and isinstance(new_interval, int) and new_interval >= 60:
        REFRESH_INTERVAL = new_interval
        return jsonify({"status": "success", "new_interval": REFRESH_INTERVAL})
    return jsonify({"status": "error", "message": "유효하지 않은 갱신 주기입니다."}), 400

@app.route('/get_refresh_interval')
def get_refresh_interval():
    return jsonify({"interval": REFRESH_INTERVAL})

def get_base_date_time():
    now_kst = datetime.now(timezone(timedelta(hours=9))) # 한국 시간 (KST)
    
    # 단기예보 발표 시각 (02, 05, 08, 11, 14, 17, 20, 23시)
    # 각 시각에서 10분 이후가 되어야 해당 시각 데이터가 생성됩니다.
    # 예: 02시 발표는 02시 10분 이후에 호출 가능
    base_times = [2, 5, 8, 11, 14, 17, 20, 23]
    
    # 현재 시간으로부터 가장 가까운 과거의 발표 시각을 찾습니다.
    # 예를 들어 현재 10:30 이면, 08:00 발표를 가져와야 합니다.
    # 10분 이내라면 이전 시간대의 발표를 가져와야 합니다.
    
    target_time = None
    for i in range(len(base_times) - 1, -1, -1):
        # 현재 시간을 기준으로, 발표 시간과 10분 이후를 계산
        base_hour = base_times[i]
        candidate_time = now_kst.replace(hour=base_hour, minute=0, second=0, microsecond=0)
        # 발표 시각 + 10분 (데이터 생성 완료 시간)
        valid_after = candidate_time + timedelta(minutes=10)
        
        if now_kst >= valid_after:
            target_time = candidate_time
            break

    # 만약 현재 시각 기준으로 적절한 발표 시각을 찾지 못했다면 (예: 자정부터 02시 10분 사이)
    # 전날의 마지막 발표 시각을 사용합니다.
    if target_time is None:
        target_time = now_kst.replace(hour=23, minute=0, second=0, microsecond=0) - timedelta(days=1)

    base_date = target_time.strftime("%Y%m%d")
    base_time = target_time.strftime("%H%M")

    return base_date, base_time

def fetch_and_store_weather_data_from_api():
    try:
        # KST 기준으로 현재 시간 설정 (UTC+9)
        now_utc = datetime.now(timezone.utc)
        kst_offset = timedelta(hours=9)
        now_kst = now_utc + kst_offset

        # API 호출을 위한 base_date (오늘 날짜) 및 base_time 계산
        # API는 매시 30분에 발표. 현재 시각이 30분 전이라면 이전 시간의 30분 데이터 사용.
        # 예: 17:15 -> 16:30 데이터 사용. 17:35 -> 17:30 데이터 사용.
        base_date, base_time = get_base_date_time()

        # 테스트를 위해 base_time 출력
        print(f"Base Date: {base_date}, Base Time: {base_time}")

        params = {
            "serviceKey": WEATHER_API_KEY,
            "pageNo": "1",
            "numOfRows": "1000",
            "dataType": "XML",
            "base_date": base_date,
            "base_time": base_time,
            "nx": WEATHER_NX,
            "ny": WEATHER_NY
        }

        print(f"Weather API Request URL: {WEATHER_API_URL}?" + urllib.parse.urlencode(params))
        response = requests.get(WEATHER_API_URL, params=params)
        response.raise_for_status() # HTTP 오류 발생 시 예외 발생

        print(f"Weather API Status Code: {response.status_code}")
        print(f"Weather API Raw Response Body: {response.text}")

        soup = BeautifulSoup(response.text, 'xml')
        items = soup.find_all('item')

        if not items:
            result_code = soup.find('resultCode')
            result_msg = soup.find('resultMsg')
            print(f"Weather API Error: {result_code.text if result_code else 'N/A'} - {result_msg.text if result_msg else 'N/A'}")
            return {"error": "날씨 API 오류", "message": f"{result_code.text if result_code else 'N/A'} - {result_msg.text if result_msg else 'N/A'}"}

        parsed_data = {}
        for item in items:
            fcst_date = item.find('fcstDate').text
            fcst_time = item.find('fcstTime').text
            category_tag = item.find('category')
            fcst_value_tag = item.find('fcstValue')

            category = category_tag.text if category_tag else "UNKNOWN_CATEGORY"
            fcst_value = fcst_value_tag.text if fcst_value_tag else "" # fcstValue가 없을 경우 빈 문자열

            print(f"Debug: Parsed category: {category}, value: {fcst_value} for {fcst_date} {fcst_time}") # 추가된 디버그 출력

            forecast_datetime_str = f"{fcst_date}{fcst_time}"

            if forecast_datetime_str not in parsed_data:
                parsed_data[forecast_datetime_str] = {
                    "date": fcst_date,
                    "time": fcst_time,
                    "weather": {}
                }
            parsed_data[forecast_datetime_str]["weather"][category] = fcst_value

        raw_forecasts = []
        for dt_str in sorted(parsed_data.keys()):
            raw_forecasts.append({
                "date": parsed_data[dt_str]["date"],
                "time": parsed_data[dt_str]["time"],
                "weather": parsed_data[dt_str]["weather"]
            })

        return {
            "location": {"latitude": None, "longitude": None, "grid_x": int(WEATHER_NX), "grid_y": int(WEATHER_NY)},
            "base_reference_time": f"{base_date[:4]}-{base_date[4:6]}-{base_date[6:]} {base_time[:2]}:{base_time[2:]}",
            "forecasts": raw_forecasts, # 원본 예측 데이터 반환
            "message": "날씨 정보 조회 성공"
        }

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] 날씨 API 요청 오류: {e}")
        return {"error": "날씨 API 오류", "message": str(e)}
    except Exception as e:
        print(f"[ERROR] 예상치 못한 오류 발생: {e}")
        return {"error": "예상치 못한 오류 발생", "message": str(e)}

@app.route('/get_weather_data')
def get_weather_data_route(): # 함수 이름 변경 (기존 get_weather_data와 충돌 방지)
    # 데이터베이스에서 최신 날씨 정보를 가져와 반환
    weather_data = get_latest_forecasts_from_db(WEATHER_NX, WEATHER_NY)
    if weather_data:
        return jsonify(weather_data)
    else:
        return jsonify({"error": "날씨 정보를 불러올 수 없습니다.", "message": "데이터베이스에 날씨 정보가 없거나 오류가 발생했습니다."}), 500

if __name__ == '__main__':
    init_db()
    # 5분마다 날씨 데이터를 업데이트하는 스레드 시작
    def update_weather_data_periodically():
        while True:
            print("Updating weather data...")
            # 외부 API에서 데이터를 가져와 데이터베이스에 저장
            weather_data = fetch_and_store_weather_data_from_api()
            if weather_data and weather_data.get("forecasts"):
                insert_forecast_data(weather_data)
            else:
                print("Failed to fetch or insert weather data from API.")
            time.sleep(REFRESH_INTERVAL) # 5분마다 갱신

    weather_thread = threading.Thread(target=update_weather_data_periodically)
    weather_thread.daemon = True
    weather_thread.start()
    app.run(debug=True, host='0.0.0.0', port=5000) 