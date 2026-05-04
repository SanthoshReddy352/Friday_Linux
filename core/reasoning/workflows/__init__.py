# Phase 6: Named workflow library for GraphCompiler.
# Each workflow handles a specific multi-step task pattern.
from core.reasoning.workflows.research_mode import ResearchWorkflow
from core.reasoning.workflows.focus_mode import FocusModeWorkflow

__all__ = ["ResearchWorkflow", "FocusModeWorkflow"]
