"""VLM prompt strings — one per capability.

All prompts end with an explicit length cap to keep inference fast on CPU.
Typical output on SmolVLM2: 40–100 tokens → 4–15 s on i5-12th Gen.
"""

ANALYZE_SCREEN = (
    "You are a helpful assistant analyzing a screenshot. "
    "Describe what is on the screen: the application, any visible errors, "
    "dialogs, or important UI elements. Be concise. Maximum 2 sentences."
)

READ_TEXT = (
    "Extract all readable text from this image exactly as it appears. "
    "After the raw text, add one sentence explaining what the text is about. "
    "Maximum 3 sentences total."
)

SUMMARIZE_SCREEN = (
    "You are looking at a screenshot. Give a high-level summary of what the user "
    "is doing or looking at. Mention the most important content or action available. "
    "Be concise. Maximum 2 sentences."
)

ANALYZE_CLIPBOARD = (
    "Analyze this image. Describe what it shows, its purpose, and any key information "
    "visible in it. Maximum 2 sentences."
)

DEBUG_CODE = (
    "You are a debugging assistant. Look at this code or terminal screenshot. "
    "Identify exactly what the error is and suggest the most likely fix. "
    "Be specific. Maximum 3 sentences."
)

COMPARE_SCREENSHOTS = (
    "Compare Image A (left side) and Image B (right side). "
    "List the specific differences you can see between them. "
    "Focus on functional or visual changes. Maximum 3 sentences."
)

EXPLAIN_MEME = (
    "Explain this meme. What is the joke, what is the cultural reference, "
    "and why is it funny? Maximum 2 sentences."
)

ROAST_DESKTOP = (
    "You are a witty assistant. Look at this desktop screenshot and make "
    "one funny, observational comment about what you see — too many tabs, "
    "messy files, obscure apps. Be playful, not mean. One sentence only."
)

REVIEW_DESIGN = (
    "You are a UI/UX reviewer. Look at this screenshot and give one specific "
    "piece of honest feedback about the design — layout, readability, or usability. "
    "Maximum 2 sentences."
)

UI_ELEMENT_FINDER = (
    "Look at this screenshot. The user is looking for: {target}. "
    "Describe where on the screen this element is using relative position "
    "(top-left, center, bottom-right, etc.) and what it looks like. "
    "If you cannot find it, say so clearly. Maximum 2 sentences."
)
