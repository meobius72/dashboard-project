import requests
import math
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

# weather1.py에서 가져온 인증키 및 지역 코드
AUTH_KEY = "6pbnk4lATQe55OJQG0Hzw"
REGION_CODE_NAMYANGJU = "11B20502"

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
        pty_map = {
            "0": "없음", "1": "비", "2": "비/눈", "3": "눈",
            "4": "소나기", "5": "빗방울", "6": "빗방울/눈날림", "7": "눈날림"
        }

        formatted_forecasts = []
        for dt_str in sorted(forecasts_by_time.keys()):
            forecast_item = forecasts_by_time[dt_str]
            weather_data = forecast_item["weather"]

            precipitation_str = weather_data.get("RN6", "0.0")
            if precipitation_str == "강수없음":
                precipitation_mm = 0.0
            else:
                try:
                    precipitation_mm = float(precipitation_str)
                except ValueError:
                    precipitation_mm = 0.0

            formatted_forecast = {
                "location": location_info,
                "forecast_time": f"{forecast_item['date'][:4]}-{forecast_item['date'][4:6]}-{forecast_item['date'][6:]} {forecast_item['time'][:2]}:{forecast_item['time'][2:]}",
                "weather": {
                    "temperature_celsius": float(weather_data.get("TMP", 0.0)),
                    "humidity_percent": float(weather_data.get("REH", 0.0)),
                    "precipitation_mm": precipitation_mm,
                    "precipitation_type": pty_map.get(weather_data.get("PTY", "0"), "정보 없음"),
                    "wind_direction_deg": float(weather_data.get("VEC", 0.0)),
                    "wind_speed_ms": float(weather_data.get("WSD", 0.0)),
                    "sky_condition": weather_data.get("SKY", "정보 없음"),
                    "precipitation_probability": float(weather_data.get("POP", 0.0))
                }
            }
            formatted_forecasts.append(formatted_forecast)

        return {
            "location": location_info,
            "base_reference_time": base_reference_time,
            "forecasts": formatted_forecasts,
            "message": "날씨 정보 조회 성공"
        }

# KMA API를 위한 위경도-격자 좌표 변환 함수
def convert_gps_to_grid(latitude, longitude):
    """
    위경도 좌표를 기상청 격자 X, Y 좌표로 변환하는 함수.
    Lambert Conformal Conic projection 기반.
    """
    # 파라미터 설정
    Re = 6371.00877  # 지구 반경 (km)
    grid = 5.0      # 격자 간격 (km)
    slat1 = 30.0    # 표준 위도 1 (degree)
    slat2 = 60.0    # 표준 위도 2 (degree)
    olon = 126.0    # 기준 경도 (degree)
    olat = 38.0     # 기준 위도 (degree)
    xo = 43         # 기준점 X좌표 (격자 단위)
    yo = 136        # 기준점 Y좌표 (격자 단위)

    # 도(degree) 단위를 라디안(radian)으로 변환하기 위한 상수
    DEGRAD = math.pi / 180.0
    
    # 표준 위도 및 기준 경도/위도를 라디안으로 변환
    re = Re / grid  # 지구 반경을 격자 간격으로 나눈 값
    slat1_rad = slat1 * DEGRAD
    slat2_rad = slat2 * DEGRAD
    olon_rad = olon * DEGRAD
    olat_rad = olat * DEGRAD

    # Lambert Conformal Conic Projection 계산 과정
    # sn: 투영 비율 계수 계산에 사용
    sn = math.tan(math.pi * 0.25 + slat2_rad * 0.5) / math.tan(math.pi * 0.25 + slat1_rad * 0.5)
    sn = math.log(math.cos(slat1_rad) / math.cos(slat2_rad)) / math.log(sn)

    # sf: 표준 위도에서의 투영 인자
    sf = math.tan(math.pi * 0.25 + slat1_rad * 0.5)
    sf = (math.pow(sf, sn) * math.cos(slat1_rad)) / sn

    # ro: 기준 위도에서의 극점까지의 거리
    ro = math.tan(math.pi * 0.25 + olat_rad * 0.5)
    ro = re * sf / math.pow(ro, sn)

    # 입력 위경도를 라디안으로 변환
    ra = math.tan(math.pi * 0.25 + latitude * DEGRAD * 0.5)
    # ra: 입력 위도에서의 극점까지의 거리
    ra = re * sf / math.pow(ra, sn)

    # theta: 기준 경도로부터의 경도 차이에 따른 각도
    theta = longitude * DEGRAD - olon_rad
    # 기준 경도와의 차이가 \(pi\)보다 크면 조정
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    
    # 최종 각도에 sn 곱하기
    theta *= sn

    # X, Y 좌표 계산
    # 기준점 X좌표(xo)에 계산된 X 위치 더하기 (반올림하여 정수화)
    x = math.floor(ra * math.sin(theta) + xo + 0.5)
    # 기준점 Y좌표(yo)에 계산된 Y 위치 빼기 (반올림하여 정수화)
    # Y 좌표는 북쪽으로 갈수록 증가하므로, 극점에서부터의 거리를 빼고 기준점 Y를 더함
    y = math.floor(ro - ra * math.cos(theta) + yo + 0.5)

    return int(x), int(y)

# KMAWeatherAPI 클래스 (단기예보 API 클라이언트)
class KMAWeatherAPI:
    def __init__(self, service_key):
        if not service_key or service_key == "YOUR_KMA_SERVICE_KEY":
            raise ValueError("유효한 서비스 키를 입력해야 합니다. 환경 변수 등을 통해 안전하게 관리하세요.")
        self.service_key = service_key
        # 단기예보 API 엔드포인트
        self.endpoint = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"

    def _get_grid_coords(self, latitude, longitude):
        return convert_gps_to_grid(latitude, longitude)

    def _get_base_date_time(self):
        now = datetime.now(timezone.utc) + timedelta(hours=9) # KST (UTC+9)

        # 단기예보 (getVilageFcst)는 3시간 간격으로 발표 (02, 05, 08, 11, 14, 17, 20, 23시)
        # 각 발표 시각 10분 이후부터 조회 가능 (e.g., 02시 발표 자료는 02:10부터)
        base_times = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]
        base_date = now.strftime("%Y%m%d")
        base_time = ""

        # 가장 최근의 발표 시간을 찾음 (발표 시간 + 10분 이후)
        for bt_str in sorted(base_times, reverse=True):
            bt_hour = int(bt_str[:2])
            
            # 현재 시간 (now)이 발표 시간 (bt_hour:00) + 10분 보다 같거나 이후인 경우
            if now.hour > bt_hour or (now.hour == bt_hour and now.minute >= 10):
                base_time = bt_str
                break
        
        # 만약 현재 시간이 당일 02시 10분 이전이라면, 전날의 마지막 발표 시간(2300)을 사용
        if not base_time:
            base_date = (now - timedelta(days=1)).strftime("%Y%m%d")
            base_time = "2300"

        return base_date, base_time

    def get_forecast_weather(self, latitude, longitude): # 이름 변경
        nx, ny = self._get_grid_coords(latitude, longitude)
        base_date, base_time = self._get_base_date_time()

        params = {
            "serviceKey": self.service_key,
            "pageNo": 1,
            "numOfRows": 1000,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx,
            "ny": ny
        }

        try:
            response = requests.get(self.endpoint, params=params, timeout=10)
            response.raise_for_status()
            
            print(f"Raw API response status: {response.status_code}")
            print(f"Raw API response text: {response.text}") # 원시 응답 텍스트 출력 추가
            
            data = response.json()
            print(json.dumps(data, indent=4, ensure_ascii=False)) # API 원시 응답 로깅

            header = data.get("response", {}).get("header", {})
            result_code = header.get("resultCode")
            result_msg = header.get("resultMsg")

            if result_code != "00":
                raise Exception(f"API Error {result_code}: {result_msg}. Raw response: {response.text}") # 원시 응답 포함

            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if not items:
                return {
                    "location": {"latitude": latitude, "longitude": longitude, "grid_x": nx, "grid_y": ny},
                    "base_reference_time": f"{base_date[:4]}-{base_date[4:6]}-{base_date[6:]} {base_time[:2]}:{base_time[2:]}",
                    "forecasts": [], # 예보 목록
                    "message": "해당 조건의 날씨 데이터가 없습니다."
                }

            # 단기예보는 여러 예보 시간과 항목을 포함하므로, 이를 구조화하여 저장
            forecasts_by_time = {}
            for item in items:
                category = item.get("category")
                fcst_value = item.get("fcstValue")
                fcst_date = item.get("fcstDate")
                fcst_time = item.get("fcstTime")

                if category and fcst_value is not None and fcst_date and fcst_time:
                    forecast_datetime_str = f"{fcst_date}{fcst_time}"
                    if forecast_datetime_str not in forecasts_by_time:
                        forecasts_by_time[forecast_datetime_str] = {
                            "date": fcst_date,
                            "time": fcst_time,
                            "weather": {}
                        }
                    forecasts_by_time[forecast_datetime_str]["weather"][category] = fcst_value
            
            # 정렬하여 리스트로 변환
            sorted_forecasts = []
            for dt_str in sorted(forecasts_by_time.keys()):
                sorted_forecasts.append(forecasts_by_time[dt_str])

            # PTY (강수형태) 매핑
            pty_map = {
                "0": "없음", "1": "비", "2": "비/눈", "3": "눈",
                "4": "소나기", "5": "빗방울", "6": "빗방울/눈날림", "7": "눈날림"
            }

            # 각 예보 항목을 최종 형식으로 가공
            formatted_forecasts = []
            for forecast_item in sorted_forecasts:
                weather_data = forecast_item["weather"]
                
                precipitation_str = weather_data.get("RN6", "0.0") # 6시간 강수량
                if precipitation_str == "강수없음": # API에서 "강수없음"으로 올 경우 처리
                    precipitation_mm = 0.0
                else:
                    try:
                        precipitation_mm = float(precipitation_str)
                    except ValueError:
                        precipitation_mm = 0.0

                formatted_forecast = {
                    "location": {"latitude": latitude, "longitude": longitude, "grid_x": nx, "grid_y": ny},
                    "forecast_time": f"{forecast_item['date'][:4]}-{forecast_item['date'][4:6]}-{forecast_item['date'][6:]} {forecast_item['time'][:2]}:{forecast_item['time'][2:]}",
                    "weather": {
                        "temperature_celsius": float(weather_data.get("TMP", 0.0)), # 기온은 TMP
                        "humidity_percent": float(weather_data.get("REH", 0.0)), # 습도 REH
                        "precipitation_mm": precipitation_mm,
                        "precipitation_type": pty_map.get(weather_data.get("PTY", "0"), "정보 없음"), # 강수형태 PTY
                        "wind_direction_deg": float(weather_data.get("VEC", 0.0)), # 풍향 VEC
                        "wind_speed_ms": float(weather_data.get("WSD", 0.0)), # 풍속 WSD
                        "sky_condition": weather_data.get("SKY", "정보 없음"), # 하늘상태 SKY
                        "precipitation_probability": float(weather_data.get("POP", 0.0)) # 강수확률 POP
                    }
                }
                formatted_forecasts.append(formatted_forecast)

            return {
                "location": {"latitude": latitude, "longitude": longitude, "grid_x": nx, "grid_y": ny},
                "base_reference_time": f"{base_date[:4]}-{base_date[4:6]}-{base_date[6:]} {base_time[:2]}:{base_time[2:]}",
                "forecasts": formatted_forecasts,
                "message": "날씨 정보 조회 성공"
            }

        except requests.exceptions.HTTPError as e:
            raise Exception(f"HTTP Error: {e.response.status_code} {e.response.reason} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")
        except json.JSONDecodeError:
            raise Exception("Failed to parse API response as JSON.")
        except KeyError as e:
            raise Exception(f"Unexpected API response structure. Missing key: {e}")
        except Exception as e:
            raise e

# KMA API 설정
KMA_API_KEY = "6pbnk4lATQeW55OJQG0Hzw" # 사용자 제공 API 키
kma_api = KMAWeatherAPI(service_key=KMA_API_KEY)
# 하계동 위경도 (웹 검색을 통해 찾은 값)
HAGYE_DONG_LATITUDE = 37.6365682
HAGYE_DONG_LONGITUDE = 127.0679542

# Global variable to store the latest forecast data (no longer strictly needed for persistent storage)
# but can be used for initial load or fallback
latest_forecast_data = {}

# Function to update weather data periodically
def update_weather_data():
    global latest_forecast_data
    print("Fetching latest weather data...")
    try:
        latitude = 37.5665  # Example: Seoul coordinates
        longitude = 126.9780 # Example: Seoul coordinates
        fetched_data = kma_api.get_forecast_weather(latitude, longitude)
        if fetched_data:
            latest_forecast_data = fetched_data # Still keep this for immediate access
            insert_forecast_data(fetched_data) # Insert into database
            print("Weather data updated and saved to DB successfully.")
        else:
            print("Failed to fetch weather data or no data returned.")
    except Exception as e:
        # 오류 발생 시 더 자세한 정보를 출력
        print(f"Error fetching weather data: {e}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"API response text on error: {e.response.text}")
    
    threading.Timer(10800, update_weather_data).start()

# Start the initial weather data fetch and schedule subsequent updates
with app.app_context():
    init_db() # Initialize database on app startup
    update_weather_data()

@app.route('/get_weather')
def get_weather():
    # Fetch data from the database instead of global variable
    latitude = 37.5665 # Example: Seoul coordinates
    longitude = 126.9780 # Example: Seoul coordinates
    nx, ny = convert_gps_to_grid(latitude, longitude)
    
    forecast_from_db = get_latest_forecasts_from_db(nx, ny)
    
    if forecast_from_db:
        return jsonify(forecast_from_db)
    elif latest_forecast_data: # Fallback to in-memory data if DB is empty for some reason
        return jsonify(latest_forecast_data)
    else:
        return jsonify({"message": "Weather data not available yet.", "forecasts": []}), 503

@app.route('/')
def index():
    kotsa_notices = scrape_kotsa_notices() # 최신 3개만 가져옴
    kaa_notices = scrape_kaa_notices() # 알림 3개, 일반 3개 가져옴
    return render_template('index.html',
                           current_video_id=YOUTUBE_VIDEO_IDS[current_youtube_index],
                           kotsa_notices=kotsa_notices,
                           kaa_notices=kaa_notices)

@app.route('/get_notices')
def get_notices():
    kotsa_notices = scrape_kotsa_notices()
    kaa_notices = scrape_kaa_notices()
    return jsonify({"kotsa_notices": kotsa_notices, "kaa_notices": kaa_notices})

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

def get_regional_forecast_data(auth_key: str, region_code: str):
    """
    '지역별 단기예보' API를 호출하여 날씨 정보를 가져옵니다.
    """
    api_url = "https://apihub.kma.go.kr/api/typ01/url/fct_shrt_reg.php"
    
    params = {
        'tmfc': '0',
        'reg': region_code,
        'disp': '1',
        'authKey': auth_key
    }

    try:
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status()

        cleaned_data = '\n'.join(
            line for line in response.text.splitlines()
            if line.strip() and not line.strip().startswith('#')
        )
        
        if not cleaned_data:
            print("오류: API 응답에 유효한 데이터가 없습니다. 원시 응답:\n", response.text)
            return None

        try:
            df = pd.read_csv(io.StringIO(cleaned_data))
        except pd.errors.EmptyDataError:
            print("오류: pandas가 읽을 데이터가 없습니다. 원시 응답:\n", response.text)
            return None
        except Exception as e:
            print(f"오류: pandas 데이터 처리 중 예외 발생: {e}. 원시 응답:\n", response.text)
            return None

        df.columns = df.columns.str.strip()
        
        # 필요한 컬럼만 선택하여 리스트로 변환
        if not df.empty:
            # TM_EF 컬럼의 데이터를 문자열로 변환하고 필요한 부분만 추출
            df['TM_EF_STR'] = df['TM_EF'].astype(str)
            # WF, TA, ST, WS, SKY 컬럼도 함께 반환
            return df[['TM_EF_STR', 'WF', 'SKY', 'TA', 'ST', 'WS']].to_dict(orient='records')
        return []

    except requests.exceptions.RequestException as e:
        print(f"API 요청 중 오류가 발생했습니다: {e}")
        return None
    except Exception as e:
        print(f"데이터 처리 중 오류가 발생했습니다: {e}")
        return None

@app.route('/weather')
def weather_api():
    forecast_data = get_regional_forecast_data(AUTH_KEY, REGION_CODE_NAMYANGJU)
    if forecast_data is None:
        return jsonify({"error": "날씨 정보를 가져오지 못했습니다."}), 500
    return jsonify(forecast_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True) 