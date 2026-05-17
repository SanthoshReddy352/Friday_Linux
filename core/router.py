import difflib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass

from core.embedding_router import EmbeddingRouter
from core.intent_recognizer import IntentRecognizer
from core.logger import logger
from core.model_manager import LocalModelManager
# Re-export RoutingDecision from its new home for backward compatibility.
from core.routing_state import RoutingDecision, RoutingState


# Tools whose planned action is "confirmation-shaped" — short, context-free
# answers that an active workflow may legitimately want to claim. For these
# the router gives the workflow first chance before executing the plan.
# Imperative tools that re-enter the workflow themselves (play_youtube,
# manage_file, …) are deliberately excluded so the action's args are not
# lost by pre-emption. (Batch 4 / Issue 4 wiring.)
_WORKFLOW_PRE_EMPT_TOOLS = frozenset({
    "confirm_yes",
    "confirm_no",
    "select_file_candidate",
})


class CommandRouter:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.capability_registry = None
        self.tools = []
        self._tools_by_name = {}
        self._tool_aliases = {}
        self._tool_patterns = {}
        self._tools_prompt_cache = None
        self.llm = None
        self.chat_llm = None
        self.tool_llm = None
        self._llm_lock = threading.Lock()
        self._tool_llm_lock = threading.Lock()
        # Inference locks now live on LocalModelManager (the model owner).
        # Exposed on the router as @property for backward compatibility with
        # callers like LLMChatPlugin and ResearchAgentService.
        self._llm_load_failed = False
        self._tool_llm_load_failed = False
        self._last_context = {}
        self.assistant_context = None
        self.context_store = None
        self.workflow_orchestrator = None
        self.session_id = None
        # Embedding router catches paraphrases that the deterministic layer
        # misses, before we pay the LLM-router latency. Disabled when the
        # FRIDAY_DISABLE_EMBED_ROUTER env var is set.
        self.embedding_router = None
        if os.getenv("FRIDAY_DISABLE_EMBED_ROUTER") != "1":
            try:
                self.embedding_router = EmbeddingRouter()
            except Exception as exc:
                logger.warning("[router] Embedding router unavailable: %s", exc)
        # routing_state and response_finalizer are injected by FridayApp after
        # construction. A local fallback RoutingState is created so the router
        # works stand-alone in tests (e.g. test_router_tools.py).
        self.routing_state: RoutingState = RoutingState()
        self.response_finalizer = None
        # Use LLM for tool routing by default, but allow override.
        self.enable_llm_tool_routing = os.getenv("FRIDAY_USE_LLM_TOOL_ROUTER", "1") == "1"
        self.routing_policy = "selective_executor"
        self.tool_timeout_ms = int(os.getenv("FRIDAY_TOOL_TIMEOUT_MS", "8000"))
        self.tool_max_tokens = int(os.getenv("FRIDAY_TOOL_MAX_TOKENS", "96"))
        self.tool_target_max_tokens = int(os.getenv("FRIDAY_TOOL_TARGET_MAX_TOKENS", "64"))
        self.tool_top_p = float(os.getenv("FRIDAY_TOOL_TOP_P", "0.2"))
        self.tool_json_response = os.getenv("FRIDAY_TOOL_JSON_RESPONSE", "1") == "1"
        self.model_manager = LocalModelManager(base_dir=os.path.dirname(os.path.dirname(__file__)))
        self.refresh_runtime_settings()
        self.intent_recognizer = IntentRecognizer(self)
        if os.path.exists(self.llm_model_path):
            logger.info("[router] Chat model available for loading: %s", self.llm_model_path)
        else:
            logger.warning("Chat model not found at %s. Conversational fallback will be unavailable.", self.llm_model_path)
        if os.path.exists(self.tool_model_path):
            logger.info("[router] Tool model available for loading: %s", self.tool_model_path)
        else:
            logger.warning("Tool model not found at %s. Selective tool reasoning will be unavailable.", self.tool_model_path)

    # ------------------------------------------------------------------
    # Compatibility properties bridging to routing_state
    # These let existing callers (e.g. tests) read/write router.*
    # without knowing about RoutingState yet.
    # ------------------------------------------------------------------

    @property
    def _voice_already_spoken(self) -> bool:
        return self.routing_state.voice_already_spoken

    @_voice_already_spoken.setter
    def _voice_already_spoken(self, value: bool) -> None:
        self.routing_state.voice_already_spoken = value

    @property
    def last_routing_decision(self) -> RoutingDecision:
        return self.routing_state.last_decision

    @last_routing_decision.setter
    def last_routing_decision(self, value: RoutingDecision) -> None:
        self.routing_state.last_decision = value

    @property
    def current_route_source(self) -> str:
        return self.routing_state.current_route_source

    @current_route_source.setter
    def current_route_source(self, value: str) -> None:
        self.routing_state.current_route_source = value

    @property
    def current_model_lane(self) -> str:
        return self.routing_state.current_model_lane

    @current_model_lane.setter
    def current_model_lane(self, value: str) -> None:
        self.routing_state.current_model_lane = value

    @property
    def chat_inference_lock(self):
        return self.model_manager.inference_lock("chat")

    @property
    def tool_inference_lock(self):
        return self.model_manager.inference_lock("tool")

    def refresh_runtime_settings(self, config=None):
        self.model_manager.refresh_from_config(config)
        self.llm_model_path = self.model_manager.profile("chat").path
        self.tool_model_path = self.model_manager.profile("tool").path
        if config is not None and hasattr(config, "get"):
            self.routing_policy = config.get("routing.policy", "selective_executor")
            self.tool_timeout_ms = int(config.get("routing.tool_timeout_ms", self.tool_timeout_ms))
            self.tool_max_tokens = int(config.get("routing.tool_max_tokens", self.tool_max_tokens))
            self.tool_target_max_tokens = int(config.get("routing.tool_target_max_tokens", self.tool_target_max_tokens))
            self.tool_top_p = float(config.get("routing.tool_top_p", self.tool_top_p))
            self.tool_json_response = bool(config.get("routing.tool_json_response", self.tool_json_response))

    # ------------------------------------------------------------------
    # Primary API: structured tool registration
    # ------------------------------------------------------------------

    def register_tool(self, tool_spec: dict, callback, capability_meta=None):
        """
        Register a tool that Gemma can call.

        tool_spec = {
            "name": "launch_app",
            "description": "Launch a desktop application by name.",
            "parameters": {
                "app_name": "string – the application to open, e.g. 'firefox'"
            }
        }

        callback signature: callback(raw_text: str, args: dict) -> str
        """
        spec = dict(tool_spec)
        aliases = self._build_aliases(spec)
        patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self._build_patterns(spec)]

        route = {
            "spec": spec,
            "callback": callback,
            "aliases": aliases,
            "patterns": patterns,
            "context_terms": self._build_context_terms(spec),
            "capability_meta": capability_meta or {},
        }
        self.tools.append(route)
        self._tools_by_name[spec["name"]] = route
        self._tool_aliases[spec["name"]] = aliases
        self._tool_patterns[spec["name"]] = patterns
        self._tools_prompt_cache = None
        # Embedding index becomes stale on every tool registration; mark it
        # for rebuild on the next route() call.
        if self.embedding_router is not None:
            self.embedding_router._index_signature = ""
        capability_registry = getattr(self, "capability_registry", None)
        if capability_registry is not None:
            capability_registry.register_tool(spec, callback, metadata=capability_meta)
        logger.debug(f"[Router] Registered tool: {tool_spec['name']}")

    # ------------------------------------------------------------------
    # Legacy API (kept for backward compatibility during transition)
    # ------------------------------------------------------------------

    def register_handler(self, keywords, callback):
        """
        Legacy keyword-based handler registration. Wraps in a tool_spec
        so the system still works. Use register_tool() for new code.
        """
        # Build a minimal tool spec from the first keyword
        tool_name = keywords[0].replace(" ", "_") if keywords else "unknown"
        spec = {
            "name": tool_name,
            "description": f"Handle commands related to: {', '.join(keywords)}",
            "parameters": {}
        }
        # Wrap the old-style callback (raw_text) → new-style (raw_text, args)
        def _wrapped(raw_text, args):
            return callback(raw_text)
        spec["aliases"] = keywords
        self.register_tool(spec, _wrapped)

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    def process_text(self, text):
        """
        Process user text using deterministic routing first, then
        selective Qwen tool reasoning, and finally Gemma chat fallback.
        Returns a response string.
        """
        self._voice_already_spoken = False
        self.current_route_source = "idle"
        self.current_model_lane = "idle"
        self.last_routing_decision = RoutingDecision(source="idle", args={})
        # STT typo correction (Issue 8): cheap, conservative, must happen
        # before any downstream parser sees the input.
        from core.text_normalize import normalize_for_routing  # noqa: PLC0415
        text = normalize_for_routing(text)
        logger.info(f"Router received: {text}")
        text_lower = self._normalize_text(text)
        if not text_lower or not re.search(r"[a-z0-9]", text_lower):
            return ""
        if not self._is_confirmation_input(text_lower):
            dialog_state = getattr(self, "dialog_state", None)
            if dialog_state and hasattr(dialog_state, "clear_pending_clarification"):
                dialog_state.clear_pending_clarification()

        # --- TRANSCRIPT CLEANING ---
        # Remove common voice-recognition stutters and repetitive phrases
        stutter_patterns = [
            r"\b(what do you say|what do you say)\b", 
            r"\b(can you tell me|can you tell me)\b",
            r"\b(tell me|tell me)\b"
        ]
        text_clean = text_lower
        for p in stutter_patterns:
            text_clean = re.sub(p, "", text_clean).strip()

        # 1. Deterministic Fast-Path for simple commands (high confidence)
        best_route = self._find_best_route(text_clean, min_score=80)
        action_plan = self._plan_actions(text)

        if len(action_plan) > 1:
            self._set_routing_decision("deterministic", tool_name="multi_action_plan")
            return self._execute_plan(action_plan)

        # If the intent recognizer fully resolved a launch_app action with
        # specific app_names, trust it — no need to defer to the LLM.
        if (
            len(action_plan) == 1
            and action_plan[0]["route"]["spec"]["name"] == "launch_app"
            and action_plan[0]["args"].get("app_names")
        ):
            logger.info("[router] Fast-path multi-app launch (intent recognizer resolved app names)")
            self._set_routing_decision("deterministic", tool_name="launch_app", args=action_plan[0]["args"])
            return self._execute_plan(action_plan)

        if len(action_plan) == 1:
            # Batch 4 / Issue 4: an active workflow waiting on a short
            # conversational answer (write_confirmation, content_source,
            # …) must win against IntentRecognizer's planned tool. We
            # pre-empt when either (a) the planned tool is itself a
            # confirmation-shaped surface — confirm_yes / confirm_no /
            # select_file_candidate — or (b) the workflow has explicitly
            # told us it expects this kind of answer. Imperative tool
            # calls like play_youtube package their args via the action
            # plan and re-enter the workflow through the tool handler,
            # so we must not pre-empt them.
            planned_name = action_plan[0]["route"]["spec"]["name"]
            if planned_name in _WORKFLOW_PRE_EMPT_TOOLS or self._active_workflow_expects_short_answer():
                workflow_result = self._continue_active_workflow(text)
                if workflow_result is not None:
                    return workflow_result
            planned_route = action_plan[0]["route"]
            logger.info(f"[router] Fast-path (planned) routing: {planned_route['spec']['name']}")
            self._set_routing_decision("deterministic", tool_name=planned_route["spec"]["name"], args=action_plan[0]["args"])
            return self._execute_plan(action_plan)

        is_complex_action = best_route and best_route["spec"]["name"] in (
            "search_file",
            "open_file",
            "read_file",
            "summarize_file",
            "list_folder_contents",
            "open_folder",
        )
        if best_route and not is_complex_action:
            logger.info(f"[router] Match Found: Exact/Fuzzy match on tool '{best_route['spec']['name']}'")
            self._set_routing_decision("deterministic", tool_name=best_route["spec"]["name"], args={})
            result = self._invoke_route(best_route, text, {})
            self._last_context = {"tool": best_route["spec"]["name"], "domain": best_route["spec"]["name"], "args": {}}
            return result

        if not action_plan:
            workflow_result = self._continue_active_workflow(text)
            if workflow_result is not None:
                return workflow_result

        # 1.5. Embedding router: catch paraphrases the regex layer missed
        # before paying the LLM-router latency cost.
        embed_result = self._try_embedding_route(text, text_clean)
        if embed_result is not None:
            return embed_result

        # 2. Selective Qwen tool reasoning for ambiguous or complex tool requests
        should_use_tool_model = (
            self.routing_policy == "selective_executor"
            and self.enable_llm_tool_routing
            and self.tools
            and (is_complex_action or self._should_use_tool_model(text_clean, best_route, action_plan))
        )
        if should_use_tool_model and self.get_tool_llm():
            result = self._infer_with_tool_llm(text, target_tool=best_route if is_complex_action else None)
            if result is not None:
                return result

        # 3. Deterministic fallback for actions
        if action_plan:
            action = action_plan[0]
            self._set_routing_decision("deterministic", tool_name=action["route"]["spec"]["name"], args=action["args"])
            return self._execute_plan(action_plan)

        # 4. Deterministic fallback
        fallback_result = self._keyword_fallback(text, text_lower)
        if fallback_result is not None:
            return fallback_result

        workflow_result = self._continue_active_workflow(text)
        if workflow_result is not None:
            return workflow_result

        if should_use_tool_model:
            self._set_routing_decision("fallback_clarify")
            return "I need a bit more detail before I can do that."

        # 5. Final fallback to conversational chat
        llm_chat = self._tools_by_name.get("llm_chat")
        if llm_chat:
            logger.info("[router] No specific tool matched. Falling back to conversational chat.")
            try:
                self._set_routing_decision("gemma_chat", tool_name="llm_chat", args={"query": text})
                return self._remember_possible_clarification(llm_chat["callback"](text, {"query": text}))
            except Exception as e:
                logger.error(f"Error executing llm_chat fallback: {e}")
                return f"Error running command: {e}"

        return "I didn't understand that command."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_routing_decision(self, source, tool_name="", args=None, spoken_ack=""):
        self.routing_state.set_decision(source, tool_name=tool_name, args=args, spoken_ack=spoken_ack)
        # Surface the routing source on every decision so the HUD event
        # stream + logs make the active path visible. Cheap (string log +
        # bus publish); the event_bus drops messages with no subscribers.
        try:
            logger.info("[router] decision source=%s tool=%s", source, tool_name or "—")
            if self.event_bus is not None:
                self.event_bus.publish("router_decision", {
                    "source":    source,
                    "tool_name": tool_name or "",
                    "args":      args or {},
                })
        except Exception:
            # Telemetry must never break routing.
            pass

    # ------------------------------------------------------------------
    # Public compatibility API for the capability broker
    # ------------------------------------------------------------------

    def plan_actions(self, text):
        return self._plan_actions(text)

    def find_best_route(self, text, min_score=20):
        return self._find_best_route(text, min_score=min_score)

    def continue_active_workflow(self, text):
        return self._continue_active_workflow(text)

    def finalize_response(self, response):
        return self._finalize_response(response)

    def _should_use_tool_model(self, text_clean, best_route, action_plan):
        if self.llm is not None:
            return True
        if action_plan:
            return False
        if best_route and best_route["spec"]["name"] == "llm_chat":
            return False
        if self._looks_conversational(text_clean):
            return False
        return self._is_tool_oriented_text(text_clean)

    def _looks_conversational(self, text_clean):
        patterns = (
            r"^(?:hi|hello|hey)\b",
            r"\b(?:how are you|what is your name|who are you)\b",
            r"\b(?:tell me something|let'?s talk|chat with me)\b",
        )
        return any(re.search(pattern, text_clean) for pattern in patterns)

    def _is_tool_oriented_text(self, text_clean):
        starters = (
            "open", "launch", "start", "bring up", "run", "execute", "take", "capture", "find", "search",
            "locate", "set", "save", "read", "show", "list", "check", "summarize",
            "summary", "remind", "enable", "disable", "turn", "mute", "unmute",
            "increase", "decrease", "lower", "raise", "pause", "stop",
        )
        if any(text_clean.startswith(starter) for starter in starters):
            return True
        return bool(re.search(r"\b(?:run|open|launch|start|execute)\b.*\b(?:browser|app|application|file|folder)\b", text_clean))

    def _run_tool_model_request(self, llm, text, target_tool=None):
        prompt = self._build_router_prompt(
            text,
            dialog_state=getattr(self, "dialog_state", None),
            target_tool=target_tool,
        )
        # Qwen3 toggle: disable chain-of-thought for tool routing (latency-critical).
        # Harmless on non-Qwen3 models — appears as literal text they ignore.
        messages = [{"role": "user", "content": prompt + "\n\n/no_think"}]
        output_tokens = max(
            24,
            self.tool_target_max_tokens if target_tool else self.tool_max_tokens,
        )

        def _call():
            if hasattr(llm, "create_chat_completion"):
                kwargs = {
                    "messages": messages,
                    "max_tokens": output_tokens,
                    "temperature": self.model_manager.profile("tool").temperature,
                    "top_p": self.tool_top_p,
                }
                if self.tool_json_response:
                    kwargs["response_format"] = {"type": "json_object"}
                try:
                    return llm.create_chat_completion(**kwargs)
                except TypeError:
                    kwargs.pop("response_format", None)
                    return llm.create_chat_completion(**kwargs)
            return {
                "choices": [
                    {
                        "message": {
                            "content": llm(
                                prompt,
                                max_tokens=output_tokens,
                                temperature=self.model_manager.profile("tool").temperature,
                            )["choices"][0]["text"]
                        }
                    }
                ]
            }

        def _call_locked():
            with self.tool_inference_lock:
                return _call()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call_locked)
            try:
                return future.result(timeout=max(1, self.tool_timeout_ms) / 1000)
            except FutureTimeout as exc:
                raise TimeoutError(f"tool model exceeded {self.tool_timeout_ms}ms") from exc

    def _build_tools_prompt(self):
        """Serialize available tools into a compact JSON string for the prompt."""
        if self._tools_prompt_cache is None:
            tools_list = []
            for route in self.tools:
                spec = route["spec"]
                tools_list.append({
                    "name": spec["name"],
                    "description": spec["description"],
                    "parameters": spec.get("parameters", {})
                })
            self._tools_prompt_cache = json.dumps(tools_list, separators=(",", ":"))
        return self._tools_prompt_cache

    def get_llm(self):
        if self.chat_llm is not None:
            return self.chat_llm
        if self.llm is not None:
            return self.llm
        if self._llm_load_failed:
            return None

        with self._llm_lock:
            if self.chat_llm is not None:
                return self.chat_llm
            if self.llm is not None:
                return self.llm
            model = self.model_manager.get_chat_model()
            if model is None:
                self._llm_load_failed = True
                return None
            self.chat_llm = model
            return self.chat_llm

    def get_tool_llm(self):
        if self.tool_llm is not None:
            return self.tool_llm
        if self.llm is not None and self.tool_llm is None:
            return self.llm
        if self._tool_llm_load_failed:
            return None
        # Fast-fail: if tool model is still loading from disk (preload in progress),
        # don't block the turn — keyword/intent matching handles it.
        if not self.model_manager.is_loaded("tool"):
            logger.debug("[router] tool model not in memory yet, skipping LLM routing")
            return None

        with self._tool_llm_lock:
            if self.tool_llm is not None:
                return self.tool_llm
            if self.llm is not None and self.tool_llm is None:
                return self.llm
            model = self.model_manager.get_tool_model()
            if model is None:
                self._tool_llm_load_failed = True
                return None
            self.tool_llm = model
            return self.tool_llm

    def _infer_with_llm(self, text, target_tool=None):
        return self._infer_with_tool_llm(text, target_tool=target_tool)

    def _infer_with_tool_llm(self, text, target_tool=None):
        """
        Ask the tool model to pick a tool and provide args.
        Returns a response string, or None if inference/parsing fails.
        """
        llm = self.get_tool_llm()
        if llm is None:
            return None

        try:
            res = self._run_tool_model_request(llm, text, target_tool=target_tool)

            choice = res["choices"][0]
            raw_output = ""
            if isinstance(choice, dict):
                raw_output = (
                    choice.get("message", {}).get("content")
                    or choice.get("text")
                    or ""
                )
            raw_output = raw_output.strip()

            # Qwen3 reasoning models may still emit <think>...</think> even with
            # /no_think — strip it before JSON parsing.
            raw_output = re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL).strip()

            # Strip markdown fences if Gemma wraps the JSON
            raw_output = raw_output.replace("```json", "").replace("```", "").strip()
            # Ensure the JSON object is terminated
            if raw_output.count("{") > raw_output.count("}"):
                raw_output += "}"

            logger.info(f"[Tool LLM] Raw tool-call output: {raw_output}")
            data = self._parse_llm_payload(raw_output)
            if data is None:
                return None

            if data["mode"] in {"chat", "clarify"} and data["reply"]:
                self._set_routing_decision("qwen_tool", tool_name=data["tool"], args=data["args"], spoken_ack=data["say"])
                return self._remember_possible_clarification(data["reply"])

            tool_name = data["tool"]
            args = data["args"]

            logger.info(f"[Tool LLM] Tool: '{tool_name}', Args: {args}")

            # Find and invoke the matching tool
            route = self._tools_by_name.get(tool_name)
            if route:
                if data["say"]:
                    self.event_bus.publish("voice_response", data["say"])
                self._set_routing_decision("qwen_tool", tool_name=tool_name, args=args, spoken_ack=data["say"])
                return self._invoke_route(route, text, args)

            logger.warning(f"[Tool LLM] Tool '{tool_name}' not found in registered tools.")
        except json.JSONDecodeError as e:
            logger.error(f"[Tool LLM] JSON parse failed: {e}")
        except TimeoutError as e:
            logger.warning(f"[Tool LLM] Inference timed out: {e}")
        except Exception as e:
            logger.error(f"[Tool LLM] Inference error: {e}")

        return None

    def _keyword_fallback(self, text, text_lower):
        """Keyword + fuzzy matching fallback.

        The router used to call _find_best_route with min_score=20, low
        enough that a single ambiguous word like "battery" could elect a
        tool. We keep the default low to accept multi-word aliases (40+),
        but make sure single-word aliases now only score 15 so they can't
        win on their own (see _score_route).
        """
        best_route = self._find_best_route(text, min_score=30)
        if best_route:
            self._set_routing_decision("deterministic", tool_name=best_route["spec"]["name"], args={})
            result = self._invoke_route(best_route, text, {})
            self._last_context = {"tool": best_route["spec"]["name"], "domain": best_route["spec"]["name"], "args": {}}
            return result

        alias_to_tool = {}
        for route in self.tools:
            if route["spec"]["name"] == "llm_chat":
                continue
            for alias in route["aliases"]:
                alias_to_tool[alias] = route

        closest = difflib.get_close_matches(text_lower, list(alias_to_tool), n=1, cutoff=0.75)
        if closest:
            best = closest[0]
            logger.info(f"[router] Fuzzy matched '{text_lower}' → '{best}'")
            route = alias_to_tool[best]
            self._set_routing_decision("deterministic", tool_name=route["spec"]["name"], args={})
            result = self._invoke_route(route, text, {})
            self._last_context = {"tool": route["spec"]["name"], "domain": route["spec"]["name"], "args": {}}
            return result

        logger.debug("No handler matched the command.")
        return None

    def _try_embedding_route(self, text, text_clean):
        """Dispatch via embedding similarity if the top match is confident.

        Skips tools that need structured args (those flagged via the router's
        blocklist or capability_meta.embeddable=False). Returns None if no
        confident match — callers should then fall through to the LLM router.
        """
        router = getattr(self, "embedding_router", None)
        if router is None or not self._tools_by_name:
            return None
        try:
            router.build_index(self._tools_by_name)
            match = router.route(text_clean or text)
        except Exception as exc:
            logger.warning("[router] Embedding route failed: %s", exc)
            return None
        if not match:
            return None

        route = self._tools_by_name.get(match["tool"])
        if route is None:
            return None
        logger.info(
            "[router] Embedding match: '%s' (score=%.2f) — skipping LLM router.",
            match["tool"], match["score"],
        )
        self._set_routing_decision(
            "embedding", tool_name=match["tool"], args={},
        )
        return self._invoke_route(route, text, {})

    def _continue_active_workflow(self, text):
        orchestrator = getattr(self, "workflow_orchestrator", None)
        session_id = getattr(self, "session_id", None)
        if not orchestrator or not session_id:
            return None

        result = orchestrator.continue_active(
            text,
            session_id,
            context={"last_context": dict(self._last_context or {})},
        )
        if not result or not result.handled:
            return None

        self._set_routing_decision("workflow", tool_name=result.workflow_name, args=result.state)
        return self._finalize_response(result.response)

    # Pending slots that mean "I'm waiting for a short conversational
    # answer (yes/no/dictate/generate/topic)" — anything else the user
    # types in that state should defer to the workflow first, even if
    # the IntentRecognizer found a confident-looking tool match.
    _SHORT_ANSWER_SLOTS = frozenset({
        "write_confirmation",
        "content_source",
        "content_topic",
    })

    def _active_workflow_expects_short_answer(self) -> bool:
        memory = getattr(self, "context_store", None) or getattr(self, "memory_service", None)
        session_id = getattr(self, "session_id", None)
        if memory is None or not session_id or not hasattr(memory, "get_active_workflow"):
            return False
        try:
            active = memory.get_active_workflow(session_id)
        except Exception:
            return False
        if not active:
            return False
        pending = set(active.get("pending_slots") or [])
        return bool(pending & self._SHORT_ANSWER_SLOTS)

    def _normalize_text(self, text):
        return " ".join(text.lower().strip().split())

    def _invoke_route(self, route, text, args):
        try:
            response = route["callback"](text, args)
            self._remember_tool_use(route["spec"]["name"], args)
            return self._finalize_response(response)
        except Exception as e:
            logger.error(f"Error executing tool '{route['spec']['name']}': {e}")
            return f"Error running command: {e}"

    def _plan_actions(self, text):
        planned = []
        for action in self.intent_recognizer.plan(text, context=self._last_context):
            route = self._tools_by_name.get(action["tool"])
            if not route:
                return []
            planned.append({
                "route": route,
                "text": action.get("text", text),
                "args": dict(action.get("args", {})),
                "domain": action.get("domain", action["tool"]),
            })

        if planned:
            logger.info(
                "[router] Planned actions: %s",
                ", ".join(action["route"]["spec"]["name"] for action in planned),
            )
            return planned

        return []

    def _execute_plan(self, actions):
        responses = []
        for index, action in enumerate(actions):
            response = self._invoke_route(action["route"], action["text"], action["args"])
            if isinstance(response, list):
                responses.extend(str(item) for item in response if item)
            elif response:
                responses.append(str(response))
            self._remember_action(action)

            dialog_state = getattr(self, "dialog_state", None)
            pending = getattr(dialog_state, "pending_file_request", None) if dialog_state else None
            if pending and pending.candidates and index < len(actions) - 1:
                remaining_actions = []
                for follow_up in actions[index + 1:]:
                    tool_name = follow_up["route"]["spec"]["name"]
                    mapped = self._map_tool_to_file_action(tool_name)
                    if mapped and mapped not in pending.requested_actions:
                        remaining_actions.append(mapped)
                pending.requested_actions.extend(remaining_actions)
                break

        deduped = []
        seen = set()
        for response in responses:
            key = response.strip()
            if key and key not in seen:
                deduped.append(key)
                seen.add(key)

        return self._format_plan_responses(deduped)

    def _format_plan_responses(self, responses):
        if not responses:
            return "Done."
        if len(responses) == 1:
            return responses[0]
        lead = "Got both:" if len(responses) == 2 else "Got those:"
        return f"{lead}\n" + "\n".join(responses)

    def _map_tool_to_file_action(self, tool_name):
        mapping = {
            "open_file": "open",
            "read_file": "read",
            "summarize_file": "summarize",
        }
        return mapping.get(tool_name)

    def _remember_action(self, action):
        self._last_context = {
            "tool": action["route"]["spec"]["name"],
            "domain": action.get("domain", action["route"]["spec"]["name"]),
            "args": dict(action.get("args", {})),
        }
        self._remember_tool_use(action["route"]["spec"]["name"], action.get("args", {}))

    def _remember_tool_use(self, tool_name, args):
        finalizer = getattr(self, "response_finalizer", None)
        if finalizer:
            finalizer.remember_tool_use(tool_name, args)
        else:
            assistant_context = getattr(self, "assistant_context", None)
            if assistant_context:
                assistant_context.remember_tool_use(tool_name, args)

    def _finalize_response(self, response):
        finalizer = getattr(self, "response_finalizer", None)
        if finalizer:
            return finalizer.finalize(response)
        if not isinstance(response, str):
            return response
        assistant_context = getattr(self, "assistant_context", None)
        if assistant_context:
            response = assistant_context.humanize_tool_result(response)
        return self._remember_possible_clarification(response)

    def _remember_possible_clarification(self, response):
        dialog_state = getattr(self, "dialog_state", None)
        if not dialog_state or not isinstance(response, str):
            return response

        search_match = re.search(
            r"Would you like me to search for [\"'](.+?)[\"'](?: on (YouTube(?: Music)?))?\?",
            response,
            re.IGNORECASE,
        )
        if search_match:
            query = search_match.group(1).strip()
            platform = (search_match.group(2) or "").lower()
            action_text = (
                f"play {query} in youtube music"
                if "music" in platform
                else f"play {query} in youtube"
            )
            dialog_state.set_pending_clarification(
                action_text=action_text,
                prompt=response,
                cancel_message="Okay. Tell me what you'd like instead.",
            )
            return response

        meant_match = re.search(r"\"([^\"]+)\"\.\s*Is that what you meant\?", response, re.IGNORECASE)
        if not meant_match:
            meant_match = re.search(r"(?:^|[\s])'([^']+)'\.\s*Is that what you meant\?", response, re.IGNORECASE)
        if meant_match:
            dialog_state.set_pending_clarification(
                action_text=meant_match.group(1).strip(),
                prompt=response,
                cancel_message="Okay. Please say it again in a different way.",
            )
        return response

    def _is_confirmation_input(self, text_lower):
        normalized = text_lower.strip(" .!?")
        return normalized in {
            "yes", "yeah", "yep", "sure", "okay", "ok", "open it", "do it",
            "no", "nope", "cancel", "stop",
        }

    def _build_router_prompt(self, text, dialog_state=None, target_tool=None):
        assistant_context = getattr(self, "assistant_context", None)
        if assistant_context:
            return assistant_context.build_router_prompt(
                text,
                tools=json.loads(self._build_tools_prompt()),
                dialog_state=dialog_state,
                last_context=self._last_context,
                target_tool=target_tool,
            )

        if target_tool:
            tools_json = json.dumps([{
                "name": target_tool["spec"]["name"],
                "description": target_tool["spec"]["description"],
                "parameters": target_tool["spec"].get("parameters", {})
            }])
        else:
            tools_json = self._build_tools_prompt()

        context_str = ""
        if dialog_state:
            state_dict = {}
            if dialog_state.current_folder:
                state_dict["last_folder"] = dialog_state.current_folder
            if dialog_state.selected_file:
                state_dict["last_file"] = dialog_state.selected_file
            if state_dict:
                context_str = f"Context: {json.dumps(state_dict)}\n"

        return (
            "ROUTER_HEADER: FAST_JSON_TOOL_ROUTER_V2\n"
            "ROUTER_FLAGS: JSON_ONLY, COMPACT_ARGS, NO_EXTRA_TEXT\n"
            f"You are a router. Pick the best tool.\n"
            f"{context_str}Tools: {tools_json}\nUser: {text}\n"
            f"First, speak a short natural sentence (e.g. 'Sure, let me check that.'), "
            f"then output exactly 1 JSON object: {{\"tool\": \"name\", \"args\": {{\"key\": \"val\"}}}}"
        )

    def _parse_llm_payload(self, raw_output):
        data = json.loads(raw_output)
        if not isinstance(data, dict):
            return None

        tool_name = data.get("tool", "")
        if not isinstance(tool_name, str):
            tool_name = ""

        args = data.get("args", {})
        if not isinstance(args, dict):
            args = {}

        mode = data.get("mode", "tool")
        if mode not in {"tool", "chat", "clarify"}:
            mode = "tool"

        say = data.get("say", "")
        reply = data.get("reply", "")

        return {
            "mode": mode,
            "tool": tool_name.strip(),
            "args": args,
            "say": say.strip() if isinstance(say, str) else "",
            "reply": reply.strip() if isinstance(reply, str) else "",
        }

    def _split_into_clauses(self, text):
        clauses = [text]
        strong_connector = re.compile(r"\b(?:and then|then|also|after that|afterwards|plus)\b", re.IGNORECASE)
        split_punctuation = re.compile(r"\s*[,;]\s*")

        processed = []
        for clause in clauses:
            processed.extend(part.strip() for part in strong_connector.split(clause) if part.strip())
        clauses = processed

        processed = []
        for clause in clauses:
            parts = split_punctuation.split(clause)
            if len(parts) > 1 and all(self._looks_like_action_clause(part) for part in parts if part.strip()):
                processed.extend(part.strip() for part in parts if part.strip())
            else:
                processed.append(clause.strip())
        clauses = processed

        final_clauses = []
        for clause in clauses:
            final_clauses.extend(self._split_on_action_and(clause))
        return [clause for clause in final_clauses if clause]

    def _split_on_action_and(self, clause):
        if re.search(r"\bopen\s+youtube(?:\s+music)?\b.*\band\s+play\b", clause, re.IGNORECASE):
            return [clause.strip()]
        lower_clause = clause.lower()
        marker = " and "
        idx = lower_clause.find(marker)
        while idx != -1:
            left = clause[:idx].strip(" ,")
            right = clause[idx + len(marker):].strip(" ,")
            if left and right and self._looks_like_action_clause(right):
                return self._split_on_action_and(left) + self._split_on_action_and(right)
            idx = lower_clause.find(marker, idx + len(marker))
        return [clause.strip()]

    def _looks_like_action_clause(self, text):
        starters = (
            "open", "launch", "start", "take", "capture", "find", "search", "locate",
            "open file", "set", "save", "read", "show", "list", "get", "check",
            "tell", "what", "remind", "enable", "disable", "turn", "mute", "unmute",
            "increase", "decrease", "stop", "pause", "play",
        )
        normalized = self._normalize_text(text)
        if any(normalized.startswith(starter) for starter in starters):
            return True
        return self._find_best_route(text, min_score=40) is not None

    def _find_best_route(self, text, min_score=20):
        text_lower = self._normalize_text(text)
        best_route = None
        best_score = 0
        for route in self.tools:
            if route["spec"]["name"] == "llm_chat":
                continue
            score = self._score_route(route, text_lower)
            if score > best_score:
                best_score = score
                best_route = route
        return best_route if best_score >= min_score else None

    def _score_route(self, route, text_lower):
        """Score how well a route matches *text_lower*.

        Tuned so that single-word aliases (e.g. "time", "battery") only
        contribute a small bias rather than enough to fast-path on their
        own. False triggers like "set my time zone" or "battery in my car"
        used to fire here because a bare word-boundary hit scored 41 —
        above the keyword-fallback floor. Now single-word aliases yield
        15 points; multi-word aliases ramp up linearly.
        """
        score = 0

        if text_lower in route["aliases"]:
            score = max(score, 120)

        for pattern in route["patterns"]:
            if pattern.fullmatch(text_lower):
                score = max(score, 110)
            elif pattern.search(text_lower):
                score = max(score, 90)

        for alias in route["aliases"]:
            if alias == text_lower:
                score = max(score, 120)
                continue
            if len(alias) <= 2:
                continue
            if not re.search(rf"\b{re.escape(alias)}\b", text_lower):
                continue
            alias_words = alias.split()
            if len(alias_words) == 1:
                # Single-word aliases are too ambiguous to fast-path on
                # their own. Give a small bias only.
                score = max(score, 15)
            else:
                score = max(score, 40 + len(alias_words))

        for term in route["context_terms"]:
            if len(term) > 2 and re.search(rf"\b{re.escape(term)}\b", text_lower):
                score += 6

        tool_name_words = route["spec"]["name"].split("_")
        if tool_name_words and all(word in text_lower for word in tool_name_words):
            score = max(score, 25)

        return score

    def _build_aliases(self, spec):
        aliases = set(spec.get("aliases", []))
        aliases.add(spec["name"].replace("_", " "))
        aliases.update(self._default_aliases_for(spec["name"]))
        return sorted(alias for alias in aliases if alias)

    def _build_patterns(self, spec):
        return list(spec.get("patterns") or []) + self._default_patterns_for(spec["name"])

    def _build_context_terms(self, spec):
        terms = set(spec.get("context_terms", []))
        terms.update(spec["name"].split("_"))
        terms.update(self._default_context_terms_for(spec["name"]))
        return sorted(term for term in terms if term)

    def _default_aliases_for(self, tool_name):
        defaults = {
            "greet": {"hello", "hi", "hey", "hey friday", "good morning", "good evening"},
            "show_capabilities": {"what can you do", "show help", "show commands", "list capabilities"},
            "launch_app": {"open", "launch", "start"},
            "set_volume": {"volume up", "volume down", "mute", "increase volume", "decrease volume"},
            "take_screenshot": {"screen shot", "capture screen"},
            "search_file": {"find file", "search file", "locate file"},
            "open_file": {"open file"},
            "get_system_status": {"system status", "system health"},
            # Aliases used to include a bare "battery" → high score on any
            # mention. Now require a status framing in the alias too.
            "get_battery": {"battery status", "battery level", "battery percent"},
            "get_cpu_ram": {"cpu usage", "ram usage", "memory usage"},
            "set_reminder": {"remind me", "set reminder"},
            "save_note": {"save note", "note down", "remember this"},
            "read_notes": {"read notes", "show notes", "my notes"},
            "get_time": {"what time is it", "current time", "tell me the time"},
            "get_date": {"today's date", "what day is it", "current date", "tell me the date"},
            "manage_file": {"create file", "make file", "new file", "write it to", "save it to", "write that to", "save that to"},
            "enable_voice": {"enable voice", "start listening", "turn on mic", "turn on microphone"},
            "disable_voice": {"disable voice", "stop listening", "turn off mic", "turn off microphone"},
            "confirm_yes": {"yes", "yeah", "open it", "do it", "sure", "okay"},
            "confirm_no": {"no", "nope", "cancel", "stop that"},
            "select_file_candidate": {"first one", "second one", "this one", "that one", "option 1", "option 2"},
        }
        return defaults.get(tool_name, set())

    def _default_context_terms_for(self, tool_name):
        defaults = {
            "greet": {"greet", "greeting"},
            "show_capabilities": {"commands", "abilities", "capabilities"},
            "launch_app": {"application", "app", "browser", "firefox", "chrome", "calculator"},
            "set_volume": {"volume", "audio", "sound", "mute"},
            "take_screenshot": {"screenshot", "screen", "capture"},
            "search_file": {"find", "search", "file", "locate"},
            "open_file": {"open", "file", "document"},
            "get_system_status": {"system", "status", "health"},
            "get_battery": {"battery", "charge"},
            "get_cpu_ram": {"cpu", "ram", "memory"},
            "set_reminder": {"reminder", "remind"},
            "save_note": {"note", "remember", "save"},
            "read_notes": {"notes", "read", "show"},
            "get_time": {"time", "clock"},
            "get_date": {"date", "day", "today"},
            "manage_file": {"create", "file", "document", "write"},
            "enable_voice": {"voice", "microphone", "mic", "listen"},
            "disable_voice": {"voice", "microphone", "mic", "stop"},
            "confirm_yes": {"yes", "confirm"},
            "confirm_no": {"no", "cancel"},
        }
        return defaults.get(tool_name, set())

    def _default_patterns_for(self, tool_name):
        defaults = {
            "greet": [r"\b(hi|hello|hey|good morning|good afternoon|good evening)\b"],
            "show_capabilities": [r"what can you do", r"show (?:me )?(?:your\s+)?(?:commands|capabilities|abilities)", r"list (?:your\s+)?(?:commands|capabilities)"],
            # Generic "open X" used to fast-path to launch_app even when X was not an
            # app name (e.g. "open the discussion"). We keep the loose pattern here
            # but score it lower; the IntentRecognizer's registry-aware extractor
            # remains the authoritative path. Without an `app_names` resolution it
            # should not auto-execute.
            "launch_app": [r"\b(?:open|launch|start|bring up)\s+(?!file\b|folder\b|the\s+folder\b)[a-z0-9][\w\-\s,]*(?:\band\b\s*[a-z0-9][\w\-\s]*)*"],
            "set_volume": [r"\b(?:volume|mute|unmute)\b", r"\b(?:increase|decrease|turn)\s+volume\b"],
            # Both forms require an explicit capture verb. Previously the second
            # alternative was bare `\bscreenshot\b` which fired on "I deleted my
            # screenshot folder" — pure mention.
            "take_screenshot": [
                r"\b(?:take|capture|grab|snap|get|make)\s+(?:a\s+|another\s+|the\s+)?(?:screenshot|screen\s*shot|screen\s+capture)\b",
                r"^(?:please\s+)?screen\s*shot(?:\s+please)?[.!?]?$",
            ],
            "search_file": [r"\b(?:find|search|locate)\s+(?:for\s+)?(?:file\s+)?\S+"],
            "open_file": [r"\bopen\s+(?:the\s+)?file\b"],
            "get_system_status": [r"\b(?:system status|system health)\b"],
            # `\bbattery\b` alone overmatches ("the battery in my car"); require an
            # explicit status verb or possessive context.
            "get_battery": [
                r"\b(?:battery\s+(?:status|level|percent(?:age)?|charge|life|remaining)|"
                r"(?:what(?:'s| is)\s+(?:my\s+|the\s+)?battery)|how('s|\s+is)\s+(?:my\s+|the\s+)?battery)\b",
            ],
            # `memory` alone overmatches; require explicit usage/load language.
            "get_cpu_ram": [
                r"\b(?:cpu\s+(?:usage|load|status)|ram\s+(?:usage|status|free)|memory\s+(?:usage|load|status|free))\b",
                r"\bsystem\s+(?:usage|load|performance)\b",
            ],
            "set_reminder": [r"\bremind me\b", r"\bset (?:a )?reminder\b"],
            "save_note": [r"\b(?:save note|note down|remember this|remember that)\b"],
            "read_notes": [r"\b(?:read|show|list)\s+(?:my\s+)?notes\b"],
            # Anchored time/date patterns only — bare `\btime\b` / `\bdate\b` overmatch on
            # phrases like "set my time zone", "I have a date tonight", "time to leave".
            "get_time": [r"\b(?:what(?:'s| is)? the time|what time is it|current time|tell me(?: the)? time)\b"],
            "get_date": [r"\b(?:today(?:'s)? date|what day is it|current date|tell me(?: the)? date)\b"],
            "manage_file": [
                r"\b(?:create|make)\s+(?:a\s+)?file\b",
                r"\b(?:write|save|append|add)\s+(?:it|that|this|the answer|the response)\s+(?:to|into|in)\s+\S+",
            ],
            "enable_voice": [r"\b(?:enable|start|turn on)\s+(?:the\s+)?(?:mic|microphone|voice)\b"],
            "disable_voice": [r"\b(?:disable|stop|turn off)\s+(?:the\s+)?(?:mic|microphone|voice)\b"],
            "confirm_yes": [r"^(?:yes|yeah|yep|sure|okay|ok|open it|do it)$"],
            "confirm_no": [r"^(?:no|nope|cancel|stop)$"],
            "select_file_candidate": [r"^(?:the\s+)?(?:first|second|third|fourth|fifth|last)\s+(?:one|file)$", r"^(?:the\s+)?(?:this|that)\s+(?:one|file)$", r"^(?:option\s+)?\d+$", r"^(?:the\s+)?(?:pdf|txt|md|json|csv|py|docx)\s+one$"],
        }
        return defaults.get(tool_name, [])
