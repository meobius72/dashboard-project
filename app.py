import requests
import math
from flask import Flask, render_template, jsonify, request
from scrape_notices import scrape_kotsa_notices, scrape_kaa_notices
from gfz_client import GFZClient
from datetime import datetime, timedelta
import json
from collections import Counter

app = Flask(__name__)

print("Hello, from Flask app startup!") # 테스트를 위한 출력

# KMA API 설정 (API 키는 이미 사용자에게서 받음)
KMA_API_KEY = "6pbnk4lATQeW55OJQG0Hzw"
KMA_WEATHER_BASE_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"

# YouTube 동영상 ID 목록
YOUTUBE_VIDEO_IDS = [
    "dQw4w9WgXcQ", # Rick Astley - Never Gonna Give You Up
    "JGwWNGJdvx8", # Imagine Dragons - Believer
    "kJQP7kiw5Fk"  # Luis Fonsi - Despacito
]
current_youtube_index = 0

# 화면 갱신 주기 설정 (초 단위, 기본값 5분 = 300초)
REFRESH_INTERVAL = 300

# Kp 지수 클라이언트 인스턴스 생성 (추가)
gfz_client = GFZClient()

# 기상청 격자 좌표 변환을 위한 전역 변수 (추가)
RE = 6371.00877      # 지구 반경(km)
GRID = 5.0          # 격자 간격(km)
SLAT1 = 30.0        # 투영 위도1(degree)
SLAT2 = 60.0        # 투영 위도2(degree)
OLON = 126.0        # 기준점 경도(degree)
OLAT = 38.0         # 기준점 위도(degree)
XO = 43             # 기준점 X좌표(GRID)
YO = 136            # 기준점 Y좌표(GRID)

PI = math.asin(1.0) * 2.0
DEGRAD = PI / 180.0
RADDEG = 180.0 / PI

re = RE / GRID
slat1 = SLAT1 * DEGRAD
slat2 = SLAT2 * DEGRAD
olon = OLON * DEGRAD
olat = OLAT * DEGRAD

sn = math.tan(PI * 0.25 + slat2 * 0.5) / math.tan(PI * 0.25 + slat1 * 0.5)
sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
sf = math.tan(PI * 0.25 + slat1 * 0.5)
sf = math.pow(sf, sn) * math.cos(slat1) / sn
ro = math.tan(PI * 0.25 + olat * 0.5)
ro = re * sf / math.pow(ro, sn)

def convert_to_grid(lat, lon):
    ra = math.tan(PI * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / pow(ra, sn)
    theta = lon * DEGRAD - olon
    if theta > PI :
        theta -= 2.0 * PI
    if theta < -PI :
        theta += 2.0 * PI
    theta *= sn
    x = (ra * math.sin(theta)) + XO
    y = (ro - ra * math.cos(theta)) + YO
    x = int(x + 1.5)
    y = int(y + 1.5)
    return x, y

# 기본 위치 설정 (서울시청 기준 위도/경도)
SEOUL_LAT = 37.5665
SEOUL_LON = 126.9780

# Helper function to get the base_date and base_time for KMA API
def get_base_date_time():
    now = datetime.now()
    
    # KMA 단기예보 발표 시각 (HHMM)
    base_times = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]
    
    current_hour_minute = now.strftime("%H%M")
    
    target_base_date = now
    target_base_time = None
    
    for bt in reversed(base_times):
        if current_hour_minute >= bt:
            target_base_time = bt
            break
            
    if target_base_time is None:
        # If current_hour_minute is earlier than the earliest base_time (0200),
        # then use the last base_time (2300) of the previous day.
        target_base_date = now - timedelta(days=1)
        target_base_time = "2300"
        
    return target_base_date.strftime("%Y%m%d"), target_base_time

# 날씨 정보 가져오기 함수 (KMA API 사용으로 변경)
def get_weather_data():
    base_date, base_time = get_base_date_time()
    
    # Seoul's nx, ny coordinates
    nx = 60 # From KMA API documentation example for Seoul
    ny = 127 # From KMA API documentation example for Seoul

    # API 요청 파라미터 설정
    params = {
        "serviceKey": KMA_API_KEY, # Parameter name change from authKey to serviceKey
        "pageNo": "1",
        "numOfRows": "1000", # Max rows to get all forecast items for a day/period
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }

    api_request_url = f"{KMA_WEATHER_BASE_URL}?{requests.compat.urlencode(params)}"
    print(f"KMA API 요청: {api_request_url}")

    try:
        response = requests.get(KMA_WEATHER_BASE_URL, params=params)
        print(f"KMA API 응답 상태 코드: {response.status_code}") # 디버깅: 응답 상태 코드 출력
        print(f"KMA API 응답 헤더: {response.headers}") # 디버깅: 응답 헤더 출력
        print(f"KMA API 응답 텍스트: {response.text}") # 디버깅: 원시 응답 텍스트 출력
        response.raise_for_status() # HTTP 오류가 발생하면 예외 발생
        api_data_json = response.json()
        
        parsed_data = parse_kma_forecast(api_data_json)
        return parsed_data

    except requests.exceptions.RequestException as e:
        print(f"날씨 정보를 가져오는 중 오류 발생: {e}")
        return {"error": "날씨 정보를 불러올 수 없습니다."}
    except json.JSONDecodeError as e: # JSON 디코딩 오류 처리 추가
        print(f"날씨 데이터 JSON 디코딩 오류 발생: {e}. 응답 내용 확인 필요.")
        return {"error": "날씨 데이터 형식이 올바르지 않습니다."}
    except Exception as e:
        print(f"날씨 데이터 처리 중 오류 발생: {e}")
        import traceback
        traceback.print_exc() # 전체 트레이스백 출력을 통해 디버깅 정보 추가
        return {"error": "날씨 데이터 처리 중 오류가 발생했습니다."}

# KMA 예보 데이터 파싱 함수 (JSON 응답 처리)
def parse_kma_forecast(api_data_json):
    print("parse_kma_forecast 함수 호출됨 (JSON 처리)")
    weather_info = {
        "current_weather": {},
        "daily_forecast": [],
        "hourly_forecast": []
    }

    try:
        response_data = api_data_json.get('response', {})
        header = response_data.get('header', {})
        
        if header.get('resultCode') != '00':
            print(f"KMA API 오류: {header.get('resultMsg', '알 수 없는 오류')}")
            return {"error": f"KMA API 오류: {header.get('resultMsg', '알 수 없는 오류')}"}
        
        body = response_data.get('body', {})
        items = body.get('items', {}).get('item', [])
        
        if not items:
            print("KMA API 응답에 예보 항목이 없습니다.")
            return {"error": "KMA API 응답에 예보 항목이 없습니다."}

        # Group forecast items by forecast date and time
        forecast_by_datetime = {}
        for item in items:
            fcst_date_time = f"{item['fcstDate']}{item['fcstTime']}"
            if fcst_date_time not in forecast_by_datetime:
                forecast_by_datetime[fcst_date_time] = {
                    "fcstDate": item['fcstDate'],
                    "fcstTime": item['fcstTime'],
                    "categories": {}
                }
            forecast_by_datetime[fcst_date_time]["categories"][item['category']] = item['fcstValue']

        # Sort by forecast date and time
        sorted_forecasts = sorted(forecast_by_datetime.items())

        now = datetime.now()
        
        # Current Weather
        current_fcst_item_data = None
        current_day_forecasts = []
        for dt_str, data in sorted_forecasts:
            fcst_dt = datetime.strptime(dt_str, "%Y%m%d%H%M")
            if fcst_dt.date() == now.date():
                current_day_forecasts.append((fcst_dt, data["categories"]))

        if current_day_forecasts:
            closest_future_or_current = None
            min_diff = timedelta(days=100)

            for fcst_dt, categories in current_day_forecasts:
                if fcst_dt >= now:
                    diff = fcst_dt - now
                    if diff < min_diff:
                        min_diff = diff
                        closest_future_or_current = categories
            
            if closest_future_or_current:
                current_fcst_item_data = closest_future_or_current
            elif current_day_forecasts:
                current_fcst_item_data = current_day_forecasts[-1][1]
        
        if not current_fcst_item_data and sorted_forecasts:
            current_fcst_item_data = sorted_forecasts[0][1]["categories"]


        if current_fcst_item_data:
            weather_info["current_weather"] = {
                "temperature": current_fcst_item_data.get("TMP"),
                "sky_condition": get_sky_condition_text(current_fcst_item_data.get("SKY")),
                "precipitation_type": get_precipitation_type_text(current_fcst_item_data.get("PTY")),
                "wind_speed": current_fcst_item_data.get("WSD"),
                "wind_direction": get_wind_direction_text(current_fcst_item_data.get("VEC")),
                "humidity": current_fcst_item_data.get("REH"),
                "precipitation_probability": current_fcst_item_data.get("POP"),
            }

        # Hourly Forecast
        hourly_forecasts_list = []
        for dt_str, data in sorted_forecasts:
            fcst_dt = datetime.strptime(dt_str, "%Y%m%d%H%M")
            if fcst_dt >= now:
                categories = data["categories"]
                hourly_forecasts_list.append({
                    "time": fcst_dt.strftime("%H%M"),
                    "temperature": categories.get("TMP"),
                    "sky_condition": get_sky_condition_text(categories.get("SKY")),
                    "precipitation_type": get_precipitation_type_text(categories.get("PTY")),
                    "precipitation_probability": categories.get("POP"),
                })
        weather_info["hourly_forecast"] = hourly_forecasts_list


        # Daily Forecast
        daily_data_map = {}
        for dt_str, data in sorted_forecasts:
            fcst_date_str = data["fcstDate"]
            categories = data["categories"]

            if fcst_date_str not in daily_data_map:
                daily_data_map[fcst_date_str] = {
                    "date": fcst_date_str,
                    "min_temp": float('inf'),
                    "max_temp": float('-inf'),
                    "sky_conditions_codes": [],
                    "precipitation_types_codes": [],
                    "max_precipitation_probability": 0,
                    "wind_speed_values": [],
                    "wind_direction_values": [],
                    "humidity_values": []
                }
            
            tmp = categories.get("TMP")
            if tmp is not None:
                try:
                    tmp = float(tmp)
                    daily_data_map[fcst_date_str]["min_temp"] = min(daily_data_map[fcst_date_str]["min_temp"], tmp)
                    daily_data_map[fcst_date_str]["max_temp"] = max(daily_data_map[fcst_date_str]["max_temp"], tmp)
                except ValueError:
                    pass

            sky = categories.get("SKY")
            if sky is not None:
                daily_data_map[fcst_date_str]["sky_conditions_codes"].append(sky)
            
            pty = categories.get("PTY")
            if pty is not None:
                daily_data_map[fcst_date_str]["precipitation_types_codes"].append(pty)
            
            pop = categories.get("POP")
            if pop is not None:
                try:
                    pop = int(pop)
                    daily_data_map[fcst_date_str]["max_precipitation_probability"] = max(daily_data_map[fcst_date_str]["max_precipitation_probability"], pop)
                except ValueError:
                    pass
            
            wsd = categories.get("WSD")
            if wsd is not None:
                try:
                    daily_data_map[fcst_date_str]["wind_speed_values"].append(float(wsd))
                except ValueError:
                    pass
            
            vec = categories.get("VEC")
            if vec is not None:
                try:
                    daily_data_map[fcst_date_str]["wind_direction_values"].append(int(vec))
                except ValueError:
                    pass
            
            reh = categories.get("REH")
            if reh is not None:
                try:
                    daily_data_map[fcst_date_str]["humidity_values"].append(int(reh))
                except ValueError:
                    pass
        
        for date_str, data in sorted(daily_data_map.items()):
            dominant_sky = "알 수 없음"
            if data["sky_conditions_codes"]:
                sky_counts = Counter(data["sky_conditions_codes"])
                dominant_sky_code = sky_counts.most_common(1)[0][0]
                dominant_sky = get_sky_condition_text(dominant_sky_code)
            
            dominant_precipitation = "없음"
            if data["precipitation_types_codes"]:
                pty_counts = Counter(data["precipitation_types_codes"])
                dominant_precipitation_code = pty_counts.most_common(1)[0][0]
                dominant_precipitation = get_precipitation_type_text(dominant_precipitation_code)

            avg_wind_speed = round(sum(data["wind_speed_values"]) / len(data["wind_speed_values"]), 1) if data["wind_speed_values"] else None
            
            dominant_wind_direction = "알 수 없음"
            if data["wind_direction_values"]:
                wind_direction_texts = [get_wind_direction_text(d) for d in data["wind_direction_values"]]
                if wind_direction_texts:
                    direction_counts = Counter(wind_direction_texts)
                    dominant_wind_direction = direction_counts.most_common(1)[0][0]

            avg_humidity = int(sum(data["humidity_values"]) / len(data["humidity_values"])) if data["humidity_values"] else None

            weather_info["daily_forecast"].append({
                "date": date_str,
                "min_temperature": data["min_temp"] if data["min_temp"] != float('inf') else None,
                "max_temperature": data["max_temp"] if data["max_temp"] != float('-inf') else None,
                "sky_condition": dominant_sky,
                "precipitation_type": dominant_precipitation,
                "max_precipitation_probability": data["max_precipitation_probability"],
                "avg_wind_speed": avg_wind_speed,
                "dominant_wind_direction": dominant_wind_direction,
                "avg_humidity": avg_humidity,
            })

    except KeyError as e:
        print(f"KMA API 응답 파싱 오류 (키 없음): {e}")
        return {"error": "KMA API 응답 파싱 중 예상치 못한 형식입니다."}
    except Exception as e:
        print(f"KMA API 응답 파싱 중 일반 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"error": "날씨 데이터 파싱 중 오류가 발생했습니다."}

    return weather_info

def get_sky_condition_text(code):
    code = str(code)
    if code == '1':
        return '맑음'
    elif code == '3':
        return '구름많음'
    elif code == '4':
        return '흐림'
    return '알 수 없음'

def get_precipitation_type_text(code):
    code = str(code)
    if code == '0':
        return '없음'
    elif code == '1':
        return '비'
    elif code == '2':
        return '비/눈'
    elif code == '3':
        return '눈'
    elif code == '4': # KMA 단기예보의 소나기
        return '소나기'
    elif code == '5':
        return '빗방울'
    elif code == '6':
        return '빗방울눈날림'
    elif code == '7':
        return '눈날림'
    return '알 수 없음'

def get_wind_direction_text(code):
    try:
        code = int(code)
        if 0 <= code < 22.5: return "북"
        elif 22.5 <= code < 67.5: return "북동"
        elif 67.5 <= code < 112.5: return "동"
        elif 112.5 <= code < 157.5: return "남동"
        elif 157.5 <= code < 202.5: return "남"
        elif 202.5 <= code < 247.5: return "남서"
        elif 247.5 <= code < 292.5: return "서"
        elif 292.5 <= code < 337.5: return "북서"
        elif 337.5 <= code <= 360: return "북"
        else: return "알 수 없음"
    except (ValueError, TypeError):
        return "알 수 없음"

# Kp 지수 정보 가져오기 함수 (추가)
def get_kp_index_data():
    try:
        now = datetime.utcnow() # GFZ API는 UTC 시간을 권장합니다.
        # Kp 지수 데이터를 가져올 시간 범위 설정 (예: 지난 24시간)
        start_time_str = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_time_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # gfz_client.get_kp_index() 함수에 문자열 형식의 starttime, endtime, index 인자 전달
        kp_indices = gfz_client.get_kp_index(starttime=start_time_str, endtime=end_time_str, index="Kp")
        print(f"GFZ Kp 지수 API 응답: {kp_indices}") # 디버깅을 위한 출력
        if kp_indices:
            # 가장 최신 Kp 지수 (보통 리스트의 첫 번째 항목)
            latest_kp = kp_indices[0] 
            current_kp = latest_kp.kp_index
            updated_time = latest_kp.time_tag.strftime("%Y-%m-%d %H:%M:%S")
            return {
                "current_kp": current_kp,
                "updated_time": updated_time
            }
        else:
            print("GFZ Kp 지수 API에서 데이터를 받지 못했습니다.")
            return {"current_kp": "정보 없음", "updated_time": "정보 없음"}
    except Exception as e:
        print(f"Kp 지수 정보를 가져오는 중 오류 발생: {e}")
        import traceback
        traceback.print_exc() # 전체 트레이스백 출력을 통해 디버깅 정보 추가
        return {"current_kp": "오류 발생", "updated_time": "오류 발생"}

@app.route('/')
def index():
    kotsa_notices = scrape_kotsa_notices()
    kaa_notices = scrape_kaa_notices()
    weather_data = {}
    kp_index_data = {}
    try:
        weather_data = get_weather_data()
        print(f"Weather Data from get_weather_data in index: {weather_data}")
    except Exception as e:
        print(f"Error fetching weather data in index route: {e}")
        weather_data = {"error": "날씨 정보를 불러올 수 없습니다."}

    try:
        kp_index_data = get_kp_index_data()
        print(f"Kp Index Data from get_kp_index_data in index: {kp_index_data}")
    except Exception as e:
        print(f"Error fetching Kp index data in index route: {e}")
        kp_index_data = {"current_kp": "오류 발생", "updated_time": "오류 발생"}

    global current_youtube_index # 전역 변수임을 명시
    current_video_id = YOUTUBE_VIDEO_IDS[current_youtube_index]

    if isinstance(kotsa_notices, list) and kotsa_notices and "error" in kotsa_notices[0]:
        kotsa_notices_display = [{"title": kotsa_notices[0]["error"], "link_id": "#", "date": ""}]
    else:
        kotsa_notices_display = kotsa_notices

    if isinstance(kaa_notices, dict) and "error" in kaa_notices:
        kaa_alarm_notices_display = [{"title": kaa_notices["error"], "link_id": "#", "date": ""}]
        kaa_numbered_notices_display = []
    elif isinstance(kaa_notices, dict):
        kaa_alarm_notices_display = kaa_notices["alarm_notices"]
        kaa_numbered_notices_display = kaa_notices["numbered_notices"]
    else:
        kaa_alarm_notices_display = [{"title": "항공교육훈련포털 공지사항을 불러올 수 없습니다.", "link_id": "#", "date": ""}]
        kaa_numbered_notices_display = []

    return render_template('index.html',
                           kotsa_notices=kotsa_notices_display,
                           kaa_alarm_notices=kaa_alarm_notices_display,
                           kaa_numbered_notices=kaa_numbered_notices_display,
                           weather_data=weather_data,
                           kp_index_data=kp_index_data,
                           current_video_id=current_video_id)

@app.route('/get_weather')
def get_weather():
    weather_data = get_weather_data()
    return jsonify(weather_data)

@app.route('/get_kp_index')
def get_kp_index():
    kp_data = get_kp_index_data()
    return jsonify(kp_data)

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
    if new_interval is not None and isinstance(new_interval, (int, float)) and new_interval > 0:
        REFRESH_INTERVAL = int(new_interval)
        return jsonify({"status": "success", "new_interval": REFRESH_INTERVAL})
    return jsonify({"status": "error", "message": "유효하지 않은 갱신 주기입니다."}), 400

@app.route('/get_refresh_interval')
def get_refresh_interval():
    return jsonify({"interval": REFRESH_INTERVAL})

if __name__ == '__main__':
    app.run(debug=True) 