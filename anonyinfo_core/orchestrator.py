from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Iterable, List
from uuid import uuid4

from .dossier import CaseBuilder
from .models import Artifact, CaseRecord, Entity, Finding, ModuleResult, Relationship
from .modules import ModuleRegistry
from .normalizer import EntityResolver, InputNormalizer
from .scoring import ResultScorer


class InvestigationOrchestrator:
    def __init__(self, registry: ModuleRegistry, storage) -> None:
        self.registry = registry
        self.storage = storage
        self.normalizer = InputNormalizer()
        self.resolver = EntityResolver()
        self.scorer = ResultScorer()
        self.case_builder = CaseBuilder()

    async def investigate(
        self,
        target_input: str,
        depth: str = "standard",
        selected_modules: Iterable[str] | None = None,
        use_cache: bool = True,
    ) -> tuple[CaseRecord, dict]:
        seed_entities = self.normalizer.normalize(target_input)
        entities, base_relationships = self.resolver.resolve(seed_entities)
        max_entities = 40 if depth == "standard" else 120

        all_entities = {entity.key(): entity for entity in entities}
        entity_queue = list(all_entities.values())
        findings: List[Finding] = []
        relationships: List[Relationship] = list(base_relationships)
        artifacts: List[Artifact] = []
        module_runs: List[ModuleResult] = []
        seen_relationships = {item.dedupe_key() for item in relationships}
        processed_pairs = set()

        index = 0
        while index < len(entity_queue):
            entity = entity_queue[index]
            index += 1
            applicable = self.registry.applicable(entity, selected_modules)
            tasks = [
                asyncio.create_task(self._run_module(module, entity, depth, use_cache))
                for module in applicable
                if (entity.key(), module.name) not in processed_pairs
            ]
            for module in applicable:
                processed_pairs.add((entity.key(), module.name))
            if not tasks:
                continue
            results = await asyncio.gather(*tasks)
            for module_result in results:
                module_runs.append(module_result)
                for new_entity in module_result.entities:
                    existing = all_entities.get(new_entity.key())
                    if existing:
                        self._merge_entity(existing, new_entity)
                    else:
                        if len(all_entities) >= max_entities:
                            continue
                        all_entities[new_entity.key()] = new_entity
                        entity_queue.append(new_entity)
                findings.extend(module_result.findings)
                artifacts.extend(module_result.artifacts)
                for relationship in module_result.relationships:
                    if relationship.dedupe_key() not in seen_relationships:
                        relationships.append(relationship)
                        seen_relationships.add(relationship.dedupe_key())

        modules = sorted({run.module for run in module_runs})
        summary = self.scorer.summarize(list(all_entities.values()), findings, [run.to_dict() for run in module_runs])
        summary["best_leads"] = self.scorer.prioritize_leads(findings)
        summary["watch_match_count"] = len(self._match_watch_targets(target_input, all_entities))
        evidence_sources = self._collect_evidence_sources(findings, module_runs)

        case_record = CaseRecord(
            case_id=f"case_{uuid4().hex[:12]}",
            target_input=target_input,
            depth=depth,
            created_at=datetime.utcnow().isoformat() + "Z",
            modules=modules,
            summary=summary,
            entities=list(all_entities.values()),
            findings=findings,
            relationships=relationships,
            artifacts=artifacts,
            module_runs=module_runs,
            evidence_sources=evidence_sources,
        )
        self.storage.save_case(case_record)
        self._sync_watch_targets(target_input, list(all_entities.values()), case_record.case_id)
        dossier = self.case_builder.build(case_record)
        return case_record, dossier

    async def _run_module(self, module, entity: Entity, depth: str, use_cache: bool) -> ModuleResult:
        if use_cache:
            cached = self.storage.get_module_cache(module.name, entity.entity_type, entity.value, depth)
            if cached:
                module_result = self._module_result_from_cache(module.name, cached)
                module_result.cached = True
                return module_result

        try:
            module_result = await asyncio.wait_for(module.run(entity, depth), timeout=module.timeout_seconds)
        except Exception as exc:
            module_result = ModuleResult(module=module.name, status="error", error=str(exc))

        self.storage.save_module_cache(module.name, entity.entity_type, entity.value, depth, module_result.to_dict(), module.cache_ttl_seconds)
        return module_result

    @staticmethod
    def _module_result_from_cache(module_name: str, payload: dict) -> ModuleResult:
        module_result = ModuleResult(module=module_name, tier=payload.get("tier", "public_passive"), source_family=payload.get("source_family", "public"))
        module_result.status = payload.get("status", "success")
        module_result.error = payload.get("error")
        module_result.runtime_ms = payload.get("runtime_ms")
        module_result.raw = payload.get("raw", {})
        module_result.entities = [Entity(**item) for item in payload.get("entities", [])]
        module_result.findings = [Finding(**item) for item in payload.get("findings", [])]
        module_result.relationships = [Relationship(**item) for item in payload.get("relationships", [])]
        module_result.artifacts = [Artifact(**item) for item in payload.get("artifacts", [])]
        return module_result

    @staticmethod
    def _merge_entity(existing: Entity, candidate: Entity) -> None:
        existing.confidence = max(existing.confidence, candidate.confidence)
        if candidate.source and candidate.source != existing.source and candidate.source not in existing.aliases:
            existing.aliases.append(candidate.source)
        for alias in candidate.aliases:
            if alias not in existing.aliases:
                existing.aliases.append(alias)
        existing.provenance.update(candidate.provenance)

    @staticmethod
    def _collect_evidence_sources(findings: list[Finding], module_runs: list[ModuleResult]) -> list[dict]:
        seen = {}
        for finding in findings:
            key = (finding.module, finding.source_label or finding.module, finding.source_url or "")
            if key in seen:
                continue
            run = next((item for item in module_runs if item.module == finding.module), None)
            seen[key] = {
                "source_id": f"src_{uuid4().hex[:12]}",
                "module": finding.module,
                "source_label": finding.source_label or finding.module,
                "source_url": finding.source_url,
                "reputation": finding.confidence if not run else max(finding.confidence, 0.0),
                "metadata": {"tier": getattr(run, "tier", None), "why": finding.why},
            }
        return list(seen.values())

    def _sync_watch_targets(self, target_input: str, entities: list[Entity], case_id: str) -> None:
        for entity in entities:
            if entity.value.lower() == target_input.lower() or entity.source == "seed":
                self.storage.add_watch_target(target_input, entity.entity_type, entity.value, last_case_id=case_id)
                break

    def _match_watch_targets(self, target_input: str, entity_map: dict[str, Entity]) -> list[dict]:
        watch_targets = self.storage.get_watch_targets()
        matches = []
        keys = {entity.key() for entity in entity_map.values()}
        for item in watch_targets:
            if f"{item['normalized_type'].lower()}::{item['normalized_value'].lower()}" in keys:
                matches.append(item)
        return matches


def dumps_case_json(dossier: dict) -> str:
    return json.dumps(dossier, indent=2)
