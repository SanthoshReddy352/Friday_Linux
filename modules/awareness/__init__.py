from .plugin import AwarenessPlugin


def setup(app):
    return AwarenessPlugin(app)
