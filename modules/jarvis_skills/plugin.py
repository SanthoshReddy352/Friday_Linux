import os
import importlib.util
import inspect
import json
from core.plugin_manager import FridayPlugin
from core.skill import Skill, SkillDescriptor
from core.logger import logger


RESERVED_NATIVE_TOOLS = {
    "get_system_status",
    "get_battery",
    "get_cpu_ram",
    "launch_app",
    "set_volume",
    "take_screenshot",
    "search_file",
    "open_file",
    "read_file",
    "summarize_file",
    "manage_file",
    "list_folder_contents",
    "open_folder",
    "select_file_candidate",
    "confirm_yes",
    "confirm_no",
    "shutdown_assistant",
    "get_friday_status",
    "enable_voice",
    "disable_voice",
    "set_voice_mode",
    "llm_chat",
    "get_time",
    "get_date",
}


class JarvisSkillsPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "JarvisSkills"
        self.skills = []
        self.on_load()

    def on_load(self):
        skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "skills")
        if not os.path.exists(skills_dir):
            logger.warning(f"Skills directory not found: {skills_dir}")
            return

        for filename in os.listdir(skills_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                skill_path = os.path.join(skills_dir, filename)
                self.load_skill(skill_path)
        
        logger.info(f"JarvisSkillsPlugin loaded with {len(self.skills)} skills.")

    def load_skill(self, skill_path):
        try:
            module_name = os.path.basename(skill_path)[:-3]
            spec = importlib.util.spec_from_file_location(module_name, skill_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, Skill) and obj is not Skill:
                    descriptor = obj.describe()
                    is_available, reason = self._check_descriptor_availability(descriptor)
                    tool_names = [
                        tool.get("function", tool).get("name")
                        for tool in (descriptor.tool_specs or [])
                        if tool.get("function", tool).get("name")
                    ]
                    self._record_skill_status(descriptor, is_available, reason, tool_names)

                    if not is_available:
                        logger.info("Skill %s disabled: %s", descriptor.name, reason)
                        continue

                    skill_instance = obj()
                    # Initialize with app context if needed
                    skill_instance.initialize(
                        {
                            "app": self.app,
                            "config": self.app.config,
                            "capabilities": getattr(self.app, "capabilities", None),
                        }
                    )
                    self.skills.append(skill_instance)
                    
                    # Register tools with the router
                    tools = skill_instance.get_tools()
                    functions = skill_instance.get_functions()
                    
                    for tool in tools:
                        tool_spec = tool.get("function", tool) # JARVIS uses OpenAI format sometimes
                        tool_name = tool_spec.get("name")
                        if not tool_name or tool_name not in functions:
                            continue
                        if tool_name in RESERVED_NATIVE_TOOLS:
                            logger.info(
                                "Skipping JARVIS tool '%s' from skill %s because FRIDAY provides a native implementation.",
                                tool_name,
                                descriptor.name,
                            )
                            continue
                        if tool_name in self.app.router._tools_by_name:
                            logger.warning(
                                "Skipping JARVIS tool '%s' from skill %s because a tool with that name is already registered.",
                                tool_name,
                                descriptor.name,
                            )
                            continue
                        self.app.router.register_tool(
                            tool_spec,
                            self._wrap_skill_function(functions[tool_name]),
                            capability_meta=self._build_capability_meta(descriptor, tool_name),
                        )
                        logger.info(f"Registered JARVIS tool: {tool_name}")
        except Exception as e:
            capabilities = getattr(self.app, "capabilities", None)
            if capabilities:
                capabilities.register_skill_status(
                    os.path.basename(skill_path)[:-3],
                    False,
                    reason=str(e),
                )
            logger.error(f"Failed to load skill from {skill_path}: {e}")

    def _check_descriptor_availability(self, descriptor: SkillDescriptor):
        capabilities = getattr(self.app, "capabilities", None)
        if capabilities is None:
            return True, ""

        if descriptor.supported_platforms and capabilities.platform not in descriptor.supported_platforms:
            return False, f"Supported only on {', '.join(descriptor.supported_platforms)}."

        config = getattr(self.app, "config", None)
        if (
            getattr(config, "get", None)
            and config.get("skills.mode", "local_first") == "local_first"
            and not descriptor.enabled_by_default
            and not config.get(f"skills.enable.{descriptor.name}", False)
        ):
            return False, "Disabled by default in local-first mode."

        missing_modules = capabilities.missing_python_modules(descriptor.required_python_modules)
        if missing_modules:
            return False, f"Missing Python modules: {', '.join(missing_modules)}."

        missing_binaries = capabilities.missing_binaries(descriptor.required_binaries)
        if missing_binaries:
            return False, f"Missing binaries: {', '.join(missing_binaries)}."

        if descriptor.availability_reason:
            return False, descriptor.availability_reason

        return True, ""

    def _record_skill_status(self, descriptor: SkillDescriptor, available: bool, reason: str, tool_names):
        capabilities = getattr(self.app, "capabilities", None)
        if capabilities:
            capabilities.register_skill_status(
                descriptor.name,
                available,
                reason=reason,
                tools=tool_names,
            )

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

    def _build_capability_meta(self, descriptor: SkillDescriptor, tool_name: str):
        lowered = f"{descriptor.name} {tool_name}".lower()
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

def setup(app):
    return JarvisSkillsPlugin(app)
