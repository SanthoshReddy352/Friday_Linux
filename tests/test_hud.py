import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gui.hud import format_hud_message


def test_format_hud_message_prefixes_user_text():
    formatted = format_hud_message("user", "open the coffee file")

    assert formatted == "USER: open the coffee file"


def test_format_hud_message_truncates_long_replies():
    text = " ".join(f"line{i}" for i in range(100))

    formatted = format_hud_message("assistant", text, max_chars=80, max_lines=3)

    assert formatted.startswith("FRIDAY: ")
    assert formatted.endswith("...")
    assert formatted.count("\n") <= 3
