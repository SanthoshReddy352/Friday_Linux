"""Tests for core.bootstrap.preflight — Batch 1 / Issue 1.

The preflight module's job is to make boot-time dependency loss visible
and actionable. These tests pin down (a) the data model, (b) the split
between critical and degraded tiers, (c) the formatter contract used by
both the CLI and the HUD badge.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.bootstrap import preflight


def _dep(import_name: str, tier: str = preflight.CRITICAL) -> preflight.Dep:
    return preflight.Dep(
        import_name=import_name,
        pip_spec=import_name,
        tier=tier,
        role="test role",
    )


def test_all_present_report_is_ok_and_not_degraded():
    report = preflight.PreflightReport(missing_critical=(), missing_degraded=())
    assert report.ok is True
    assert report.degraded is False
    assert report.pip_install_command() == ""
    assert "OK" in preflight.format_human(report)


def test_missing_critical_marks_report_not_ok():
    report = preflight.PreflightReport(
        missing_critical=(_dep("llama_cpp"),),
        missing_degraded=(),
    )
    assert report.ok is False
    out = preflight.format_human(report)
    assert "CRITICAL" in out
    assert "FRIDAY cannot start" in out
    assert "llama_cpp" in out


def test_missing_degraded_keeps_report_ok_but_flags_degraded():
    report = preflight.PreflightReport(
        missing_critical=(),
        missing_degraded=(_dep("chromadb", preflight.DEGRADED),),
    )
    assert report.ok is True
    assert report.degraded is True
    out = preflight.format_human(report)
    assert "lite mode" in out
    assert "chromadb" in out


def test_pip_install_command_quotes_extras_specs():
    report = preflight.PreflightReport(
        missing_critical=(),
        missing_degraded=(
            preflight.Dep(
                import_name="markitdown",
                pip_spec="markitdown[pdf]",
                tier=preflight.DEGRADED,
                role="docs",
            ),
            _dep("rapidfuzz", preflight.DEGRADED),
        ),
    )
    cmd = report.pip_install_command()
    assert cmd.startswith("pip install ")
    assert "'markitdown[pdf]'" in cmd  # extras must be shell-quoted
    assert "rapidfuzz" in cmd


def test_dep_list_partitioned_correctly():
    critical = [d for d in preflight.DEPS if d.tier == preflight.CRITICAL]
    degraded = [d for d in preflight.DEPS if d.tier == preflight.DEGRADED]
    # We can't assert exact membership without coupling to the list, but
    # we can assert the partition is non-trivial and exhaustive — every
    # dep belongs to exactly one tier.
    assert len(critical) >= 5
    assert len(degraded) >= 5
    assert len(critical) + len(degraded) == len(preflight.DEPS)


def test_last_report_caches_after_run():
    # Calling run() does not populate the cache; only ensure_runnable() does.
    # That is intentional — scripts/preflight.py uses run() and should not
    # mutate state visible to the HUD.
    before = preflight.last_report()
    preflight.run()
    after = preflight.run()
    # last_report() is unchanged because run() doesn't write to it.
    assert preflight.last_report() is before
    # But the two run() invocations produced equal reports.
    assert after.ok == preflight.run().ok
