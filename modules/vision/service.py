"""VisionService — lazy SmolVLM2 loading, single inference entry point, auto-unload.

Loading strategy:
- VLM is loaded on the first inference call (lazy — not at app boot).
- A watchdog thread auto-unloads after idle_timeout_s (default 300 s).
- RAM guard: refuses to load if < 3 GB free (checked via ResourceMonitor).
- Dedicated threading.Lock() — never contends with chat or tool model.

Typical latency on i5-12th Gen (CPU-only, SmolVLM2-2.2B Q4_K_M):
  50 tokens  →  5–10 s
  100 tokens → 10–20 s
Voice ack fires before inference starts, so the user is never left in silence.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from core.logger import logger


class VisionService:
    def __init__(self, config: dict):
        self._model_path: str = config.get("model_path", "")
        self._mmproj_path: str = config.get("mmproj_path", "")
        self._n_ctx: int = int(config.get("n_ctx", 2048))
        self._n_batch: int = int(config.get("n_batch", 256))
        self._idle_timeout_s: int = int(config.get("idle_timeout_s", 300))

        self._lock = threading.Lock()
        self._llm = None
        self._last_used: float = 0.0
        self._watchdog: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def infer(self, image, prompt: str, max_tokens: int = 128) -> str:
        """Run a single VLM inference pass.

        Args:
            image: PIL Image, file path (str / Path), or raw bytes.
            prompt: Instruction string sent with the image.
            max_tokens: Generation limit — keep low for voice UX.

        Returns:
            Generated text string (stripped of leading/trailing whitespace).
        """
        from modules.vision.preprocess import load_and_resize, image_to_data_uri

        img = load_and_resize(image)
        data_uri = image_to_data_uri(img)

        with self._lock:
            self._ensure_loaded()
            self._last_used = time.monotonic()

            response = self._llm.create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_uri}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=max_tokens,
                temperature=0.1,
            )
        return response["choices"][0]["message"]["content"].strip()

    def unload(self) -> None:
        """Explicitly release the VLM to free RAM."""
        with self._lock:
            if self._llm is not None:
                logger.info("[vision] Unloading VLM.")
                self._llm = None

    @property
    def is_loaded(self) -> bool:
        return self._llm is not None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Load VLM if not already loaded. Must be called under self._lock."""
        if self._llm is not None:
            return

        # RAM guard — refuse if < 3 GB free
        try:
            from core.resource_monitor import get_snapshot, ResourceMonitor
            snap = get_snapshot()
            if snap.ram_available_mb < ResourceMonitor.VLM_MIN_RAM_MB:
                raise RuntimeError(
                    f"Not enough RAM to load VLM. "
                    f"Available: {snap.ram_available_mb} MB, "
                    f"required: {ResourceMonitor.VLM_MIN_RAM_MB} MB."
                )
        except ImportError:
            pass  # resource_monitor not available — proceed without guard

        if not self._model_path or not Path(self._model_path).exists():
            raise FileNotFoundError(
                f"VLM model not found: {self._model_path!r}. "
                "Check 'vision.model_path' in config.yaml."
            )
        if not self._mmproj_path or not Path(self._mmproj_path).exists():
            raise FileNotFoundError(
                f"mmproj not found: {self._mmproj_path!r}. "
                "Check 'vision.mmproj_path' in config.yaml."
            )

        logger.info("[vision] Loading SmolVLM2 from %s …", Path(self._model_path).name)
        t0 = time.monotonic()

        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import Llava15ChatHandler

        class SmolVLM2ChatHandler(Llava15ChatHandler):
            # Idefics3 / ChatML format — image URL is inserted before the text
            # so the model receives: <|im_start|>user\n{image}\n{prompt}<|im_end|>\n<|im_start|>assistant\n
            CHAT_FORMAT = (
                "{% for message in messages %}"
                "{% if loop.first and message['role'] != 'system' %}"
                "<|im_start|>system\nYou are a helpful vision assistant.<|im_end|>\n"
                "{% endif %}"
                "<|im_start|>{{ message['role'] }}\n"
                "{% if message['content'] is string %}"
                "{{ message['content'] }}<|im_end|>\n"
                "{% else %}"
                "{% for content in message['content'] %}"
                "{% if content['type'] == 'image_url' %}"
                "{% if content.image_url is string %}{{ content.image_url }}\n"
                "{% else %}{{ content.image_url.url }}\n{% endif %}"
                "{% endif %}"
                "{% endfor %}"
                "{% for content in message['content'] %}"
                "{% if content['type'] == 'text' %}{{ content['text'] }}{% endif %}"
                "{% endfor %}"
                "<|im_end|>\n"
                "{% endif %}"
                "{% endfor %}"
                "<|im_start|>assistant\n"
            )

        chat_handler = SmolVLM2ChatHandler(
            clip_model_path=self._mmproj_path,
            verbose=False,
        )
        self._llm = Llama(
            model_path=self._model_path,
            chat_handler=chat_handler,
            n_ctx=self._n_ctx,
            n_batch=self._n_batch,
            verbose=False,
        )

        logger.info("[vision] VLM loaded in %.1f s.", time.monotonic() - t0)
        self._last_used = time.monotonic()
        self._start_watchdog()

    def _start_watchdog(self) -> None:
        """Launch the idle-timeout watchdog thread (idempotent)."""
        if self._watchdog and self._watchdog.is_alive():
            return

        timeout = self._idle_timeout_s

        def _watch():
            while True:
                time.sleep(30)
                with self._lock:
                    if self._llm is None:
                        return
                    idle_s = time.monotonic() - self._last_used
                    if idle_s >= timeout:
                        logger.info(
                            "[vision] Idle for %.0f s — unloading VLM.", idle_s
                        )
                        self._llm = None
                        return

        self._watchdog = threading.Thread(
            target=_watch, name="vision-watchdog", daemon=True
        )
        self._watchdog.start()
