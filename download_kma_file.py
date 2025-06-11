import requests

def download_file(file_url, save_path):
    with open(save_path, 'wb') as f:
        response = requests.get(file_url)
        response.raise_for_status() # HTTP 오류가 발생하면 예외 발생
        f.write(response.content)
    print(f"File downloaded successfully to {save_path}")

# URL과 저장 경로 변수를 지정합니다.
url = 'https://apihub.kma.go.kr/api/file?authKey=6pbnk4lATQeW55OJQG0Hzw'
save_file_path = 'output_file.zip'

# 파일 다운로드 함수를 호출합니다.
try:
    download_file(url, save_file_path)
except requests.exceptions.RequestException as e:
    print(f"Error downloading file: {e}") 