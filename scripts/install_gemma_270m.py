"""Download Gemma 270M models used by the intent-routing benchmark.

Two flavours, both Q4_K_M GGUF, ~250 MB each:

* **gemma**      — ``unsloth/gemma-3-270m-it-GGUF`` (plain instruction-tuned)
* **fn-gemma**   — ``unsloth/functiongemma-270m-it-GGUF`` (Google's
  function-calling fine-tune of the same 270M base; uses a ``developer``
  role in its chat template to activate tool-use mode)

Usage::

    python scripts/install_gemma_270m.py               # both
    python scripts/install_gemma_270m.py --only gemma  # only base
    python scripts/install_gemma_270m.py --only fn     # only function-tune

Idempotent — skips a download when the local file already exists at the
expected size. Gated repos (anything starting with ``google/...``) need
a Hugging Face token with the Gemma terms accepted; the ``unsloth/...``
mirrors are not gated.
"""

from __future__ import annotations


def _relaunch_under_project_venv() -> None:
    """Stdlib-only venv shim — see ``main.py`` for rationale."""
    import os
    import sys

    if os.environ.get("FRIDAY_SKIP_VENV_AUTOEXEC") == "1":
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_root = os.path.join(repo_root, ".venv")
    if os.name == "nt":
        candidate = os.path.join(venv_root, "Scripts", "python.exe")
    else:
        candidate = os.path.join(venv_root, "bin", "python3")
        if not os.path.exists(candidate):
            candidate = os.path.join(venv_root, "bin", "python")
    if not os.path.exists(candidate):
        return
    try:
        already = os.path.realpath(sys.prefix) == os.path.realpath(venv_root)
    except OSError:
        already = False
    if already:
        return
    if os.environ.get("_FRIDAY_VENV_RELAUNCHED") == "1":
        return
    os.environ["_FRIDAY_VENV_RELAUNCHED"] = "1"
    os.execv(candidate, [candidate, *sys.argv])


_relaunch_under_project_venv()


import argparse
import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class GgufTarget:
    key: str               # short cli flag value
    repo_id: str
    remote_filename: str
    local_filename: str    # canonical filename under ``models/``
    role: str              # human description


TARGETS: tuple[GgufTarget, ...] = (
    GgufTarget(
        key="gemma",
        repo_id="unsloth/gemma-3-270m-it-GGUF",
        remote_filename="gemma-3-270m-it-Q4_K_M.gguf",
        local_filename="gemma-3-270m-it-Q4_K_M.gguf",
        role="Gemma 3 270M (instruction-tuned)",
    ),
    GgufTarget(
        key="fn",
        repo_id="unsloth/functiongemma-270m-it-GGUF",
        remote_filename="functiongemma-270m-it-Q4_K_M.gguf",
        local_filename="functiongemma-270m-it-Q4_K_M.gguf",
        role="Function Gemma 270M (tool-calling fine-tune)",
    ),
)


def models_dir() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "models")


def target_path(target: GgufTarget) -> str:
    return os.path.join(models_dir(), target.local_filename)


def already_installed(target: GgufTarget) -> bool:
    path = target_path(target)
    return os.path.exists(path) and os.path.getsize(path) > 50 * 1024 * 1024


def manual_instructions(target: GgufTarget) -> str:
    return (
        "\nManual install fallback:\n"
        f"  1. Open https://huggingface.co/{target.repo_id}\n"
        f"  2. Download the file: {target.remote_filename}\n"
        f"  3. Save it as: {target_path(target)}\n"
        "  4. Re-run this script to verify.\n"
    )


def install_target(target: GgufTarget) -> bool:
    """Returns True on success (already installed counts)."""
    print(f"\n=== {target.role} ({target.key}) ===")
    os.makedirs(models_dir(), exist_ok=True)
    if already_installed(target):
        print(f"[install] Already installed: {target_path(target)} — skipping.")
        return True

    try:
        from huggingface_hub import hf_hub_download  # noqa: PLC0415
    except ImportError:
        print("[install] huggingface_hub missing — run scripts/preflight.py first.", file=sys.stderr)
        return False

    print(f"[install] Downloading {target.remote_filename} from {target.repo_id} …")
    try:
        downloaded = hf_hub_download(
            repo_id=target.repo_id,
            filename=target.remote_filename,
            local_dir=models_dir(),
        )
    except Exception as exc:
        print(f"[install] Download failed: {exc}", file=sys.stderr)
        print(manual_instructions(target), file=sys.stderr)
        return False

    if os.path.abspath(downloaded) != os.path.abspath(target_path(target)):
        # Some hf_hub_download versions write under a subdir or as a
        # symlink-to-cache; normalise so the canonical path resolves.
        try:
            if os.path.exists(target_path(target)):
                os.remove(target_path(target))
            os.symlink(downloaded, target_path(target))
        except OSError:
            import shutil
            shutil.copy2(downloaded, target_path(target))

    size_mb = os.path.getsize(target_path(target)) / (1024 * 1024)
    print(f"[install] OK — {target_path(target)} ({size_mb:.1f} MB).")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Gemma 270M GGUF models.")
    parser.add_argument(
        "--only", choices=[t.key for t in TARGETS],
        help="Install only the named target (default: install all).",
    )
    args = parser.parse_args()

    targets = [t for t in TARGETS if (args.only is None or t.key == args.only)]
    failed = []
    for tgt in targets:
        if not install_target(tgt):
            failed.append(tgt.key)
    if failed:
        print(f"\n[install] {len(failed)} target(s) failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("\n[install] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
