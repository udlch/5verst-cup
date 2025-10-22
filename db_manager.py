import os
import requests
import json
from dotenv import load_dotenv
import time

load_dotenv()

# Get Cloudflare credentials from environment variables
ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
DB_ID = os.getenv("CLOUDFLARE_DB_ID")

CLOUDFLARE_API_BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DB_ID}"

import time

def _execute_batch(statements):
    """Executes a batch of SQL statements by sending them one by one with retries."""
    if not all([ACCOUNT_ID, API_TOKEN, DB_ID]):
        raise ValueError("Cloudflare D1 environment variables are not set.")

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }

    results = []
    for stmt in statements:
        sql, params = None, []
        if isinstance(stmt, str):
            sql = stmt
        elif isinstance(stmt, dict) and "sql" in stmt:
            sql = stmt["sql"]
            params = stmt.get("params", [])

        if not sql:
            continue

        data = {"sql": sql, "params": params}
        
        for attempt in range(3): # Retry up to 3 times
            try:
                response = requests.post(f"{CLOUDFLARE_API_BASE_URL}/query", headers=headers, json=data)
                response.raise_for_status()
                results.append(response.json())
                break # Success, exit retry loop
            except requests.exceptions.RequestException as e:
                if attempt < 2: # Not the last attempt
                    print(f"  - Network error during batch, retrying in {attempt + 1}s...")
                    time.sleep(attempt + 1)
                    continue
                else:
                    print(f"Error executing statement on Cloudflare D1 after 3 attempts: {sql}")
                    if e.response is not None:
                        print(f"Response status: {e.response.status_code}")
                        print(f"Response text: {e.response.text}")
                    raise
    return results

def _execute_query(statement, params=None):
    """Executes a single SELECT query with retries and returns results."""
    if not all([ACCOUNT_ID, API_TOKEN, DB_ID]):
        raise ValueError("Cloudflare D1 environment variables are not set.")

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {"sql": statement, "params": params or []}

    for attempt in range(3): # Retry up to 3 times
        try:
            response = requests.post(f"{CLOUDFLARE_API_BASE_URL}/query", headers=headers, json=data)
            response.raise_for_status()
            result = response.json().get('result', [])
            if result:
                return result[0].get('results', [])
            return [] # Success, but no results
        except requests.exceptions.RequestException as e:
            if attempt < 2: # Not the last attempt
                print(f"  - Network error during query, retrying in {attempt + 1}s...")
                time.sleep(attempt + 1)
                continue
            else:
                print(f"Error executing query on Cloudflare D1 after 3 attempts: {statement}")
                if e.response is not None:
                    print(f"Response status: {e.response.status_code}")
                    print(f"Response text: {e.response.text}")
                raise

def init_db():
    statements = [
        '''
        CREATE TABLE IF NOT EXISTS race_results (
            race_date TEXT NOT NULL,
            location_slug TEXT NOT NULL,
            data TEXT,
            race_number INTEGER,
            PRIMARY KEY (race_date, location_slug)
        );
        ''',
        '''
        CREATE TABLE IF NOT EXISTS locations (
            slug TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL
        );
        ''',
        'CREATE INDEX IF NOT EXISTS idx_race_number ON race_results (race_number);',
        'CREATE INDEX IF NOT EXISTS idx_location ON race_results (location_slug);'
    ]
    _execute_batch(statements)

def save_locations(locations):
    statements = [
        {"sql": "INSERT OR REPLACE INTO locations (slug, name, url) VALUES (?, ?, ?)", "params": [loc['slug'], loc['name'], loc['url']]}
        for loc in locations
    ]
    if statements:
        _execute_batch(statements)

def load_locations():
    rows = _execute_query('SELECT slug, name, url FROM locations ORDER BY name')
    return rows if rows else []

def load_locations_with_races():
    query = '''
        SELECT DISTINCT T1.slug, T1.name, T1.url
        FROM locations T1
        INNER JOIN race_results T2 ON T1.slug = T2.location_slug
        ORDER BY T1.name
    '''
    rows = _execute_query(query)
    return rows if rows else []

def save_results(race_date, location_slug, race_number, results):
    results_json = json.dumps(results)
    # D1 doesn't support INSERT ... ON CONFLICT DO UPDATE, so we do a two-step
    # First, try to fetch existing data
    existing = _execute_query("SELECT 1 FROM race_results WHERE race_date = ? AND location_slug = ?", [race_date, location_slug])
    
    if existing:
        statement = {
            "sql": 'UPDATE race_results SET race_number = ?, data = ? WHERE race_date = ? AND location_slug = ?',
            "params": [race_number, results_json, race_date, location_slug]
        }
    else:
        statement = {
            "sql": 'INSERT INTO race_results (race_date, location_slug, race_number, data) VALUES (?, ?, ?, ?)',
            "params": [race_date, location_slug, race_number, results_json]
        }
    _execute_batch([statement])


def load_results(race_date, location_slug):
    rows = _execute_query('SELECT data FROM race_results WHERE race_date = ? AND location_slug = ?', [race_date, location_slug])
    if rows and rows[0]['data'] is not None:
        try:
            return json.loads(rows[0]['data'])
        except json.JSONDecodeError:
            return None
    return None

def load_all_results(location_slug=None, limit=None, offset=None):
    query_params = []
    sql_query = 'SELECT race_date, race_number, data, location_slug FROM race_results'

    if location_slug and location_slug != 'all':
        sql_query += ' WHERE location_slug = ?'
        query_params.append(location_slug)
    
    sql_query += ' ORDER BY race_date DESC'

    if limit is not None and offset is not None:
        sql_query += ' LIMIT ? OFFSET ?'
        query_params.append(limit)
        query_params.append(offset)

    rows = _execute_query(sql_query, query_params)

    results = []
    if not rows:
        return results

    for row in rows:
        if row.get('data') is None:
            continue
        try:
            data = json.loads(row['data'])
            results.append({
                'race_date': row.get('race_date'),
                'race_number': row.get('race_number'),
                'data': data,
                'location_slug': row.get('location_slug')
            })
        except (json.JSONDecodeError, TypeError) as e:
            continue
    return results

def get_total_race_results_count(location_slug=None):
    query_params = []
    sql_query = 'SELECT COUNT(*) FROM race_results'
    if location_slug and location_slug != 'all':
        sql_query += ' WHERE location_slug = ?'
        query_params.append(location_slug)
    
    rows = _execute_query(sql_query, query_params)
    if rows and len(rows) > 0:
        return rows[0]['COUNT(*)']
    return 0

def get_all_age_groups(location_slug=None):
    if location_slug and location_slug != 'all':
        rows = _execute_query('SELECT data FROM race_results WHERE location_slug = ?', [location_slug])
    else:
        rows = _execute_query('SELECT data FROM race_results')
    age_groups = set()
    if not rows:
        return []
        
    for row in rows:
        if row['data'] is None:
            continue
        try:
            data = json.loads(row['data'])
            for runner in data.get('runners', []):
                if runner.get('age_group') and runner.get('gender'):
                    age_groups.add(f"{runner['gender']}{runner['age_group']}")
        except json.JSONDecodeError:
            continue
    return sorted(list(age_groups))

def search_runners(query):
    rows = _execute_query('SELECT data FROM race_results')
    results = []
    seen_runners = set()
    if not rows:
        return []

    for row in rows:
        if row['data'] is None:
            continue
        try:
            data = json.loads(row['data'])
            for runner in data.get('runners', []):
                runner_id = str(runner.get('id'))
                runner_name = runner.get('name', '').lower()
                
                if runner_id and (query.lower() in runner_id or query.lower() in runner_name):
                    if runner_id not in seen_runners:
                        results.append(runner)
                        seen_runners.add(runner_id)
        except json.JSONDecodeError:
            continue
            
    return results
