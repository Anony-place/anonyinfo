from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from uuid import uuid4

from anonyinfo_core.models import Artifact, CaseRecord, Entity, Finding, ModuleResult, Relationship

DB_FILE = "anonyinfo_vault.db"


def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(cursor, table_name: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def _ensure_column(cursor, table_name: str, column_name: str, column_sql: str):
    if column_name not in _table_columns(cursor, table_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


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
    c.execute(
        """CREATE TABLE IF NOT EXISTS evidence_sources (
            source_id TEXT PRIMARY KEY,
            case_id TEXT,
            module TEXT,
            source_label TEXT,
            source_url TEXT,
            reputation REAL,
            metadata_json TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS case_notes (
            note_id TEXT PRIMARY KEY,
            case_id TEXT,
            note_text TEXT,
            entity_id TEXT,
            created_at TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS watch_targets (
            watch_id TEXT PRIMARY KEY,
            target_input TEXT,
            normalized_type TEXT,
            normalized_value TEXT,
            status TEXT,
            created_at TEXT,
            last_case_id TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS rerun_jobs (
            rerun_id TEXT PRIMARY KEY,
            case_id TEXT,
            requested_modules TEXT,
            requested_depth TEXT,
            status TEXT,
            created_at TEXT,
            output_case_id TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS connector_accounts (
            connector_id TEXT PRIMARY KEY,
            provider TEXT,
            label TEXT,
            config_json TEXT,
            status TEXT,
            created_at TEXT
        )"""
    )

    _ensure_column(c, "entities", "aliases_json", "aliases_json TEXT")
    _ensure_column(c, "entities", "review_state", "review_state TEXT DEFAULT 'unreviewed'")
    _ensure_column(c, "entities", "canonical_key", "canonical_key TEXT")
    _ensure_column(c, "entities", "discovered_at", "discovered_at TEXT")
    _ensure_column(c, "entities", "provenance_json", "provenance_json TEXT")
    _ensure_column(c, "findings", "source_label", "source_label TEXT")
    _ensure_column(c, "findings", "source_url", "source_url TEXT")
    _ensure_column(c, "findings", "why", "why TEXT")
    _ensure_column(c, "findings", "discovered_at", "discovered_at TEXT")
    _ensure_column(c, "findings", "tags_json", "tags_json TEXT")
    _ensure_column(c, "relationships", "reason", "reason TEXT")
    _ensure_column(c, "relationships", "analyst_reviewed", "analyst_reviewed INTEGER DEFAULT 0")
    _ensure_column(c, "relationships", "discovered_at", "discovered_at TEXT")
    _ensure_column(c, "artifacts", "source_url", "source_url TEXT")
    _ensure_column(c, "artifacts", "discovered_at", "discovered_at TEXT")
    _ensure_column(c, "module_runs", "tier", "tier TEXT")
    _ensure_column(c, "module_runs", "source_family", "source_family TEXT")
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
    c.execute("SELECT data_json, expires_at FROM module_cache WHERE cache_key = ?", (_cache_key(module, entity_type, entity_value, depth),))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    if row["expires_at"] and row["expires_at"] < datetime.utcnow().isoformat() + "Z":
        return None
    return json.loads(row["data_json"])


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
               (entity_id, case_id, entity_type, value, label, source, confidence, evidence, aliases_json, review_state, canonical_key, discovered_at, provenance_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entity.entity_id,
                case_record.case_id,
                entity.entity_type,
                entity.value,
                entity.label,
                entity.source,
                entity.confidence,
                entity.evidence,
                json.dumps(entity.aliases),
                entity.review_state,
                entity.canonical_key,
                entity.discovered_at,
                json.dumps(entity.provenance),
            ),
        )
    for finding in case_record.findings:
        c.execute(
            """INSERT INTO findings
               (finding_id, case_id, module, title, summary, entity_id, entity_type, entity_value,
                category, severity, confidence, evidence, data_json, source_label, source_url, why, discovered_at, tags_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                finding.source_label,
                finding.source_url,
                finding.why,
                finding.discovered_at,
                json.dumps(finding.tags),
            ),
        )
    for relationship in case_record.relationships:
        c.execute(
            """INSERT INTO relationships
               (relationship_id, case_id, from_entity_id, to_entity_id, rel_type, source, confidence, evidence, reason, analyst_reviewed, discovered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                relationship.relationship_id,
                case_record.case_id,
                relationship.from_entity_id,
                relationship.to_entity_id,
                relationship.rel_type,
                relationship.source,
                relationship.confidence,
                relationship.evidence,
                relationship.reason,
                1 if relationship.analyst_reviewed else 0,
                relationship.discovered_at,
            ),
        )
    for artifact in case_record.artifacts:
        c.execute(
            """INSERT INTO artifacts
               (artifact_id, case_id, module, artifact_type, label, value, entity_id, metadata_json, source_url, discovered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact.artifact_id,
                case_record.case_id,
                artifact.module,
                artifact.artifact_type,
                artifact.label,
                artifact.value,
                artifact.entity_id,
                json.dumps(artifact.metadata),
                artifact.source_url,
                artifact.discovered_at,
            ),
        )
    for run in case_record.module_runs:
        c.execute(
            """INSERT INTO module_runs (case_id, module, status, error, runtime_ms, cached, raw_json, tier, source_family)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                case_record.case_id,
                run.module,
                run.status,
                run.error,
                run.runtime_ms,
                1 if run.cached else 0,
                json.dumps(run.raw),
                run.tier,
                run.source_family,
            ),
        )
    for source in case_record.evidence_sources:
        c.execute(
            """INSERT INTO evidence_sources (source_id, case_id, module, source_label, source_url, reputation, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                source["source_id"],
                case_record.case_id,
                source.get("module"),
                source.get("source_label"),
                source.get("source_url"),
                source.get("reputation"),
                json.dumps(source.get("metadata", {})),
            ),
        )
    conn.commit()
    conn.close()


def _hydrate_case(case_id: str, target_input: str, depth: str, created_at: str, summary_json: str) -> CaseRecord:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM entities WHERE case_id = ?", (case_id,))
    entities = [
        Entity(
            entity_type=row["entity_type"],
            value=row["value"],
            label=row["label"],
            source=row["source"],
            confidence=row["confidence"],
            evidence=row["evidence"],
            aliases=json.loads(row["aliases_json"]) if row["aliases_json"] else [],
            review_state=row["review_state"] or "unreviewed",
            canonical_key=row["canonical_key"],
            discovered_at=row["discovered_at"] or created_at,
            provenance=json.loads(row["provenance_json"]) if row["provenance_json"] else {},
            entity_id=row["entity_id"],
        )
        for row in c.fetchall()
    ]
    c.execute("SELECT * FROM findings WHERE case_id = ?", (case_id,))
    findings = [
        Finding(
            module=row["module"],
            title=row["title"],
            summary=row["summary"],
            entity_id=row["entity_id"],
            entity_type=row["entity_type"],
            entity_value=row["entity_value"],
            category=row["category"],
            severity=row["severity"],
            confidence=row["confidence"],
            evidence=row["evidence"],
            source_label=row["source_label"],
            source_url=row["source_url"],
            why=row["why"],
            discovered_at=row["discovered_at"] or created_at,
            tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
            data=json.loads(row["data_json"]),
            finding_id=row["finding_id"],
        )
        for row in c.fetchall()
    ]
    c.execute("SELECT * FROM relationships WHERE case_id = ?", (case_id,))
    relationships = [
        Relationship(
            from_entity_id=row["from_entity_id"],
            to_entity_id=row["to_entity_id"],
            rel_type=row["rel_type"],
            source=row["source"],
            confidence=row["confidence"],
            evidence=row["evidence"],
            reason=row["reason"],
            analyst_reviewed=bool(row["analyst_reviewed"]),
            discovered_at=row["discovered_at"] or created_at,
            relationship_id=row["relationship_id"],
        )
        for row in c.fetchall()
    ]
    c.execute("SELECT * FROM artifacts WHERE case_id = ?", (case_id,))
    artifacts = [
        Artifact(
            module=row["module"],
            artifact_type=row["artifact_type"],
            label=row["label"],
            value=row["value"],
            entity_id=row["entity_id"],
            source_url=row["source_url"],
            discovered_at=row["discovered_at"] or created_at,
            metadata=json.loads(row["metadata_json"]),
            artifact_id=row["artifact_id"],
        )
        for row in c.fetchall()
    ]
    c.execute("SELECT * FROM module_runs WHERE case_id = ?", (case_id,))
    module_runs = [
        ModuleResult(
            module=row["module"],
            tier=row["tier"] or "public_passive",
            source_family=row["source_family"] or "public",
            status=row["status"],
            error=row["error"],
            runtime_ms=row["runtime_ms"],
            cached=bool(row["cached"]),
            raw=json.loads(row["raw_json"]),
        )
        for row in c.fetchall()
    ]
    c.execute("SELECT * FROM case_notes WHERE case_id = ? ORDER BY created_at DESC", (case_id,))
    notes = [dict(row) for row in c.fetchall()]
    c.execute("SELECT * FROM evidence_sources WHERE case_id = ?", (case_id,))
    evidence_sources = [
        {
            "source_id": row["source_id"],
            "module": row["module"],
            "source_label": row["source_label"],
            "source_url": row["source_url"],
            "reputation": row["reputation"],
            "metadata": json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        }
        for row in c.fetchall()
    ]
    c.execute("SELECT * FROM rerun_jobs WHERE case_id = ? ORDER BY created_at DESC", (case_id,))
    rerun_jobs = [dict(row) for row in c.fetchall()]
    watch_targets = get_watch_targets(case_id=case_id)
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
        notes=notes,
        watch_targets=watch_targets,
        evidence_sources=evidence_sources,
        rerun_jobs=rerun_jobs,
    )


def get_case(case_id: str) -> CaseRecord | None:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT target_input, depth, created_at, summary_json FROM cases WHERE case_id = ?", (case_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return _hydrate_case(case_id, row["target_input"], row["depth"], row["created_at"], row["summary_json"])


def get_history(limit: int = 50):
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT case_id, target_input, depth, created_at, summary_json FROM cases ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [
        {
            "case_id": row["case_id"],
            "target_input": row["target_input"],
            "depth": row["depth"],
            "created_at": row["created_at"],
            "summary": json.loads(row["summary_json"]),
        }
        for row in rows
    ]


def add_case_note(case_id: str, note_text: str, entity_id: str | None = None) -> dict:
    note = {
        "note_id": f"note_{uuid4().hex[:12]}",
        "case_id": case_id,
        "note_text": note_text,
        "entity_id": entity_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO case_notes (note_id, case_id, note_text, entity_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (note["note_id"], case_id, note_text, entity_id, note["created_at"]),
    )
    conn.commit()
    conn.close()
    return note


def get_case_notes(case_id: str):
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM case_notes WHERE case_id = ? ORDER BY created_at DESC", (case_id,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def add_watch_target(target_input: str, normalized_type: str, normalized_value: str, status: str = "ACTIVE", last_case_id: str | None = None) -> dict:
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM watch_targets WHERE normalized_type = ? AND normalized_value = ?",
        (normalized_type, normalized_value),
    )
    existing = c.fetchone()
    if existing:
        c.execute(
            "UPDATE watch_targets SET target_input = ?, status = ?, last_case_id = ? WHERE watch_id = ?",
            (target_input, status, last_case_id or existing["last_case_id"], existing["watch_id"]),
        )
        conn.commit()
        conn.close()
        item = dict(existing)
        item["target_input"] = target_input
        item["status"] = status
        item["last_case_id"] = last_case_id or existing["last_case_id"]
        return item
    watch = {
        "watch_id": f"watch_{uuid4().hex[:12]}",
        "target_input": target_input,
        "normalized_type": normalized_type,
        "normalized_value": normalized_value,
        "status": status,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "last_case_id": last_case_id,
    }
    c.execute(
        """INSERT OR REPLACE INTO watch_targets
           (watch_id, target_input, normalized_type, normalized_value, status, created_at, last_case_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        tuple(watch.values()),
    )
    conn.commit()
    conn.close()
    return watch


def get_watch_targets(case_id: str | None = None):
    conn = _connect()
    c = conn.cursor()
    if case_id:
        c.execute("SELECT * FROM watch_targets WHERE last_case_id = ? ORDER BY created_at DESC", (case_id,))
    else:
        c.execute("SELECT * FROM watch_targets ORDER BY created_at DESC")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def add_connector_account(provider: str, label: str, config: dict, status: str = "ACTIVE") -> dict:
    item = {
        "connector_id": f"conn_{uuid4().hex[:12]}",
        "provider": provider,
        "label": label,
        "config_json": json.dumps(config),
        "status": status,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO connector_accounts (connector_id, provider, label, config_json, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        tuple(item.values()),
    )
    conn.commit()
    conn.close()
    item["config"] = config
    return item


def get_connector_accounts():
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM connector_accounts ORDER BY created_at DESC")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    for row in rows:
        row["config"] = json.loads(row["config_json"]) if row.get("config_json") else {}
    return rows


def create_rerun_job(case_id: str, requested_modules: list[str] | None, requested_depth: str) -> dict:
    item = {
        "rerun_id": f"rerun_{uuid4().hex[:12]}",
        "case_id": case_id,
        "requested_modules": json.dumps(requested_modules or []),
        "requested_depth": requested_depth,
        "status": "QUEUED",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "output_case_id": None,
    }
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO rerun_jobs (rerun_id, case_id, requested_modules, requested_depth, status, created_at, output_case_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        tuple(item.values()),
    )
    conn.commit()
    conn.close()
    return item


def complete_rerun_job(rerun_id: str, output_case_id: str):
    conn = _connect()
    c = conn.cursor()
    c.execute("UPDATE rerun_jobs SET status = 'COMPLETED', output_case_id = ? WHERE rerun_id = ?", (output_case_id, rerun_id))
    conn.commit()
    conn.close()


def get_rerun_jobs(case_id: str | None = None):
    conn = _connect()
    c = conn.cursor()
    if case_id:
        c.execute("SELECT * FROM rerun_jobs WHERE case_id = ? ORDER BY created_at DESC", (case_id,))
    else:
        c.execute("SELECT * FROM rerun_jobs ORDER BY created_at DESC")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    for row in rows:
        row["requested_modules"] = json.loads(row["requested_modules"]) if row["requested_modules"] else []
    return rows
