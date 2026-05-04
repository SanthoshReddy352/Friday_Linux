from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable


@dataclass
class SkillDescriptor:
    name: str
    supported_platforms: List[str] = field(default_factory=list)
    required_python_modules: List[str] = field(default_factory=list)
    required_binaries: List[str] = field(default_factory=list)
    tool_specs: List[Dict[str, Any]] = field(default_factory=list)
    availability_reason: str = ""
    enabled_by_default: bool = True

class Skill(ABC):
    """Base class for all Skills."""
    
    @abstractmethod
    def get_tools(self) -> List[Dict[str, Any]]:
        """Return the list of tool schemas provided by this skill."""
        pass

    @abstractmethod
    def get_functions(self) -> Dict[str, Callable]:
        """Return a dictionary mapping function names to the actual callables."""
        pass

    def initialize(self, context: Dict[str, Any]):
        """
        Initialize the skill with context from the main application.
        Override this if the skill needs access to global state (e.g., pause_event).
        """
        pass

    @classmethod
    def describe(cls) -> SkillDescriptor:
        descriptor = getattr(cls, "DESCRIPTOR", None)
        if isinstance(descriptor, SkillDescriptor):
            return descriptor
        return SkillDescriptor(name=getattr(cls, "__name__", "unknown_skill"))

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the skill."""
        pass
