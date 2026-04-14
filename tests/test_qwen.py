import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


MODELS = {
    "chat": Path("/mnt/NewVolume/FRIDAY/models/gemma-2b-it.gguf"),
    "tool": Path("/mnt/NewVolume/FRIDAY/models/qwen2.5-7b-instruct.gguf"),
}

EVAL_CASES = [
    {
        "label": "tool-launch",
        "user": "open firefox and chromium",
        "expect_mode": "tool",
        "expect_tool": "launch_app",
    },
    {
        "label": "tool-time",
        "user": "what time is it",
        "expect_mode": "tool",
        "expect_tool": "get_time",
    },
    {
        "label": "chat-name",
        "user": "what is your name",
        "expect_mode": "chat",
        "expect_tool": "",
    },
    {
        "label": "chat-smalltalk",
        "user": "hello there",
        "expect_mode": "chat",
        "expect_tool": "",
    },
]


def build_router_prompt(user_text):
    tools = [
        {"name": "launch_app", "description": "Launch a desktop application by name.", "parameters": {"app_names": ["string"]}},
        {"name": "get_time", "description": "Tell the current time.", "parameters": {}},
        {"name": "take_screenshot", "description": "Capture a screenshot.", "parameters": {}},
        {"name": "llm_chat", "description": "General conversation fallback.", "parameters": {"query": "string"}},
    ]
    payload = {
        "assistant_identity": "FRIDAY, a warm local desktop assistant.",
        "available_tools": tools,
        "response_style": ["Return strict JSON only."],
    }
    return (
        "You are FRIDAY's intent engine.\n"
        "Return exactly one JSON object and nothing else.\n"
        '{"mode":"tool|chat|clarify","tool":"tool_name","args":{},"say":"short spoken acknowledgement","reply":"assistant reply"}\n'
        f"Context: {json.dumps(payload, ensure_ascii=True)}\n"
        f"User: {user_text}"
    )


def parse_payload(raw_text):
    cleaned = raw_text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


@pytest.mark.skipif(
    os.getenv("FRIDAY_RUN_MODEL_EVAL") != "1",
    reason="Set FRIDAY_RUN_MODEL_EVAL=1 to run the local model evaluation harness.",
)
def test_local_model_eval_harness():
    from llama_cpp import Llama

    results = []
    for role, model_path in MODELS.items():
        assert model_path.exists(), f"Missing model: {model_path}"

        llm = Llama(model_path=str(model_path), n_ctx=4096, n_batch=512, verbose=False)
        for case in EVAL_CASES:
            start = time.perf_counter()
            response = llm.create_chat_completion(
                messages=[{"role": "user", "content": build_router_prompt(case["user"])}],
                max_tokens=120,
                temperature=0.1,
            )
            elapsed = time.perf_counter() - start
            payload = parse_payload(response["choices"][0]["message"]["content"])

            results.append(
                {
                    "role": role,
                    "label": case["label"],
                    "elapsed_s": round(elapsed, 2),
                    "payload": payload,
                }
            )

            assert payload["mode"] in {"tool", "chat", "clarify"}
            if case["expect_mode"] == "tool":
                assert payload["tool"] == case["expect_tool"]
            if case["expect_mode"] == "chat":
                assert payload["mode"] in {"chat", "clarify"}

    print("\nModel evaluation results:")
    for item in results:
        print(
            f"{item['role']} {item['label']} {item['elapsed_s']}s "
            f"{json.dumps(item['payload'], ensure_ascii=True)}"
        )
