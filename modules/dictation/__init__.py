from .plugin import DictationPlugin


def setup(app):
    return DictationPlugin(app)
