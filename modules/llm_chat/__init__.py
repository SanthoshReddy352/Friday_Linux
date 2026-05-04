from .plugin import LLMChatPlugin


def setup(app):
    return LLMChatPlugin(app)
