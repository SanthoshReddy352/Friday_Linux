"""DocumentStore — Chroma collection + SQLite metadata for indexed documents.

Uses the existing Chroma instance at data/chroma/ (same path as ContextStore).
Collection: "friday_documents" — isolated from the semantic memory collection.
Metadata table in data/friday.db via its own connection (no schema collision).
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path

COLLECTION_NAME = "friday_documents"
DB_PATH = "data/friday.db"
CHROMA_PATH = "data/chroma"


class DocumentStore:
    def __init__(self, chroma_path: str = CHROMA_PATH, db_path: str = DB_PATH):
        import chromadb
        from chromadb.config import Settings

        self._client = chromadb.PersistentClient(
            path=chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._db_path = db_path
        self._init_table()

    def _init_table(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS indexed_documents (
                    file_id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    document_type TEXT,
                    title TEXT,
                    chunk_count INTEGER DEFAULT 0,
                    indexed_at TEXT,
                    modified_at TEXT,
                    workspace TEXT DEFAULT 'default'
                )
            """)
            conn.commit()

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def is_indexed(self, file_path: str) -> bool:
        file_hash = self._hash_file(file_path)
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT file_hash FROM indexed_documents WHERE path = ?",
                (str(file_path),),
            ).fetchone()
        return row is not None and row[0] == file_hash

    def add_chunks(self, file_path: str, chunks: list[dict], workspace: str = "default") -> None:
        """Upsert chunks into Chroma and record metadata in SQLite."""
        path = Path(file_path)
        file_hash = self._hash_file(str(path))
        file_id = hashlib.md5(str(path).encode()).hexdigest()

        from modules.document_intel.embedder import embed_batch
        texts = [c["text"] for c in chunks]
        embeddings = embed_batch(texts)

        ids = [f"{file_id}_chunk_{c['chunk_index']}" for c in chunks]
        metadatas = [
            {
                "path": str(path),
                "heading": c.get("heading", ""),
                "chunk_index": c["chunk_index"],
                "workspace": workspace,
            }
            for c in chunks
        ]

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO indexed_documents
                    (file_id, path, file_hash, document_type, title, chunk_count,
                     indexed_at, modified_at, workspace)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                    file_hash = excluded.file_hash,
                    chunk_count = excluded.chunk_count,
                    indexed_at = excluded.indexed_at,
                    modified_at = excluded.modified_at
                """,
                (
                    file_id, str(path), file_hash,
                    path.suffix.lstrip("."),
                    path.stem, len(chunks),
                    now, now, workspace,
                ),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        question_embedding: list[float],
        top_k: int = 4,
        workspace: str | None = None,
    ) -> list[dict]:
        where = {"workspace": workspace} if workspace else None
        results = self._collection.query(
            query_embeddings=[question_embedding],
            n_results=min(top_k, 10),
            where=where,
        )
        if not results["documents"] or not results["documents"][0]:
            return []
        return [
            {
                "text": doc,
                "source_file": meta.get("path", ""),
                "heading": meta.get("heading", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "score": float(dist),
            }
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_file(path: str) -> str:
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(65536), b""):
                    h.update(block)
        except OSError:
            return ""
        return h.hexdigest()
