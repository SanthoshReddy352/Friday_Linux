from .plugin import FocusSessionPlugin


def setup(app):
    return FocusSessionPlugin(app)
