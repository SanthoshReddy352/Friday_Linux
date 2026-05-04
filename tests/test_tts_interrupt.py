"""
tests/test_tts_interrupt.py
Tests for the interruptible TextToSpeech engine.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import time
import threading
import pytest
from unittest.mock import patch, MagicMock


# We patch subprocess.Popen so no real audio is played during tests
class FakePopen:
    def __init__(self, *args, **kwargs):
        self._killed = False
        self.stdin = MagicMock()
        self.stdout = MagicMock()
        self.stderr = MagicMock()

    def wait(self, timeout=None):
        # Simulate a long-running process; checks killed flag
        for _ in range(100):
            if self._killed:
                return
            time.sleep(0.05)

    def poll(self):
        return None if not self._killed else 0

    def kill(self):
        self._killed = True

    def terminate(self):
        self._killed = True


@pytest.fixture
def tts():
    from modules.voice_io.tts import TextToSpeech
    app_core = MagicMock()
    app_core.is_speaking = False
    t = TextToSpeech(app_core)
    # Point to dummy paths so _check_files() passes
    t.model_path = "/tmp/dummy.onnx"
    t.piper_path = "/tmp/dummy_piper"
    t.aplay_path = "/usr/bin/aplay"
    t._runtime_prepared = True
    return t


def test_speak_chunked_sets_is_speaking(tts):
    """speak_chunked should set is_speaking=True while active."""
    fake_piper = FakePopen()
    fake_aplay = FakePopen()
    with patch("os.path.exists", return_value=True), \
         patch("subprocess.Popen", side_effect=[fake_piper, fake_aplay]):
        tts.speak_chunked("Hello. How are you?")
        time.sleep(0.1)
        assert tts.is_speaking is True


def test_stop_kills_speech(tts):
    """stop() should set is_speaking=False within 1 second."""
    fake_piper = FakePopen()
    fake_aplay = FakePopen()
    with patch("os.path.exists", return_value=True), \
         patch("subprocess.Popen", side_effect=[fake_piper, fake_aplay]):
        tts.speak_chunked("This is a long sentence. And another one. And yet another.")
        time.sleep(0.15)
        assert tts.is_speaking is True

        tts.stop()
        time.sleep(0.3)
        assert tts.is_speaking is False


def test_interrupt_event_set_on_stop(tts):
    """stop() must set interrupt_event."""
    tts.interrupt_event.clear()
    with patch("os.path.exists", return_value=True):
        tts.stop()
        assert tts.interrupt_event.is_set()


def test_speak_chunked_finishes_naturally(tts):
    """With fast (instant) subprocess, all sentences complete and is_speaking goes False."""
    class InstantPopen(FakePopen):
        def wait(self):
            return  # returns immediately

    fake_piper_1 = InstantPopen()
    fake_aplay_1 = InstantPopen()
    fake_piper_2 = InstantPopen()
    fake_aplay_2 = InstantPopen()
    with patch("os.path.exists", return_value=True), \
         patch("subprocess.Popen", side_effect=[fake_piper_1, fake_aplay_1, fake_piper_2, fake_aplay_2]):
        tts.speak_chunked("Sentence one. Sentence two.")
        # Wait for thread to finish
        for _ in range(20):
            if not tts.is_speaking:
                break
            time.sleep(0.05)
        assert tts.is_speaking is False


def test_split_sentences():
    """Sentence splitter should handle various punctuation."""
    from modules.voice_io.tts import _split_sentences
    result = _split_sentences("Hello. How are you? I am fine!")
    assert len(result) == 3
    assert result[0] == "Hello."
    assert result[2] == "I am fine!"


def test_split_sentences_single():
    from modules.voice_io.tts import _split_sentences
    result = _split_sentences("Just one sentence")
    assert len(result) == 1


def test_sanitize_for_speech_strips_markdown_and_emoji():
    from modules.voice_io.plugin import sanitize_for_speech

    result = sanitize_for_speech("**Heading**\n* Item one\n`code`\nDone 😊")

    assert result == "Heading\nItem one\ncode\nDone"


def test_sanitize_for_speech_makes_links_and_dates_speakable():
    from modules.voice_io.plugin import sanitize_for_speech

    result = sanitize_for_speech("Source: https://example.com/a/b. Date: 25/04/2026 and 2026-04-28.")

    assert "https://" not in result
    assert "/a/b" not in result
    assert "25th April 2026" in result
    assert "28th April 2026" in result
    assert "link from example.com" in result
