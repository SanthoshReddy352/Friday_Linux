"""Typed knowledge graph — entity/fact/relationship extraction and recall.

Mirrors jarvis src/vault/{entities,facts,relationships,extractor}.ts.

This module provides:
  - EntityExtractor: lightweight regex-based entity extraction from turn text
  - GraphRecall: builds a typed context fragment from entities relevant to a query

The extractor runs on every completed turn and upserts entities/facts to
the shared ContextStore tables (entities, entity_facts, entity_relationships).

EntityExtractor is intentionally lightweight (regex + heuristics) to avoid
adding LLM calls to the critical path. For richer extraction, the Mem0 client
already handles free-text user facts; this module adds *typed* structure.

Entity types supported:
  person, project, tool, place, concept, event, file, topic
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.logger import logger


# ---------------------------------------------------------------------------
# Lightweight regex entity patterns
# ---------------------------------------------------------------------------

_PERSON_PATTERNS = [
    re.compile(r"\bmy (?:name is|friend|colleague|boss|manager) ([A-Z][a-z]{1,30})\b"),
    re.compile(r"\b([A-Z][a-z]{1,30}) (?:said|told|asked|mentioned|works?)\b"),
    re.compile(r"\bcall me ([A-Z][a-zA-Z\s]{1,30})\b", re.IGNORECASE),
]
_TOOL_PATTERNS = [
    re.compile(r"\busing ([A-Za-z][A-Za-z0-9_\-\.]{1,40}) (?:for|to|as)\b"),
    re.compile(r"\b(?:tool|library|framework|package) (?:called )?([A-Za-z][A-Za-z0-9_\-\.]{1,40})\b"),
]
_PROJECT_PATTERNS = [
    re.compile(r"\b(?:project|repo|repository|app|application) (?:called |named )?[\"']?([A-Za-z][A-Za-z0-9_\-\s]{1,40})[\"']?\b"),
]
_PLACE_PATTERNS = [
    re.compile(r"\bin ([A-Z][a-z]{2,30}(?:,\s*[A-Z][a-z]{2,30})?)\b"),
    re.compile(r"\b(?:based in|located in|from) ([A-Z][a-z]{2,30})\b"),
]


@dataclass
class ExtractedEntity:
    name: str
    entity_type: str
    predicate: str = ""
    obj: str = ""
    confidence: float = 0.7


def extract_entities(text: str) -> list[ExtractedEntity]:
    """Extract named entities from text using lightweight regex patterns."""
    results: list[ExtractedEntity] = []
    text_stripped = (text or "").strip()
    if not text_stripped:
        return results

    for pattern in _PERSON_PATTERNS:
        for m in pattern.finditer(text_stripped):
            name = m.group(1).strip()
            if len(name) > 1:
                results.append(ExtractedEntity(
                    name=name, entity_type="person", confidence=0.75
                ))

    for pattern in _TOOL_PATTERNS:
        for m in pattern.finditer(text_stripped):
            name = m.group(1).strip()
            if len(name) > 1:
                results.append(ExtractedEntity(
                    name=name, entity_type="tool", confidence=0.7
                ))

    for pattern in _PROJECT_PATTERNS:
        for m in pattern.finditer(text_stripped):
            name = m.group(1).strip()
            if len(name) > 1:
                results.append(ExtractedEntity(
                    name=name, entity_type="project", confidence=0.7
                ))

    for pattern in _PLACE_PATTERNS:
        for m in pattern.finditer(text_stripped):
            name = m.group(1).strip()
            if len(name) > 2:
                results.append(ExtractedEntity(
                    name=name, entity_type="place", confidence=0.75
                ))

    return results


class EntityExtractor:
    """Extracts entities from user turns and persists them to the knowledge graph."""

    def __init__(self, memory_service):
        self._memory = memory_service

    def process_turn(self, user_text: str, assistant_text: str, session_id: str = "") -> int:
        """Extract entities from the user turn and upsert them. Returns count upserted."""
        entities = extract_entities(user_text)
        count = 0
        for ent in entities:
            try:
                self._memory.upsert_entity(
                    name=ent.name,
                    entity_type=ent.entity_type,
                    session_id=session_id,
                )
                count += 1
            except Exception as exc:
                logger.debug("[graph] upsert_entity failed (non-fatal): %s", exc)
        return count


class GraphRecall:
    """Builds a typed knowledge-graph context fragment for prompt injection."""

    def __init__(self, memory_service):
        self._memory = memory_service

    def build_fragment(self, query: str, max_entities: int = 5) -> str:
        """Return a compact text block of relevant entities + facts for the query."""
        words = {w.lower() for w in re.split(r"\W+", query or "") if len(w) > 2}
        if not words:
            return ""
        fragments: list[str] = []
        for word in list(words)[:5]:
            entities = self._memory.find_entities(name_fragment=word)
            for ent in entities[:max_entities]:
                facts = self._memory.query_entity_facts(ent["id"])
                if facts:
                    facts_str = "; ".join(
                        f"{f['predicate']}: {f['object']}" for f in facts[:3]
                    )
                    fragments.append(f"{ent['name']} ({ent['entity_type']}): {facts_str}")
                else:
                    fragments.append(f"{ent['name']} ({ent['entity_type']})")
        if not fragments:
            return ""
        return "Known entities:\n" + "\n".join(f"  • {f}" for f in fragments[:max_entities])
