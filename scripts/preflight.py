"""FRIDAY preflight — verify the Python environment before launching.

Run this once after pulling new code or recreating the venv:

    python scripts/preflight.py

Exit codes:
  0 — all critical dependencies present (degraded warnings may still print)
  1 — one or more critical dependencies missing; refuse to launch

The same checks are invoked programmatically by ``core.bootstrap.preflight``
when ``main.py`` boots, so this script is for manual / CI use. The data
model and logic live in ``core/bootstrap/preflight.py`` — this file is a
thin CLI shell over it.
"""

from __future__ import annotations


# Project-venv auto-bootstrap — keep this stdlib-only so it works even
# when the system Python is missing FRIDAY's pip deps.
def _relaunch_under_project_venv() -> None:
    """Mirror of `main.py:_relaunch_under_project_venv` so that running
    ``python scripts/preflight.py`` from a bare shell uses the venv's
    interpreter automatically. The script's report (and exit code) then
    reflects the venv state — which is what the user actually cares
    about when they're about to launch FRIDAY.

    Opt out with ``FRIDAY_SKIP_VENV_AUTOEXEC=1``.
    """
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
    # See main.py for the rationale — compare on sys.prefix, not on
    # sys.executable, because venv pythons are typically symlinks to the
    # system interpreter and their executable paths match.
    try:
        already_in_venv = (
            os.path.realpath(sys.prefix) == os.path.realpath(venv_root)
        )
    except OSError:
        already_in_venv = False
    if already_in_venv:
        return
    if os.environ.get("_FRIDAY_VENV_RELAUNCHED") == "1":
        return
    os.environ["_FRIDAY_VENV_RELAUNCHED"] = "1"
    os.execv(candidate, [candidate, *sys.argv])


_relaunch_under_project_venv()

import os
import sys

# Allow running from anywhere: ensure the repo root is on sys.path so
# the ``core`` package resolves without requiring an editable install.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.bootstrap.preflight import format_human, run  # noqa: E402


def main() -> int:
    report = run()
    print(format_human(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
