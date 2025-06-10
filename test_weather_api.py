import requests
from datetime import datetime, timedelta

# app.py에서 필요한 설정과 함수들을 복사
KMA_API_KEY = "6pbnk4lATQeW55OJQG0Hzw"
KMA_WEATHER_BASE_URL = "https://apihub.kma.go.kr/api/typ01/url/fct_shrt_reg.php"
SEOUL_REG_ID = "11B10101"

def get_weather_data_test():
    params = {
        "authKey": KMA_API_KEY,
        "tmfc": "0",
        "reg": SEOUL_REG_ID,
        "disp": "1"
    }

    print(f"KMA API 요청: {KMA_WEATHER_BASE_URL}?{requests.compat.urlencode(params)}")

    try:
        response = requests.get(KMA_WEATHER_BASE_URL, params=params)
        response.raise_for_status()
        data = response.text
        
        with open('raw_kma_response_test.txt', 'w', encoding='utf-8') as f:
            f.write(data)
        print("KMA API 원시 응답이 raw_kma_response_test.txt에 저장되었습니다.")
        
        # 실제 파싱은 여기서는 하지 않고, 파일 저장 여부만 확인
        return {"status": "success", "message": "API 응답을 파일에 저장했습니다."}

    except requests.exceptions.RequestException as e:
        print(f"날씨 정보를 가져오는 중 오류 발생: {e}")
        return {"error": "날씨 정보를 불러올 수 없습니다."}
    except Exception as e:
        print(f"날씨 데이터 처리 중 오류 발생: {e}")
        return {"error": "날씨 데이터 처리 중 오류가 발생했습니다."}

if __name__ == "__main__":
    print("test_weather_api.py 스크립트 실행 시작")
    result = get_weather_data_test()
    print(f"결과: {result}") 