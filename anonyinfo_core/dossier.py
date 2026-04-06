from __future__ import annotations

import json
from html import escape

from .models import CaseRecord


class CaseBuilder:
    def build(self, case_record: CaseRecord) -> dict:
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
        if dossier["executive_summary"]:
            lines.append("")
            lines.extend(dossier["executive_summary"])
        if dossier["best_leads"]:
            lines.append("")
            lines.append("Best leads:")
            for item in dossier["best_leads"][:5]:
                lines.append(f"- [{item['module']}] {item['title']} ({item['entity']}, conf {item['confidence']})")
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
            f"<tr><td>{escape(item['module'])}</td><td>{escape(item['title'])}</td><td>{escape(item['summary'])}</td><td>{item['confidence']}</td></tr>"
            for item in dossier["evidence_table"]
        )
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
    <h2>Entities</h2>
    <table><thead><tr><th>Type</th><th>Value</th><th>Source</th></tr></thead><tbody>{entity_rows}</tbody></table>
  </div>
  <div class="panel">
    <h2>Evidence</h2>
    <table><thead><tr><th>Module</th><th>Title</th><th>Summary</th><th>Confidence</th></tr></thead><tbody>{finding_rows}</tbody></table>
  </div>
  <div class="panel">
    <h2>Raw Module Output</h2>
    <pre>{raw_json}</pre>
  </div>
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
        return lines
