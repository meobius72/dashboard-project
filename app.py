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

# KMAWeatherAPI 클래스 (초단기실황조회 API 클라이언트)
class KMAWeatherAPI:
    def __init__(self, service_key):
        if not service_key or service_key == "YOUR_KMA_SERVICE_KEY":
            raise ValueError("유효한 서비스 키를 입력해야 합니다. 환경 변수 등을 통해 안전하게 관리하세요.")
        self.service_key = service_key
        self.endpoint = "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getUltraSrtNcst"

    def _get_grid_coords(self, latitude, longitude):
        return convert_gps_to_grid(latitude, longitude)

    def _get_base_date_time(self):
        now = datetime.now(timezone.utc) + timedelta(hours=9) # KST (UTC+9)

        target_dt = now

        # 초단기실황조회 (getUltraSrtNcst)는 매 시간 10분 이후에 호출 권장
        # base_time은 HH00 형식 (정시 단위)
        if now.minute < 10:
            target_dt -= timedelta(hours=1)

        base_hour_str = f"{target_dt.hour:02d}"
        base_time_str = base_hour_str + "00" # HH00 형식으로 고정

        # 24시인 경우 00시로 조정 (API가 00시를 사용)
        if base_time_str == '2400':
            base_time_str = '0000'
            # 날짜도 다음 날로 변경 (이전 시각이 23:xx이고 다음날 00:xx로 조정될 경우)
            target_dt += timedelta(days=1) 

        base_date_str = target_dt.strftime("%Y%m%d")
        
        return base_date_str, base_time_str

    def get_realtime_weather(self, latitude, longitude):
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
            
            data = response.json()
            print(json.dumps(data, indent=4, ensure_ascii=False)) # API 원시 응답 로깅

            header = data.get("response", {}).get("header", {})
            result_code = header.get("resultCode")
            result_msg = header.get("resultMsg")

            if result_code!= "00":
                raise Exception(f"API Error {result_code}: {result_msg}")

            items = data.get("response", {}).get("body", {}).get("items", {}).get("item",)
            if not items:
                return {
                    "location": {"latitude": latitude, "longitude": longitude, "grid_x": nx, "grid_y": ny},
                    "reference_time": f"{base_date[:4]}-{base_date[4:6]}-{base_date[6:]} {base_time[:2]}:{base_time[2:]}",
                    "weather": {},
                    "message": "해당 조건의 날씨 데이터가 없습니다."
                }

            weather_info = {}
            for item in items:
                category = item.get("category")
                obsr_value = item.get("obsrValue")
                if category and obsr_value is not None:
                    weather_info[category] = obsr_value
            
            pty_map = {
                "0": "없음", "1": "비", "2": "비/눈", "3": "눈",
                "4": "소나기", "5": "빗방울", "6": "빗방울/눈날림", "7": "눈날림"
            }
            
            precipitation_str = weather_info.get("RN1", "0.0")
            if precipitation_str == "강수없음":
                precipitation_mm = 0.0
            else:
                try:
                    precipitation_mm = float(precipitation_str)
                except ValueError:
                    precipitation_mm = 0.0

            formatted_weather = {
                "location": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "grid_x": nx,
                    "grid_y": ny
                },
                "reference_time": f"{base_date[:4]}-{base_date[4:6]}-{base_date[6:]} {base_time[:2]}:{base_time[2:]}",
                "weather": {
                    "temperature_celsius": float(weather_info.get("T1H", 0.0)),
                    "humidity_percent": float(weather_info.get("REH", 0.0)),
                    "precipitation_mm": precipitation_mm,
                    "precipitation_type": pty_map.get(weather_info.get("PTY", "0"), "정보 없음"),
                    "wind_direction_deg": float(weather_info.get("VEC", 0.0)),
                    "wind_speed_ms": float(weather_info.get("WSD", 0.0))
                }
            }
            return formatted_weather

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
kma_api_client = KMAWeatherAPI(service_key=KMA_API_KEY)
# 하계동 위경도 (웹 검색을 통해 찾은 값)
HAGYE_DONG_LATITUDE = 37.6365682
HAGYE_DONG_LONGITUDE = 127.0679542

@app.route('/get_weather')
def get_weather():
    try:
        # KMAWeatherAPI 클래스를 사용하여 날씨 정보 가져오기
        weather_data = kma_api_client.get_realtime_weather(HAGYE_DONG_LATITUDE, HAGYE_DONG_LONGITUDE)
        
        # 클라이언트에 보낼 형식으로 데이터 가공 (필요하다면)
        # 예시: { "temperature": 25.0, "rainfall": 0.0, "humidity": 70.0, "error": null }
        # KMAWeatherAPI.get_realtime_weather는 이미 표준화된 JSON 형식 반환
        
        # API 오류가 message 필드에 있을 수 있으므로 확인
        if "message" in weather_data:
            return jsonify({"error": weather_data["message"]}), 500
        
        # 기존 형식에 맞춰 반환 (temperature, rainfall, humidity)
        return jsonify({
            "temperature": weather_data["weather"].get("temperature_celsius"),
            "rainfall": weather_data["weather"].get("precipitation_mm"),
            "humidity": weather_data["weather"].get("humidity_percent"),
            "error": None # 성공 시 에러 없음
        })

    except ValueError as ve:
        return jsonify({"error": f"설정 오류: {str(ve)}"}), 500
    except Exception as e:
        return jsonify({"error": f"날씨 정보 조회 오류: {str(e)}"}), 500

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