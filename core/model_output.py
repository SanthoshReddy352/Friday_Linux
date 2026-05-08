"""Helpers for cleaning local model output before it reaches users or files."""

from __future__ import annotations

import re
from typing import Any


THINK_BLOCK_PATTERN = re.compile(
    r"<think\b[^>]*>.*?(?:</think>|$)",
    re.IGNORECASE | re.DOTALL,
)
NO_THINK_SUFFIX = "/no_think"


def strip_model_artifacts(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = THINK_BLOCK_PATTERN.sub("", text)
    cleaned = re.sub(r"(?im)^\s*/(?:no_)?think\s*$", "", cleaned)
    return cleaned.strip()


def with_no_think_user_message(messages: list[dict]) -> list[dict]:
    patched = [dict(message) for message in messages]
    for message in reversed(patched):
        if message.get("role") == "user":
            content = str(message.get("content", "")).rstrip()
            recent_lines = content.splitlines()[-2:]
            if NO_THINK_SUFFIX not in recent_lines:
                message["content"] = f"{content}\n\n{NO_THINK_SUFFIX}".strip()
            break
    return patched


def extract_fenced_code(text: str) -> str:
    if not isinstance(text, str):
        return ""
    match = re.search(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()
