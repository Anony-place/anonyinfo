from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class Entity:
    entity_type: str
    value: str
    label: Optional[str] = None
    source: str = "seed"
    confidence: float = 1.0
    evidence: Optional[str] = None
    entity_id: str = field(default_factory=lambda: _new_id("ent"))

    def key(self) -> str:
        return f"{self.entity_type.lower()}::{self.value.lower()}"

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
    metadata: Dict[str, Any] = field(default_factory=dict)
    artifact_id: str = field(default_factory=lambda: _new_id("art"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModuleResult:
    module: str
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
        }
