from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import Entity, Relationship


EMAIL_RE = re.compile(r"^([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})$")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$")
IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


class InputNormalizer:
    def normalize(self, raw_input: str) -> list[Entity]:
        raw_input = raw_input.strip()
        entities: list[Entity] = []

        email_match = EMAIL_RE.match(raw_input)
        if email_match:
            username, domain = email_match.groups()
            entities.append(Entity(entity_type="email", value=raw_input, label="Email Address"))
            entities.append(Entity(entity_type="username", value=username, source="email_local_part", confidence=0.9))
            entities.append(Entity(entity_type="domain", value=domain, source="email_domain", confidence=1.0))
            return entities

        if raw_input.startswith(("http://", "https://")):
            parsed = urlparse(raw_input)
            domain = parsed.netloc.split(":")[0]
            entities.append(Entity(entity_type="url", value=raw_input, label="URL"))
            if domain:
                entities.append(Entity(entity_type="domain", value=domain, source="url_host", confidence=0.95))
            if raw_input.lower().endswith(IMAGE_EXTENSIONS):
                entities.append(Entity(entity_type="image_url", value=raw_input, source="url_image", confidence=1.0))
            return entities

        compact_phone = re.sub(r"[^0-9+]", "", raw_input)
        if (compact_phone.startswith("+") and compact_phone[1:].isdigit()) or (
            compact_phone.isdigit() and 7 <= len(compact_phone) <= 15
        ):
            entities.append(Entity(entity_type="phone", value=compact_phone, label="Phone Number"))
            return entities

        lowered = raw_input.lower()
        if IP_RE.match(lowered):
            entities.append(Entity(entity_type="ip", value=lowered, label="IP Address"))
            return entities

        if DOMAIN_RE.match(lowered):
            entities.append(Entity(entity_type="domain", value=lowered, label="Domain"))
            return entities

        entities.append(Entity(entity_type="username", value=raw_input, label="Username"))
        return entities


class EntityResolver:
    def resolve(self, entities: list[Entity]) -> tuple[list[Entity], list[Relationship]]:
        deduped: dict[str, Entity] = {}
        relationships: list[Relationship] = []

        for entity in entities:
            deduped.setdefault(entity.key(), entity)

        entity_list = list(deduped.values())
        key_map = {entity.key(): entity for entity in entity_list}

        for entity in list(entity_list):
            if entity.entity_type == "email":
                local, domain = entity.value.split("@", 1)
                username = self._upsert_entity(key_map, entity_list, Entity("username", local, source="resolver_email"))
                domain_entity = self._upsert_entity(key_map, entity_list, Entity("domain", domain, source="resolver_email"))
                relationships.append(
                    Relationship(entity.entity_id, username.entity_id, "identifies_username", "resolver", 0.95, entity.value)
                )
                relationships.append(
                    Relationship(entity.entity_id, domain_entity.entity_id, "hosted_on", "resolver", 1.0, entity.value)
                )
            elif entity.entity_type == "url":
                parsed = urlparse(entity.value)
                domain = parsed.netloc.split(":")[0]
                if domain:
                    domain_entity = self._upsert_entity(key_map, entity_list, Entity("domain", domain, source="resolver_url"))
                    relationships.append(
                        Relationship(entity.entity_id, domain_entity.entity_id, "hosts", "resolver", 0.95, entity.value)
                    )

        return entity_list, self._dedupe_relationships(relationships)

    @staticmethod
    def _upsert_entity(key_map: dict[str, Entity], entity_list: list[Entity], entity: Entity) -> Entity:
        existing = key_map.get(entity.key())
        if existing:
            return existing
        key_map[entity.key()] = entity
        entity_list.append(entity)
        return entity

    @staticmethod
    def _dedupe_relationships(relationships: list[Relationship]) -> list[Relationship]:
        deduped: dict[str, Relationship] = {}
        for rel in relationships:
            deduped.setdefault(rel.dedupe_key(), rel)
        return list(deduped.values())
