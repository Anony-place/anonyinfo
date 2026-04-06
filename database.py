from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from anonyinfo_core.models import Artifact, CaseRecord, Entity, Finding, ModuleResult, Relationship

DB_FILE = "anonyinfo_vault.db"


def _connect():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY,
            target_input TEXT,
            depth TEXT,
            created_at TEXT,
            summary_json TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS entities (
            entity_id TEXT PRIMARY KEY,
            case_id TEXT,
            entity_type TEXT,
            value TEXT,
            label TEXT,
            source TEXT,
            confidence REAL,
            evidence TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS findings (
            finding_id TEXT PRIMARY KEY,
            case_id TEXT,
            module TEXT,
            title TEXT,
            summary TEXT,
            entity_id TEXT,
            entity_type TEXT,
            entity_value TEXT,
            category TEXT,
            severity TEXT,
            confidence REAL,
            evidence TEXT,
            data_json TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS relationships (
            relationship_id TEXT PRIMARY KEY,
            case_id TEXT,
            from_entity_id TEXT,
            to_entity_id TEXT,
            rel_type TEXT,
            source TEXT,
            confidence REAL,
            evidence TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY,
            case_id TEXT,
            module TEXT,
            artifact_type TEXT,
            label TEXT,
            value TEXT,
            entity_id TEXT,
            metadata_json TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS module_runs (
            case_id TEXT,
            module TEXT,
            status TEXT,
            error TEXT,
            runtime_ms INTEGER,
            cached INTEGER,
            raw_json TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS module_cache (
            cache_key TEXT PRIMARY KEY,
            module TEXT,
            entity_type TEXT,
            entity_value TEXT,
            depth TEXT,
            data_json TEXT,
            expires_at TEXT
        )"""
    )
    conn.commit()
    conn.close()


def _cache_key(module: str, entity_type: str, entity_value: str, depth: str) -> str:
    return f"{module}|{entity_type.lower()}|{entity_value.lower()}|{depth}"


def save_module_cache(module: str, entity_type: str, entity_value: str, depth: str, data: dict, ttl_seconds: int):
    conn = _connect()
    c = conn.cursor()
    expires_at = (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat() + "Z"
    c.execute(
        """INSERT OR REPLACE INTO module_cache
           (cache_key, module, entity_type, entity_value, depth, data_json, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (_cache_key(module, entity_type, entity_value, depth), module, entity_type, entity_value, depth, json.dumps(data), expires_at),
    )
    conn.commit()
    conn.close()


def get_module_cache(module: str, entity_type: str, entity_value: str, depth: str):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT data_json, expires_at FROM module_cache WHERE cache_key = ?",
        (_cache_key(module, entity_type, entity_value, depth),),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    data_json, expires_at = row
    if expires_at and expires_at < datetime.utcnow().isoformat() + "Z":
        return None
    return json.loads(data_json)


def save_case(case_record: CaseRecord):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO cases (case_id, target_input, depth, created_at, summary_json) VALUES (?, ?, ?, ?, ?)",
        (case_record.case_id, case_record.target_input, case_record.depth, case_record.created_at, json.dumps(case_record.summary)),
    )
    for entity in case_record.entities:
        c.execute(
            """INSERT INTO entities
               (entity_id, case_id, entity_type, value, label, source, confidence, evidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entity.entity_id,
                case_record.case_id,
                entity.entity_type,
                entity.value,
                entity.label,
                entity.source,
                entity.confidence,
                entity.evidence,
            ),
        )
    for finding in case_record.findings:
        c.execute(
            """INSERT INTO findings
               (finding_id, case_id, module, title, summary, entity_id, entity_type, entity_value,
                category, severity, confidence, evidence, data_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                finding.finding_id,
                case_record.case_id,
                finding.module,
                finding.title,
                finding.summary,
                finding.entity_id,
                finding.entity_type,
                finding.entity_value,
                finding.category,
                finding.severity,
                finding.confidence,
                finding.evidence,
                json.dumps(finding.data),
            ),
        )
    for relationship in case_record.relationships:
        c.execute(
            """INSERT INTO relationships
               (relationship_id, case_id, from_entity_id, to_entity_id, rel_type, source, confidence, evidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                relationship.relationship_id,
                case_record.case_id,
                relationship.from_entity_id,
                relationship.to_entity_id,
                relationship.rel_type,
                relationship.source,
                relationship.confidence,
                relationship.evidence,
            ),
        )
    for artifact in case_record.artifacts:
        c.execute(
            """INSERT INTO artifacts
               (artifact_id, case_id, module, artifact_type, label, value, entity_id, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact.artifact_id,
                case_record.case_id,
                artifact.module,
                artifact.artifact_type,
                artifact.label,
                artifact.value,
                artifact.entity_id,
                json.dumps(artifact.metadata),
            ),
        )
    for run in case_record.module_runs:
        c.execute(
            """INSERT INTO module_runs (case_id, module, status, error, runtime_ms, cached, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                case_record.case_id,
                run.module,
                run.status,
                run.error,
                run.runtime_ms,
                1 if run.cached else 0,
                json.dumps(run.raw),
            ),
        )
    conn.commit()
    conn.close()


def get_case(case_id: str) -> CaseRecord | None:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT target_input, depth, created_at, summary_json FROM cases WHERE case_id = ?", (case_id,))
    case_row = c.fetchone()
    if not case_row:
        conn.close()
        return None
    target_input, depth, created_at, summary_json = case_row

    c.execute("SELECT entity_id, entity_type, value, label, source, confidence, evidence FROM entities WHERE case_id = ?", (case_id,))
    entities = [
        Entity(entity_type=row[1], value=row[2], label=row[3], source=row[4], confidence=row[5], evidence=row[6], entity_id=row[0])
        for row in c.fetchall()
    ]
    c.execute(
        """SELECT finding_id, module, title, summary, entity_id, entity_type, entity_value, category, severity, confidence, evidence, data_json
           FROM findings WHERE case_id = ?""",
        (case_id,),
    )
    findings = [
        Finding(
            module=row[1],
            title=row[2],
            summary=row[3],
            entity_id=row[4],
            entity_type=row[5],
            entity_value=row[6],
            category=row[7],
            severity=row[8],
            confidence=row[9],
            evidence=row[10],
            data=json.loads(row[11]),
            finding_id=row[0],
        )
        for row in c.fetchall()
    ]
    c.execute(
        "SELECT relationship_id, from_entity_id, to_entity_id, rel_type, source, confidence, evidence FROM relationships WHERE case_id = ?",
        (case_id,),
    )
    relationships = [
        Relationship(
            from_entity_id=row[1],
            to_entity_id=row[2],
            rel_type=row[3],
            source=row[4],
            confidence=row[5],
            evidence=row[6],
            relationship_id=row[0],
        )
        for row in c.fetchall()
    ]
    c.execute(
        "SELECT artifact_id, module, artifact_type, label, value, entity_id, metadata_json FROM artifacts WHERE case_id = ?",
        (case_id,),
    )
    artifacts = [
        Artifact(
            module=row[1],
            artifact_type=row[2],
            label=row[3],
            value=row[4],
            entity_id=row[5],
            metadata=json.loads(row[6]),
            artifact_id=row[0],
        )
        for row in c.fetchall()
    ]
    c.execute("SELECT module, status, error, runtime_ms, cached, raw_json FROM module_runs WHERE case_id = ?", (case_id,))
    module_runs = [
        ModuleResult(
            module=row[0],
            status=row[1],
            error=row[2],
            runtime_ms=row[3],
            cached=bool(row[4]),
            raw=json.loads(row[5]),
        )
        for row in c.fetchall()
    ]
    conn.close()

    return CaseRecord(
        case_id=case_id,
        target_input=target_input,
        depth=depth,
        created_at=created_at,
        modules=sorted({run.module for run in module_runs}),
        summary=json.loads(summary_json),
        entities=entities,
        findings=findings,
        relationships=relationships,
        artifacts=artifacts,
        module_runs=module_runs,
    )


def get_history(limit: int = 50):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT case_id, target_input, depth, created_at, summary_json FROM cases ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "case_id": row[0],
            "target_input": row[1],
            "depth": row[2],
            "created_at": row[3],
            "summary": json.loads(row[4]),
        }
        for row in rows
    ]
