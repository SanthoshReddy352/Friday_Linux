import hashlib
import json
import math
import os
import sqlite3
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _project_root():
    return os.path.dirname(os.path.dirname(__file__))


def _default_db_path():
    return os.path.join(_project_root(), "data", "friday.db")


def _default_vector_path():
    return os.path.join(_project_root(), "data", "chroma")


def _tokenize(text):
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(text or ""))
    return [token for token in cleaned.split() if len(token) > 1]


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
        return self._row_to_workflow(row)

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
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
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

