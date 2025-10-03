import sqlite3
import json

DB_NAME = 'race_data.db'

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Create race_results table with composite primary key
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS race_results (
            race_date TEXT NOT NULL,
            location_slug TEXT NOT NULL,
            data TEXT,
            race_number INTEGER,
            PRIMARY KEY (race_date, location_slug)
        )
    ''')
    # Create locations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            slug TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_race_number ON race_results (race_number)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_location ON race_results (location_slug)')
    conn.commit()
    conn.close()

def save_locations(db_path, locations):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.executemany(
        'INSERT OR REPLACE INTO locations (slug, name, url) VALUES (:slug, :name, :url)',
        locations
    )
    conn.commit()
    conn.close()

def load_locations(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT slug, name, url FROM locations ORDER BY name')
    rows = cursor.fetchall()
    conn.close()
    return [{'slug': r[0], 'name': r[1], 'url': r[2]} for r in rows]

def load_locations_with_races(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT T1.slug, T1.name, T1.url
        FROM locations T1
        INNER JOIN race_results T2 ON T1.slug = T2.location_slug
        ORDER BY T1.name
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [{'slug': r[0], 'name': r[1], 'url': r[2]} for r in rows]

def save_results(db_path, race_date, location_slug, race_number, results):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    results_json = json.dumps(results)
    try:
        cursor.execute(
            'INSERT INTO race_results (race_date, location_slug, race_number, data) VALUES (?, ?, ?, ?)',
            (race_date, location_slug, race_number, results_json)
        )
    except sqlite3.IntegrityError:
        cursor.execute(
            'UPDATE race_results SET race_number = ?, data = ? WHERE race_date = ? AND location_slug = ?',
            (race_number, results_json, race_date, location_slug)
        )
    conn.commit()
    conn.close()

def load_results(db_path, race_date, location_slug):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT data FROM race_results WHERE race_date = ? AND location_slug = ?', (race_date, location_slug))
    row = cursor.fetchone()
    conn.close()
    if row and row[0] is not None:
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None
    return None

def load_all_results(db_path, location_slug=None):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    if location_slug:
        cursor.execute('SELECT race_date, race_number, data, location_slug FROM race_results WHERE location_slug = ? ORDER BY race_date DESC', (location_slug,))
    else:
        cursor.execute('SELECT race_date, race_number, data, location_slug FROM race_results ORDER BY race_date DESC')
    
    rows = cursor.fetchall()
    conn.close()
    results = []
    for row in rows:
        if row[2] is None:
            continue
        try:
            data = json.loads(row[2])
            results.append({
                'race_date': row[0],
                'race_number': row[1],
                'data': data,
                'location_slug': row[3]
            })
        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON for race_date {row[0]}")
            continue
    return results