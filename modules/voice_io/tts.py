import re
import threading
import subprocess
import os
import shutil
import tempfile
import queue
import time
from core.logger import logger


def _split_sentences(text):
    """Split text into speakable sentence chunks."""
    # Split on sentence-ending punctuation, keeping the delimiter
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


class TextToSpeech:
    def __init__(self, app_core=None):
        self.app_core = app_core
        self._is_speaking = False
        self.interrupt_event = threading.Event()
        self._current_processes = []
        self._speak_lock = threading.Lock()
        self._run_id = 0
        self._runtime_prepared = False
        self._runtime_lock = threading.Lock()
        
        self.speech_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.worker_thread.start()

        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.model_path = os.path.join(
            self.project_root,
            "models", "en_US-lessac-medium.onnx"
        )
        self._source_piper_dir = os.path.join(self.project_root, "piper")
        self._runtime_dir = os.path.join(tempfile.gettempdir(), "friday_runtime", "piper")
        self.piper_path = os.path.join(self._runtime_dir, "piper")
        self.aplay_path = shutil.which("aplay")
        self.current_text = ""
        self.current_sentence = ""
        self.speaking_started_at = 0.0
        self.speaking_stopped_at = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_speaking(self):
        return self._is_speaking

    def speak(self, text):
        """Legacy single-shot speak (non-interruptible). Prefer speak_chunked()."""
        if not text or not text.strip():
            return
        run_id = self._next_run_id(stop_current=True)
        threading.Thread(target=self._speak_chunk, args=(text, True, run_id), daemon=True).start()

    def speak_chunked(self, text):
        """
        Queue text to be spoken sentence-by-sentence in the background thread.
        Strips any JSON blocks or markdown fences before queuing.
        """
        if not text or not text.strip():
            return
        # Strip markdown code fences
        text = re.sub(r'```[a-z]*', '', text).replace('```', '').strip()
        # Remove any JSON object - everything between { and the final }
        text = re.sub(r'\{[^}]*\}', '', text, flags=re.DOTALL).strip()
        if not text:
            return
        self.speech_queue.put(text)

    def _tts_worker(self):
        while True:
            text = self.speech_queue.get()
            if text is None:
                self.speech_queue.task_done()
                continue

            # Always clear the interrupt event before processing a new item
            # so that stop() followed by speak_chunked() works correctly
            self.interrupt_event.clear()
            run_id = self._next_run_id(stop_current=False)
            self._chunked_speak_loop(text, run_id)
            self.speech_queue.task_done()

    def stop(self):
        """
        Signal the TTS to stop immediately.
        Kills the current aplay/piper subprocess and clears the speaking flag.
        NOTE: interrupt_event is NOT left set — the worker clears it before
        the next item, so subsequent speak_chunked() calls work correctly.
        """
        logger.info("[TTS] Stop requested.")
        self.interrupt_event.set()

        # Drain the queue so pending items don't play after stop
        drained = 0
        while True:
            try:
                self.speech_queue.get_nowait()
                self.speech_queue.task_done()
                drained += 1
            except queue.Empty:
                break
        if drained:
            logger.debug(f"[TTS] Drained {drained} pending item(s) from queue.")

        with self._speak_lock:
            self._run_id += 1
            self._stop_processes(self._current_processes)
            self._current_processes = []
        self._set_speaking(False)

    def warm_up(self):
        try:
            self._check_files()
        except Exception as e:
            logger.warning(f"[TTS] Warm-up failed: {e}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _set_speaking(self, state: bool):
        self._is_speaking = state
        if state:
            self.speaking_started_at = time.monotonic()
        else:
            # Add a tiny buffer (50ms) to allow for OS-level audio buffer handoffs
            # The STT will add its own larger grace period on top of this.
            if not self.interrupt_event.is_set():
                time.sleep(0.05)
            self.speaking_stopped_at = time.monotonic()
        if not state:
            self.current_text = ""
            self.current_sentence = ""
        if self.app_core:
            self.app_core.is_speaking = state

    def _chunked_speak_loop(self, text, run_id):
        if not self._check_files():
            return

        sentences = _split_sentences(text)
        self.current_text = text
        self._set_speaking(True)

        try:
            for sentence in sentences:
                self.current_sentence = sentence
                if self.interrupt_event.is_set() or run_id != self._run_id:
                    logger.info("[TTS] Interrupted before sentence.")
                    break
                self._speak_chunk(sentence, set_flags=False, run_id=run_id)
                if self.interrupt_event.is_set() or run_id != self._run_id:
                    logger.info("[TTS] Interrupted after sentence.")
                    break
        finally:
            if run_id == self._run_id:
                self._set_speaking(False)
            logger.debug("[TTS] Chunked speak loop finished.")

    def _speak_chunk(self, text, set_flags=True, run_id=None):
        """Speak a single piece of text synchronously (blocks until done or interrupted)."""
        if not self._check_files():
            return
        if set_flags:
            self.interrupt_event.clear()
            self.current_text = text
            self.current_sentence = text
            self._set_speaking(True)
        if run_id is None:
            run_id = self._run_id

        if not self.aplay_path:
            logger.error("[TTS] aplay not found on PATH.")
            if set_flags:
                self._set_speaking(False)
            return

        try:
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = self._runtime_dir + os.pathsep + env.get("LD_LIBRARY_PATH", "")
            env["PIPER_DATA_DIR"] = self._runtime_dir

            piper_proc = subprocess.Popen(
                [self.piper_path, "--model", self.model_path, "--output_raw"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            aplay_proc = subprocess.Popen(
                [self.aplay_path, "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"],
                stdin=piper_proc.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if piper_proc.stdout:
                piper_proc.stdout.close()

            with self._speak_lock:
                self._current_processes = [piper_proc, aplay_proc]

            if piper_proc.stdin:
                piper_proc.stdin.write(text.encode("utf-8"))
                piper_proc.stdin.close()

            aplay_proc.wait()
            piper_proc.wait()
            interrupted = self.interrupt_event.is_set() or run_id != self._run_id
            if piper_proc.returncode not in (0, None) and not interrupted:
                logger.error(f"[TTS] Piper exited with code {piper_proc.returncode}.")
            elif piper_proc.returncode not in (0, None):
                logger.debug(f"[TTS] Piper interrupted with code {piper_proc.returncode}.")
            if aplay_proc.returncode not in (0, None) and not interrupted:
                logger.error(f"[TTS] aplay exited with code {aplay_proc.returncode}.")
            elif aplay_proc.returncode not in (0, None):
                logger.debug(f"[TTS] aplay interrupted with code {aplay_proc.returncode}.")
        except Exception as e:
            logger.error(f"[TTS] Subprocess error: {e}")
        finally:
            self._stop_processes([piper_proc, aplay_proc] if 'piper_proc' in locals() else [])
            with self._speak_lock:
                self._current_processes = []
            if set_flags and run_id == self._run_id:
                self._set_speaking(False)

    def _check_files(self):
        if not os.path.exists(self.model_path):
            logger.error(f"[TTS] Model not found: {self.model_path}")
            return False
        if not self._prepare_runtime():
            logger.error(f"[TTS] Piper runtime not available: {self._runtime_dir}")
            return False
        return True

    def _next_run_id(self, stop_current=False):
        if stop_current and (self.is_speaking or self._current_processes):
            self.stop()
        with self._speak_lock:
            self._run_id += 1
            run_id = self._run_id
        self.interrupt_event.clear()
        return run_id

    def _prepare_runtime(self):
        with self._runtime_lock:
            if self._runtime_prepared and os.path.exists(self.piper_path):
                return True

            source_piper = os.path.join(self._source_piper_dir, "piper")
            if not os.path.exists(source_piper):
                logger.error(f"[TTS] Piper binary not found: {source_piper}")
                return False

            os.makedirs(self._runtime_dir, exist_ok=True)
            self._sync_runtime_dir(self._source_piper_dir, self._runtime_dir)

            for executable in ("piper", "piper_phonemize", "espeak-ng"):
                runtime_path = os.path.join(self._runtime_dir, executable)
                if os.path.exists(runtime_path):
                    os.chmod(runtime_path, os.stat(runtime_path).st_mode | 0o111)

            self._runtime_prepared = os.path.exists(self.piper_path)
            return self._runtime_prepared

    def _sync_runtime_dir(self, src_dir, dst_dir):
        for entry in os.listdir(src_dir):
            src_path = os.path.join(src_dir, entry)
            dst_path = os.path.join(dst_dir, entry)

            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
                continue

            should_copy = (
                not os.path.exists(dst_path)
                or os.path.getsize(src_path) != os.path.getsize(dst_path)
                or os.path.getmtime(src_path) > os.path.getmtime(dst_path)
            )
            if should_copy:
                shutil.copy2(src_path, dst_path)

    def _stop_processes(self, processes):
        for proc in reversed(processes):
            if not proc:
                continue
            try:
                if getattr(proc, "stdin", None):
                    proc.stdin.close()
            except Exception:
                pass
            try:
                if getattr(proc, "stdout", None):
                    proc.stdout.close()
            except Exception:
                pass
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=0.08)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=0.08)
                    logger.debug("[TTS] Stopped active subprocess.")
            except Exception as e:
                logger.warning(f"[TTS] Could not stop process: {e}")
