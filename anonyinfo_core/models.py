from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


@dataclass
class Entity:
    entity_type: str
    value: str
    label: Optional[str] = None
    source: str = "seed"
    confidence: float = 1.0
    evidence: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    review_state: str = "unreviewed"
    canonical_key: Optional[str] = None
    discovered_at: str = field(default_factory=_utc_now)
    provenance: Dict[str, Any] = field(default_factory=dict)
    entity_id: str = field(default_factory=lambda: _new_id("ent"))

    def key(self) -> str:
        return self.canonical_key or f"{self.entity_type.lower()}::{self.value.lower()}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Finding:
    module: str
    title: str
    summary: str
    entity_id: str
    entity_type: str
    entity_value: str
    category: str
    severity: str = "info"
    confidence: float = 0.5
    evidence: Optional[str] = None
    source_label: Optional[str] = None
    source_url: Optional[str] = None
    why: Optional[str] = None
    discovered_at: str = field(default_factory=_utc_now)
    tags: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    finding_id: str = field(default_factory=lambda: _new_id("fnd"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Relationship:
    from_entity_id: str
    to_entity_id: str
    rel_type: str
    source: str
    confidence: float = 0.5
    evidence: Optional[str] = None
    reason: Optional[str] = None
    analyst_reviewed: bool = False
    discovered_at: str = field(default_factory=_utc_now)
    relationship_id: str = field(default_factory=lambda: _new_id("rel"))

    def dedupe_key(self) -> str:
        return "|".join([self.from_entity_id, self.to_entity_id, self.rel_type, self.source])

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Artifact:
    module: str
    artifact_type: str
    label: str
    value: str
    entity_id: Optional[str] = None
    source_url: Optional[str] = None
    discovered_at: str = field(default_factory=_utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    artifact_id: str = field(default_factory=lambda: _new_id("art"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModuleResult:
    module: str
    tier: str = "public_passive"
    source_family: str = "public"
    entities: List[Entity] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    artifacts: List[Artifact] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    status: str = "success"
    error: Optional[str] = None
    runtime_ms: Optional[int] = None
    cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "tier": self.tier,
            "source_family": self.source_family,
            "status": self.status,
            "error": self.error,
            "runtime_ms": self.runtime_ms,
            "cached": self.cached,
            "entities": [item.to_dict() for item in self.entities],
            "findings": [item.to_dict() for item in self.findings],
            "relationships": [item.to_dict() for item in self.relationships],
            "artifacts": [item.to_dict() for item in self.artifacts],
            "raw": self.raw,
        }


@dataclass
class CaseRecord:
    case_id: str
    target_input: str
    depth: str
    created_at: str
    modules: List[str]
    summary: Dict[str, Any]
    entities: List[Entity]
    findings: List[Finding]
    relationships: List[Relationship]
    artifacts: List[Artifact]
    module_runs: List[ModuleResult]
    notes: List[Dict[str, Any]] = field(default_factory=list)
    watch_targets: List[Dict[str, Any]] = field(default_factory=list)
    evidence_sources: List[Dict[str, Any]] = field(default_factory=list)
    rerun_jobs: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "target_input": self.target_input,
            "depth": self.depth,
            "created_at": self.created_at,
            "modules": self.modules,
            "summary": self.summary,
            "entities": [item.to_dict() for item in self.entities],
            "findings": [item.to_dict() for item in self.findings],
            "relationships": [item.to_dict() for item in self.relationships],
            "artifacts": [item.to_dict() for item in self.artifacts],
            "module_runs": [item.to_dict() for item in self.module_runs],
            "notes": self.notes,
            "watch_targets": self.watch_targets,
            "evidence_sources": self.evidence_sources,
            "rerun_jobs": self.rerun_jobs,
        }
