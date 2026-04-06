from __future__ import annotations

from anonyinfo_core.models import Relationship


def analyze_relationships(entities):
    relationships = []
    entity_index = {entity.key(): entity for entity in entities}

    for entity in entities:
        if entity.entity_type == "email":
            local, domain = entity.value.split("@", 1)
            username = entity_index.get(f"username::{local.lower()}")
            domain_entity = entity_index.get(f"domain::{domain.lower()}")
            if username:
                relationships.append(
                    Relationship(entity.entity_id, username.entity_id, "identifies_username", "engine", 0.9, entity.value)
                )
            if domain_entity:
                relationships.append(
                    Relationship(entity.entity_id, domain_entity.entity_id, "hosted_on", "engine", 1.0, entity.value)
                )
        if entity.entity_type == "url":
            domain = entity.value.split("//")[-1].split("/")[0].split(":")[0]
            domain_entity = entity_index.get(f"domain::{domain.lower()}")
            if domain_entity:
                relationships.append(
                    Relationship(entity.entity_id, domain_entity.entity_id, "hosts", "engine", 0.9, entity.value)
                )

    deduped = {}
    for relationship in relationships:
        deduped.setdefault(relationship.dedupe_key(), relationship)
    return list(deduped.values())
