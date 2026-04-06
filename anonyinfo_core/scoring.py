from __future__ import annotations

from collections import Counter

from .models import Entity, Finding


class ResultScorer:
    def summarize(self, entities: list[Entity], findings: list[Finding], module_runs: list[dict]) -> dict:
        category_counts = Counter(finding.category for finding in findings)
        average_confidence = round(
            sum(finding.confidence for finding in findings) / len(findings), 2
        ) if findings else 0.0
        successful_modules = sum(1 for run in module_runs if run.get("status") == "success")
        failed_modules = sum(1 for run in module_runs if run.get("status") == "error")
        return {
            "entity_count": len(entities),
            "finding_count": len(findings),
            "category_counts": dict(category_counts),
            "average_confidence": average_confidence,
            "successful_modules": successful_modules,
            "failed_modules": failed_modules,
        }

    def prioritize_leads(self, findings: list[Finding]) -> list[dict]:
        prioritized = sorted(
            findings,
            key=lambda item: (item.confidence, self._severity_weight(item.severity)),
            reverse=True,
        )
        return [
            {
                "title": item.title,
                "summary": item.summary,
                "module": item.module,
                "entity": f"{item.entity_type}:{item.entity_value}",
                "confidence": item.confidence,
                "severity": item.severity,
            }
            for item in prioritized[:8]
        ]

    @staticmethod
    def _severity_weight(severity: str) -> int:
        weights = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        return weights.get(severity, 0)
