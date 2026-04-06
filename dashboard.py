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
            .grid { display: grid; grid-template-columns: 1.1fr 1.4fr; gap: 20px; align-items: start; }
            .viewer { border: 1px solid #334155; background: #111827; padding: 16px; border-radius: 12px; position: sticky; top: 24px; }
            pre { white-space: pre-wrap; word-break: break-word; }
            table { width: 100%; border-collapse: collapse; margin-top: 12px; }
            td, th { border-bottom: 1px solid #334155; padding: 8px; text-align: left; }
            input, select, button, textarea { background: #0f172a; color: #e2e8f0; border: 1px solid #334155; border-radius: 8px; padding: 8px; }
            .controls { display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0; }
        </style>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            window.__renderMermaid = async function(source) {
                mermaid.initialize({ startOnLoad: false, theme: 'dark' });
                const el = document.getElementById('graph');
                el.innerHTML = source;
                await mermaid.run({ nodes: [el] });
            };
        </script>
    </head>
    <body>
        <h1>AnonyInfo Investigation Dashboard</h1>
        <div class="grid">
          <div id="results">Loading cases...</div>
          <div class="viewer">
            <h2>Case Viewer</h2>
            <div id="summary" class="meta">Select a case to inspect graph and summary.</div>
            <div class="controls">
              <input id="filterModule" placeholder="Filter module">
              <select id="filterEntityType"><option value="">All entity types</option></select>
              <input id="filterConfidence" type="number" min="0" max="1" step="0.05" placeholder="Min confidence">
            </div>
            <div id="graph"></div>
            <pre id="leads"></pre>
            <h3>Evidence</h3>
            <table id="evidenceTable"><thead><tr><th>Module</th><th>Title</th><th>Confidence</th></tr></thead><tbody></tbody></table>
            <h3>Notes</h3>
            <textarea id="noteText" rows="3" placeholder="Add investigator note"></textarea>
            <div class="controls">
              <button onclick="addNote()">Save note</button>
            </div>
            <ul id="notesList"></ul>
          </div>
        </div>
        <script>
            let currentCaseId = null;
            let currentEvidence = [];
            function renderEvidence() {
                const moduleValue = document.getElementById('filterModule').value.toLowerCase();
                const entityValue = document.getElementById('filterEntityType').value.toLowerCase();
                const minConfidence = parseFloat(document.getElementById('filterConfidence').value || '0');
                const rows = currentEvidence.filter(item => {
                    const moduleOk = !moduleValue || item.module.toLowerCase().includes(moduleValue);
                    const entityOk = !entityValue || item.entity_type.toLowerCase() === entityValue;
                    const confidenceOk = parseFloat(item.confidence || 0) >= minConfidence;
                    return moduleOk && entityOk && confidenceOk;
                }).map(item => `<tr><td>${item.module}</td><td title="${(item.why || '').replace(/"/g, '&quot;')}">${item.title}</td><td>${item.confidence}</td></tr>`).join('');
                document.querySelector('#evidenceTable tbody').innerHTML = rows || '<tr><td colspan="3">No matching evidence.</td></tr>';
            }
            async function showCase(caseId) {
                currentCaseId = caseId;
                const data = await fetch(`/api/case/${caseId}`).then(r => r.json());
                document.getElementById('summary').innerHTML =
                  `<strong>${data.case.target_input}</strong><br>${data.case.id}<br>Entities: ${data.summary.entity_count} | Findings: ${data.summary.finding_count} | Score: ${data.summary.investigation_score || 0}<br>Watch matches: ${data.summary.watch_match_count || 0}`;
                const graphSource = data.graph ? `graph TD\n${data.graph.nodes.map(n => `  ${n.id}["${n.label.replace(/"/g, "'")} (${n.type})"]`).join('\n')}\n${data.graph.edges.map(e => `  ${e.from} -- "${e.type}" --> ${e.to}`).join('\n')}` : 'graph TD';
                window.__renderMermaid(graphSource);
                document.getElementById('leads').textContent = (data.best_leads || []).slice(0, 8).map(x => `- [${x.module}] ${x.title}${x.why ? `\n  why: ${x.why}` : ''}`).join('\n');
                currentEvidence = data.evidence_table || [];
                document.getElementById('filterEntityType').innerHTML = '<option value="">All entity types</option>' + [...new Set(currentEvidence.map(x => x.entity_type))].map(x => `<option value="${x}">${x}</option>`).join('');
                renderEvidence();
                document.getElementById('notesList').innerHTML = (data.notes || []).map(x => `<li>${x.created_at}: ${x.note_text}</li>`).join('') || '<li>No notes yet.</li>';
            }
            async function addNote() {
                if (!currentCaseId) return;
                const text = document.getElementById('noteText').value.trim();
                if (!text) return;
                await fetch(`/api/case/${currentCaseId}/notes`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ note_text: text })
                });
                document.getElementById('noteText').value = '';
                showCase(currentCaseId);
            }
            document.getElementById('filterModule').addEventListener('input', renderEvidence);
            document.getElementById('filterEntityType').addEventListener('change', renderEvidence);
            document.getElementById('filterConfidence').addEventListener('input', renderEvidence);
            fetch('/api/history').then(r => r.json()).then(data => {
                let html = '';
                data.forEach(item => {
                    html += `<div class="card">
                        <div><strong>${item.target_input}</strong></div>
                        <div class="meta">${item.case_id} | ${item.created_at}</div>
                        <div>Entities: ${item.summary.entity_count} | Findings: ${item.summary.finding_count} | Score: ${item.summary.investigation_score || 0}</div>
                        <div><a href="#" onclick="showCase('${item.case_id}'); return false;">Inspect</a> | <a href="/api/case/${item.case_id}">JSON</a> | <a href="/case/${item.case_id}">HTML dossier</a></div>
                    </div>`;
                });
                document.getElementById('results').innerHTML = html || '<div class="card">No investigations yet.</div>';
                if (data.length) { showCase(data[0].case_id); }
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


@app.route("/api/case/<case_id>/notes", methods=["POST"])
def api_case_note(case_id):
    from flask import request
    from database import add_case_note

    payload = request.get_json(force=True, silent=True) or {}
    note_text = (payload.get("note_text") or "").strip()
    if not note_text:
        return jsonify({"error": "note_text required"}), 400
    return jsonify(add_case_note(case_id, note_text))


@app.route("/case/<case_id>")
def view_case(case_id):
    case_record = get_case(case_id)
    if not case_record:
        return Response("Case not found", status=404)
    return Response(case_builder.render_html(case_builder.build(case_record)), mimetype="text/html")


if __name__ == "__main__":
    app.run(port=5000)
