import ctypes
import logging
import os
import threading
from dataclasses import dataclass

from core.logger import logger


_LLAMA_LOG_SILENCED = False
_LLAMA_LOG_CALLBACK = None


def _silence_llama_native_logs():
    global _LLAMA_LOG_SILENCED, _LLAMA_LOG_CALLBACK

    if _LLAMA_LOG_SILENCED:
        return

    try:
        import llama_cpp

        @llama_cpp.llama_log_callback
        def _noop_log_callback(level, text, user_data):
            return

        llama_cpp.llama_log_set(_noop_log_callback, ctypes.c_void_p(0))
        logging.getLogger("llama-cpp-python").setLevel(logging.CRITICAL + 1)
        _LLAMA_LOG_CALLBACK = _noop_log_callback
        _LLAMA_LOG_SILENCED = True
    except Exception:
        pass


@dataclass
class ModelProfile:
    role: str
    path: str
    preload: bool = False
    n_ctx: int = 4096
    n_batch: int = 512
    temperature: float = 0.1


class LocalModelManager:
    def __init__(self, config=None, base_dir=None):
        self.config = config
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(__file__))
        self._models = {}
        self._load_failed = set()
        self._locks = {
            "chat": threading.Lock(),
            "tool": threading.Lock(),
        }
        # Per-domain inference locks. llama.cpp instances are NOT thread-safe;
        # any caller that runs `create_chat_completion` against a model must
        # hold the matching domain lock for the duration of the call. Lives
        # here (not on CommandRouter) so research / chat / tool callers can
        # share the same lock without depending on the router.
        self._inference_locks = {
            "chat": threading.RLock(),
            "tool": threading.RLock(),
        }
        self._profiles = {}
        self.refresh_from_config(config)

    def refresh_from_config(self, config=None):
        if config is not None:
            self.config = config

        models_dir = os.path.join(self.base_dir, "models")
        self._profiles = {
            "chat": ModelProfile(
                role="chat",
                path=self._resolve_path(self._config_get("models.chat.path", os.path.join(models_dir, "mlabonne_Qwen3-1.7B-abliterated-Q4_K_M.gguf"))),
                preload=bool(self._config_get("models.chat.preload", True)),
                n_ctx=int(self._config_get("models.chat.n_ctx", 4096)),
                n_batch=int(self._config_get("models.chat.n_batch", 512)),
                temperature=float(self._config_get("models.chat.temperature", 0.7)),
            ),
            "tool": ModelProfile(
                role="tool",
                path=self._resolve_path(self._config_get("models.tool.path", os.path.join(models_dir, "mlabonne_Qwen3-4B-abliterated-Q4_K_M.gguf"))),
                preload=bool(self._config_get("models.tool.preload", False)),
                n_ctx=int(self._config_get("models.tool.n_ctx", 4096)),
                n_batch=int(self._config_get("models.tool.n_batch", 512)),
                temperature=float(self._config_get("models.tool.temperature", 0.1)),
            ),
        }
        return self._profiles

    def profile(self, role):
        return self._profiles[role]

    def inference_lock(self, role):
        """Return the inference lock for a model domain ("chat" or "tool")."""
        return self._inference_locks[role]

    def get_chat_model(self):
        return self.get_model("chat")

    def get_tool_model(self):
        return self.get_model("tool")

    def get_model(self, role):
        if role in self._models:
            return self._models[role]

        profile = self.profile(role)
        if role in self._load_failed:
            return None
        if not os.path.exists(profile.path):
            return None

        with self._locks[role]:
            if role in self._models:
                return self._models[role]
            if role in self._load_failed:
                return None
            try:
                from llama_cpp import Llama

                _silence_llama_native_logs()
                logger.info("Loading %s model from %s...", role, profile.path)
                self._models[role] = Llama(
                    model_path=profile.path,
                    n_ctx=profile.n_ctx,
                    n_batch=profile.n_batch,
                    n_threads=max(1, (os.cpu_count() or 2) - 1),
                    verbose=False,
                )
            except Exception as exc:
                logger.error("Error initializing %s model: %s", role, exc)
                self._load_failed.add(role)
                self._models.pop(role, None)
        return self._models.get(role)

    def preload_requested_models(self):
        for role, profile in self._profiles.items():
            if profile.preload and os.path.exists(profile.path):
                threading.Thread(target=self.get_model, args=(role,), daemon=True).start()

    def status(self, role):
        profile = self.profile(role)
        return {
            "role": role,
            "path": profile.path,
            "exists": os.path.exists(profile.path),
            "loaded": role in self._models,
            "failed": role in self._load_failed,
        }

    def _config_get(self, key, default):
        if self.config is None:
            return default
        if hasattr(self.config, "get"):
            return self.config.get(key, default)
        return default

    def _resolve_path(self, value):
        if not value:
            return value
        if os.path.isabs(value):
            return value
        return os.path.join(self.base_dir, value)
