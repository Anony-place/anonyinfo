from __future__ import annotations

from flask import Flask, Response, jsonify
from flask_cors import CORS

from anonyinfo_core.dossier import CaseBuilder
from database import get_case, get_history, init_db

app = Flask(__name__)
CORS(app)
case_builder = CaseBuilder()
init_db()


@app.route("/")
def index():
    return """
    <html>
    <head>
        <title>AnonyInfo Case Dashboard</title>
        <style>
            body { background: #0f172a; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; padding: 24px; }
            .card { border: 1px solid #334155; background: #111827; padding: 16px; margin: 10px 0; border-radius: 12px; }
            a { color: #7dd3fc; text-decoration: none; }
            .meta { color: #94a3b8; }
        </style>
    </head>
    <body>
        <h1>AnonyInfo Investigation Dashboard</h1>
        <div id="results">Loading cases...</div>
        <script>
            fetch('/api/history').then(r => r.json()).then(data => {
                let html = '';
                data.forEach(item => {
                    html += `<div class="card">
                        <div><strong>${item.target_input}</strong></div>
                        <div class="meta">${item.case_id} | ${item.created_at}</div>
                        <div>Entities: ${item.summary.entity_count} | Findings: ${item.summary.finding_count}</div>
                        <div><a href="/api/case/${item.case_id}">JSON</a> | <a href="/case/${item.case_id}">HTML dossier</a></div>
                    </div>`;
                });
                document.getElementById('results').innerHTML = html || '<div class="card">No investigations yet.</div>';
            });
        </script>
    </body>
    </html>
    """


@app.route("/api/history")
def api_history():
    return jsonify(get_history())


@app.route("/api/case/<case_id>")
def api_case(case_id):
    case_record = get_case(case_id)
    if not case_record:
        return jsonify({})
    return jsonify(case_builder.build(case_record))


@app.route("/case/<case_id>")
def view_case(case_id):
    case_record = get_case(case_id)
    if not case_record:
        return Response("Case not found", status=404)
    return Response(case_builder.render_html(case_builder.build(case_record)), mimetype="text/html")


if __name__ == "__main__":
    app.run(port=5000)
