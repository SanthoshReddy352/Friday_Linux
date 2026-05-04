"""Phase 10: Import graph linter.

Ensures core.* modules do not import from extensions.* or modules.* at
module level (only lazy inside functions is permitted).
"""
import ast
import os
import pathlib
import pytest


CORE_ROOT = pathlib.Path(__file__).parent.parent / "core"
FORBIDDEN_PREFIXES = ("modules.", "extensions.")


def _top_level_imports(source: str) -> list[str]:
    """Return all module names imported at the top level of a Python source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names = []
    for node in ast.walk(tree):
        # Only look at top-level (not inside function/class bodies)
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


def _is_top_level_import(filepath: pathlib.Path, source: str) -> list[tuple[int, str]]:
    """Return (lineno, module) for forbidden top-level imports."""
    violations = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    # Track which nodes are inside function or class bodies
    function_ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            function_ranges.append((node.lineno, getattr(node, "end_lineno", node.lineno + 999)))

    def in_function(lineno: int) -> bool:
        return any(start <= lineno <= end for start, end in function_ranges)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if in_function(node.lineno):
            continue
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module]
        for mod in modules:
            if any(mod.startswith(p) for p in FORBIDDEN_PREFIXES):
                violations.append((node.lineno, mod))
    return violations


def collect_core_py_files():
    files = []
    for path in CORE_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        files.append(path)
    return files


@pytest.mark.parametrize("filepath", collect_core_py_files(), ids=lambda p: str(p.relative_to(CORE_ROOT.parent)))
def test_no_forbidden_top_level_imports(filepath):
    source = filepath.read_text(encoding="utf-8")
    violations = _is_top_level_import(filepath, source)
    assert not violations, (
        f"{filepath.relative_to(CORE_ROOT.parent)} has forbidden top-level imports "
        f"(core must not import from modules.* or extensions.* at module level):\n"
        + "\n".join(f"  line {ln}: {mod}" for ln, mod in violations)
    )
