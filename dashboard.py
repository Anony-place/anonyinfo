from flask import Flask, jsonify, render_template
from flask_cors import CORS
from database import get_history, DB_FILE
import sqlite3
import json

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return """
    <html>
    <head>
        <title>AnonyInfo Intelligence Dashboard</title>
        <style>
            body { background: #0d0d0d; color: #00ff41; font-family: monospace; padding: 20px; }
            .card { border: 1px solid #00ff41; padding: 15px; margin: 10px; border-radius: 5px; }
            h1 { border-bottom: 2px solid #00ff41; }
            .target { color: #fff; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>ANONYINFO v7.0 :: MISSION DASHBOARD</h1>
        <div id="results">Loading Intelligence from Vault...</div>
        <script>
            fetch('/api/history').then(r => r.json()).then(data => {
                let html = '';
                data.forEach(item => {
                    html += `<div class="card">
                        [${item[2]}] <span class="target">${item[0]}</span> (${item[1]})
                    </div>`;
                });
                document.getElementById('results').innerHTML = html;
            });
        </script>
    </body>
    </html>
    """

@app.route('/api/history')
def api_history():
    return jsonify(get_history())

@app.route('/api/intel/<target>')
def api_intel(target):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT data FROM intel_results WHERE target = ? ORDER BY timestamp DESC LIMIT 1", (target,))
    row = c.fetchone()
    conn.close()
    return jsonify(json.loads(row[0]) if row else {})

if __name__ == '__main__':
    app.run(port=5000)
