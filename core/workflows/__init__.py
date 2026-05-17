"""Workflow template registry and compiler.

YAML workflow templates live under ``core/workflows/templates/``. They are
loaded by :class:`WorkflowTemplateLoader` and compiled into the existing
``ToolPlan`` shape by :class:`WorkflowTemplateCompiler` so the DAG executor
runs them unchanged.
"""
from .template_loader import (
    WorkflowTemplate,
    WorkflowTemplateStep,
    WorkflowTemplateLoader,
    TemplateError,
    default_template_dir,
    load_templates,
)
from .template_compiler import WorkflowTemplateCompiler, CompileError

__all__ = [
    "WorkflowTemplate",
    "WorkflowTemplateStep",
    "WorkflowTemplateLoader",
    "WorkflowTemplateCompiler",
    "TemplateError",
    "CompileError",
    "default_template_dir",
    "load_templates",
]
