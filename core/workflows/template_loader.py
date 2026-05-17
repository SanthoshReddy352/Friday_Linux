"""Load and validate YAML workflow templates.

A template is a declarative description of a multi-step capability invocation:

  workflow_name: lab_network_inventory
  description:   Inventory hosts and services in an authorized lab subnet.
  required_inputs:  [target_subnet]
  optional_inputs:  [scan_profile]
  preconditions:    [...]                # free-form policy strings
  permission_checks: [authorized_scope]
  steps:
    - step_id: s1
      capability: ping_sweep
      args: { subnet: "{{target_subnet}}" }
    - step_id: s2
      capability: host_service_scan
      depends_on: [s1]
      args: { target: "${s1.hosts.first}", profile: "{{scan_profile|default:quick}}" }
  stop_conditions: [user_cancelled]
  final_report:
    format: markdown
    sections: [scope, hosts, services]

The loader is responsible for:
  - Reading every ``*.yaml`` under a directory.
  - Validating shape (required fields, types).
  - Producing a :class:`WorkflowTemplate` per file.

It is intentionally permissive about *content* — slot substitution and
capability validation happen at compile time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable

import yaml


_REQUIRED_TOP_LEVEL = ("workflow_name", "steps")


class TemplateError(ValueError):
    """Raised when a YAML template is malformed."""


@dataclass
class WorkflowTemplateStep:
    step_id: str
    capability: str
    args: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    requires_confirmation: bool = False
    side_effect_level: str = "read"
    timeout_ms: int = 0
    retries: int = 0
    expected_observation: str = ""
    success_condition: str = ""
    when: str = ""           # branching predicate (Phase 6 will evaluate)


@dataclass
class WorkflowTemplate:
    workflow_name: str
    description: str = ""
    version: str = "1.0.0"
    domain: str = "general"
    tags: list[str] = field(default_factory=list)
    required_inputs: list[str] = field(default_factory=list)
    optional_inputs: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    permission_checks: list[str] = field(default_factory=list)
    steps: list[WorkflowTemplateStep] = field(default_factory=list)
    branching_rules: list[dict] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    final_report: dict = field(default_factory=dict)
    source_path: str = ""    # filled by loader for diagnostics

    @property
    def step_ids(self) -> list[str]:
        return [s.step_id for s in self.steps]


class WorkflowTemplateLoader:
    def __init__(self, directory: str | os.PathLike):
        self.directory = os.fspath(directory)

    def discover(self) -> list[str]:
        if not os.path.isdir(self.directory):
            return []
        out: list[str] = []
        for name in sorted(os.listdir(self.directory)):
            if not name.endswith((".yaml", ".yml")):
                continue
            full = os.path.join(self.directory, name)
            if os.path.isfile(full):
                out.append(full)
        return out

    def load_all(self) -> dict[str, WorkflowTemplate]:
        templates: dict[str, WorkflowTemplate] = {}
        for path in self.discover():
            tpl = self.load_file(path)
            if tpl.workflow_name in templates:
                raise TemplateError(
                    f"duplicate workflow_name {tpl.workflow_name!r} "
                    f"(also in {templates[tpl.workflow_name].source_path})"
                )
            templates[tpl.workflow_name] = tpl
        return templates

    def load_file(self, path: str) -> WorkflowTemplate:
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise TemplateError(f"{path}: YAML parse error: {exc}") from exc
        if not isinstance(data, dict):
            raise TemplateError(f"{path}: top-level must be a mapping")

        for key in _REQUIRED_TOP_LEVEL:
            if key not in data:
                raise TemplateError(f"{path}: missing required key {key!r}")

        steps_raw = data.get("steps") or []
        if not isinstance(steps_raw, list) or not steps_raw:
            raise TemplateError(f"{path}: 'steps' must be a non-empty list")

        steps = [self._build_step(path, idx, raw) for idx, raw in enumerate(steps_raw)]
        seen_ids: set[str] = set()
        for step in steps:
            if step.step_id in seen_ids:
                raise TemplateError(f"{path}: duplicate step_id {step.step_id!r}")
            seen_ids.add(step.step_id)
        # Forward-reference check: every depends_on must point to a known step.
        for step in steps:
            for dep in step.depends_on:
                if dep not in seen_ids:
                    raise TemplateError(
                        f"{path}: step {step.step_id!r} depends on unknown {dep!r}"
                    )

        tpl = WorkflowTemplate(
            workflow_name=str(data["workflow_name"]).strip(),
            description=str(data.get("description") or ""),
            version=str(data.get("version") or "1.0.0"),
            domain=str(data.get("domain") or "general"),
            tags=list(data.get("tags") or []),
            required_inputs=list(data.get("required_inputs") or []),
            optional_inputs=list(data.get("optional_inputs") or []),
            preconditions=list(data.get("preconditions") or []),
            permission_checks=list(data.get("permission_checks") or []),
            steps=steps,
            branching_rules=list(data.get("branching_rules") or []),
            stop_conditions=list(data.get("stop_conditions") or []),
            final_report=dict(data.get("final_report") or {}),
            source_path=path,
        )
        if not tpl.workflow_name:
            raise TemplateError(f"{path}: workflow_name must be non-empty")
        return tpl

    def _build_step(self, path: str, idx: int, raw: Any) -> WorkflowTemplateStep:
        if not isinstance(raw, dict):
            raise TemplateError(f"{path}: step #{idx} is not a mapping")
        if "step_id" not in raw or "capability" not in raw:
            raise TemplateError(
                f"{path}: step #{idx} missing required 'step_id' or 'capability'"
            )
        return WorkflowTemplateStep(
            step_id=str(raw["step_id"]).strip(),
            capability=str(raw["capability"]).strip(),
            args=dict(raw.get("args") or {}),
            depends_on=list(raw.get("depends_on") or []),
            requires_confirmation=bool(raw.get("requires_confirmation", False)),
            side_effect_level=str(raw.get("side_effect_level") or "read"),
            timeout_ms=int(raw.get("timeout_ms") or 0),
            retries=int(raw.get("retries") or 0),
            expected_observation=str(raw.get("expected_observation") or ""),
            success_condition=str(raw.get("success_condition") or ""),
            when=str(raw.get("when") or ""),
        )


def default_template_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "templates")


def load_templates(directory: str | os.PathLike | None = None) -> dict[str, WorkflowTemplate]:
    """Convenience: load every template from ``directory`` (defaults to the
    bundled template dir)."""
    return WorkflowTemplateLoader(directory or default_template_dir()).load_all()
