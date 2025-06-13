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
    print(f"[DEBUG] safe_int_conversion 시작 - 입력값: '{value}', 타입: {type(value)}")
    if value is None:
        print(f"[DEBUG] safe_int_conversion - None 값 감지, 기본값 반환: {default}")
        return default
    s_value = str(value).strip()
    try:
        result = int(float(s_value))  # float로 먼저 변환하여 소수점 있는 문자열도 처리
        print(f"[DEBUG] safe_int_conversion 성공 - 변환 결과: {result} (입력: '{s_value}')")
        return result
    except ValueError as e:
        print(f"[DEBUG] safe_int_conversion 실패 - ValueError: {str(e)}, 기본값 반환: {default}")
        return default

# 안전한 float 변환 도우미 함수
def safe_float_conversion(value, default=0.0):
    print(f"[DEBUG] safe_float_conversion 시작 - 입력값: '{value}', 타입: {type(value)}")
    if value is None:
        print(f"[DEBUG] safe_float_conversion - None 값 감지, 기본값 반환: {default}")
        return default
    s_value = str(value).strip()
    if s_value == "" or s_value == "강수없음" or s_value == "1mm 미만":
        print(f"[DEBUG] safe_float_conversion - 특수 문자열 감지 ('{s_value}'), 기본값 반환: {default}")
        return default
    # 'mm' 문자열이 포함된 경우 제거
    if "mm" in s_value:
        s_value = s_value.replace("mm", "")
        print(f"[DEBUG] safe_float_conversion - 'mm' 제거 후 문자열: '{s_value}'")
    try:
        result = float(s_value)
        print(f"[DEBUG] safe_float_conversion 성공 - 변환 결과: {result} (입력: '{s_value}')")
        return result
    except ValueError as e:
        print(f"[DEBUG] safe_float_conversion 실패 - ValueError: {str(e)}, 기본값 반환: {default}")
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
    """
    데이터베이스에서 최신 날씨 데이터를 가져와 포맷팅합니다.
    현재 시간 이후 10시간의 예보를 필터링하고 시간 순서대로 정렬합니다.
    """
    with app.app_context():
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        try:
            # 현재 KST 시간 계산
            now_utc = datetime.now(timezone.utc)
            kst_offset = timedelta(hours=9)
            current_kst = (now_utc + kst_offset).replace(minute=0, second=0, microsecond=0) # 현재 시간을 정각으로 설정
            print(f"[DEBUG] get_latest_forecasts_from_db - 현재 KST 시간 (정각): {current_kst}")

            # 최신 base_date와 base_time 조회
            cursor.execute('''
                SELECT base_date, base_time FROM short_term_forecasts
                WHERE nx = ? AND ny = ?
                ORDER BY base_date DESC, base_time DESC
                LIMIT 1
            ''', (nx, ny))
            latest_base = cursor.fetchone()
            
            if not latest_base:
                print("[ERROR] get_latest_forecasts_from_db - 데이터베이스에 예보 데이터 없음")
                return None
                
            base_date, base_time = latest_base
            print(f"[DEBUG] get_latest_forecasts_from_db - 최신 기준 시간: {base_date} {base_time}")

            # 해당 기준 시간의 모든 예보 데이터 조회
            cursor.execute('''
                SELECT forecast_date, forecast_time, category, fcst_value
                FROM short_term_forecasts
                WHERE base_date = ? AND base_time = ? AND nx = ? AND ny = ?
                ORDER BY forecast_date ASC, forecast_time ASC
            ''', (base_date, base_time, nx, ny))
            rows = cursor.fetchall()

            if not rows:
                print("[ERROR] get_latest_forecasts_from_db - 예보 데이터 조회 결과 없음")
                return None

            # 시간별로 데이터 그룹화
            forecasts_by_time = {}
            for row in rows:
                fcst_date, fcst_time, category, fcst_value = row
                forecast_datetime_str = f"{fcst_date}{fcst_time}"
                
                # 예보 시간을 datetime 객체로 변환
                fcst_dt = datetime.strptime(f"{fcst_date} {fcst_time}", "%Y%m%d %H%M")
                fcst_dt = fcst_dt.replace(tzinfo=timezone(timedelta(hours=9)))  # KST로 설정
                
                print(f"[DEBUG] get_latest_forecasts_from_db - 예보 시간: {fcst_dt}, 현재 시간: {current_kst}")
                
                # 현재 시간 이후의 예보만 필터링
                if fcst_dt >= current_kst:
                    if forecast_datetime_str not in forecasts_by_time:
                        forecasts_by_time[forecast_datetime_str] = {
                            "date": fcst_date,
                            "time": fcst_time,
                            "weather": {}
                        }
                    forecasts_by_time[forecast_datetime_str]["weather"][category] = fcst_value

            # 시간 순서대로 정렬
            sorted_forecasts = []
            for dt_str in sorted(forecasts_by_time.keys()):
                forecast_item = forecasts_by_time[dt_str]
                weather_data = forecast_item["weather"]

                # 각 카테고리별 데이터 변환 및 매핑
                temperature_c = safe_float_conversion(weather_data.get("TMP", "0"))
                precipitation_mm = safe_float_conversion(weather_data.get("PCP", "0"))
                humidity_percent = safe_float_conversion(weather_data.get("REH", "0"))
                wind_direction_deg = safe_float_conversion(weather_data.get("VEC", "0"))
                wind_speed_ms = safe_float_conversion(weather_data.get("WSD", "0"))
                pop_percent = safe_int_conversion(weather_data.get("POP", "0"))

                # SKY 매핑
                raw_sky_value = weather_data.get("SKY", "0")
                converted_sky_value = safe_int_conversion(raw_sky_value)
                sky_map_key = str(converted_sky_value)
                mapped_sky_value = SKY_MAP.get(sky_map_key, "정보 없음")
                print(f"[DEBUG] SKY 매핑 - 원본: {raw_sky_value}, 변환: {converted_sky_value}, 매핑: {mapped_sky_value}")

                # PTY 매핑
                raw_pty_value = weather_data.get("PTY", "0")
                converted_pty_value = safe_int_conversion(raw_pty_value)
                pty_map_key = str(converted_pty_value)
                mapped_pty_value = PTY_MAP.get(pty_map_key, "정보 없음")
                print(f"[DEBUG] PTY 매핑 - 원본: {raw_pty_value}, 변환: {converted_pty_value}, 매핑: {mapped_pty_value}")

                formatted_forecast = {
                    "date": forecast_item["date"],
                    "time": forecast_item["time"],
                    "forecast_time": f"{forecast_item['date']} {forecast_item['time']}",
                    "weather": {
                        "temperature_celsius": temperature_c,
                        "precipitation_mm": precipitation_mm,
                        "humidity_percent": humidity_percent,
                        "wind_direction_deg": wind_direction_deg,
                        "wind_speed_ms": wind_speed_ms,
                        "precipitation_pop": pop_percent,
                        "sky_status_code": converted_sky_value,
                        "sky_status": mapped_sky_value,
                        "precipitation_type_code": converted_pty_value,
                        "precipitation_type": mapped_pty_value,
                        "raw_precipitation_value": weather_data.get("PCP", "0")
                    }
                }
                sorted_forecasts.append(formatted_forecast)

            # 최대 10개의 예보만 반환
            print(f"[DEBUG] get_latest_forecasts_from_db - 반환할 예보 수: {len(sorted_forecasts[:10])}")
            return sorted_forecasts[:10]

        except sqlite3.Error as e:
            print(f"[ERROR] get_latest_forecasts_from_db - 데이터베이스 오류: {str(e)}")
            return None
        except Exception as e:
            print(f"[ERROR] get_latest_forecasts_from_db - 예상치 못한 오류: {str(e)}")
            return None
        finally:
            conn.close()

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

@app.route('/get_weather_data')
def get_weather_data_route():
    weather_data = get_latest_forecasts_from_db(WEATHER_NX, WEATHER_NY)
    if weather_data:
        return jsonify({"weather_data": weather_data})
    return jsonify({"error": "날씨 데이터를 가져오는 데 실패했습니다.", "weather_data": []}), 500

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

    print(f"[DEBUG] get_base_date_time - 최종 기준 날짜: {base_date}, 기준 시간: {base_time}")
    return base_date, base_time

def get_weather_data():
    """
    기상청 API에서 날씨 데이터를 가져와 데이터베이스에 저장합니다.
    API 호출 및 오류 처리에 집중하며, 데이터 포맷팅은 get_latest_forecasts_from_db에서 처리합니다.
    """
    try:
        base_date, base_time = get_base_date_time()
        print(f"[DEBUG] get_weather_data - 기준 시간: {base_date} {base_time}")

        params = {
            'serviceKey': WEATHER_API_KEY,
            'pageNo': '1',
            'numOfRows': '1000',
            'dataType': 'JSON',
            'base_date': base_date,
            'base_time': base_time,
            'nx': WEATHER_NX,
            'ny': WEATHER_NY
        }

        print(f"[DEBUG] get_weather_data - API 요청 파라미터: {params}")
        response = requests.get(WEATHER_API_URL, params=params)
        print(f"[DEBUG] get_weather_data - API 응답 상태 코드: {response.status_code}")
        print(f"[DEBUG] get_weather_data - API 응답 내용: {response.text}") # Raw API 응답 내용 추가

        if response.status_code != 200:
            print(f"[ERROR] get_weather_data - API 요청 실패: {response.status_code}")
            return None

        data = response.json()
        print(f"[DEBUG] get_weather_data - API 응답 데이터 구조: {list(data.keys())}")

        if 'response' not in data or 'body' not in data['response']:
            print("[ERROR] get_weather_data - API 응답 형식 오류")
            return None

        items = data['response']['body'].get('items', {}).get('item', [])
        if not items:
            print("[ERROR] get_weather_data - 날씨 데이터 없음 (API 응답 items 비어있음)") # 메시지 상세화
            return None
        print(f"[DEBUG] get_weather_data - API에서 가져온 항목 수: {len(items)}") # 가져온 항목 수 로그 추가

        # 데이터베이스에 저장할 형식으로 변환
        forecast_data = {
            "base_reference_time": f"{base_date[:4]}-{base_date[4:6]}-{base_date[6:]} {base_time[:2]}:{base_time[2:]}",
            "location": {
                "grid_x": WEATHER_NX,
                "grid_y": WEATHER_NY
            },
            "forecasts": []
        }

        # 시간별로 데이터 그룹화
        forecasts_by_time = {}
        for item in items:
            fcst_date = item['fcstDate']
            fcst_time = item['fcstTime']
            category = item['category']
            fcst_value = item['fcstValue']

            time_key = f"{fcst_date}{fcst_time}"
            if time_key not in forecasts_by_time:
                forecasts_by_time[time_key] = {
                    "date": fcst_date,
                    "time": fcst_time,
                    "weather": {}
                }
            forecasts_by_time[time_key]["weather"][category] = fcst_value

        forecast_data["forecasts"] = list(forecasts_by_time.values())
        print(f"[DEBUG] get_weather_data - 처리된 예보 데이터 수: {len(forecast_data['forecasts'])}")

        # 데이터베이스에 저장
        insert_forecast_data(forecast_data)
        return forecast_data

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] get_weather_data - API 요청 예외 발생: {str(e)}")
        return None
    except Exception as e:
        print(f"[ERROR] get_weather_data - 예상치 못한 오류 발생: {str(e)}")
        return None

if __name__ == '__main__':
    init_db()
    # 5분마다 날씨 데이터를 업데이트하는 스레드 시작
    def update_weather_data_periodically():
        while True:
            print("Updating weather data...")
            weather_data = get_weather_data()
            if weather_data and weather_data.get("forecasts"):
                insert_forecast_data(weather_data)
            else:
                print("Failed to fetch or insert weather data.")
            time.sleep(REFRESH_INTERVAL) # 5분마다 갱신

    weather_thread = threading.Thread(target=update_weather_data_periodically)
    weather_thread.daemon = True
    weather_thread.start()
    app.run(debug=True, host='0.0.0.0', port=5000) 