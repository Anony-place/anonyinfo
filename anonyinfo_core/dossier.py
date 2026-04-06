from __future__ import annotations

import json
from html import escape

from .models import CaseRecord


class CaseBuilder:
    def build(self, case_record: CaseRecord) -> dict:
        graph = self._graph_payload(case_record)
        timeline = sorted(
            [
                {
                    "type": "finding",
                    "timestamp": finding.discovered_at,
                    "title": finding.title,
                    "summary": finding.summary,
                    "module": finding.module,
                }
                for finding in case_record.findings
            ]
            + [
                {
                    "type": "note",
                    "timestamp": note["created_at"],
                    "title": "Case note",
                    "summary": note["note_text"],
                    "module": "notes",
                }
                for note in case_record.notes
            ],
            key=lambda item: item["timestamp"],
            reverse=True,
        )
        return {
            "case": {
                "id": case_record.case_id,
                "target_input": case_record.target_input,
                "created_at": case_record.created_at,
                "depth": case_record.depth,
                "modules": case_record.modules,
            },
            "executive_summary": self._executive_summary(case_record),
            "entities": [entity.to_dict() for entity in case_record.entities],
            "relationships": [item.to_dict() for item in case_record.relationships],
            "evidence_table": [item.to_dict() for item in case_record.findings],
            "artifacts": [item.to_dict() for item in case_record.artifacts],
            "best_leads": case_record.summary.get("best_leads", []),
            "graph": graph,
            "timeline": timeline,
            "notes": case_record.notes,
            "watch_targets": case_record.watch_targets,
            "evidence_sources": case_record.evidence_sources,
            "rerun_jobs": case_record.rerun_jobs,
            "raw_module_output": [
                {
                    "module": run.module,
                    "status": run.status,
                    "error": run.error,
                    "cached": run.cached,
                    "runtime_ms": run.runtime_ms,
                    "raw": run.raw,
                }
                for run in case_record.module_runs
            ],
            "summary": case_record.summary,
        }

    def render_console(self, dossier: dict, full: bool = False) -> str:
        lines = []
        case = dossier["case"]
        summary = dossier["summary"]
        lines.append(f"Case {case['id']} for {case['target_input']}")
        lines.append(
            f"Entities: {summary['entity_count']} | Findings: {summary['finding_count']} | "
            f"Modules OK/Failed: {summary['successful_modules']}/{summary['failed_modules']}"
        )
        lines.append(f"Investigation score: {summary.get('investigation_score', 0)}")
        if dossier["executive_summary"]:
            lines.append("")
            lines.extend(dossier["executive_summary"])
        if summary.get("module_health"):
            lines.append("")
            lines.append("Module health:")
            for module, stats in sorted(summary["module_health"].items()):
                lines.append(f"- {module}: ok {stats['success']}, fail {stats['error']}, cached {stats['cached']}")
        if dossier["best_leads"]:
            lines.append("")
            lines.append("Best leads:")
            for item in dossier["best_leads"][:5]:
                lines.append(f"- [{item['module']}] {item['title']} ({item['entity']}, conf {item['confidence']})")
                if item.get("why"):
                    lines.append(f"  why: {item['why']}")
        registration_findings = [item for item in dossier["evidence_table"] if item["category"] == "registration"]
        if registration_findings:
            lines.append("")
            lines.append("Registration intel:")
            for finding in registration_findings[:4]:
                lines.append(f"- {finding['summary']}")
        if dossier["graph"]["edges"]:
            lines.append("")
            lines.append(f"Graph edges: {len(dossier['graph']['edges'])}")
        if dossier["notes"]:
            lines.append("")
            lines.append("Notes:")
            for note in dossier["notes"][:5]:
                lines.append(f"- {note['created_at']}: {note['note_text']}")
        if full:
            lines.append("")
            lines.append("Entities:")
            for entity in dossier["entities"]:
                lines.append(f"- {entity['entity_type']}: {entity['value']} ({entity['source']})")
            lines.append("")
            lines.append("Evidence:")
            for finding in dossier["evidence_table"]:
                lines.append(f"- {finding['module']}: {finding['title']} -> {finding['summary']}")
        return "\n".join(lines)

    def render_html(self, dossier: dict) -> str:
        lead_items = "".join(
            f"<li><strong>{escape(item['title'])}</strong> [{escape(item['module'])}] - {escape(item['summary'])}</li>"
            for item in dossier["best_leads"]
        )
        entity_rows = "".join(
            f"<tr><td>{escape(item['entity_type'])}</td><td>{escape(item['value'])}</td><td>{escape(item['source'])}</td></tr>"
            for item in dossier["entities"]
        )
        finding_rows = "".join(
            f"<tr data-module=\"{escape(item['module'])}\" data-category=\"{escape(item['category'])}\" data-confidence=\"{item['confidence']}\" data-entity=\"{escape(item['entity_type'])}\">"
            f"<td>{escape(item['module'])}</td><td>{escape(item['title'])}</td><td>{escape(item['summary'])}</td><td>{item['confidence']}</td><td>{escape(item.get('why') or '')}</td></tr>"
            for item in dossier["evidence_table"]
        )
        module_health = "".join(
            f"<tr><td>{escape(module)}</td><td>{stats['success']}</td><td>{stats['error']}</td><td>{stats['cached']}</td></tr>"
            for module, stats in sorted(dossier["summary"].get("module_health", {}).items())
        )
        source_rows = "".join(
            f"<tr><td>{escape(item.get('module') or '')}</td><td>{escape(item.get('source_label') or '')}</td><td>{escape(item.get('source_url') or '')}</td><td>{item.get('reputation', '')}</td></tr>"
            for item in dossier["evidence_sources"]
        )
        note_rows = "".join(
            f"<li>{escape(item['created_at'])}: {escape(item['note_text'])}</li>" for item in dossier["notes"]
        )
        timeline_rows = "".join(
            f"<tr><td>{escape(item['timestamp'])}</td><td>{escape(item['module'])}</td><td>{escape(item['title'])}</td><td>{escape(item['summary'])}</td></tr>"
            for item in dossier["timeline"][:25]
        )
        mermaid = escape(self.render_graph(dossier["graph"]))
        raw_json = escape(json.dumps(dossier["raw_module_output"], indent=2))
        summary = dossier["summary"]
        return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>AnonyInfo Dossier</title>
  <style>
    body {{ font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 24px; }}
    .panel {{ background: #111827; border: 1px solid #334155; border-radius: 16px; padding: 20px; margin-bottom: 20px; }}
    h1, h2 {{ margin-top: 0; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #334155; text-align: left; padding: 10px; vertical-align: top; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
    .stat {{ background: #1e293b; border-radius: 12px; padding: 12px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
    .filters {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }}
    input, select {{ background: #0f172a; color: #e2e8f0; border: 1px solid #475569; border-radius: 10px; padding: 8px; }}
  </style>
</head>
<body>
  <div class="panel">
    <h1>AnonyInfo Case Dossier</h1>
    <p>Case <strong>{escape(dossier['case']['id'])}</strong> for <strong>{escape(dossier['case']['target_input'])}</strong></p>
    <div class="stats">
      <div class="stat">Entities: {summary['entity_count']}</div>
      <div class="stat">Findings: {summary['finding_count']}</div>
      <div class="stat">Avg confidence: {summary['average_confidence']}</div>
      <div class="stat">Modules failed: {summary['failed_modules']}</div>
      <div class="stat">Investigation score: {summary.get('investigation_score', 0)}</div>
      <div class="stat">Corroborated findings: {summary.get('corroborated_findings', 0)}</div>
    </div>
  </div>
  <div class="panel">
    <h2>Executive Summary</h2>
    <ul>{''.join(f'<li>{escape(line)}</li>' for line in dossier['executive_summary'])}</ul>
  </div>
  <div class="panel">
    <h2>Best Leads</h2>
    <ul>{lead_items}</ul>
  </div>
  <div class="panel">
    <h2>Graph Snapshot</h2>
    <div>Nodes: {len(dossier['graph']['nodes'])} | Edges: {len(dossier['graph']['edges'])}</div>
  </div>
  <div class="panel">
    <h2>Entities</h2>
    <table><thead><tr><th>Type</th><th>Value</th><th>Source</th></tr></thead><tbody>{entity_rows}</tbody></table>
  </div>
  <div class="panel">
    <h2>Evidence</h2>
    <div class="filters">
      <input id="moduleFilter" placeholder="Filter module">
      <input id="entityFilter" placeholder="Filter entity type">
      <input id="confidenceFilter" type="number" min="0" max="1" step="0.05" placeholder="Min confidence">
    </div>
    <table id="evidenceTable"><thead><tr><th>Module</th><th>Title</th><th>Summary</th><th>Confidence</th><th>Why</th></tr></thead><tbody>{finding_rows}</tbody></table>
  </div>
  <div class="panel">
    <h2>Module Health</h2>
    <table><thead><tr><th>Module</th><th>Success</th><th>Errors</th><th>Cached</th></tr></thead><tbody>{module_health}</tbody></table>
  </div>
  <div class="panel">
    <h2>Evidence Sources</h2>
    <table><thead><tr><th>Module</th><th>Source</th><th>URL</th><th>Reputation</th></tr></thead><tbody>{source_rows}</tbody></table>
  </div>
  <div class="panel">
    <h2>Timeline</h2>
    <table><thead><tr><th>Timestamp</th><th>Module</th><th>Title</th><th>Summary</th></tr></thead><tbody>{timeline_rows}</tbody></table>
  </div>
  <div class="panel">
    <h2>Notes</h2>
    <ul>{note_rows or '<li>No notes yet.</li>'}</ul>
  </div>
  <div class="panel">
    <h2>Graph (Mermaid)</h2>
    <pre>{mermaid}</pre>
  </div>
  <div class="panel">
    <h2>Raw Module Output</h2>
    <pre>{raw_json}</pre>
  </div>
  <script>
    const applyFilters = () => {{
      const moduleValue = document.getElementById('moduleFilter').value.toLowerCase();
      const entityValue = document.getElementById('entityFilter').value.toLowerCase();
      const confidenceValue = parseFloat(document.getElementById('confidenceFilter').value || '0');
      document.querySelectorAll('#evidenceTable tbody tr').forEach((row) => {{
        const matchesModule = !moduleValue || row.dataset.module.toLowerCase().includes(moduleValue);
        const matchesEntity = !entityValue || row.dataset.entity.toLowerCase().includes(entityValue);
        const matchesConfidence = parseFloat(row.dataset.confidence || '0') >= confidenceValue;
        row.style.display = matchesModule && matchesEntity && matchesConfidence ? '' : 'none';
      }});
    }};
    document.getElementById('moduleFilter').addEventListener('input', applyFilters);
    document.getElementById('entityFilter').addEventListener('input', applyFilters);
    document.getElementById('confidenceFilter').addEventListener('input', applyFilters);
  </script>
</body>
</html>"""

    @staticmethod
    def _executive_summary(case_record: CaseRecord) -> list[str]:
        summary = case_record.summary
        lines = [
            f"Analyzed {summary['entity_count']} entities from one seed input across {len(case_record.modules)} modules.",
            f"Collected {summary['finding_count']} findings with average confidence {summary['average_confidence']}.",
        ]
        if summary["failed_modules"]:
            lines.append(f"{summary['failed_modules']} module runs failed but the investigation completed with partial results.")
        categories = summary.get("category_counts", {})
        if categories:
            category_line = ", ".join(f"{key}: {value}" for key, value in sorted(categories.items()))
            lines.append(f"Finding categories: {category_line}.")
        entity_types = summary.get("entity_type_counts", {})
        if entity_types:
            entity_line = ", ".join(f"{key}: {value}" for key, value in sorted(entity_types.items()))
            lines.append(f"Entity types: {entity_line}.")
        if summary.get("source_counts"):
            source_line = ", ".join(f"{key}: {value}" for key, value in sorted(summary["source_counts"].items())[:5])
            lines.append(f"Top sources: {source_line}.")
        return lines

    @staticmethod
    def _graph_payload(case_record: CaseRecord) -> dict:
        nodes = [
            {"id": entity.entity_id, "label": entity.value, "type": entity.entity_type}
            for entity in case_record.entities
        ]
        edges = [
            {
                "from": rel.from_entity_id,
                "to": rel.to_entity_id,
                "type": rel.rel_type,
                "source": rel.source,
                "confidence": rel.confidence,
            }
            for rel in case_record.relationships
        ]
        return {"nodes": nodes, "edges": edges}

    def render_graph(self, graph: dict) -> str:
        lines = ["graph TD"]
        for node in graph.get("nodes", []):
            safe_label = node["label"].replace('"', "'")
            lines.append(f'  {node["id"]}["{safe_label}\\n({node["type"]})"]')
        for edge in graph.get("edges", []):
            lines.append(f'  {edge["from"]} -- "{edge["type"]}" --> {edge["to"]}')
        return "\n".join(lines)
