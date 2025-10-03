import sys
import db_manager
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), db_manager.DB_NAME)

def find_medals_for_runner(runner_name):
    all_races = db_manager.load_all_results(DB_PATH)
    medals_found = []

    for race in all_races:
        race_data = race.get('data', {})
        runners = race_data.get('runners', [])
        
        for runner in runners:
            if runner.get('name', '').upper() == runner_name.upper():
                medal = None
                rank = runner.get('overall_rank')
                gender_rank = runner.get('gender_rank')
                gender = runner.get('gender')

                if gender == 'М':
                    if rank == 1: medal = 'Золото'
                    elif rank == 2: medal = 'Серебро'
                    elif rank == 3: medal = 'Бронза'
                elif gender == 'Ж':
                    if gender_rank == 1: medal = 'Золото'
                    elif gender_rank == 2: medal = 'Серебро'
                    elif gender_rank == 3: medal = 'Бронза'
                
                if medal:
                    medals_found.append({
                        'date': race.get('race_date'),
                        'number': race.get('race_number'),
                        'medal': medal,
                        'rank': gender_rank if gender == 'Ж' and gender_rank is not None else rank
                    })
                break # Оптимизация: переходим к следующему забегу, как только нашли участника

    return medals_found

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python find_medals.py \"Имя Фамилия\"")
        sys.exit(1)

    runner_name_to_find = sys.argv[1]
    print(f"Поиск медалей для участника: {runner_name_to_find}...")
    
    medals = find_medals_for_runner(runner_name_to_find)

    if not medals:
        print("Медалей не найдено.")
    else:
        print("\nНайденные медали:")
        # Сортируем медали по дате от новых к старым
        sorted_medals = sorted(medals, key=lambda x: datetime.strptime(x['date'], '%d.%m.%Y'), reverse=True)
        for m in sorted_medals:
            print(f"  - {m['date']} (Забег №{m['number']}): {m['medal']} ({m['rank']} место)")
