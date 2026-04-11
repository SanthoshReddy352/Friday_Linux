from .plugin import TaskManagerPlugin


def setup(app):
    return TaskManagerPlugin(app)
