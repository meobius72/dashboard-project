import requests
import math
from flask import Flask, render_template, jsonify, request
from scrape_notices import scrape_kotsa_notices, scrape_kaa_notices
from datetime import datetime, timedelta, timezone
import json
from collections import Counter

app = Flask(__name__)

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

# KMA API 설정
KMA_WEATHER_API_BASE_URL = "https://apihub.kma.go.kr/api/typ02/openApi/NwpModelInfoService/getLdapsUnisArea"
KMA_API_KEY = "6pbnk4lATQeW55OJQG0Hzw" # 사용자 제공 API 키
HAGYE_DONG_DONGCODE = "1135010400" # 하계동 행정구역 코드

@app.route('/get_weather')
def get_weather():
    try:
        now_utc = datetime.now(timezone.utc)
        anal_time = now_utc.strftime("%Y%m%d%H%M") # 분석 시간 (현재 시간으로 가정)

        # 온도 데이터 요청
        temp_params = {
            "pageNo": 1,
            "numOfRows": 10,
            "dataTypeCd": "Temp", # 온도
            "authKey": KMA_API_KEY,
            "baseTime": anal_time,
            "dongCode": HAGYE_DONG_DONGCODE, # 하계동 코드 추가
            "dataType": "JSON" # JSON 형식으로 요청
        }
        temp_response = requests.get(KMA_WEATHER_API_BASE_URL, params=temp_params)
        temp_data = temp_response.json()
        print(f"Temperature API Response: {temp_data}") # 디버깅을 위한 출력

        # 강수량 데이터 요청
        rain_params = {
            "pageNo": 1,
            "numOfRows": 10,
            "dataTypeCd": "rain", # 강수량
            "authKey": KMA_API_KEY,
            "baseTime": anal_time,
            "dongCode": HAGYE_DONG_DONGCODE, # 하계동 코드 추가
            "dataType": "JSON"
        }
        rain_response = requests.get(KMA_WEATHER_API_BASE_URL, params=rain_params)
        rain_data = rain_response.json()
        print(f"Rainfall API Response: {rain_data}") # 디버깅을 위한 출력

        # 습도 데이터 요청
        humi_params = {
            "pageNo": 1,
            "numOfRows": 10,
            "dataTypeCd": "humi", # 습도
            "authKey": KMA_API_KEY,
            "baseTime": anal_time,
            "dongCode": HAGYE_DONG_DONGCODE, # 하계동 코드 추가
            "dataType": "JSON"
        }
        humi_response = requests.get(KMA_WEATHER_API_BASE_URL, params=humi_params)
        humi_data = humi_response.json()
        print(f"Humidity API Response: {humi_data}") # 디버깅을 위한 출력

        # 데이터 파싱 및 통합
        weather_info = {
            "temperature": None,
            "rainfall": None,
            "humidity": None,
            "error": None
        }

        # 온도 파싱
        if temp_data and "response" in temp_data and "body" in temp_data["response"] and "items" in temp_data["response"]["body"] and "item" in temp_data["response"]["body"]["items"]:
            for item in temp_data["response"]["body"]["items"]["item"]:
                if item.get("dataTypeCd") == "Temp":
                    weather_info["temperature"] = item.get("fcstValue")
                    break
        else:
            weather_info["error"] = temp_data.get("response", {}).get("header", {}).get("returnAuthMsg", "온도 데이터 없음")

        # 강수량 파싱
        if rain_data and "response" in rain_data and "body" in rain_data["response"] and "items" in rain_data["response"]["body"] and "item" in rain_data["response"]["body"]["items"]:
            for item in rain_data["response"]["body"]["items"]["item"]:
                if item.get("dataTypeCd") == "rain":
                    weather_info["rainfall"] = item.get("fcstValue")
                    break
        else:
            if not weather_info["error"]: # 이미 에러가 없으면 추가
                weather_info["error"] = rain_data.get("response", {}).get("header", {}).get("returnAuthMsg", "강수량 데이터 없음")

        # 습도 파싱
        if humi_data and "response" in humi_data and "body" in humi_data["response"] and "items" in humi_data["response"]["body"] and "item" in humi_data["response"]["body"]["items"]:
            for item in humi_data["response"]["body"]["items"]["item"]:
                if item.get("dataTypeCd") == "humi":
                    weather_info["humidity"] = item.get("fcstValue")
                    break
        else:
            if not weather_info["error"]: # 이미 에러가 없으면 추가
                weather_info["error"] = humi_data.get("response", {}).get("header", {}).get("returnAuthMsg", "습도 데이터 없음")

        return jsonify(weather_info)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"API 호출 오류: {str(e)}"}), 500
    except json.JSONDecodeError:
        return jsonify({"error": "API 응답 JSON 파싱 오류"}), 500
    except Exception as e:
        return jsonify({"error": f"서버 오류: {str(e)}"}), 500

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True) 