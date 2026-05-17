from .plugin import SecurityToolsPlugin


def setup(app):
    return SecurityToolsPlugin(app)
