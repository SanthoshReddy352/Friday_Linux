import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.assistant_context import AssistantContext


def test_build_chat_messages_coerces_history_to_alternating_roles():
    context = AssistantContext(max_messages=16)
    context.record_message("assistant", "Hello from FRIDAY.")
    context.record_message("assistant", "Still here.")
    context.record_message("user", "hi")
    context.record_message("user", "what is your name")

    messages = context.build_chat_messages("what is your name")
    roles = [message["role"] for message in messages]

    assert roles[0] == "user"
    assert roles[-1] == "user"
    for index in range(1, len(roles)):
        assert roles[index] != roles[index - 1]


def test_build_chat_messages_appends_latest_query_after_assistant_turn():
    context = AssistantContext(max_messages=16)
    context.record_message("user", "hello")
    context.record_message("assistant", "hey there")

    messages = context.build_chat_messages("tell me more")

    assert messages[-1]["role"] == "user"
    assert "tell me more" in messages[-1]["content"]
