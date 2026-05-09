import hashlib
import json
import math
import os
import sqlite3
import threading
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


# Phase 1 (v2): workflow states older than this auto-expire. Prevents stale
# `calendar_event_workflow` / `file_workflow` rows from surviving a FRIDAY
# restart and resurrecting half-finished multi-turn flows.
WORKFLOW_TTL_HOURS = 24


def _parse_iso_utc(value):
    if not value:
        return None
    try:
        # SQLite stores the ISO string we wrote in _utc_now(); fromisoformat
        # round-trips it, including the +00:00 offset.
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _is_workflow_expired(updated_at, ttl_hours=WORKFLOW_TTL_HOURS):
    parsed = _parse_iso_utc(updated_at)
    if parsed is None:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - parsed
    return age.total_seconds() > ttl_hours * 3600


def _project_root():
    return os.path.dirname(os.path.dirname(__file__))


def _default_db_path():
    return os.path.join(_project_root(), "data", "friday.db")


def _default_vector_path():
    return os.path.join(_project_root(), "data", "chroma")


def _tokenize(text):
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(text or ""))
    return [token for token in cleaned.split() if len(token) > 1]


@dataclass
class WorkingArtifact:
    """Tracks the last meaningful capability output for the current session.

    Stored in the session state JSON blob so it survives across the turn boundary.
    Enables pronoun resolution: "save that", "use this", "read it back".
    """
    content: str
    output_type: str = "text"
    capability_name: str = ""
    artifact_type: str = "text"
    source_path: str = ""


class HashEmbeddingFunction:
    """
    Small deterministic embedding function for local semantic recall.

    This keeps Chroma usable without downloading a heavy embedding model.
    """

    def __init__(self, dimensions=64):
        self.dimensions = max(16, int(dimensions))

    def __call__(self, input):
        embeddings = []
        for text in input:
            vector = [0.0] * self.dimensions
            for token in _tokenize(text):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[index] += sign
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            embeddings.append([value / norm for value in vector])
        return embeddings


class ContextStore:
    def __init__(self, db_path=None, vector_path=None):
        self.db_path = db_path or _default_db_path()
        self.vector_path = vector_path or _default_vector_path()
        self._lock = threading.RLock()
        self._vector_collection = None
        self._vector_available = False
        self._ensure_storage()
        self._init_vector_store()

    def start_session(self, metadata=None):
        session_id = str(uuid.uuid4())
        now = _utc_now()
        payload = json.dumps(metadata or {}, ensure_ascii=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, started_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, now, now, payload),
            )
            conn.commit()
        return session_id

    def append_turn(self, session_id, role, text, source=None):
        if not session_id or not text:
            return
        now = _utc_now()
        source_value = source or role
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO turns (session_id, role, text, source, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, str(text), source_value, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            conn.commit()
        self._upsert_memory_item(
            item_id=f"turn:{session_id}:{role}:{hashlib.md5(str(text).encode('utf-8')).hexdigest()}",
            text=str(text),
            metadata={"session_id": session_id, "kind": "turn", "role": role, "source": source_value},
        )

    def get_active_workflow(self, session_id, workflow_name=None):
        if not session_id:
            return None
        query = """
            SELECT workflow_name, status, pending_slots_json, last_action, target_json,
                   result_summary, state_json, updated_at
            FROM workflows
            WHERE session_id = ? AND status IN ('active', 'pending')
        """
        params = [session_id]
        if workflow_name:
            query += " AND workflow_name = ?"
            params.append(workflow_name)
        query += " ORDER BY updated_at DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        if not row:
            return None
        # Phase 1 (v2): auto-expire stale workflows. A stale row is treated
        # as no active workflow and is also marked completed in-place so it
        # stops shadowing future queries.
        if _is_workflow_expired(row[7]):
            try:
                self._mark_workflow_expired(session_id, row[0])
            except Exception:
                pass
            return None
        return self._row_to_workflow(row)

    def _mark_workflow_expired(self, session_id, workflow_name):
        with self._connect() as conn:
            conn.execute(
                "UPDATE workflows SET status = 'expired', updated_at = ? "
                "WHERE session_id = ? AND workflow_name = ?",
                (_utc_now(), session_id, workflow_name),
            )
            conn.commit()

    def save_workflow_state(self, session_id, workflow_name, state):
        if not session_id or not workflow_name:
            return
        state = dict(state or {})
        now = _utc_now()
        pending_slots = json.dumps(list(state.get("pending_slots") or []), ensure_ascii=True)
        target_json = json.dumps(state.get("target") or {}, ensure_ascii=True)
        state_json = json.dumps(state, ensure_ascii=True)
        status = str(state.get("status") or "active")
        last_action = str(state.get("last_action") or "")
        result_summary = str(state.get("result_summary") or "")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workflows (
                    session_id, workflow_name, status, pending_slots_json,
                    last_action, target_json, result_summary, state_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, workflow_name)
                DO UPDATE SET
                    status = excluded.status,
                    pending_slots_json = excluded.pending_slots_json,
                    last_action = excluded.last_action,
                    target_json = excluded.target_json,
                    result_summary = excluded.result_summary,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    workflow_name,
                    status,
                    pending_slots,
                    last_action,
                    target_json,
                    result_summary,
                    state_json,
                    now,
                ),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            conn.commit()
        summary_text = " ".join(
            part for part in [workflow_name.replace("_", " "), last_action, result_summary] if part
        ).strip()
        if summary_text:
            self._upsert_memory_item(
                item_id=f"workflow:{session_id}:{workflow_name}",
                text=summary_text,
                metadata={"session_id": session_id, "kind": "workflow", "workflow_name": workflow_name},
            )

    def clear_workflow_state(self, session_id, workflow_name):
        active = self.get_active_workflow(session_id, workflow_name=workflow_name)
        if not active:
            return
        active["status"] = "completed"
        active["pending_slots"] = []
        self.save_workflow_state(session_id, workflow_name, active)

    def store_fact(self, key, value, session_id=None, namespace="general"):
        if not key:
            return
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO facts (session_id, namespace, key, value, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, namespace, key)
                DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (session_id or "", namespace, key, value, now),
            )
            conn.commit()
        self._upsert_memory_item(
            item_id=f"fact:{session_id or 'global'}:{namespace}:{key}",
            text=f"{key}: {value}",
            metadata={"session_id": session_id or "", "kind": "fact", "namespace": namespace, "key": key},
        )

    def save_persona(self, payload):
        data = dict(payload or {})
        persona_id = str(data.get("persona_id") or "").strip()
        if not persona_id:
            return
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO personas (
                    persona_id, display_name, system_identity, tone_traits, conversation_style,
                    speech_style, humor_level, verbosity_preference, formality_level,
                    empathy_style, tool_ack_style, memory_scope, retrieval_filters,
                    example_dialogues, enabled_skills, disallowed_behaviors, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(persona_id)
                DO UPDATE SET
                    display_name = excluded.display_name,
                    system_identity = excluded.system_identity,
                    tone_traits = excluded.tone_traits,
                    conversation_style = excluded.conversation_style,
                    speech_style = excluded.speech_style,
                    humor_level = excluded.humor_level,
                    verbosity_preference = excluded.verbosity_preference,
                    formality_level = excluded.formality_level,
                    empathy_style = excluded.empathy_style,
                    tool_ack_style = excluded.tool_ack_style,
                    memory_scope = excluded.memory_scope,
                    retrieval_filters = excluded.retrieval_filters,
                    example_dialogues = excluded.example_dialogues,
                    enabled_skills = excluded.enabled_skills,
                    disallowed_behaviors = excluded.disallowed_behaviors,
                    updated_at = excluded.updated_at
                """,
                (
                    persona_id,
                    data.get("display_name", persona_id),
                    data.get("system_identity", ""),
                    data.get("tone_traits", ""),
                    data.get("conversation_style", ""),
                    data.get("speech_style", ""),
                    data.get("humor_level", ""),
                    data.get("verbosity_preference", ""),
                    data.get("formality_level", ""),
                    data.get("empathy_style", ""),
                    data.get("tool_ack_style", ""),
                    data.get("memory_scope", "shared"),
                    data.get("retrieval_filters", ""),
                    data.get("example_dialogues", ""),
                    data.get("enabled_skills", "*"),
                    data.get("disallowed_behaviors", ""),
                    now,
                ),
            )
            conn.commit()
        if data.get("example_dialogues"):
            self._upsert_memory_item(
                item_id=f"persona:{persona_id}:examples",
                text=str(data.get("example_dialogues")),
                metadata={"session_id": "", "kind": "persona_style", "persona_id": persona_id},
            )

    def get_persona(self, persona_id):
        if not persona_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT persona_id, display_name, system_identity, tone_traits, conversation_style,
                       speech_style, humor_level, verbosity_preference, formality_level,
                       empathy_style, tool_ack_style, memory_scope, retrieval_filters,
                       example_dialogues, enabled_skills, disallowed_behaviors, updated_at
                FROM personas
                WHERE persona_id = ?
                """,
                (persona_id,),
            ).fetchone()
        if not row:
            return None
        columns = (
            "persona_id", "display_name", "system_identity", "tone_traits", "conversation_style",
            "speech_style", "humor_level", "verbosity_preference", "formality_level",
            "empathy_style", "tool_ack_style", "memory_scope", "retrieval_filters",
            "example_dialogues", "enabled_skills", "disallowed_behaviors", "updated_at",
        )
        return dict(zip(columns, row))

    def list_personas(self):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT persona_id, display_name, system_identity, tone_traits, conversation_style,
                       speech_style, humor_level, verbosity_preference, formality_level,
                       empathy_style, tool_ack_style, memory_scope, retrieval_filters,
                       example_dialogues, enabled_skills, disallowed_behaviors, updated_at
                FROM personas
                ORDER BY display_name ASC
                """
            ).fetchall()
        columns = (
            "persona_id", "display_name", "system_identity", "tone_traits", "conversation_style",
            "speech_style", "humor_level", "verbosity_preference", "formality_level",
            "empathy_style", "tool_ack_style", "memory_scope", "retrieval_filters",
            "example_dialogues", "enabled_skills", "disallowed_behaviors", "updated_at",
        )
        return [dict(zip(columns, row)) for row in rows]

    def save_session_state(self, session_id, state):
        if not session_id:
            return
        payload = dict(state or {})
        now = _utc_now()
        active_persona_id = str(payload.get("active_persona_id") or "")
        pending_online_json = json.dumps(payload.get("pending_online") or {}, ensure_ascii=True)
        state_json = json.dumps(payload, ensure_ascii=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversation_sessions (
                    session_id, active_persona_id, pending_online_json, state_json, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id)
                DO UPDATE SET
                    active_persona_id = excluded.active_persona_id,
                    pending_online_json = excluded.pending_online_json,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (session_id, active_persona_id, pending_online_json, state_json, now),
            )
            conn.commit()

    def get_session_state(self, session_id):
        if not session_id:
            return {}
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT active_persona_id, pending_online_json, state_json, updated_at
                FROM conversation_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if not row:
            return {}
        active_persona_id, pending_online_json, state_json, updated_at = row
        payload = json.loads(state_json or "{}")
        payload.setdefault("active_persona_id", active_persona_id or "")
        payload.setdefault("pending_online", json.loads(pending_online_json or "{}"))
        payload.setdefault("updated_at", updated_at)
        return payload

    def set_active_persona(self, session_id, persona_id):
        state = self.get_session_state(session_id)
        state["active_persona_id"] = persona_id
        self.save_session_state(session_id, state)

    def get_active_persona_id(self, session_id):
        return (self.get_session_state(session_id) or {}).get("active_persona_id", "")

    def set_pending_online(self, session_id, payload):
        state = self.get_session_state(session_id)
        state["pending_online"] = dict(payload or {})
        self.save_session_state(session_id, state)

    def clear_pending_online(self, session_id):
        state = self.get_session_state(session_id)
        if not state:
            return
        state["pending_online"] = {}
        self.save_session_state(session_id, state)

    # ------------------------------------------------------------------
    # Working artifact — tracks last meaningful capability output
    # ------------------------------------------------------------------

    def save_artifact(self, session_id: str, artifact: "WorkingArtifact") -> None:
        """Persist the working artifact into the session state JSON blob."""
        state = self.get_session_state(session_id) or {}
        state["working_artifact"] = {
            "content": artifact.content,
            "output_type": artifact.output_type,
            "capability_name": artifact.capability_name,
            "artifact_type": artifact.artifact_type,
            "source_path": artifact.source_path,
        }
        self.save_session_state(session_id, state)

    def get_artifact(self, session_id: str) -> "WorkingArtifact | None":
        """Retrieve the current working artifact for this session, or None."""
        state = self.get_session_state(session_id) or {}
        data = state.get("working_artifact")
        if not data:
            return None
        return WorkingArtifact(
            content=data.get("content", ""),
            output_type=data.get("output_type", "text"),
            capability_name=data.get("capability_name", ""),
            artifact_type=data.get("artifact_type", "text"),
            source_path=data.get("source_path", ""),
        )

    # ------------------------------------------------------------------
    # Reference registry — cross-turn entity and ordinal bindings
    # ------------------------------------------------------------------

    def save_reference(self, session_id: str, key: str, value: str) -> None:
        """Save a named reference (ordinal, last_file, active_document) in session state."""
        state = self.get_session_state(session_id) or {}
        refs = state.setdefault("reference_registry", {})
        refs[key] = value
        self.save_session_state(session_id, state)

    def get_reference(self, session_id: str, key: str) -> "str | None":
        """Return a specific reference value, or None if not set."""
        state = self.get_session_state(session_id) or {}
        return state.get("reference_registry", {}).get(key)

    def get_all_references(self, session_id: str) -> dict:
        """Return the full reference registry dict for this session."""
        state = self.get_session_state(session_id) or {}
        return dict(state.get("reference_registry", {}))

    def log_online_permission(self, session_id, tool_name, decision, reason=""):
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO online_permission_events (
                    session_id, tool_name, decision, reason, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (session_id or "", tool_name or "", decision or "", reason or "", now),
            )
            conn.commit()

    def store_memory_item(self, session_id, content, memory_type="episodic", persona_id="", sensitivity="safe_auto", metadata=None):
        if not content:
            return
        payload = dict(metadata or {})
        item_id = str(payload.get("item_id") or uuid.uuid4())
        now = _utc_now()
        content_text = str(content).strip()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_items (
                    item_id, session_id, persona_id, memory_type, sensitivity,
                    content, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id)
                DO UPDATE SET
                    session_id = excluded.session_id,
                    persona_id = excluded.persona_id,
                    memory_type = excluded.memory_type,
                    sensitivity = excluded.sensitivity,
                    content = excluded.content,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    item_id,
                    session_id or "",
                    persona_id or "",
                    memory_type or "episodic",
                    sensitivity or "safe_auto",
                    content_text,
                    json.dumps(payload, ensure_ascii=True),
                    now,
                    now,
                ),
            )
            conn.commit()
        self._upsert_memory_item(
            item_id=f"memory:{item_id}",
            text=content_text,
            metadata={
                "session_id": session_id or "",
                "persona_id": persona_id or "",
                "kind": memory_type or "episodic",
                "sensitivity": sensitivity or "safe_auto",
            },
        )

    def recent_memory_items(self, session_id, limit=6, persona_id=None):
        params = [session_id or ""]
        query = """
            SELECT item_id, session_id, persona_id, memory_type, sensitivity, content, metadata_json, created_at, updated_at
            FROM memory_items
            WHERE session_id = ?
        """
        if persona_id:
            query += " AND (persona_id = ? OR persona_id = '')"
            params.append(persona_id)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        items = []
        for row in rows:
            item_id, sid, pid, memory_type, sensitivity, content, metadata_json, created_at, updated_at = row
            items.append(
                {
                    "item_id": item_id,
                    "session_id": sid,
                    "persona_id": pid,
                    "memory_type": memory_type,
                    "sensitivity": sensitivity,
                    "content": content,
                    "metadata": json.loads(metadata_json or "{}"),
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
            )
        return items

    def semantic_recall(self, query, session_id, limit=3):
        if not query:
            return []
        if self._vector_available and self._vector_collection is not None:
            try:
                response = self._vector_collection.query(
                    query_texts=[query],
                    n_results=max(1, int(limit)),
                    where={"session_id": session_id},
                )
                documents = response.get("documents", [[]])[0]
                return [doc for doc in documents if doc]
            except Exception:
                pass
        return self._fallback_semantic_recall(query, session_id, limit=limit)

    def summarize_session(self, session_id, limit=6):
        if not session_id:
            return ""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, text
                FROM turns
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, max(1, int(limit))),
            ).fetchall()
        if not rows:
            return ""
        rows = list(reversed(rows))
        return "\n".join(f"{role}: {text}" for role, text in rows)

    def get_workflow_summary(self, session_id):
        active = self.get_active_workflow(session_id)
        if not active:
            return ""
        pending = ", ".join(active.get("pending_slots") or [])
        summary = active.get("result_summary") or ""
        if pending:
            summary = f"{summary} Pending: {pending}.".strip()
        return f"{active['workflow_name']}: {summary}".strip()

    def _row_to_workflow(self, row):
        workflow_name, status, pending_slots_json, last_action, target_json, result_summary, state_json, updated_at = row
        state = json.loads(state_json or "{}")
        state.setdefault("workflow_name", workflow_name)
        state.setdefault("status", status)
        state.setdefault("pending_slots", json.loads(pending_slots_json or "[]"))
        state.setdefault("last_action", last_action or "")
        state.setdefault("target", json.loads(target_json or "{}"))
        state.setdefault("result_summary", result_summary or "")
        state.setdefault("updated_at", updated_at)
        return state

    def prune_old_turns(self, session_id, older_than_days=30):
        """Delete turns older than *older_than_days* days for *session_id*.

        Phase 7: episodic rolling-window pruning.
        Returns number of rows deleted.
        """
        import datetime as _dt
        cutoff = (_dt.datetime.utcnow() - _dt.timedelta(days=older_than_days)).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM turns WHERE session_id = ? AND created_at < ?",
                (session_id, cutoff),
            )
            conn.commit()
        return cur.rowcount

    def delete_memory_item(self, item_id):
        """Remove a memory item by its item_id.

        Phase 7: used by SemanticMemory.forget() and prune().
        """
        with self._connect() as conn:
            conn.execute("DELETE FROM memory_items WHERE item_id = ?", (item_id,))
            conn.commit()

    def prune_low_confidence_memories(self, session_id, min_confidence=0.5):
        """Remove semantic memory items whose confidence < *min_confidence*.

        Phase 7: floor-pruning for semantic memory store.
        Returns number of rows deleted.
        """
        items = self.recent_memory_items(session_id, limit=500) or []
        removed = 0
        for item in items:
            if item.get("memory_type") != "semantic":
                continue
            meta = item.get("metadata") or {}
            conf = float(meta.get("confidence", 1.0))
            if conf < min_confidence:
                self.delete_memory_item(item["item_id"])
                removed += 1
        return removed

    def get_facts_by_namespace(self, namespace="general"):
        """Return all facts in *namespace* as list of {key, value} dicts.

        Phase 7: used by ProceduralMemory to reload persisted success rates.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value FROM facts WHERE namespace = ? ORDER BY updated_at DESC",
                (namespace,),
            ).fetchall()
        return [{"key": k, "value": v} for k, v in rows]

    def _fallback_semantic_recall(self, query, session_id, limit=3):
        query_tokens = Counter(_tokenize(query))
        if not query_tokens:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT text
                FROM turns
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT 50
                """,
                (session_id,),
            ).fetchall()
            facts = conn.execute(
                """
                SELECT key, value
                FROM facts
                WHERE session_id = ? OR session_id = ''
                ORDER BY updated_at DESC
                LIMIT 20
                """,
                (session_id,),
            ).fetchall()
        candidates = [text for (text,) in rows if text]
        candidates.extend(f"{key}: {value}" for key, value in facts if key)
        scored = []
        for text in candidates:
            tokens = Counter(_tokenize(text))
            overlap = sum(min(query_tokens[token], tokens[token]) for token in query_tokens)
            if overlap:
                scored.append((overlap, text))
        scored.sort(key=lambda item: (-item[0], -len(item[1])))
        unique = []
        seen = set()
        for _, text in scored:
            if text not in seen:
                unique.append(text)
                seen.add(text)
            if len(unique) >= limit:
                break
        return unique

    def _ensure_storage(self):
        _db_dir = os.path.dirname(self.db_path)
        if _db_dir:
            os.makedirs(_db_dir, exist_ok=True)
        os.makedirs(self.vector_path, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workflows (
                    session_id TEXT NOT NULL,
                    workflow_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    pending_slots_json TEXT NOT NULL DEFAULT '[]',
                    last_action TEXT NOT NULL DEFAULT '',
                    target_json TEXT NOT NULL DEFAULT '{}',
                    result_summary TEXT NOT NULL DEFAULT '',
                    state_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, workflow_name)
                );

                CREATE TABLE IF NOT EXISTS facts (
                    session_id TEXT NOT NULL DEFAULT '',
                    namespace TEXT NOT NULL DEFAULT 'general',
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, namespace, key)
                );

                CREATE TABLE IF NOT EXISTS personas (
                    persona_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    system_identity TEXT NOT NULL DEFAULT '',
                    tone_traits TEXT NOT NULL DEFAULT '',
                    conversation_style TEXT NOT NULL DEFAULT '',
                    speech_style TEXT NOT NULL DEFAULT '',
                    humor_level TEXT NOT NULL DEFAULT '',
                    verbosity_preference TEXT NOT NULL DEFAULT '',
                    formality_level TEXT NOT NULL DEFAULT '',
                    empathy_style TEXT NOT NULL DEFAULT '',
                    tool_ack_style TEXT NOT NULL DEFAULT '',
                    memory_scope TEXT NOT NULL DEFAULT 'shared',
                    retrieval_filters TEXT NOT NULL DEFAULT '',
                    example_dialogues TEXT NOT NULL DEFAULT '',
                    enabled_skills TEXT NOT NULL DEFAULT '*',
                    disallowed_behaviors TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    active_persona_id TEXT NOT NULL DEFAULT '',
                    pending_online_json TEXT NOT NULL DEFAULT '{}',
                    state_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS online_permission_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL DEFAULT '',
                    tool_name TEXT NOT NULL DEFAULT '',
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_items (
                    item_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL DEFAULT '',
                    persona_id TEXT NOT NULL DEFAULT '',
                    memory_type TEXT NOT NULL DEFAULT 'episodic',
                    sensitivity TEXT NOT NULL DEFAULT 'safe_auto',
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_vector_store(self):
        try:
            import chromadb

            client = chromadb.PersistentClient(path=self.vector_path)
            self._vector_collection = client.get_or_create_collection(
                name="friday_memory",
                embedding_function=HashEmbeddingFunction(),
            )
            self._vector_available = True
        except Exception:
            self._vector_collection = None
            self._vector_available = False

    def _upsert_memory_item(self, item_id, text, metadata):
        if not text:
            return
        if self._vector_available and self._vector_collection is not None:
            try:
                self._vector_collection.upsert(
                    ids=[item_id],
                    documents=[text],
                    metadatas=[metadata],
                )
                return
            except Exception:
                self._vector_available = False
