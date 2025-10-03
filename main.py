import requests
from bs4 import BeautifulSoup
import re
from datetime import date, timedelta, datetime
import os
import db_manager
import json
import sys
import concurrent.futures

DB_PATH = os.path.join(os.path.dirname(__file__), db_manager.DB_NAME)

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
    content_area = soup.find(class_='post-content')
    if not content_area:
        print("Warning: Could not find content area on events page. Falling back to all links.")
        content_area = soup

    for link in content_area.find_all('a', href=True):
        url = link['href']
        name = link.text.strip()
        if name and '5verst.ru' in url and '/events' not in url:
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
    """Downloads and parses a single race results page for runners and volunteers, including their IDs."""
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
                    score_match = re.search(r'([\d\.]+)\%', age_grade_text)
                    gender_match = re.search(r'^[МЖ]', age_grade_text)
                    age_group_match = re.search(r'[МЖ](\d{2}-\d{2})', age_grade_text)

                    time_text = cells[3].text.strip()
                    if not re.match(r'^\d{2}:\d{2}:\d{2}$', time_text): continue
                    time_parts = [int(x) for x in time_text.split(':')]

                    runners.append({
                        'id': runner_id, 'name': name,
                        'score': float(score_match.group(1)) if score_match else 0.0,
                        'time_in_seconds': time_parts[0] * 3600 + time_parts[1] * 60 + time_parts[2],
                        'gender': gender_match.group(0) if gender_match else "Н/Д",
                        'age_group': age_group_match.group(1) if age_group_match else None,
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
    """Worker function to process a single race: fetch, parse, and save."""
    print(f"  - Проверка: {race['date']} (№{race['number']})...")
    html_content = get_results_from_url(race['url'])
    if html_content:
        scraped_data = parse_html_for_results(html_content)
        if scraped_data and (scraped_data.get('runners') or scraped_data.get('volunteers')):
            db_manager.save_results(DB_PATH, race['date'], location_slug, race['number'], scraped_data)
            print(f"    -> Сохранено: {len(scraped_data['runners'])} бегунов, {len(scraped_data['volunteers'])} волонтеров.")
        else:
            # Save empty result to prevent re-scraping old, non-existent races
            db_manager.save_results(DB_PATH, race['date'], location_slug, race['number'], {'runners': [], 'volunteers': []})

if __name__ == '__main__':
    db_manager.init_db(DB_PATH)
    
    print("Этап 1: Получение списка всех локаций...")
    locations = get_all_locations()
    if not locations:
        print("Не удалось получить список локаций. Выход.")
        sys.exit(1)
    
    db_manager.save_locations(DB_PATH, locations)
    print(f"Найдено и сохранено {len(locations)} локаций.")

    # --- Логика для выбора локаций --- #
    single_location_slug = None
    # Ищем аргумент вида --slug
    for arg in sys.argv[1:]:
        if arg.startswith('--') and arg != '--weekly' and arg != '--full':
            single_location_slug = arg[2:]
            break

    if single_location_slug:
        print(f"Запуск в режиме одной локации: {single_location_slug}")
        locations_to_process = [loc for loc in locations if loc['slug'] == single_location_slug]
        if not locations_to_process:
            print(f"Ошибка: Локация '{single_location_slug}' не найдена в общем списке.")
            sys.exit(1)
    else:
        locations_to_process = locations

    is_weekly = '--weekly' in sys.argv
    if is_weekly: print("\nЗапуск в режиме недельного обновления...")
    else: print("\nЗапуск в режиме полного обновления...")

    for loc in locations_to_process:
        print(f"\n--- Поиск забегов для локации: {loc['name']} ---")
        races_for_loc = get_race_list_for_location(loc['slug'])
        if not races_for_loc:
            print("Забеги не найдены, пропускаем.")
            continue

        for race in races_for_loc:
            race_date_obj = datetime.strptime(race['date'], '%d.%m.%Y').date()
            # Если забег старый, проверяем, есть ли он в базе
            if race_date_obj < update_threshold:
                existing_data = db_manager.load_results(DB_PATH, race['date'], loc['slug'])
                if existing_data and (existing_data.get('runners') or existing_data.get('volunteers')):
                    continue # Пропускаем, если данные уже есть
            
            # Добавляем в очередь на скачивание, если забег свежий или его нет в базе
            tasks_to_run.append((race, loc['slug']))

    if not tasks_to_run:
        print("\nНет новых забегов для обновления.")
    else:
        print(f"\nВсего задач на скачивание: {len(tasks_to_run)}. Запускаем {min(10, len(tasks_to_run))} потоков...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Распаковываем аргументы для process_race
            futures = [executor.submit(process_race, task[0], task[1]) for task in tasks_to_run]
            concurrent.futures.wait(futures)
            
    print("\nСбор данных завершен.")
