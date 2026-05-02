import os
import importlib
import importlib.util
import inspect
import json
from core.logger import logger
from core.extensions.protocol import Extension, ExtensionContext
from core.extensions.adapter import LegacyExtensionAdapter
from core.plugin_manager import FridayPlugin
from core.skill import Skill, SkillDescriptor

class LegacySkillAdapter:
    """Wrap an existing Skill instance as an Extension."""
    def __init__(self, skill: Skill, skill_path: str):
        self._skill = skill
        self._skill_path = skill_path
        self._descriptor = skill.describe()
        self.name = self._descriptor.name
        self._ctx = None

    def load(self, ctx: ExtensionContext) -> None:
        self._ctx = ctx
        is_available, reason = self._check_availability()
        
        # Determine all tools this skill exposes
        tool_names = [
            tool.get("function", tool).get("name")
            for tool in (self._descriptor.tool_specs or [])
            if tool.get("function", tool).get("name")
        ]
        
        # Inform the system capabilities about the skill status
        capabilities = self._ctx.get_service("capabilities")
        if capabilities:
            capabilities.register_skill_status(
                self.name,
                is_available,
                reason=reason,
                tools=tool_names,
            )

        if not is_available:
            logger.info("Skill %s disabled: %s", self.name, reason)
            return

        # Initialize the skill
        app = self._ctx.get_service("self") or self._ctx._app_ref
        self._skill.initialize({
            "app": app,
            "config": self._ctx.get_config("self") or self._ctx._config,  # Just passing whole config object
            "capabilities": capabilities,
        })

        # Register tools
        tools = self._skill.get_tools()
        functions = self._skill.get_functions()
        reserved = self._get_reserved_tools()
        router_tools = self._ctx.get_service("router")._tools_by_name if self._ctx.get_service("router") else {}
        registry = self._ctx.registry

        for tool in tools:
            tool_spec = tool.get("function", tool)
            tool_name = tool_spec.get("name")
            if not tool_name or tool_name not in functions:
                continue
            if tool_name in reserved:
                logger.info("Skipping JARVIS tool '%s' from skill %s (native implementation).", tool_name, self.name)
                continue
            if tool_name in router_tools:
                logger.warning("Skipping JARVIS tool '%s' from skill %s (already registered).", tool_name, self.name)
                continue
            # A native extension (e.g. workspace_agent) may have already
            # claimed this tool name in the capability registry. Don't let a
            # legacy skill silently shadow it.
            if registry is not None and registry.has_capability(tool_name):
                logger.warning("Skipping JARVIS tool '%s' from skill %s (capability already registered by an extension).", tool_name, self.name)
                continue
                
            self._ctx.register_capability(
                tool_spec,
                self._wrap_skill_function(functions[tool_name]),
                metadata=self._build_capability_meta(tool_name)
            )
            logger.info(f"Registered JARVIS tool: {tool_name}")

    def unload(self) -> None:
        pass

    def _check_availability(self):
        capabilities = self._ctx.get_service("capabilities")
        if capabilities is None:
            return True, ""

        if self._descriptor.supported_platforms and capabilities.platform not in self._descriptor.supported_platforms:
            return False, f"Supported only on {', '.join(self._descriptor.supported_platforms)}."

        config = self._ctx._config
        if (
            config and hasattr(config, "get")
            and config.get("skills.mode", "local_first") == "local_first"
            and not self._descriptor.enabled_by_default
            and not config.get(f"skills.enable.{self.name}", False)
        ):
            return False, "Disabled by default in local-first mode."

        missing_modules = capabilities.missing_python_modules(self._descriptor.required_python_modules)
        if missing_modules:
            return False, f"Missing Python modules: {', '.join(missing_modules)}."

        missing_binaries = capabilities.missing_binaries(self._descriptor.required_binaries)
        if missing_binaries:
            return False, f"Missing binaries: {', '.join(missing_binaries)}."

        if self._descriptor.availability_reason:
            return False, self._descriptor.availability_reason

        return True, ""

    def _wrap_skill_function(self, func):
        signature = inspect.signature(func)
        params = list(signature.parameters.values())

        def _wrapped(raw_text, args):
            kwargs = dict(args or {})
            try:
                if not params:
                    return func()

                if len(params) == 1 and params[0].kind in (
                    inspect.Parameter.VAR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                ):
                    return func(**kwargs)

                if all(
                    param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
                    for param in params
                ):
                    return func(**kwargs)

                return func(raw_text, kwargs)
            except TypeError:
                try:
                    return func(**kwargs)
                except TypeError:
                    return func()
            except Exception as exc:
                return json.dumps({"status": "error", "message": str(exc)})

        return _wrapped

    def _build_capability_meta(self, tool_name: str):
        lowered = f"{self.name} {tool_name}".lower()
        connectivity = "online" if any(
            token in lowered
            for token in ("weather", "web", "whatsapp", "email", "gemini", "online", "browser")
        ) else "local"
        permission_mode = "ask_first" if connectivity == "online" else "always_ok"
        return {
            "connectivity": connectivity,
            "permission_mode": permission_mode,
            "latency_class": "interactive",
            "side_effect_level": "write" if any(
                token in tool_name.lower() for token in ("open", "start", "send", "play", "launch", "write", "save")
            ) else "read",
        }

    def _get_reserved_tools(self):
        return {
            "get_system_status", "get_battery", "get_cpu_ram", "launch_app", "set_volume",
            "take_screenshot", "search_file", "open_file", "read_file", "summarize_file",
            "manage_file", "list_folder_contents", "open_folder", "select_file_candidate",
            "confirm_yes", "confirm_no", "shutdown_assistant", "get_friday_status",
            "enable_voice", "disable_voice", "set_voice_mode", "llm_chat", "get_time", "get_date"
        }

class ExtensionLoader:
    """Discovers and loads Phase 4 extensions and legacy Phase 3 plugins/skills."""
    def __init__(self, app):
        self.app = app
        self.extensions: list[Extension] = []
        self._ctx = ExtensionContext(
            registry=app.capability_registry,
            events=app.event_bus,
            consent=app.consent_service,
            config=app.config,
            app_ref=app
        )

    def load_all(self):
        self._load_modules()
        self._load_skills()

    def _load_modules(self):
        modules_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "modules")
        if not os.path.exists(modules_dir):
            return

        for item in sorted(os.listdir(modules_dir)):
            if item.startswith("__") or not os.path.isdir(os.path.join(modules_dir, item)):
                continue
            
            # Skip jarvis_skills module itself because we are porting its logic into load_skills
            if item == "jarvis_skills":
                continue

            try:
                extension = self._load_module(item, modules_dir)
                if extension:
                    extension.load(self._ctx)
                    self.extensions.append(extension)
                    logger.info(f"Successfully loaded extension/plugin: {item}")
            except Exception as e:
                logger.error(f"Failed to load module {item}: {e}", exc_info=True)

    def _load_module(self, item_name: str, modules_dir: str) -> Extension | None:
        """Attempt to load native extension first, fallback to legacy FridayPlugin."""
        package_path = os.path.join(modules_dir, item_name)
        
        # 1. Native Extension (extension.py)
        if os.path.exists(os.path.join(package_path, "extension.py")):
            spec = importlib.util.spec_from_file_location(f"modules.{item_name}.extension", os.path.join(package_path, "extension.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find the Extension class
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and not name.startswith("_") and hasattr(obj, "load") and obj.__module__ == module.__name__:
                    # If there's a setup method on the module (optional), use it, otherwise instantiate directly
                    if hasattr(module, "setup"):
                        return module.setup()
                    return obj()
        
        # 2. Legacy Plugin (__init__.py -> plugin.py)
        module_name = f"modules.{item_name}"
        module = importlib.import_module(module_name)
        if hasattr(module, "setup"):
            plugin_instance = module.setup(self.app)
            if plugin_instance:
                return LegacyExtensionAdapter(plugin_instance)
        
        return None

    def _load_skills(self):
        skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "skills")
        if not os.path.exists(skills_dir):
            return

        for filename in sorted(os.listdir(skills_dir)):
            if filename.endswith(".py") and filename != "__init__.py":
                skill_path = os.path.join(skills_dir, filename)
                try:
                    module_name = os.path.basename(skill_path)[:-3]
                    spec = importlib.util.spec_from_file_location(module_name, skill_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, Skill) and obj is not Skill:
                            skill_instance = obj()
                            adapter = LegacySkillAdapter(skill_instance, skill_path)
                            adapter.load(self._ctx)
                            self.extensions.append(adapter)
                except Exception as e:
                    capabilities = self._ctx.get_service("capabilities")
                    if capabilities:
                        capabilities.register_skill_status(
                            os.path.basename(skill_path)[:-3],
                            False,
                            reason=str(e),
                        )
                    logger.error(f"Failed to load skill from {skill_path}: {e}")

    def get_extension(self, name: str) -> Extension | None:
        """Find an extension by its name attribute."""
        for ext in self.extensions:
            if getattr(ext, "name", None) == name:
                return ext
        return None
