"""AgentHierarchy — lightweight multi-agent registry.

Mirrors jarvis src/agents/hierarchy.ts + task-manager.ts, but adapted for
FRIDAY's single-process architecture using ThreadPoolExecutor for background
sub-agents rather than a separate sidecar process.

Architecture:
  AgentNode         — represents one agent (primary + any sub-agents)
  AgentHierarchy    — manages the parent-child tree
  AgentTaskManager  — launches/tracks background sub-agents
  SubAgentRunner    — executes an agent loop in a thread

Typical flow:
  1. FridayApp creates primary node on boot.
  2. User asks "research X in the background" → AgentTaskManager.launch()
     returns a task_id immediately, posts an agent_message to MemoryService.
  3. SubAgentRunner executes the task in a daemon thread.
  4. On completion it posts a report agent_message back to the primary.
"""
from __future__ import annotations

import concurrent.futures
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from core.logger import logger


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentNode:
    agent_id: str
    name: str
    role: str = "general"
    parent_id: str = ""
    status: str = "idle"        # idle | running | completed | failed
    current_task: str = ""
    authority_level: int = 1
    created_at: str = field(default_factory=_utc_now)


class AgentHierarchy:
    """Maintains the tree of active agents."""

    def __init__(self):
        self._nodes: dict[str, AgentNode] = {}
        self._lock = threading.RLock()

    def add_agent(self, node: AgentNode) -> None:
        with self._lock:
            self._nodes[node.agent_id] = node

    def remove_agent(self, agent_id: str, recursive: bool = True) -> None:
        with self._lock:
            if recursive:
                children = self.get_children(agent_id)
                for child in children:
                    self.remove_agent(child.agent_id, recursive=True)
            self._nodes.pop(agent_id, None)

    def get_children(self, parent_id: str) -> list[AgentNode]:
        with self._lock:
            return [n for n in self._nodes.values() if n.parent_id == parent_id]

    def get_parent(self, agent_id: str) -> AgentNode | None:
        with self._lock:
            node = self._nodes.get(agent_id)
            if node and node.parent_id:
                return self._nodes.get(node.parent_id)
            return None

    def get_primary(self) -> AgentNode | None:
        with self._lock:
            for n in self._nodes.values():
                if not n.parent_id:
                    return n
            return None

    def get_tree(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "agent_id": n.agent_id,
                    "name": n.name,
                    "role": n.role,
                    "parent_id": n.parent_id,
                    "status": n.status,
                    "current_task": n.current_task,
                }
                for n in self._nodes.values()
            ]

    def update_status(self, agent_id: str, status: str, task: str = "") -> None:
        with self._lock:
            node = self._nodes.get(agent_id)
            if node:
                node.status = status
                if task:
                    node.current_task = task


@dataclass
class AgentTask:
    task_id: str
    agent_id: str
    description: str
    status: str = "running"     # running | completed | failed
    result: str = ""
    created_at: str = field(default_factory=_utc_now)
    completed_at: str = ""


class AgentTaskManager:
    """Launches background sub-agents and tracks their completion.

    Mirrors jarvis AgentTaskManager (src/agents/task-manager.ts).
    Background tasks run in a shared daemon thread pool.
    """

    _CLEANUP_AFTER_MINUTES = 10
    _MAX_WORKERS = 3

    def __init__(self, hierarchy: AgentHierarchy, memory_service=None):
        self._hierarchy = hierarchy
        self._memory = memory_service
        self._tasks: dict[str, AgentTask] = {}
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self._MAX_WORKERS, thread_name_prefix="friday-agent"
        )
        self._lock = threading.RLock()

    def launch(
        self,
        description: str,
        fn: Callable[[], str],
        parent_id: str = "",
        role: str = "worker",
    ) -> str:
        """Launch a background sub-agent. Returns task_id immediately."""
        task_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        node = AgentNode(
            agent_id=agent_id,
            name=f"sub-agent:{role}",
            role=role,
            parent_id=parent_id,
            status="running",
            current_task=description,
        )
        self._hierarchy.add_agent(node)

        task = AgentTask(task_id=task_id, agent_id=agent_id, description=description)
        with self._lock:
            self._tasks[task_id] = task

        if self._memory:
            try:
                self._memory.post_agent_message(
                    from_agent=parent_id or "friday",
                    to_agent=agent_id,
                    msg_type="task",
                    content=description,
                )
            except Exception:
                pass

        self._pool.submit(self._run, task_id, agent_id, fn)
        logger.info("[AgentTaskManager] launched task %s: %s", task_id[:8], description[:60])
        return task_id

    def _run(self, task_id: str, agent_id: str, fn: Callable[[], str]) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        try:
            result = fn()
            with self._lock:
                task.status = "completed"
                task.result = str(result or "")[:2000]
                task.completed_at = _utc_now()
            self._hierarchy.update_status(agent_id, "completed")
            if self._memory:
                try:
                    self._memory.post_agent_message(
                        from_agent=agent_id,
                        to_agent="friday",
                        msg_type="report",
                        content=task.result,
                    )
                except Exception:
                    pass
            logger.info("[AgentTaskManager] task %s completed", task_id[:8])
        except Exception as exc:
            with self._lock:
                task.status = "failed"
                task.result = str(exc)[:500]
                task.completed_at = _utc_now()
            self._hierarchy.update_status(agent_id, "failed")
            logger.warning("[AgentTaskManager] task %s failed: %s", task_id[:8], exc)

    def get_task(self, task_id: str) -> AgentTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_running(self) -> list[AgentTask]:
        with self._lock:
            return [t for t in self._tasks.values() if t.status == "running"]

    def list_completed(self) -> list[AgentTask]:
        with self._lock:
            return [t for t in self._tasks.values() if t.status in ("completed", "failed")]

    def cleanup_old(self) -> int:
        import time
        now = time.time()
        removed = 0
        with self._lock:
            for tid in list(self._tasks.keys()):
                task = self._tasks[tid]
                if task.status in ("completed", "failed") and task.completed_at:
                    try:
                        ts = datetime.fromisoformat(task.completed_at).timestamp()
                        if now - ts > self._CLEANUP_AFTER_MINUTES * 60:
                            del self._tasks[tid]
                            self._hierarchy.remove_agent(task.agent_id)
                            removed += 1
                    except Exception:
                        pass
        return removed

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)
