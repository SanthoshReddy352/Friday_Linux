from .plugin import GoalsPlugin


def setup(app):
    return GoalsPlugin(app)
