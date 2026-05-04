from typing import Any, Callable

def capability(name: str, description: str, parameters: dict[str, Any] | None = None, **metadata):
    """Decorator to mark an Extension method as a FRIDAY tool/capability.

    Args:
        name: The tool name exposed to the LLM (e.g., "search_file").
        description: The prompt describing when and how to use the tool.
        parameters: JSON Schema of the parameters (defaults to empty object).
        **metadata: Additional metadata (e.g., latency_class, permission_mode, side_effect_level).
    """
    def decorator(func: Callable) -> Callable:
        func.__capability_spec__ = {
            "name": name,
            "description": description,
            "parameters": parameters or {"type": "object", "properties": {}},
        }
        func.__capability_meta__ = metadata
        return func
    return decorator
