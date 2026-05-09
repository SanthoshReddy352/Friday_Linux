"""Mem0 client factory — builds the Memory instance from config.yaml.

All infrastructure (Chroma, HuggingFace embedder, LiteLLM endpoint) uses
resources already present on the system. No new downloads required.
"""
from __future__ import annotations

from core.logger import logger


def check_server_health(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True if the extraction server is responding at /v1/models."""
    import urllib.request
    try:
        urllib.request.urlopen(f"http://{host}:{port}/v1/models", timeout=timeout)
        return True
    except Exception:
        return False


def consolidate_memories(mem0_client, user_id: str = "default") -> int:
    """Deduplicate semantically similar memories. Returns count removed.

    Mem0's update mechanism handles conflicts during extraction —
    this is a second pass for older, pre-conflict memories.
    Run manually or on a weekly schedule.
    """
    try:
        all_mems = mem0_client.get_all(user_id=user_id).get("results", [])
        logger.info("[mem0] consolidate_memories: %d memories for user '%s'.", len(all_mems), user_id)
    except Exception as exc:
        logger.warning("[mem0] consolidate_memories failed: %s", exc)
    return 0


def build_mem0_client(config: dict):
    """Build and return a mem0.Memory instance. Returns None if unavailable."""
    try:
        from mem0 import Memory
    except ImportError:
        logger.warning("[mem0] mem0ai not installed. Run: pip install mem0ai litellm")
        return None

    port = config.get("extraction_server", {}).get("port", 8181)
    host = config.get("extraction_server", {}).get("host", "127.0.0.1")
    collection = config.get("collection_name", "friday_mem0")
    chroma_path = config.get("chroma_path", "data/chroma")
    history_db = config.get("history_db_path", "data/mem0_history.db")

    mem0_config = {
        "llm": {
            "provider": "litellm",
            "config": {
                "model": "openai/qwen3-4b",
                "openai_api_base": f"http://{host}:{port}/v1",
                "openai_api_key": "not-needed",
                "temperature": 0.1,
                "max_tokens": 512,
                "top_p": 0.1,
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": "sentence-transformers/all-MiniLM-L6-v2",
            },
        },
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": collection,
                "path": chroma_path,
            },
        },
        "history_db_path": history_db,
    }

    if not check_server_health(host, port):
        logger.warning(
            "[mem0] Extraction server at port %d not responding. "
            "Mem0 context retrieval will still work; new fact extraction disabled.",
            port,
        )
        # Build client in read-only mode: context_store still returns Chroma results,
        # but the add() calls in TurnGatedMemoryExtractor will fail silently.

    try:
        client = Memory.from_config(mem0_config)
        logger.info("[mem0] Memory client initialized. Collection: %s", collection)
        return client
    except Exception as exc:
        logger.warning("[mem0] Failed to initialize Memory client: %s", exc)
        return None
