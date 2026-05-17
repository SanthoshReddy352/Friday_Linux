from .plugin import CommsPlugin


def setup(app):
    return CommsPlugin(app)
