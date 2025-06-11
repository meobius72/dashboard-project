import requests
import json

# URL 문자열
url = 'https://apihub.kma.go.kr/api/json?authKey=6pbnk4lATQeW55OJQG0Hzw'

# GET 요청
try:
    response = requests.get(url, timeout=10)
    response.raise_for_status() # HTTP 오류가 발생하면 예외 발생
    
    # 응답을 JSON 형태로 변환
    json_response = response.json()
    print(json.dumps(json_response, indent=4, ensure_ascii=False))

except requests.exceptions.HTTPError as e:
    print(f"HTTP Error: {e.response.status_code} {e.response.reason} - {e.response.text}")
except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")
except json.JSONDecodeError:
    print("Failed to parse API response as JSON.") 