from __future__ import annotations

from collections import Counter

from .models import Entity, Finding


class ResultScorer:
    def summarize(self, entities: list[Entity], findings: list[Finding], module_runs: list[dict]) -> dict:
        category_counts = Counter(finding.category for finding in findings)
        entity_type_counts = Counter(entity.entity_type for entity in entities)
        source_counts = Counter(finding.source_label or finding.module for finding in findings)
        average_confidence = round(
            sum(finding.confidence for finding in findings) / len(findings), 2
        ) if findings else 0.0
        successful_modules = sum(1 for run in module_runs if run.get("status") == "success")
        failed_modules = sum(1 for run in module_runs if run.get("status") == "error")
        module_health = self._module_health(module_runs)
        investigation_score = self._investigation_score(
            len(entities), len(findings), average_confidence, failed_modules
        )
        corroborated_findings = sum(1 for finding in findings if finding.confidence >= 0.8)
        return {
            "entity_count": len(entities),
            "entity_type_counts": dict(entity_type_counts),
            "finding_count": len(findings),
            "category_counts": dict(category_counts),
            "source_counts": dict(source_counts),
            "average_confidence": average_confidence,
            "successful_modules": successful_modules,
            "failed_modules": failed_modules,
            "module_health": module_health,
            "investigation_score": investigation_score,
            "corroborated_findings": corroborated_findings,
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
                "why": item.why,
            }
            for item in prioritized[:8]
        ]

    def compare_cases(self, left_case, right_case) -> dict:
        left_entities = {f"{entity.entity_type}:{entity.value}" for entity in left_case.entities}
        right_entities = {f"{entity.entity_type}:{entity.value}" for entity in right_case.entities}
        left_modules = set(left_case.modules)
        right_modules = set(right_case.modules)
        left_findings = {finding.title for finding in left_case.findings}
        right_findings = {finding.title for finding in right_case.findings}
        return {
            "left_case_id": left_case.case_id,
            "right_case_id": right_case.case_id,
            "shared_entities": sorted(left_entities & right_entities),
            "left_only_entities": sorted(left_entities - right_entities),
            "right_only_entities": sorted(right_entities - left_entities),
            "shared_modules": sorted(left_modules & right_modules),
            "left_only_modules": sorted(left_modules - right_modules),
            "right_only_modules": sorted(right_modules - left_modules),
            "shared_finding_titles": sorted(left_findings & right_findings),
            "left_score": self._case_score(left_case),
            "right_score": self._case_score(right_case),
        }

    @staticmethod
    def _severity_weight(severity: str) -> int:
        weights = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        return weights.get(severity, 0)

    @staticmethod
    def _module_health(module_runs: list[dict]) -> dict:
        summary = {}
        for run in module_runs:
            item = summary.setdefault(run.get("module", "unknown"), {"success": 0, "error": 0, "cached": 0})
            if run.get("status") == "success":
                item["success"] += 1
            else:
                item["error"] += 1
            if run.get("cached"):
                item["cached"] += 1
        return summary

    @staticmethod
    def _investigation_score(entity_count: int, finding_count: int, average_confidence: float, failed_modules: int) -> int:
        score = int(entity_count * 8 + finding_count * 3 + average_confidence * 35 - failed_modules * 10)
        return max(score, 0)

    def _case_score(self, case_record) -> int:
        summary = case_record.summary or {}
        if "investigation_score" in summary:
            return summary["investigation_score"]
        return self._investigation_score(
            summary.get("entity_count", len(getattr(case_record, "entities", []))),
            summary.get("finding_count", len(getattr(case_record, "findings", []))),
            summary.get("average_confidence", 0.0),
            summary.get("failed_modules", 0),
        )
