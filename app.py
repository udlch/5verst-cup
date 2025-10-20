from flask import Flask, jsonify, render_template, request
import os
import db_manager
from datetime import datetime
import math

app = Flask(__name__)


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

def calculate_leaderboard(races_data, ag_filter=None):
    participants = {}
    for race in races_data:
        race_content = race.get('data', {})
        runners = race_content.get('runners', [])
        volunteers = race_content.get('volunteers', [])

        if ag_filter and ag_filter != 'all':
            runners = [r for r in runners if f"{r.get('gender')}{r.get('age_group')}" == ag_filter]

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
                    'gold_medals': 0, 'silver_medals': 0, 'bronze_medals': 0,
                    'best_time_date': None, 'best_time_location_slug': None
                }
            
            stats = participants[runner_id]
            stats['name'] = runner.get('name')
            stats['run_count'] += 1
            stats['total_score'] += runner.get('score', 0.0)
            stats['total_time_seconds'] += runner.get('time_in_seconds', 0)

            if runner.get('time_in_seconds', float('inf')) < stats['best_time_seconds']:
                stats['best_time_seconds'] = runner['time_in_seconds']
                stats['best_time_race_number'] = race.get('race_number')
                stats['best_time_date'] = race.get('race_date')
                stats['best_time_location_slug'] = race.get('location_slug')
            
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
                    'gold_medals': 0, 'silver_medals': 0, 'bronze_medals': 0,
                    'best_time_date': None, 'best_time_location_slug': None
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
        if stats['best_time_location_slug'] and stats['best_time_date']:
            stats['best_time_race_url'] = f"https://5verst.ru/{stats['best_time_location_slug']}/results/{stats['best_time_date']}/"
        else:
            stats['best_time_race_url'] = None
        leaderboard.append(stats)

    if ag_filter:
        leaderboard.sort(key=lambda x: x['best_time_seconds'])
    else:
        leaderboard.sort(key=lambda x: x['total_score'], reverse=True)
        
    return leaderboard

def get_all_locations_data(page, ag_filter):
    all_races = db_manager.load_all_results(location_slug='all')
    participants = {}
    for race in all_races:
        runners = race.get('data', {}).get('runners', [])
        volunteers = race.get('data', {}).get('volunteers', [])
        runner_ids_this_race = {r['id'] for r in runners if r.get('id')}

        for runner in runners:
            runner_id = runner.get('id')
            if not runner_id:
                continue

            if runner_id not in participants:
                participants[runner_id] = {
                    'name': runner.get('name'), 'run_count': 0, 'volunteer_count': 0,
                    'total_time_seconds': 0, 'best_time_seconds': float('inf'),
                    'age_group': None, 'best_time_date': None, 'best_time_race_number': None,
                    'best_time_location_slug': None, 'gold_medals': 0, 'silver_medals': 0, 'bronze_medals': 0,
                    'gender': runner.get('gender'), 'total_score': 0.0
                }

            stats = participants[runner_id]
            stats['name'] = runner.get('name')
            stats['run_count'] += 1
            stats['total_score'] += runner.get('score', 0.0)
            stats['total_time_seconds'] += runner.get('time_in_seconds', 0)
            if runner.get('time_in_seconds', float('inf')) < stats['best_time_seconds']:
                stats['best_time_seconds'] = runner['time_in_seconds']
                stats['best_time_date'] = race.get('race_date')
                stats['best_time_race_number'] = race.get('race_number')
                stats['best_time_location_slug'] = race.get('location_slug')
            
            if runner.get('age_group'):
                stats['age_group'] = runner.get('age_group')

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
                    'name': volunteer.get('name'), 'run_count': 0, 'volunteer_count': 0,
                    'total_time_seconds': 0, 'best_time_seconds': float('inf'),
                    'age_group': None, 'best_time_date': None, 'best_time_race_number': None,
                    'best_time_location_slug': None, 'gold_medals': 0, 'silver_medals': 0, 'bronze_medals': 0,
                    'gender': None, 'total_score': 0.0
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
        if stats['best_time_location_slug'] and stats['best_time_date']:
            stats['best_time_race_url'] = f"https://5verst.ru/{stats['best_time_location_slug']}/results/{stats['best_time_date']}/"
        else:
            stats['best_time_race_url'] = None
        leaderboard.append(stats)

    for stats in leaderboard:
        if stats['best_time_seconds'] == float('inf'):
            stats['best_time_seconds'] = None

    if ag_filter and ag_filter != 'all':
        leaderboard = [p for p in leaderboard if f"{p.get('gender')}{p.get('age_group')}" == ag_filter]

    leaderboard.sort(key=lambda x: (x['best_time_seconds'] is None, x['best_time_seconds']))

    page_size = 1000
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    paginated_leaderboard = leaderboard[start_index:end_index]
    total_pages = math.ceil(len(leaderboard) / page_size)

    return paginated_leaderboard, total_pages

@app.route('/')
def index():
    return render_template('leaderboard.html')

@app.route('/api/data')
def get_data():
    try:
        location_slug = request.args.get('location', default='korolev', type=str)
        page = request.args.get('page', default=1, type=int)
        ag_filter = request.args.get('ag', default=None, type=str)
        year_filter = request.args.get('year', default=None, type=int)
        season_filter = request.args.get('season', default=None, type=str)
        month_filter = request.args.get('month', default=None, type=int)
        race_number_filter = request.args.get('race_number', default=None, type=int)
        filter_mode = request.args.get('filter', default=None, type=str)

        # Special handling for the main 'all' locations page which has its own pagination logic
        if location_slug == 'all' and not any([year_filter, season_filter, month_filter, race_number_filter, ag_filter, filter_mode]):
            leaderboard_data, total_pages = get_all_locations_data(page, ag_filter)
            
            fastest_runner = None
            if leaderboard_data:
                fastest_runner = leaderboard_data[0]

            record_age_days = None
            if fastest_runner and fastest_runner.get('best_time_date'):
                try:
                    record_date_obj = datetime.strptime(fastest_runner['best_time_date'], '%d.%m.%Y')
                    record_age_days = (datetime.now() - record_date_obj).days
                except (ValueError, TypeError): pass

            response_data = {
                'leaderboard': leaderboard_data,
                'pages': total_pages,
                'metadata': {
                    'top_male': None,
                    'top_female': None,
                    'overall_fastest': {
                        'name': fastest_runner.get('name') if fastest_runner else None,
                        'time': fastest_runner.get('best_time_seconds') if fastest_runner else None,
                        'race_number': fastest_runner.get('best_time_race_number') if fastest_runner else None,
                        'age_days': record_age_days,
                        'location_slug': fastest_runner.get('best_time_location_slug') if fastest_runner else None,
                        'date': fastest_runner.get('best_time_date') if fastest_runner else None
                    }
                }
            }
            return jsonify(response_data)

        # Unified data fetching and filtering for all other cases, including filtered 'all'
        all_races = db_manager.load_all_results(location_slug=location_slug)
        races_to_process = all_races

        if race_number_filter:
            # When filtering by race number, we ignore other date filters
            races_to_process = [r for r in all_races if r.get('race_number') == race_number_filter]
        else:
            if filter_mode == 'current_season':
                now = datetime.now()
                year_filter = now.year
                season_filter = get_current_season(now.month)

            # Apply date filters
            temp_races = all_races
            if year_filter:
                if season_filter == 'зима':
                    previous_year = year_filter - 1
                    winter_races = []
                    for race in temp_races:
                        try:
                            race_date = datetime.strptime(race['race_date'], '%d.%m.%Y')
                            if (race_date.year == year_filter and race_date.month in [1, 2]) or \
                               (race_date.year == previous_year and race_date.month == 12):
                                winter_races.append(race)
                        except (ValueError, KeyError):
                            continue
                    temp_races = winter_races
                    if month_filter:
                         temp_races = [r for r in temp_races if datetime.strptime(r['race_date'], '%d.%m.%Y').month == month_filter]
                else:
                    temp_races = [r for r in temp_races if r.get('race_date') and datetime.strptime(r['race_date'], '%d.%m.%Y').year == year_filter]
                    if season_filter and season_filter in SEASONS:
                        season_months = SEASONS[season_filter]
                        temp_races = [r for r in temp_races if r.get('race_date') and datetime.strptime(r['race_date'], '%d.%m.%Y').month in season_months]
                    if month_filter:
                        temp_races = [r for r in temp_races if r.get('race_date') and datetime.strptime(r['race_date'], '%d.%m.%Y').month == month_filter]
            
            races_to_process = temp_races


        leaderboard_data = calculate_leaderboard(races_to_process, ag_filter)

        for stats in leaderboard_data:
            if stats['best_time_seconds'] == float('inf'):
                stats['best_time_seconds'] = None
        
        top_male, top_female, best_run_info, fastest_time = (None, None, None, float('inf'))

        for race in races_to_process:
            for runner in race.get('data', {}).get('runners', []):
                if (time := runner.get('time_in_seconds')) is not None and time < fastest_time:
                    fastest_time = time
                    best_run_info = {'name': runner.get('name'), 'time': time, 'race_number': race.get('race_number'), 'date': race.get('race_date'), 'location_slug': race.get('location_slug')}

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
            'pages': 1,  # Simplified pagination for filtered results
            'metadata': {
                'top_male': top_male,
                'top_female': top_female,
                'overall_fastest': {
                    'name': best_run_info.get('name') if best_run_info else None,
                    'time': best_run_info.get('time') if best_run_info else None,
                    'race_number': best_run_info.get('race_number') if best_run_info else None,
                    'age_days': record_age_days,
                    'location_slug': best_run_info.get('location_slug') if best_run_info else None,
                    'date': best_run_info.get('date') if best_run_info else None,
                }
            }
        }
        return jsonify(response_data)
    except Exception as e:
        print(f"Error in /api/data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "An internal server error occurred."}), 500


@app.route('/api/global-search')
def global_search():
    query = request.args.get('query', default='', type=str).upper()
    if not query:
        return jsonify([])

    all_races = db_manager.load_all_results(location_slug='all')
    matching_runners = {}
    for race in all_races:
        for runner in race.get('data', {}).get('runners', []):
            runner_id = runner.get('id')
            runner_name = runner.get('name', '').upper()
            if runner_id and (query in runner_name or query in str(runner_id)):
                if runner_id not in matching_runners:
                    matching_runners[runner_id] = {
                        'id': runner_id,
                        'name': runner.get('name')
                    }
    return jsonify(list(matching_runners.values()))


@app.route('/api/locations')
def get_locations():
    """API эндпоинт для получения списка всех локаций, у которых есть забеги."""
    locations = db_manager.load_locations_with_races()
    return jsonify(locations)

@app.route('/api/age-groups')
def get_age_groups():
    age_groups = db_manager.get_all_age_groups()
    return jsonify(age_groups)

@app.route('/api/years')
def get_available_years():
    location_slug = request.args.get('location', default='korolev', type=str)
    all_races = db_manager.load_all_results(location_slug=location_slug)
    years = {datetime.strptime(race['race_date'], '%d.%m.%Y').year for race in all_races if race.get('data') and race.get('race_date')}
    return jsonify(sorted(list(years), reverse=True))

@app.route('/api/racedates')
def get_available_races():
    location_slug = request.args.get('location', default='korolev', type=str)
    all_races = db_manager.load_all_results(location_slug=location_slug)
    races = [
        {"number": race['race_number'], "date": race['race_date']}
        for race in all_races if race.get('race_number') and race.get('race_number') > 0
    ]
    races.sort(key=lambda x: x['number'], reverse=True)
    return jsonify(races)

@app.route('/search')
def search():
    query = request.args.get('query', '')
    if not query:
        return render_template('search_results.html', results=[], query=query)

    search_results = db_manager.search_runners(query)
    return render_template('search_results.html', results=search_results, query=query)

if __name__ == '__main__':
    db_manager.init_db()
    app.run(debug=True, port=5001)