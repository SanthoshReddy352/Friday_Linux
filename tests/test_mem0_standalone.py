"""Standalone Mem0 verification tests.

Run with the venv Python to check whether the full Mem0 stack is working:

    .venv/bin/python3 -m pytest tests/test_mem0_standalone.py -v

Or to also test against a running extraction server (memory.enabled: true in config):

    .venv/bin/python3 tests/test_mem0_standalone.py

Tests are organised from fast/cheap (no server needed) to full (server required).
"""
from __future__ import annotations

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8181
_TEST_USER = "mem0_test_user"
_CHROMA_PATH = "data/chroma"
_HISTORY_DB = "data/mem0_history.db"


def _server_running(host=_DEFAULT_HOST, port=_DEFAULT_PORT) -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"http://{host}:{port}/v1/models", timeout=2.0)
        return True
    except Exception:
        return False


def _make_client(host=_DEFAULT_HOST, port=_DEFAULT_PORT):
    """Build a Mem0 Memory client pointed at the local extraction server."""
    from mem0 import Memory
    config = {
        "llm": {
            "provider": "litellm",
            "config": {
                "model": "openai/qwen3-4b",
                "openai_api_base": f"http://{host}:{port}/v1",
                "openai_api_key": "not-needed",
                "temperature": 0.1,
                "max_tokens": 256,
                "top_p": 0.1,
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {"model": "sentence-transformers/all-MiniLM-L6-v2"},
        },
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "friday_mem0_test",
                "path": _CHROMA_PATH,
            },
        },
        "history_db_path": _HISTORY_DB,
    }
    return Memory.from_config(config)


# ---------------------------------------------------------------------------
# T-M1: mem0ai package is importable
# ---------------------------------------------------------------------------

class TestMem0Package(unittest.TestCase):
    def test_mem0_importable(self):
        """mem0ai must be installed in the current Python environment."""
        try:
            import mem0  # noqa: F401
        except ImportError:
            self.skipTest(
                "mem0ai is not installed. Run: .venv/bin/pip install mem0ai litellm"
            )

    def test_mem0_version_present(self):
        try:
            import mem0
        except ImportError:
            self.skipTest("mem0ai not installed")
        ver = getattr(mem0, "__version__", None)
        self.assertIsNotNone(ver, "mem0 has no __version__ attribute")
        print(f"\n  mem0 version: {ver}")


# ---------------------------------------------------------------------------
# T-M2: ChromaDB is importable and writable
# ---------------------------------------------------------------------------

class TestChromaDB(unittest.TestCase):
    def test_chromadb_importable(self):
        try:
            import chromadb  # noqa: F401
        except ImportError:
            self.skipTest(
                "chromadb not installed. Run: .venv/bin/pip install chromadb"
            )

    def test_chromadb_can_create_collection(self):
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            self.skipTest("chromadb not installed")
        client = chromadb.PersistentClient(
            path=_CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        col = client.get_or_create_collection("mem0_smoke_test")
        self.assertIsNotNone(col)
        print(f"\n  Chroma path: {_CHROMA_PATH} — collection created OK")


# ---------------------------------------------------------------------------
# T-M3: Sentence-transformer embedder
# ---------------------------------------------------------------------------

class TestEmbedder(unittest.TestCase):
    def test_sentence_transformers_importable(self):
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            self.skipTest(
                "sentence-transformers not installed. "
                "Run: .venv/bin/pip install sentence-transformers"
            )

    def test_embedder_produces_vector(self):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            self.skipTest("sentence-transformers not installed")
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        vec = model.encode(["FRIDAY is a local AI assistant."])
        self.assertEqual(len(vec), 1)
        self.assertGreater(len(vec[0]), 0)
        print(f"\n  Embedding dim: {len(vec[0])}")


# ---------------------------------------------------------------------------
# T-M4: Extraction server connectivity (skipped when server is not running)
# ---------------------------------------------------------------------------

class TestExtractionServer(unittest.TestCase):
    def setUp(self):
        if not _server_running():
            self.skipTest(
                f"Extraction server not running at {_DEFAULT_HOST}:{_DEFAULT_PORT}. "
                "Start it with: scripts/start_mem0_server.sh  "
                "OR set memory.enabled: true in config.yaml and restart FRIDAY."
            )

    def test_server_lists_models(self):
        import urllib.request, json
        resp = urllib.request.urlopen(
            f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}/v1/models", timeout=5.0
        )
        data = json.loads(resp.read())
        self.assertIn("data", data)
        print(f"\n  Models on server: {[m['id'] for m in data.get('data', [])]}")

    def test_server_accepts_completion(self):
        import urllib.request, json
        payload = json.dumps({
            "model": "qwen3-4b",
            "messages": [{"role": "user", "content": "Say: OK"}],
            "max_tokens": 10,
            "temperature": 0.0,
        }).encode()
        req = urllib.request.Request(
            f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30.0)
        data = json.loads(resp.read())
        reply = data["choices"][0]["message"]["content"]
        self.assertIsInstance(reply, str)
        self.assertGreater(len(reply), 0)
        print(f"\n  Server reply: {reply!r}")


# ---------------------------------------------------------------------------
# T-M5: Full Mem0 client — add and retrieve a memory (server required)
# ---------------------------------------------------------------------------

class TestMem0ClientFull(unittest.TestCase):
    def setUp(self):
        if not _server_running():
            self.skipTest(
                "Extraction server not running — skipping full client test. "
                "Run T-M4 server tests first."
            )
        self.client = _make_client()

    def test_add_memory(self):
        result = self.client.add(
            "My name is FRIDAY test. I prefer concise answers.",
            user_id=_TEST_USER,
        )
        self.assertIsNotNone(result)
        print(f"\n  add() result: {result}")

    def test_search_retrieves_added_memory(self):
        # Add first, then search
        self.client.add("FRIDAY test prefers metric units.", user_id=_TEST_USER)
        time.sleep(1.0)  # allow async write to settle

        results = self.client.search("units preference", user_id=_TEST_USER, limit=5)
        memories = results.get("results", []) if isinstance(results, dict) else results
        texts = [m.get("memory", "") for m in memories]
        self.assertTrue(
            any("metric" in t.lower() or "units" in t.lower() for t in texts),
            f"Expected 'metric' in memories, got: {texts}",
        )
        print(f"\n  search() found {len(texts)} result(s)")

    def test_get_all_returns_list(self):
        results = self.client.get_all(user_id=_TEST_USER)
        memories = results.get("results", []) if isinstance(results, dict) else results
        self.assertIsInstance(memories, list)
        print(f"\n  get_all() returned {len(memories)} memories for user '{_TEST_USER}'")

    def tearDown(self):
        # Clean up test memories
        try:
            results = self.client.get_all(user_id=_TEST_USER)
            memories = results.get("results", []) if isinstance(results, dict) else results
            for m in memories:
                mid = m.get("id")
                if mid:
                    self.client.delete(mid)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# T-M6: TurnGatedMemoryExtractor — queue + drain (no server needed)
# ---------------------------------------------------------------------------

class TestTurnGatedMemoryExtractor(unittest.TestCase):
    def test_extractor_queues_without_server(self):
        """Extractor must never crash even when the mem0 client is broken."""
        from unittest.mock import MagicMock
        from core.memory_extractor import TurnGatedMemoryExtractor

        broken_client = MagicMock()
        broken_client.add.side_effect = RuntimeError("server down")

        feedback = MagicMock()
        feedback.active_turns = 0

        extractor = TurnGatedMemoryExtractor(broken_client, feedback)
        extractor.queue_turn("Hello Friday", "Hi there!")
        time.sleep(0.2)

        extractor.stop()
        # If we reach this line without an exception, the extractor handled the failure silently.

    def test_extractor_calls_mem0_add_on_drain(self):
        from unittest.mock import MagicMock, patch
        from core.memory_extractor import TurnGatedMemoryExtractor

        calls = []

        mock_client = MagicMock()
        mock_client.add.side_effect = lambda messages, user_id: calls.append(messages) or {}

        feedback = MagicMock()
        feedback.active_turns = 0

        extractor = TurnGatedMemoryExtractor(mock_client, feedback)
        extractor.queue_turn("What is the weather?", "It is sunny today.", user_id="default")
        time.sleep(0.5)
        extractor.stop()

        self.assertGreater(len(calls), 0, "mem0.add() was never called after queuing a turn")


# ---------------------------------------------------------------------------
# T-M7: MemoryService integration — retrieval with Mem0
# ---------------------------------------------------------------------------

class TestMemoryServiceWithMem0(unittest.TestCase):
    def test_memory_service_calls_mem0_search(self):
        from unittest.mock import MagicMock
        from core.memory_service import MemoryService
        from core.context_store import ContextStore

        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [{"memory": "User prefers dark mode.", "score": 0.9}]
        }

        store = ContextStore(db_path=":memory:")
        svc = MemoryService(store, memory_broker=None, mem0_client=mock_client)

        context = svc.build_context_bundle("what theme do you prefer")
        mem_facts = context.get("mem0_facts", [])
        self.assertIsInstance(mem_facts, list)
        # search should have been called with the query text
        mock_client.search.assert_called_once()
        print(f"\n  mem0_facts injected: {mem_facts}")


# ---------------------------------------------------------------------------
# CLI entry point — run all tests and print a summary
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("FRIDAY Mem0 Verification Suite")
    print("=" * 60)
    print(f"Python: {sys.executable}")
    print(f"Server: {_DEFAULT_HOST}:{_DEFAULT_PORT} — ", end="")
    print("RUNNING" if _server_running() else "NOT RUNNING (server tests will be skipped)")
    print("=" * 60)
    unittest.main(verbosity=2)
