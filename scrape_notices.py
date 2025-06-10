import requests
from bs4 import BeautifulSoup
import os

def scrape_kotsa_notices(url="https://lic.kotsa.or.kr/tsportal/board/index.do?manage_idx=10&menu_idx=9&rowCount=10&viewPage=1"):
    notices = []
    try:
        response = requests.get(url)
        response.raise_for_status() # HTTP 오류 발생 시 예외 처리
    except requests.exceptions.RequestException as e:
        return [{"error": f"웹페이지를 가져오는 중 오류 발생: {e}"}]

    soup = BeautifulSoup(response.text, 'html.parser')

    # 웹페이지의 공지사항 테이블 구조에 맞춰 선택자를 조정합니다.
    # 여기서는 table 내의 tbody, tr, td를 직접 탐색합니다.
    # 웹페이지에서 테이블에 특정 class나 id가 없는 경우, 상위 요소를 통해 접근하거나,
    # 테이블 헤더의 텍스트로 테이블을 식별하는 방법을 사용할 수 있습니다.
    # 현재 웹사이트 결과로 미루어 볼 때, 명시적인 class가 없으므로 일반적인 table-tbody-tr 구조를 따르겠습니다.
    table = None
    # HTML 구조를 정확히 파악하기 위해 웹 검색 결과를 다시 참조하여 테이블을 찾습니다.
    # 웹 검색 결과에는 실제 테이블 태그의 class 정보가 없으므로,
    # 추측하건대, HTML 구조상 <table class="table"> 이나 이와 유사한 형태일 수 있습니다.
    # 일단 th의 텍스트로 테이블을 식별하는 방식을 시도해봅니다.
    for t in soup.find_all('table'):
        if t.find('th', string='제목') and t.find('th', string='작성일'):
            table = t
            break

    if table:
        for row in table.find('tbody').find_all('tr'):
            try:
                # 제목 (class="left title" td 내의 a 태그 안의 span)
                title_td = row.find('td', class_='left title')
                title_tag = title_td.find('a').find('span')
                title = title_tag.get_text(strip=True)
                
                # 링크 ID (href 속성에서 board_idx= 값 추출)
                link_href = title_td.find('a')['href']
                link_id_start = link_href.find("board_idx=") + len("board_idx=")
                link_id_end = link_href.find("&", link_id_start)
                link_id = link_href[link_id_start:link_id_end] if link_id_end != -1 else link_href[link_id_start:]

                # 등록일 (class="adddate date" td)
                date = row.find('td', class_='adddate date').get_text(strip=True)
                notices.append({"title": title, "link_id": link_id, "date": date})
            except (AttributeError, IndexError) as e:
                # print(f"행 파싱 오류: {e} - {row}") # 디버깅을 위해 오류 행 출력
                continue # 예상 구조와 다른 행은 건너뜀
    return notices[:5] # 최신 5개만 반환

def scrape_kaa_notices(url="https://www.kaa.atims.kr/pubs/notice/notice/ListAction.do"):
    alarm_notices = []
    numbered_notices = []
    try:
        response = requests.get(url)
        response.raise_for_status() # HTTP 오류 발생 시 예외 처리
    except requests.exceptions.RequestException as e:
        return [{"error": f"웹페이지를 가져오는 중 오류 발생: {e}"}]

    soup = BeautifulSoup(response.text, 'html.parser')

    table = soup.find('table', class_='uk-table uk-table-divider table-list notice-list')
    if table:
        for row in table.find('tbody').find_all('tr'):
            try:
                # 첫 번째 td (번호 또는 알림)
                first_td_text = row.find_all('td')[0].get_text(strip=True)

                title_a_tag = row.find('a') # 행 내의 첫 번째 <a> 태그
                if not title_a_tag:
                    continue

                title = title_a_tag.get_text(strip=True)
                
                link_id = None
                if 'onclick' in title_a_tag.attrs:
                    link_id = title_a_tag['onclick'].replace("onView('", "").replace("')", "")
                elif 'href' in title_a_tag.attrs and "board_idx=" in title_a_tag['href']:
                    link_href = title_a_tag['href']
                    link_id_start = link_href.find("board_idx=") + len("board_idx=")
                    link_id_end = link_href.find("&", link_id_start)
                    link_id = link_href[link_id_start:link_id_end] if link_id_end != -1 else link_href[link_id_start:]

                date = row.find_all('td')[3].get_text(strip=True)
                
                notice_data = {"title": title, "link_id": link_id, "date": date}

                if first_td_text == "알림":
                    alarm_notices.append(notice_data)
                elif first_td_text.isdigit(): # 번호인 경우
                    numbered_notices.append(notice_data)

            except (AttributeError, IndexError) as e:
                # print(f"행 파싱 오류: {e} - {row}")
                continue
    
    # 최신 3개 알림 공지사항과 최신 5개 번호 공지사항을 반환합니다.
    return {"alarm_notices": alarm_notices[:3], "numbered_notices": numbered_notices[:5]}

if __name__ == "__main__":
    print("교통안전공단 최신 공지사항 (최근 5개):")
    kotsa_notices = scrape_kotsa_notices()
    if isinstance(kotsa_notices, list) and kotsa_notices and "error" in kotsa_notices[0]:
        print(kotsa_notices[0]["error"])
    else:
        for notice in kotsa_notices:
            print(f"• 제목: {notice['title']}")
            print(f"  링크 ID: {notice['link_id']}")
            print(f"  등록일: {notice['date']}")
            print()

    print("\n항공교육훈련포털 최신 공지사항:")
    kaa_notices_categorized = scrape_kaa_notices()
    if isinstance(kaa_notices_categorized, list) and kaa_notices_categorized and "error" in kaa_notices_categorized[0]:
        print(kaa_notices_categorized[0]["error"])
    else:
        print("  알림 공지사항 (최신 3개):")
        for notice in kaa_notices_categorized["alarm_notices"]:
            print(f"• 제목: {notice['title']}")
            print(f"  링크 ID: {notice['link_id']}")
            print(f"  등록일: {notice['date']}")
            print()
        
        print("  일반 공지사항 (최신 5개):")
        for notice in kaa_notices_categorized["numbered_notices"]:
            print(f"• 제목: {notice['title']}")
            print(f"  링크 ID: {notice['link_id']}")
            print(f"  등록일: {notice['date']}")
            print() 