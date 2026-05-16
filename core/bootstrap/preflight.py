"""Preflight dependency check — fail-fast before model load.

Two ways to invoke:

* ``python scripts/preflight.py`` — manual / CI use, prints a human report
  and exits 0/1 (delegates to ``run()`` + the formatter here).
* ``ensure_runnable()`` — called by ``main.py`` before kernel boot. Aborts
  on missing critical deps; logs degraded warnings for optional deps so
  the HUD can surface a "lite mode" badge.

The role of this module is to make boot-time degradation **visible and
actionable** instead of the silent ``Vector store unavailable`` failure
mode we hit before. Keep the list of deps narrow: only what the code
actually imports at runtime.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass

CRITICAL = "critical"
DEGRADED = "degraded"


@dataclass(frozen=True)
class Dep:
    import_name: str
    pip_spec: str
    tier: str            # CRITICAL | DEGRADED
    role: str            # short human description

    def is_installed(self) -> bool:
        try:
            importlib.import_module(self.import_name)
        except Exception:
            return False
        return True


DEPS: tuple[Dep, ...] = (
    # --- CRITICAL: refuse to boot if any are missing ---
    Dep("PyQt6", "PyQt6", CRITICAL, "HUD / desktop UI"),
    Dep("yaml", "PyYAML==6.0.1", CRITICAL, "config parsing"),
    Dep("llama_cpp", "llama-cpp-python", CRITICAL, "local LLM inference (Qwen3)"),
    Dep("faster_whisper", "faster-whisper", CRITICAL, "speech-to-text"),
    Dep("sounddevice", "sounddevice", CRITICAL, "audio capture"),
    Dep("pyttsx3", "pyttsx3", CRITICAL, "text-to-speech"),
    Dep("numpy", "numpy", CRITICAL, "audio + math"),
    Dep("requests", "requests", CRITICAL, "HTTP for external tools"),
    Dep("psutil", "psutil", CRITICAL, "process / system probes"),
    # --- DEGRADED: log loudly but allow boot in lite mode ---
    Dep("chromadb", "chromadb", DEGRADED,
        "vector store (semantic memory, RAG cross-document search)"),
    Dep("sentence_transformers", "sentence-transformers", DEGRADED,
        "embedding router + RAG sentence embeddings"),
    Dep("markitdown", "markitdown[pdf]", DEGRADED,
        "document conversion (PDF / DOCX / PPTX -> markdown)"),
    Dep("trafilatura", "trafilatura", DEGRADED,
        "web research content extraction"),
    Dep("rapidfuzz", "rapidfuzz", DEGRADED,
        "intent routing typo tolerance"),
    Dep("httpx", "httpx[http2]", DEGRADED,
        "async HTTP for the web research agent"),
    Dep("selectolax", "selectolax", DEGRADED,
        "fast SERP parsing for DDG research"),
    Dep("dateparser", "dateparser", DEGRADED,
        "natural-language time parsing for calendar / reminders"),
)


@dataclass(frozen=True)
class PreflightReport:
    missing_critical: tuple[Dep, ...]
    missing_degraded: tuple[Dep, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_critical

    @property
    def degraded(self) -> bool:
        return bool(self.missing_degraded)

    def pip_install_command(self) -> str:
        specs = [d.pip_spec for d in self.missing_critical + self.missing_degraded]
        if not specs:
            return ""
        return "pip install " + " ".join(f"'{s}'" if "[" in s else s for s in specs)


def run() -> PreflightReport:
    missing_critical: list[Dep] = []
    missing_degraded: list[Dep] = []
    for dep in DEPS:
        if dep.is_installed():
            continue
        if dep.tier == CRITICAL:
            missing_critical.append(dep)
        else:
            missing_degraded.append(dep)
    return PreflightReport(tuple(missing_critical), tuple(missing_degraded))


def format_human(report: PreflightReport) -> str:
    """Render the report as a multi-line string for stdout / log output."""
    lines: list[str] = []
    if report.ok and not report.degraded:
        return "[preflight] OK -- all dependencies present."

    if report.missing_critical:
        lines.append("[preflight] CRITICAL dependencies missing -- FRIDAY cannot start:")
        for dep in report.missing_critical:
            lines.append(f"  - {dep.pip_spec:32s}  ({dep.role})")
        lines.append("")

    if report.missing_degraded:
        lines.append(
            "[preflight] Optional dependencies missing -- FRIDAY will boot in lite mode:"
        )
        for dep in report.missing_degraded:
            lines.append(f"  - {dep.pip_spec:32s}  ({dep.role})")
        lines.append("")

    install = report.pip_install_command()
    if install:
        lines.append("To fix, activate your venv and run:")
        lines.append(f"  {install}")
    return "\n".join(lines)


_LAST_REPORT: PreflightReport | None = None


def last_report() -> PreflightReport | None:
    """Return the most recent preflight result, or None if never run.

    The HUD calls this on startup to decide whether to show a "lite mode"
    badge — querying the cached report avoids re-running ``importlib``
    against modules that may have side effects on import.
    """
    return _LAST_REPORT


def ensure_runnable() -> PreflightReport:
    """Boot-time hook used by ``main.py``.

    Prints the report to stderr (so it survives even if logging isn't
    configured yet), aborts with exit code 1 if critical deps are missing,
    otherwise returns the report so callers can surface degraded warnings
    in the UI.
    """
    global _LAST_REPORT
    report = run()
    _LAST_REPORT = report
    if not report.ok or report.degraded:
        print(format_human(report), file=sys.stderr)
    if not report.ok:
        sys.exit(1)
    return report
