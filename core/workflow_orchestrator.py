import os
import re
from dataclasses import dataclass, field

from core.logger import logger

try:
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - optional dependency
    END = "__end__"
    StateGraph = None


@dataclass
class WorkflowResult:
    handled: bool
    response: str = ""
    workflow_name: str = ""
    state: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class BaseWorkflow:
    name = ""

    def __init__(self, app):
        self.app = app
        self._compiled_graph = None

    def should_start(self, user_text, context=None):
        return False

    def can_continue(self, user_text, state, context=None):
        return bool(state)

    def run(self, user_text, session_id, context=None):
        initial_state = {
            "user_text": user_text,
            "session_id": session_id,
            "context": dict(context or {}),
            "result": WorkflowResult(handled=False, workflow_name=self.name),
        }
        if StateGraph is None:
            return self._handle(initial_state)["result"]

        if self._compiled_graph is None:
            graph = StateGraph(dict)
            graph.add_node("handle", self._handle)
            graph.set_entry_point("handle")
            graph.add_edge("handle", END)
            self._compiled_graph = graph.compile()

        final_state = self._compiled_graph.invoke(initial_state)
        return final_state["result"]

    def _handle(self, state):
        raise NotImplementedError


class FileWorkflow(BaseWorkflow):
    name = "file_workflow"

    def can_continue(self, user_text, state, context=None):
        if not state:
            return False
        normalized = (user_text or "").strip().lower()
        if state.get("pending_slots"):
            return True
        if normalized in {"yes", "yeah", "yep", "sure", "okay", "ok", "do that", "save that", "write that"}:
            return True
        return bool(re.search(r"\b(?:save|write|append|add)\s+(?:that|this|it)\b", normalized))

    def _handle(self, state):
        user_text = state["user_text"]
        session_id = state["session_id"]
        workflow_state = self.app.context_store.get_active_workflow(session_id, workflow_name=self.name) or {}
        controller = getattr(self.app, "file_controller", None)
        if controller is None:
            state["result"] = WorkflowResult(
                handled=False,
                workflow_name=self.name,
                response="File workflow is not available yet.",
            )
            return state

        pending_slots = list(workflow_state.get("pending_slots") or [])
        target = dict(workflow_state.get("target") or {})
        action = workflow_state.get("action") or workflow_state.get("last_action") or "create"
        normalized = (user_text or "").strip()
        lower_text = normalized.lower()

        if "filename" in pending_slots:
            filename = self._extract_filename(normalized)
            if not filename:
                response = "What should I name the file?"
            else:
                response = controller.manage(
                    user_text,
                    {
                        "action": action,
                        "filename": filename,
                        "folder": target.get("folder", ""),
                        "extension": target.get("extension", ""),
                    },
                )
            state["result"] = WorkflowResult(
                handled=True,
                workflow_name=self.name,
                response=response,
                state=self.app.context_store.get_active_workflow(session_id, workflow_name=self.name) or {},
            )
            return state

        if "content" in pending_slots:
            filename = target.get("filename") or os.path.basename(target.get("path", ""))
            if lower_text in {"yes", "yeah", "yep", "sure", "okay", "ok", "do that"}:
                response = f"What would you like me to write in {filename or 'the file'}?"
                state["result"] = WorkflowResult(
                    handled=True,
                    workflow_name=self.name,
                    response=response,
                    state=workflow_state,
                )
                return state

            args = {
                "action": action if action in {"write", "append"} else "write",
                "filename": filename,
                "folder": target.get("folder", ""),
                "extension": target.get("extension", ""),
            }
            if re.search(r"\b(?:save|write|append|add)\s+(?:that|this|it|the answer|the response)\b", lower_text):
                response = controller.manage(user_text, args)
            else:
                args["content"] = normalized
                response = controller.manage(user_text, args)
            state["result"] = WorkflowResult(
                handled=True,
                workflow_name=self.name,
                response=response,
                state=self.app.context_store.get_active_workflow(session_id, workflow_name=self.name) or {},
            )
            return state

        if re.search(r"\b(?:save|write|append|add)\s+(?:that|this|it)\b", lower_text) and target.get("filename"):
            response = controller.manage(
                user_text,
                {
                    "action": "append" if "append" in lower_text or "add" in lower_text else "write",
                    "filename": target.get("filename"),
                    "folder": target.get("folder", ""),
                    "extension": target.get("extension", ""),
                },
            )
            state["result"] = WorkflowResult(
                handled=True,
                workflow_name=self.name,
                response=response,
                state=self.app.context_store.get_active_workflow(session_id, workflow_name=self.name) or workflow_state,
            )
            return state

        if lower_text in {"yes", "yeah", "yep", "sure", "okay", "ok", "do that"}:
            summary = workflow_state.get("result_summary") or "I still have the file workflow open."
            state["result"] = WorkflowResult(
                handled=True,
                workflow_name=self.name,
                response=summary,
                state=workflow_state,
            )
            return state

        state["result"] = WorkflowResult(handled=False, workflow_name=self.name, state=workflow_state)
        return state

    def _extract_filename(self, text):
        cleaned = re.sub(r"[^\w.\- ]+", " ", text or "").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if not cleaned:
            return ""
        return cleaned.strip(" .")


class BrowserMediaWorkflow(BaseWorkflow):
    name = "browser_media"

    def should_start(self, user_text, context=None):
        lower_text = (user_text or "").lower()
        return "youtube" in lower_text or "youtube music" in lower_text

    def can_continue(self, user_text, state, context=None):
        lower_text = (user_text or "").lower().strip()
        if self.should_start(user_text, context=context):
            return True
        media_keywords = {
            "pause", "resume", "next", "skip", "play", "previous", "forward", "back", "backward", "revert", "rewind",
            "open it in music instead", "play it in music instead"
        }
        return any(word in lower_text for word in media_keywords)

    def _handle(self, state):
        user_text = state["user_text"]
        session_id = state["session_id"]
        context = dict(state.get("context") or {})
        workflow_state = self.app.context_store.get_active_workflow(session_id, workflow_name=self.name) or {}
        intent = self._parse_intent(user_text, workflow_state, context)
        if not intent:
            state["result"] = WorkflowResult(handled=False, workflow_name=self.name, state=workflow_state)
            return state

        service = getattr(self.app, "browser_media_service", None)
        if service is None:
            state["result"] = WorkflowResult(
                handled=True,
                workflow_name=self.name,
                response="Browser automation is not available yet.",
                state=workflow_state,
            )
            return state

        action = intent["action"]
        platform = intent.get("platform") or workflow_state.get("platform") or "youtube"
        browser_name = intent.get("browser_name") or workflow_state.get("browser_name") or "chrome"
        query = intent.get("query") or workflow_state.get("query") or ""

        if action == "open":
            url = "https://music.youtube.com" if platform == "youtube_music" else "https://www.youtube.com"
            response = service.open_browser_url(url, browser_name=browser_name, platform=platform)
        elif action == "play":
            if platform == "youtube_music":
                response = service.play_youtube_music(query, browser_name=browser_name)
            else:
                response = service.play_youtube(query, browser_name=browser_name)
        else:
            response = service.browser_media_control(action, platform=platform, query=query)

        updated_state = {
            "status": "active",
            "pending_slots": [],
            "last_action": action,
            "target": {"browser_name": browser_name, "platform": platform, "query": query},
            "result_summary": response,
            "browser_name": browser_name,
            "platform": platform,
            "query": query,
        }
        self.app.context_store.save_workflow_state(session_id, self.name, updated_state)
        state["result"] = WorkflowResult(
            handled=True,
            workflow_name=self.name,
            response=response,
            state=updated_state,
            metadata=intent,
        )
        return state

    def _parse_intent(self, user_text, workflow_state, context):
        lower_text = (user_text or "").strip().lower()
        browser_name = context.get("browser_name") or self._extract_browser_name(lower_text) or "chrome"
        if context.get("action") == "open_browser_url":
            return {
                "action": "open",
                "platform": "youtube_music" if "music.youtube.com" in context.get("url", "") else "youtube",
                "browser_name": browser_name,
            }
        if context.get("action") in {"play_youtube", "play_youtube_music"}:
            return {
                "action": "play",
                "platform": "youtube_music" if context["action"] == "play_youtube_music" else "youtube",
                "browser_name": browser_name,
                "query": context.get("query", ""),
            }
        if context.get("action") == "browser_media_control":
            return {
                "action": context.get("control", ""),
                "platform": workflow_state.get("platform") or "youtube",
                "browser_name": browser_name,
                "query": workflow_state.get("query", ""),
            }

        play_music = re.search(r"\bplay\s+(.+?)\s+in\s+youtube music\b", lower_text)
        if play_music:
            return {
                "action": "play",
                "platform": "youtube_music",
                "browser_name": browser_name,
                "query": play_music.group(1).strip(),
            }

        play_video = re.search(r"\bplay\s+(.+?)\s+in\s+youtube\b", lower_text)
        if play_video:
            return {
                "action": "play",
                "platform": "youtube",
                "browser_name": browser_name,
                "query": play_video.group(1).strip(),
            }

        if re.search(r"\bopen\s+youtube music\b", lower_text):
            return {"action": "open", "platform": "youtube_music", "browser_name": browser_name}
        if re.search(r"\bopen\s+youtube\b", lower_text):
            return {"action": "open", "platform": "youtube", "browser_name": browser_name}

        media_map = {
            "pause": "pause",
            "resume": "resume",
            "play": "resume",
            "next": "next",
            "skip": "next",
            "previous": "previous",
            "forward": "forward",
            "backward": "backward",
            "revert": "backward",
            "rewind": "backward",
        }
        for keyword, cmd in media_map.items():
            if keyword in lower_text:
                return {
                    "action": cmd,
                    "platform": workflow_state.get("platform") or "youtube",
                    "browser_name": browser_name,
                    "query": workflow_state.get("query", ""),
                }

        if "music instead" in lower_text:
            return {
                "action": "play" if workflow_state.get("query") else "open",
                "platform": "youtube_music",
                "browser_name": browser_name,
                "query": workflow_state.get("query", ""),
            }

        if "youtube instead" in lower_text:
            return {
                "action": "play" if workflow_state.get("query") else "open",
                "platform": "youtube",
                "browser_name": browser_name,
                "query": workflow_state.get("query", ""),
            }

        return None

    def _extract_browser_name(self, text):
        if "chromium" in text:
            return "chromium"
        if "chrome" in text:
            return "chrome"
        return ""


class WorkflowOrchestrator:
    def __init__(self, app):
        self.app = app
        self.workflows = {}
        self.register(FileWorkflow(app))
        self.register(BrowserMediaWorkflow(app))

    def register(self, workflow):
        self.workflows[workflow.name] = workflow

    def run(self, workflow_name, user_text, session_id, context=None):
        workflow = self.workflows.get(workflow_name)
        if workflow is None:
            return WorkflowResult(handled=False, workflow_name=workflow_name)
        logger.info("[workflow] Running workflow: %s", workflow_name)
        return workflow.run(user_text, session_id, context=context)

    def continue_active(self, user_text, session_id, context=None):
        active = self.app.context_store.get_active_workflow(session_id)
        if not active:
            return WorkflowResult(handled=False)
        workflow = self.workflows.get(active.get("workflow_name"))
        if workflow is None or not workflow.can_continue(user_text, active, context=context):
            return WorkflowResult(handled=False, workflow_name=active.get("workflow_name", ""))
        return workflow.run(user_text, session_id, context=context)

    def detect_workflow(self, user_text, session_id, context=None):
        active = self.app.context_store.get_active_workflow(session_id)
        if active:
            workflow = self.workflows.get(active.get("workflow_name"))
            if workflow and workflow.can_continue(user_text, active, context=context):
                return workflow.name
        for workflow in self.workflows.values():
            if workflow.should_start(user_text, context=context):
                return workflow.name
        return ""

