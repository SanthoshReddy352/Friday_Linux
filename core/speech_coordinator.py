from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class SpeechTurnState:
    turn_id: str
    ack_spoken: bool = False
    progress_count: int = 0
    final_spoken: bool = False
    streamed_chunks: int = 0
    interrupted: bool = False
    spoken_texts: set[str] = field(default_factory=set)


class SpeechCoordinator:
    """
    Coordinates per-turn speech so acknowledgement, progress, streamed chunks,
    and final responses do not fight each other.
    """

    def __init__(self, app):
        self.app = app
        self._lock = threading.RLock()
        self._turns: dict[str, SpeechTurnState] = {}
        bus = app.event_bus
        bus.subscribe("turn_started", self.handle_turn_started)
        bus.subscribe("assistant_ack", self.handle_ack)
        bus.subscribe("assistant_progress", self.handle_progress)
        bus.subscribe("llm_first_token", self.handle_stream_marker)
        bus.subscribe("turn_completed", self.handle_turn_completed)
        bus.subscribe("turn_failed", self.handle_turn_failed)

    def handle_turn_started(self, payload):
        turn_id = self._turn_id(payload)
        if not turn_id:
            return
        with self._lock:
            self._turns[turn_id] = SpeechTurnState(turn_id=turn_id)

    def handle_ack(self, payload):
        self._speak_once(payload, kind="ack")

    def handle_progress(self, payload):
        turn_id = self._turn_id(payload)
        if not turn_id:
            return
        with self._lock:
            state = self._turns.setdefault(turn_id, SpeechTurnState(turn_id=turn_id))
            state.progress_count += 1
        self._speak_once(payload, kind="progress")

    def handle_stream_marker(self, payload):
        turn_id = self._turn_id(payload)
        if not turn_id:
            return
        with self._lock:
            state = self._turns.setdefault(turn_id, SpeechTurnState(turn_id=turn_id))
            state.streamed_chunks += 1

    def handle_turn_completed(self, payload):
        if not isinstance(payload, dict) or not payload.get("speak_final", True):
            return
        text = payload.get("response", "")
        if not text:
            return
        self._speak_once({"turn_id": payload.get("turn_id"), "text": text}, kind="final")

    def handle_turn_failed(self, payload):
        text = "I ran into a problem handling that."
        if isinstance(payload, dict) and payload.get("error"):
            text = f"I ran into a problem: {payload['error']}"
        self._speak_once({"turn_id": self._turn_id(payload), "text": text}, kind="final")

    def mark_interrupted(self, turn_id: str):
        if not turn_id:
            return
        with self._lock:
            state = self._turns.setdefault(turn_id, SpeechTurnState(turn_id=turn_id))
            state.interrupted = True

    def _speak_once(self, payload, kind: str):
        if not isinstance(payload, dict):
            return
        turn_id = self._turn_id(payload)
        text = str(payload.get("text") or "").strip()
        if not text:
            return
        key = " ".join(text.lower().split())
        with self._lock:
            state = self._turns.setdefault(turn_id or "", SpeechTurnState(turn_id=turn_id or ""))
            if state.interrupted or key in state.spoken_texts:
                return
            if kind == "ack" and state.ack_spoken:
                return
            if kind == "final" and state.final_spoken:
                return
            state.spoken_texts.add(key)
            if kind == "ack":
                state.ack_spoken = True
            if kind == "final":
                state.final_spoken = True
        self.app.event_bus.publish("voice_response", text)

    def _turn_id(self, payload):
        if isinstance(payload, dict):
            return str(payload.get("turn_id") or "")
        return ""
