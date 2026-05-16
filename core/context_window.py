"""Context-window budgeting for local LLM prompts (Batch 6 / Issue 5c).

Llama.cpp raises ``Requested tokens (N) exceed context window of M`` when
the prompt + reserved response tokens overflow the model's ``n_ctx``.
We saw this in the wild after a ~30-turn chat session::

    [LLMChat] Inference error: Requested tokens (5445) exceed context window of 4096

The fix is cooperative: before calling the LLM, count the tokens in the
serialized prompt and, if we're over budget, drop the oldest non-system
messages until we fit. We deliberately *don't* run an LLM summarisation
step here — that would add a second inference per turn and defeat the
purpose. Dropping the oldest user/assistant turns is the cheapest path
that keeps the model usable; semantic recall still surfaces older facts
via the assistant_context bundle.

The helpers degrade gracefully when ``llm.tokenize`` is unavailable
(tests, off-line scenarios): they fall back to a ~4-chars-per-token
approximation. That's coarse but always returns *some* answer, and the
budget headroom in ``response_budget`` (default 512) absorbs the slack.
"""

from __future__ import annotations

from typing import Sequence

from core.logger import logger

# Pessimistic chars-per-token used when the model exposes no tokenizer.
# GPT-style BPE averages ~3.5 chars/token in English; we round down to be
# safe under the budget.
_FALLBACK_CHARS_PER_TOKEN = 3.5


def _render_messages(messages: Sequence[dict]) -> str:
    """Flatten a chat-messages list to a single string for tokenization.

    Llama.cpp doesn't expose chat-template token counts directly via the
    Python binding, so we approximate with role-tagged content. The tag
    overhead (``user:``, ``assistant:``) is constant across messages and
    a few tokens of slack matters less than the conversation tail.
    """
    parts: list[str] = []
    for m in messages:
        role = str(m.get("role") or "user")
        content = str(m.get("content") or "")
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def count_tokens(llm, messages: Sequence[dict]) -> int:
    """Approximate the prompt-token count for ``messages``.

    ``llm`` is a llama-cpp-python ``Llama`` instance (or any object with a
    ``tokenize(bytes) -> list[int]`` method). When tokenization fails or
    the method is missing, falls back to a chars-per-token heuristic.
    """
    blob = _render_messages(messages)
    if llm is not None and hasattr(llm, "tokenize"):
        try:
            tokens = llm.tokenize(blob.encode("utf-8"))
            return len(tokens)
        except Exception as exc:
            logger.debug("[context-window] llm.tokenize failed: %s — falling back", exc)
    return max(1, int(len(blob) / _FALLBACK_CHARS_PER_TOKEN))


def fit_messages(
    llm,
    messages: Sequence[dict],
    n_ctx: int,
    response_budget: int = 512,
    min_keep_tail: int = 4,
) -> list[dict]:
    """Trim ``messages`` so prompt-tokens + ``response_budget`` ≤ ``n_ctx``.

    Drops the oldest *non-leading* messages one at a time. The first
    message (typically the system/persona/guidance block) is always
    preserved; so is the last ``min_keep_tail`` (the active exchange).
    Returns a new list — the input is not mutated.

    If even the head + tail exceeds the budget, returns head + tail as-is
    and lets the LLM produce a (likely truncated) reply rather than fail
    the turn. That's the same trade-off Anthropic / OpenAI clients make.
    """
    if n_ctx <= 0:
        return list(messages)
    # Keep a small floor (64) so a misconfigured n_ctx can't make every
    # prompt look "over budget"; real production models run at n_ctx ≥
    # 2048 so this floor is invisible in normal use.
    budget = max(64, int(n_ctx) - max(0, int(response_budget)))
    msgs = list(messages)
    if not msgs:
        return msgs
    current = count_tokens(llm, msgs)
    if current <= budget:
        return msgs
    if len(msgs) <= min_keep_tail + 1:
        # Nothing safe to drop — let the model deal with it.
        logger.info(
            "[context-window] %d tokens > budget %d but only %d messages — "
            "leaving as-is", current, budget, len(msgs),
        )
        return msgs

    head = [msgs[0]]
    tail = msgs[-min_keep_tail:]
    middle = msgs[1:-min_keep_tail]
    while middle:
        middle.pop(0)
        candidate = head + middle + tail
        if count_tokens(llm, candidate) <= budget:
            logger.info(
                "[context-window] trimmed %d → %d messages to fit %d/%d tokens",
                len(messages), len(candidate),
                count_tokens(llm, candidate), budget,
            )
            return candidate
    # Middle exhausted — fall back to head + tail and accept the overflow.
    fallback = head + tail
    logger.info(
        "[context-window] trimmed to head + tail (%d messages); %d tokens "
        "(budget %d). LLM may truncate the reply.",
        len(fallback), count_tokens(llm, fallback), budget,
    )
    return fallback
