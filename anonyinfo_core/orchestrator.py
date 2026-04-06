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

        all_entities = {entity.key(): entity for entity in entities}
        findings: List[Finding] = []
        relationships: List[Relationship] = list(base_relationships)
        artifacts: List[Artifact] = []
        module_runs: List[ModuleResult] = []
        seen_relationships = {item.dedupe_key() for item in relationships}

        for entity in list(all_entities.values()):
            applicable = self.registry.applicable(entity, selected_modules)
            tasks = [
                asyncio.create_task(self._run_module(module, entity, depth, use_cache))
                for module in applicable
            ]
            if not tasks:
                continue
            results = await asyncio.gather(*tasks)
            for module_result in results:
                module_runs.append(module_result)
                for new_entity in module_result.entities:
                    all_entities.setdefault(new_entity.key(), new_entity)
                findings.extend(module_result.findings)
                artifacts.extend(module_result.artifacts)
                for relationship in module_result.relationships:
                    if relationship.dedupe_key() not in seen_relationships:
                        relationships.append(relationship)
                        seen_relationships.add(relationship.dedupe_key())

        modules = sorted({run.module for run in module_runs})
        summary = self.scorer.summarize(list(all_entities.values()), findings, [run.to_dict() for run in module_runs])
        summary["best_leads"] = self.scorer.prioritize_leads(findings)

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
        )
        self.storage.save_case(case_record)
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
        module_result = ModuleResult(module=module_name)
        module_result.status = payload.get("status", "success")
        module_result.error = payload.get("error")
        module_result.runtime_ms = payload.get("runtime_ms")
        module_result.raw = payload.get("raw", {})
        module_result.entities = [Entity(**item) for item in payload.get("entities", [])]
        module_result.findings = [Finding(**item) for item in payload.get("findings", [])]
        module_result.relationships = [Relationship(**item) for item in payload.get("relationships", [])]
        module_result.artifacts = [Artifact(**item) for item in payload.get("artifacts", [])]
        return module_result


def dumps_case_json(dossier: dict) -> str:
    return json.dumps(dossier, indent=2)
