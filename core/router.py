import difflib
import json
import os
import re
import threading
from core.intent_recognizer import IntentRecognizer
from core.logger import logger


class CommandRouter:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.tools = []
        self._tools_by_name = {}
        self._tool_aliases = {}
        self._tool_patterns = {}
        self._tools_prompt_cache = None
        self.llm = None
        self.llm_model_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "models", "gemma-2b-it.gguf"
        )
        self._llm_lock = threading.Lock()
        self._llm_load_failed = False
        self._last_context = {}
        # Deterministic routing is faster and more reliable than LLM tool selection.
        self.enable_llm_tool_routing = os.getenv("FRIDAY_USE_LLM_TOOL_ROUTER", "0") == "1"
        self.intent_recognizer = IntentRecognizer(self)
        if os.path.exists(self.llm_model_path):
            logger.info(f"[router] Gemma intent model available for lazy loading: {self.llm_model_path}")
        else:
            logger.warning(f"Llama model not found at {self.llm_model_path}. Chat will be unavailable.")

    # ------------------------------------------------------------------
    # Primary API: structured tool registration
    # ------------------------------------------------------------------

    def register_tool(self, tool_spec: dict, callback):
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
        }
        self.tools.append(route)
        self._tools_by_name[spec["name"]] = route
        self._tool_aliases[spec["name"]] = aliases
        self._tool_patterns[spec["name"]] = patterns
        self._tools_prompt_cache = None
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
        Process user text using Gemma tool-calling, falling back to
        keyword/fuzzy matching when LLM is unavailable or fails.
        Returns a response string.
        """
        logger.info(f"Router received: {text}")
        text_lower = self._normalize_text(text)
        if not text_lower or not re.search(r"[a-z0-9]", text_lower):
            return ""

        # 1. Deterministic plan for one or more concrete actions
        action_plan = self._plan_actions(text)
        if action_plan:
            return self._execute_plan(action_plan)

        # 2. Optional experimental LLM tool selection
        if self.enable_llm_tool_routing and self.get_llm() and self.tools:
            result = self._infer_with_llm(text)
            if result is not None:
                return result

        # 3. Deterministic fallback
        fallback_result = self._keyword_fallback(text, text_lower)
        if fallback_result is not None:
            return fallback_result

        # 4. Final fallback to conversational chat
        llm_chat = self._tools_by_name.get("llm_chat")
        if llm_chat:
            try:
                return llm_chat["callback"](text, {"query": text})
            except Exception as e:
                logger.error(f"Error executing llm_chat fallback: {e}")
                return f"Error running command: {e}"

        return "I didn't understand that command."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
        if self.llm is not None:
            return self.llm
        if self._llm_load_failed:
            return None
        if not os.path.exists(self.llm_model_path):
            return None

        with self._llm_lock:
            if self.llm is not None:
                return self.llm
            if self._llm_load_failed:
                return None
            try:
                from llama_cpp import Llama

                logger.info(f"Loading Gemma intent model from {self.llm_model_path}...")
                self.llm = Llama(
                    model_path=self.llm_model_path,
                    n_ctx=2048,
                    n_threads=max(1, (os.cpu_count() or 2) - 1),
                    verbose=False,
                )
            except Exception as e:
                logger.error(f"Error initializing Llama: {e}")
                self._llm_load_failed = True
                self.llm = None
        return self.llm

    def _infer_with_llm(self, text):
        """
        Ask Gemma to pick a tool and provide args.
        Returns a response string, or None if inference/parsing fails.
        """
        try:
            tools_json = self._build_tools_prompt()
            prompt = (
                f"You are FRIDAY, an offline desktop assistant. "
                f"Given the user's input and the list of available tools, "
                f"reply with EXACTLY ONE JSON object selecting the best tool.\n\n"
                f"Available tools:\n{tools_json}\n\n"
                f"User input: \"{text}\"\n\n"
                f"Reply format (strict JSON, no markdown, nothing else):\n"
                f'{{\"tool\": \"<tool_name>\", \"args\": {{<key>: <value>}}}}'
            )

            messages = [
                {"role": "user", "content": prompt}
            ]
            if hasattr(self.llm, "create_chat_completion"):
                res = self.llm.create_chat_completion(messages=messages, max_tokens=150, temperature=0.1)
            else:
                res = self.llm(prompt, max_tokens=150, temperature=0.1)

            choice = res["choices"][0]
            raw_output = ""
            if isinstance(choice, dict):
                raw_output = (
                    choice.get("message", {}).get("content")
                    or choice.get("text")
                    or ""
                )
            raw_output = raw_output.strip()

            # Strip markdown fences if Gemma wraps the JSON
            raw_output = raw_output.replace("```json", "").replace("```", "").strip()
            # Ensure the JSON object is terminated
            if raw_output.count("{") > raw_output.count("}"):
                raw_output += "}"

            logger.info(f"[LLM] Raw tool-call output: {raw_output}")
            data = json.loads(raw_output)

            tool_name = data.get("tool", "").strip()
            args = data.get("args", {})
            if not isinstance(args, dict):
                args = {}

            logger.info(f"[LLM] Tool: '{tool_name}', Args: {args}")

            # Find and invoke the matching tool
            route = self._tools_by_name.get(tool_name)
            if route:
                return route["callback"](text, args)

            logger.warning(f"[LLM] Tool '{tool_name}' not found in registered tools.")
        except json.JSONDecodeError as e:
            logger.error(f"[LLM] JSON parse failed: {e}")
        except Exception as e:
            logger.error(f"[LLM] Inference error: {e}")

        return None

    def _keyword_fallback(self, text, text_lower):
        """Keyword + fuzzy matching fallback."""
        best_route = self._find_best_route(text)
        if best_route:
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
            result = self._invoke_route(route, text, {})
            self._last_context = {"tool": route["spec"]["name"], "domain": route["spec"]["name"], "args": {}}
            return result

        logger.debug("No handler matched the command.")
        return None

    def _normalize_text(self, text):
        return " ".join(text.lower().strip().split())

    def _invoke_route(self, route, text, args):
        try:
            return route["callback"](text, args)
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

        return "\n".join(deduped) if deduped else "Done."

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
            "increase", "decrease", "stop", "pause",
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
            elif len(alias) > 2 and re.search(rf"\b{re.escape(alias)}\b", text_lower):
                score = max(score, 40 + len(alias.split()))

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
        return self._default_patterns_for(spec["name"])

    def _build_context_terms(self, spec):
        terms = set(spec.get("context_terms", []))
        terms.update(spec["name"].split("_"))
        terms.update(self._default_context_terms_for(spec["name"]))
        return sorted(term for term in terms if term)

    def _default_aliases_for(self, tool_name):
        defaults = {
            "greet": {"hello", "hi", "hey", "hey friday", "good morning", "good evening"},
            "show_help": {"help", "what can you do", "show help", "show commands"},
            "launch_app": {"open", "launch", "start"},
            "set_volume": {"volume up", "volume down", "mute", "increase volume", "decrease volume"},
            "take_screenshot": {"screenshot", "screen shot", "capture screen"},
            "search_file": {"find file", "search file", "locate file"},
            "open_file": {"open file"},
            "get_system_status": {"system status", "system health"},
            "get_battery": {"battery", "battery status"},
            "get_cpu_ram": {"cpu", "ram", "memory usage"},
            "set_reminder": {"remind me", "set reminder"},
            "save_note": {"save note", "note down", "remember this"},
            "read_notes": {"read notes", "show notes", "my notes"},
            "get_time": {"time", "what time is it"},
            "get_date": {"date", "today's date", "what day is it"},
            "enable_voice": {"enable voice", "start listening", "turn on mic", "turn on microphone"},
            "disable_voice": {"disable voice", "stop listening", "turn off mic", "turn off microphone"},
            "confirm_yes": {"yes", "yeah", "open it", "do it", "sure", "okay"},
            "confirm_no": {"no", "nope", "cancel", "stop that"},
        }
        return defaults.get(tool_name, set())

    def _default_context_terms_for(self, tool_name):
        defaults = {
            "greet": {"greet", "greeting"},
            "show_help": {"help", "commands", "abilities"},
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
            "enable_voice": {"voice", "microphone", "mic", "listen"},
            "disable_voice": {"voice", "microphone", "mic", "stop"},
            "confirm_yes": {"yes", "confirm"},
            "confirm_no": {"no", "cancel"},
        }
        return defaults.get(tool_name, set())

    def _default_patterns_for(self, tool_name):
        defaults = {
            "greet": [r"\b(hi|hello|hey|good morning|good afternoon|good evening)\b"],
            "show_help": [r"\bhelp\b", r"what can you do", r"show (?:me )?(?:the )?commands"],
            "launch_app": [r"\b(?:open|launch|start|bring up)\s+(?!file\b)[a-z0-9][\w\-\s,]*(?:\band\b\s*[a-z0-9][\w\-\s]*)*"],
            "set_volume": [r"\b(?:volume|mute|unmute)\b", r"\b(?:increase|decrease|turn)\s+volume\b"],
            "take_screenshot": [r"\b(?:take|capture).*(?:screenshot|screen shot)\b", r"\bscreenshot\b"],
            "search_file": [r"\b(?:find|search|locate)\s+(?:for\s+)?(?:file\s+)?\S+"],
            "open_file": [r"\bopen\s+(?:the\s+)?file\b"],
            "get_system_status": [r"\b(?:system status|system health)\b"],
            "get_battery": [r"\bbattery\b"],
            "get_cpu_ram": [r"\b(?:cpu|ram|memory usage)\b"],
            "set_reminder": [r"\bremind me\b", r"\bset (?:a )?reminder\b"],
            "save_note": [r"\b(?:save note|note down|remember this|remember that)\b"],
            "read_notes": [r"\b(?:read|show|list)\s+(?:my\s+)?notes\b"],
            "get_time": [r"\b(?:what(?:'s| is)? the time|what time is it|current time|tell me(?: the)? time)\b"],
            "get_date": [r"\b(?:today(?:'s)? date|what day is it|current date|tell me(?: the)? date)\b"],
            "enable_voice": [r"\b(?:enable|start|turn on)\s+(?:the\s+)?(?:mic|microphone|voice)\b"],
            "disable_voice": [r"\b(?:disable|stop|turn off)\s+(?:the\s+)?(?:mic|microphone|voice)\b"],
            "confirm_yes": [r"^(?:yes|yeah|yep|sure|okay|ok|open it|do it)$"],
            "confirm_no": [r"^(?:no|nope|cancel|stop)$"],
        }
        return defaults.get(tool_name, [])
