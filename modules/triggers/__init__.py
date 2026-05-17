from .plugin import TriggerManagerPlugin


def setup(app):
    return TriggerManagerPlugin(app)
