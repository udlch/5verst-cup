from flask import Flask, jsonify, render_template, request
import os
import db_manager
from datetime import datetime

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), db_manager.DB_NAME)

SEASONS = {
    'зима': [12, 1, 2],
    'весна': [3, 4, 5],
    'лето': [6, 7, 8],
    'осень': [9, 10, 11]
}

def get_current_season(month):
    for season, months in SEASONS.items():
        if month in months:
            return season
    return None

def calculate_leaderboard(races_data):
    participants = {}
    for race in races_data:
        race_content = race.get('data', {})
        runners = race_content.get('runners', [])
        volunteers = race_content.get('volunteers', [])

        runner_ids_this_race = {r['id'] for r in runners if r.get('id')}

        for runner in runners:
            runner_id = runner.get('id')
            if not runner_id:
                continue

            if runner_id not in participants:
                participants[runner_id] = {
                    'name': runner.get('name'), 'total_score': 0.0, 'run_count': 0, 'volunteer_count': 0,
                    'total_time_seconds': 0, 'gender': 'Н/Д', 'best_time_seconds': float('inf'),
                    'best_time_race_number': None, 'age_group': None,
                    'gold_medals': 0, 'silver_medals': 0, 'bronze_medals': 0
                }
            
            stats = participants[runner_id]
            stats['name'] = runner.get('name')
            stats['run_count'] += 1
            stats['total_score'] += runner.get('score', 0.0)
            stats['total_time_seconds'] += runner.get('time_in_seconds', 0)

            if runner.get('time_in_seconds', float('inf')) < stats['best_time_seconds']:
                stats['best_time_seconds'] = runner['time_in_seconds']
                stats['best_time_race_number'] = race.get('race_number')
            
            if runner.get('age_group'):
                stats['age_group'] = runner['age_group']
            
            if stats['gender'] == 'Н/Д' and runner.get('gender', 'Н/Д') != 'Н/Д':
                stats['gender'] = runner['gender']

            gender = runner.get('gender')
            if gender == 'М':
                if runner.get('overall_rank') == 1: stats['gold_medals'] += 1
                elif runner.get('overall_rank') == 2: stats['silver_medals'] += 1
                elif runner.get('overall_rank') == 3: stats['bronze_medals'] += 1
            elif gender == 'Ж':
                if runner.get('gender_rank') == 1: stats['gold_medals'] += 1
                elif runner.get('gender_rank') == 2: stats['silver_medals'] += 1
                elif runner.get('gender_rank') == 3: stats['bronze_medals'] += 1

        for volunteer in volunteers:
            volunteer_id = volunteer.get('id')
            if not volunteer_id:
                continue

            if volunteer_id not in participants:
                participants[volunteer_id] = {
                    'name': volunteer.get('name'), 'total_score': 0.0, 'run_count': 0, 'volunteer_count': 0,
                    'total_time_seconds': 0, 'gender': 'Н/Д', 'best_time_seconds': float('inf'),
                    'best_time_race_number': None, 'age_group': None,
                    'gold_medals': 0, 'silver_medals': 0, 'bronze_medals': 0
                }

            stats = participants[volunteer_id]
            stats['name'] = volunteer.get('name')
            stats['volunteer_count'] += 1

            if volunteer_id in runner_ids_this_race:
                stats['total_score'] += 5
            else:
                stats['total_score'] += 55

    leaderboard = []
    for participant_id, stats in participants.items():
        stats['id'] = participant_id
        stats['total_score'] = stats['total_score'] / 10
        leaderboard.append(stats)

    leaderboard.sort(key=lambda x: x['total_score'], reverse=True)
    return leaderboard

@app.route('/')
def index():
    return render_template('leaderboard.html')

@app.route('/api/data')
def get_data():
    try:
        location_slug = request.args.get('location', default='korolev', type=str)
        year_filter = request.args.get('year', default=None, type=int)
        season_filter = request.args.get('season', default=None, type=str)
        month_filter = request.args.get('month', default=None, type=int)
        race_number_filter = request.args.get('race_number', default=None, type=int)
        filter_mode = request.args.get('filter', default=None, type=str)

        all_races_for_location = db_manager.load_all_results(DB_PATH, location_slug=location_slug)
        races_to_process = all_races_for_location

        if race_number_filter:
            races_to_process = [r for r in all_races_for_location if r.get('race_number') == race_number_filter]
        else:
            if filter_mode == 'current_season':
                now = datetime.now()
                year_filter = now.year
                season_filter = get_current_season(now.month)

            if season_filter == 'зима' and year_filter:
                previous_year = year_filter - 1
                winter_races = []
                for race in all_races_for_location:
                    try:
                        race_date = datetime.strptime(race['race_date'], '%d.%m.%Y')
                        if (race_date.year == year_filter and race_date.month in [1, 2]) or \
                           (race_date.year == previous_year and race_date.month == 12):
                            winter_races.append(race)
                    except (ValueError, KeyError):
                        continue
                races_to_process = winter_races
                if month_filter:
                    races_to_process = [r for r in races_to_process if datetime.strptime(r['race_date'], '%d.%m.%Y').month == month_filter]
            else:
                temp_races = races_to_process
                if year_filter:
                    temp_races = [r for r in temp_races if datetime.strptime(r['race_date'], '%d.%m.%Y').year == year_filter]
                if season_filter and season_filter in SEASONS:
                    season_months = SEASONS[season_filter]
                    temp_races = [r for r in temp_races if datetime.strptime(r['race_date'], '%d.%m.%Y').month in season_months]
                if month_filter:
                    temp_races = [r for r in temp_races if datetime.strptime(r['race_date'], '%d.%m.%Y').month == month_filter]
                races_to_process = temp_races

        leaderboard_data = calculate_leaderboard(races_to_process)

        for stats in leaderboard_data:
            if stats['best_time_seconds'] == float('inf'):
                stats['best_time_seconds'] = None
        
        top_male, top_female, best_run_info, fastest_time = (None, None, None, float('inf'))

        for race in races_to_process:
            for runner in race.get('data', {}).get('runners', []):
                if (time := runner.get('time_in_seconds')) is not None and time < fastest_time:
                    fastest_time = time
                    best_run_info = {'name': runner.get('name'), 'time': time, 'race_number': race.get('race_number'), 'date': race.get('race_date')}

        for runner in leaderboard_data:
            if runner['gender'] == 'М' and top_male is None: top_male = runner['name']
            if runner['gender'] == 'Ж' and top_female is None: top_female = runner['name']

        record_age_days = None
        if best_run_info and best_run_info.get('date'):
            try:
                record_date_obj = datetime.strptime(best_run_info['date'], '%d.%m.%Y')
                record_age_days = (datetime.now() - record_date_obj).days
            except ValueError: pass

        response_data = {
            'leaderboard': leaderboard_data,
            'metadata': {
                'top_male': top_male,
                'top_female': top_female,
                'overall_fastest': {
                    'name': best_run_info.get('name') if best_run_info else None,
                    'time': best_run_info.get('time') if best_run_info else None,
                    'race_number': best_run_info.get('race_number') if best_run_info else None,
                    'age_days': record_age_days
                }
            }
        }
        return jsonify(response_data)
    except Exception as e:
        print(f"Error in /api/data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "An internal server error occurred."}), 500

@app.route('/api/locations')
def get_locations():
    """API эндпоинт для получения списка всех локаций, у которых есть забеги."""
    locations = db_manager.load_locations_with_races(DB_PATH)
    return jsonify(locations)

@app.route('/api/years')
def get_available_years():
    location_slug = request.args.get('location', default='korolev', type=str)
    all_races = db_manager.load_all_results(DB_PATH, location_slug=location_slug)
    years = {datetime.strptime(race['race_date'], '%d.%m.%Y').year for race in all_races if race.get('data')}
    return jsonify(sorted(list(years), reverse=True))

@app.route('/api/racedates')
def get_available_races():
    location_slug = request.args.get('location', default='korolev', type=str)
    all_races = db_manager.load_all_results(DB_PATH, location_slug=location_slug)
    races = [
        {"number": race['race_number'], "date": race['race_date']}
        for race in all_races if race.get('race_number') and race.get('race_number') > 0
    ]
    races.sort(key=lambda x: x['number'], reverse=True)
    return jsonify(races)

if __name__ == '__main__':
    db_manager.init_db(DB_PATH)
    app.run(debug=True, port=5001)
