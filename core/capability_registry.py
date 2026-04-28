from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable


Handler = Callable[[str, dict], Any]


@dataclass
class CapabilityDescriptor:
    name: str
    description: str
    connectivity: str = "local"
    latency_class: str = "interactive"
    permission_mode: str = "always_ok"
    side_effect_level: str = "read"
    streaming: bool = False
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    provider_kind: str = "inprocess"
    resources: list[dict] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class CapabilityExecutionResult:
    ok: bool
    name: str
    output: Any = ""
    error: str = ""
    descriptor: CapabilityDescriptor | None = None


class CapabilityRegistry:
    """
    Internal MCP-compatible capability registry.

    The current implementation keeps providers in-process, but the descriptor
    and execution contract is shaped so external MCP-style servers can be
    adopted later without rewriting the conversation layer.
    """

    def __init__(self):
        self._descriptors: Dict[str, CapabilityDescriptor] = {}
        self._handlers: Dict[str, Handler] = {}

    def register_tool(self, tool_spec: dict, handler: Handler, metadata: dict | None = None):
        spec = dict(tool_spec or {})
        metadata = dict(metadata or {})
        name = str(spec.get("name") or "").strip()
        if not name:
            raise ValueError("Capability name is required.")

        descriptor = CapabilityDescriptor(
            name=name,
            description=str(spec.get("description") or ""),
            connectivity=metadata.get("connectivity") or self._infer_connectivity(spec, metadata),
            latency_class=metadata.get("latency_class", "interactive"),
            permission_mode=metadata.get("permission_mode") or self._infer_permission_mode(spec, metadata),
            side_effect_level=metadata.get("side_effect_level") or self._infer_side_effect_level(spec, metadata),
            streaming=bool(metadata.get("streaming", False)),
            input_schema=dict(spec.get("parameters") or {}),
            output_schema=dict(metadata.get("output_schema") or {}),
            provider_kind=str(metadata.get("provider_kind", "inprocess")),
            resources=list(metadata.get("resources") or []),
            prompts=list(metadata.get("prompts") or []),
            metadata={
                "tool_spec": spec,
                **{key: value for key, value in metadata.items() if key not in {
                    "connectivity",
                    "latency_class",
                    "permission_mode",
                    "side_effect_level",
                    "streaming",
                    "output_schema",
                    "provider_kind",
                    "resources",
                    "prompts",
                }},
            },
        )
        self._descriptors[name] = descriptor
        self._handlers[name] = handler
        return descriptor

    def get_descriptor(self, name: str) -> CapabilityDescriptor | None:
        return self._descriptors.get(name)

    def get_handler(self, name: str) -> Handler | None:
        return self._handlers.get(name)

    def has_capability(self, name: str) -> bool:
        return name in self._descriptors and name in self._handlers

    def list_capabilities(self, connectivity: str | None = None) -> list[CapabilityDescriptor]:
        items = list(self._descriptors.values())
        if connectivity:
            items = [item for item in items if item.connectivity == connectivity]
        return sorted(items, key=lambda item: item.name)

    def descriptors(self) -> Iterable[CapabilityDescriptor]:
        return self._descriptors.values()

    def _infer_connectivity(self, tool_spec: dict, metadata: dict) -> str:
        if metadata.get("online") is True:
            return "online"
        text = " ".join(
            str(tool_spec.get(key) or "")
            for key in ("name", "description")
        ).lower()
        if any(
            token in text
            for token in (
                "browser", "youtube", "website", "web", "weather", "whatsapp",
                "email", "search google", "online", "internet",
            )
        ):
            return "online"
        return "local"

    def _infer_permission_mode(self, tool_spec: dict, metadata: dict) -> str:
        if "permission_mode" in metadata:
            return str(metadata["permission_mode"])
        if self._infer_connectivity(tool_spec, metadata) == "online":
            return "ask_first"
        return "always_ok"

    def _infer_side_effect_level(self, tool_spec: dict, metadata: dict) -> str:
        if "side_effect_level" in metadata:
            return str(metadata["side_effect_level"])
        name = str(tool_spec.get("name") or "").lower()
        if any(token in name for token in ("open", "launch", "play", "set_", "manage", "write", "create", "delete", "shutdown")):
            return "write"
        return "read"


class CapabilityExecutor:
    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry

    def execute(self, name: str, raw_text: str, args: dict | None = None) -> CapabilityExecutionResult:
        descriptor = self.registry.get_descriptor(name)
        handler = self.registry.get_handler(name)
        if descriptor is None or handler is None:
            return CapabilityExecutionResult(
                ok=False,
                name=name,
                error=f"Capability '{name}' is not registered.",
            )

        try:
            output = handler(raw_text, dict(args or {}))
            return CapabilityExecutionResult(
                ok=True,
                name=name,
                output=output,
                descriptor=descriptor,
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return CapabilityExecutionResult(
                ok=False,
                name=name,
                error=str(exc),
                descriptor=descriptor,
            )
