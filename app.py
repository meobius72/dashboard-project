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
WEATHER_API_KEY = urllib.parse.quote_plus("PcVFXfWoNUlki9AS6y8ODPyW2KZKyHfrGdy6rFnMUNIBZxhC2+KnUUekPDtfSBCRBWfR/G+9UpcQwuHBZFR+Xw==") # 디코딩된 인증키를 URL 인코딩하여 사용
WEATHER_API_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
WEATHER_NX = "55"  # 경기기계공업고등학교 X좌표
WEATHER_NY = "127"  # 경기기계공업고등학교 Y좌표

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

@app.route('/')
def index():
    # 날씨 정보 가져오기
    weather_data = get_weather_data()
    
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

def get_weather_data():
    try:
        # 현재 시간 기준으로 base_date와 base_time 설정
        now = datetime.now()
        
        # API 문서에 따라 '매시각 10분 이후 호출' 조건 반영
        # 현재 분이 10분 미만이면 이전 시간 기준으로 설정
        if now.minute < 10:
            now = now - timedelta(hours=1)
            
        base_date = now.strftime("%Y%m%d")
        # base_time은 정시 단위이므로 현재 시간을 기준으로 시(hour)만 사용
        base_time = now.strftime("%H00")
        
        # API 요청 파라미터 설정
        params = {
            'serviceKey': WEATHER_API_KEY,
            'pageNo': '1',
            'numOfRows': '1000',
            'dataType': 'XML',
            'base_date': base_date,
            'base_time': base_time,
            'nx': WEATHER_NX,
            'ny': WEATHER_NY
        }
        
        # API 요청
        response = requests.get(WEATHER_API_URL, params=params)
        
        # XML 파싱
        soup = BeautifulSoup(response.text, 'xml')
        
        # 에러 체크
        result_code = soup.find('resultCode').text
        if result_code != '00':
            error_msg = soup.find('resultMsg').text
            return {'error': f'날씨 정보 조회 실패: {error_msg}'}
        
        # 날씨 데이터 파싱
        items = soup.find_all('item')
        weather_data = {}
        
        for item in items:
            category = item.find('category').text
            value = item.find('obsrValue').text
            
            if category == 'T1H':  # 기온
                weather_data['temperature'] = f"{value}°C"
            elif category == 'RN1':  # 1시간 강수량
                weather_data['rainfall'] = f"{value}mm"
            elif category == 'REH':  # 습도
                weather_data['humidity'] = f"{value}%"
            elif category == 'WSD':  # 풍속
                weather_data['wind_speed'] = f"{value}m/s"
            elif category == 'VEC':  # 풍향
                weather_data['wind_direction'] = value
            elif category == 'PTY':  # 강수형태
                weather_data['precipitation_type'] = value
        
        return weather_data
        
    except Exception as e:
        return {'error': f'날씨 정보 조회 중 오류 발생: {str(e)}'}

if __name__ == '__main__':
    init_db() # 데이터베이스 초기화
    app.run(host='0.0.0.0', debug=True) 