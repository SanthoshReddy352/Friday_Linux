from .plugin import VoiceIOPlugin

def setup(app):
    return VoiceIOPlugin(app)
