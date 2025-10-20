import requests
from bs4 import BeautifulSoup
import re
from datetime import date, timedelta, datetime
import os
import db_manager
import json
import sys
import concurrent.futures
from dotenv import load_dotenv

load_dotenv()

def get_all_locations():
    """Scrapes the main events page to get a list of all locations."""
    events_url = "https://5verst.ru/events/"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(events_url, headers=headers)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Fatal: Could not fetch locations page: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    locations = []
    seen_slugs = set()

    container = soup.find('div', class_='events-columns')
    if not container:
        print("Fatal: Could not find the 'events-columns' container.")
        return []

    for link in container.find_all('a', href=True):
        url = link['href']
        name = link.text.strip()

        if name and '5verst.ru' in url:
            try:
                path = url.split('5verst.ru/')[1]
                slug = path.strip('/')
                if slug and '/' not in slug and '#' not in slug and '?' not in slug:
                    if slug not in seen_slugs:
                        locations.append({'name': name, 'slug': slug, 'url': url})
                        seen_slugs.add(slug)
            except IndexError:
                continue
    return locations

def get_race_list_for_location(location_slug):
    """Scrapes the results history page for a single location."""
    history_url = f"https://5verst.ru/{location_slug}/results/all/"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(history_url, headers=headers)
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    history_table = soup.find('table')
    if not history_table: return []

    race_list = []
    for row in history_table.find('tbody').find_all('tr'):
        cells = row.find_all('td')
        if len(cells) > 1:
            try:
                race_number = int(cells[0].text.strip()) if cells[0].text.strip() else 0
                date_link = cells[1].find('a')
                race_list.append({
                    'date': datetime.strptime(date_link.text.strip(), '%d.%m.%Y').strftime('%d.%m.%Y'),
                    'number': race_number,
                    'url': date_link['href']
                })
            except (ValueError, TypeError, AttributeError):
                continue
    return race_list

def get_results_from_url(url):
    """Downloads and parses a single race results page."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"  - Error fetching {url}: {e}")
        return None

def parse_html_for_results(html_content):
    """Parses the HTML content of a results page."""
    soup = BeautifulSoup(html_content, 'html.parser')
    all_tables = soup.find_all('table')
    runners = []
    if len(all_tables) > 0:
        for row in all_tables[0].find_all('tr')[1:]:
            cells = row.find_all('td')
            if len(cells) > 3:
                try:
                    name_cell = cells[1].find('a')
                    runner_id = int(name_cell['href'].split('/')[-1]) if name_cell else None
                    name = name_cell.text.strip() if name_cell else "Неизвестный"
                    
                    age_grade_text = cells[2].text.strip()
                    print(f"Parsing age grade text: '{age_grade_text}'")
                    score_match = re.search(r'([\d\.]+)\%', age_grade_text)
                    gender_match = re.search(r'^[МЖ]', age_grade_text)
                    age_group_match = re.search(r'[МЖ](\d{1,2}-\d{1,2})', age_grade_text)

                    time_text = cells[3].text.strip()
                    if not re.match(r'^\d{2}:\d{2}:\d{2}$', time_text): continue
                    time_parts = [int(x) for x in time_text.split(':')]

                    age_group = age_group_match.group(1) if age_group_match else None
                    print(f"Parsed age group: {age_group} for runner {name}")

                    runners.append({
                        'id': runner_id, 'name': name,
                        'score': float(score_match.group(1)) if score_match else 0.0,
                        'time_in_seconds': time_parts[0] * 3600 + time_parts[1] * 60 + time_parts[2],
                        'gender': gender_match.group(0) if gender_match else "Н/Д",
                        'age_group': age_group,
                        'overall_rank': int(cells[0].text.strip())
                    })
                except (ValueError, IndexError, AttributeError): continue
        
        fem_runners = sorted([r for r in runners if r['gender'] == 'Ж'], key=lambda x: x['time_in_seconds'])
        for i, r_data in enumerate(fem_runners): r_data['gender_rank'] = i + 1

    volunteers = []
    if len(all_tables) > 1:
        for row in all_tables[1].find('tbody').find_all('tr'):
            name_tag = row.find('td').find('a')
            if name_tag:
                try:
                    v_id = int(name_tag['href'].split('/')[-1])
                    if not any(v['id'] == v_id for v in volunteers): 
                        volunteers.append({'id': v_id, 'name': name_tag.text.strip()})
                except (ValueError, IndexError, AttributeError): continue
    
    return {'runners': runners, 'volunteers': volunteers}

def process_race(race, location_slug):
    """Worker function to process a single race."""
    print(f"  - Проверка: {race['date']} (№{race['number']})...")
    html_content = get_results_from_url(race['url'])
    if html_content:
        scraped_data = parse_html_for_results(html_content)
        if scraped_data and (scraped_data.get('runners') or scraped_data.get('volunteers')):
            db_manager.save_results(DB_PATH, race['date'], location_slug, race['number'], scraped_data)
            print(f"    -> Сохранено: {race['date']} ({location_slug}) - {len(scraped_data['runners'])} бегунов, {len(scraped_data['volunteers'])} волонтеров.")
        else:
            db_manager.save_results(DB_PATH, race['date'], location_slug, race['number'], {'runners': [], 'volunteers': []})

if __name__ == '__main__':
    db_manager.init_db()
    
    print("Этап 1: Получение списка всех локаций...")
    locations = get_all_locations()
    if not locations:
        print("Не удалось получить список локаций. Выход.")
        sys.exit(1)
    
    (locations)
    print(f"Найдено и сохранено {len(locations)} локаций.")

    single_location_slug = None
    is_full_scan = '--full' in sys.argv

    for arg in sys.argv[1:]:
        if arg.startswith('--') and arg != '--full':
            single_location_slug = arg[2:]
            break

    if single_location_slug:
        print(f"\nЗапуск в режиме одной локации: {single_location_slug}")
        locations_to_process = [loc for loc in locations if loc['slug'] == single_location_slug]
        if not locations_to_process:
            print(f"Ошибка: Локация '{single_location_slug}' не найдена.")
            sys.exit(1)
    else:
        print("\nЗапуск в режиме умного обновления для всех локаций...")
        locations_to_process = locations

    tasks_to_run = []
    today = date.today()
    update_threshold = today - timedelta(days=3)

    for loc in locations_to_process:
        print(f"--- Поиск забегов для локации: {loc['name']} ---")
        races_for_loc = get_race_list_for_location(loc['slug'])
        if not races_for_loc:
            print("Забеги не найдены, пропускаем.")
            continue

        for race in races_for_loc:
            if single_location_slug or is_full_scan:
                tasks_to_run.append((race, loc['slug']))
                continue

            race_date_obj = datetime.strptime(race['date'], '%d.%m.%Y').date()
            if race_date_obj < update_threshold:
                if not db_manager.load_results(DB_PATH, race['date'], loc['slug']):
                    tasks_to_run.append((race, loc['slug']))
            else:
                tasks_to_run.append((race, loc['slug']))

    if not tasks_to_run:
        print("\nНет новых забегов для обновления.")
    else:
        print(f"\nВсего задач на скачивание: {len(tasks_to_run)}. Запускаем {min(10, len(tasks_to_run))} потоков...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(process_race, task[0], task[1]) for task in tasks_to_run]
            concurrent.futures.wait(futures)
            
    print("\nСбор данных завершен.")
