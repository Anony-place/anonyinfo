import sqlite3
import json
from datetime import datetime

DB_FILE = "anonyinfo_vault.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Results Table
    c.execute('''CREATE TABLE IF NOT EXISTS intel_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT,
                    type TEXT,
                    data TEXT,
                    timestamp DATETIME
                 )''')
    # Caching Table
    c.execute('''CREATE TABLE IF NOT EXISTS scan_cache (
                    target TEXT PRIMARY KEY,
                    data TEXT,
                    timestamp DATETIME
                 )''')
    conn.commit()
    conn.close()

def save_intel(target, ttype, data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO intel_results (target, type, data, timestamp) VALUES (?, ?, ?, ?)",
              (target, ttype, json.dumps(data), datetime.now()))
    # Also update cache
    c.execute("INSERT OR REPLACE INTO scan_cache (target, data, timestamp) VALUES (?, ?, ?)",
              (target, json.dumps(data), datetime.now()))
    conn.commit()
    conn.close()

def get_cached_intel(target):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT data FROM scan_cache WHERE target = ?", (target,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None

def get_history():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT target, type, timestamp FROM intel_results ORDER BY timestamp DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    return rows
