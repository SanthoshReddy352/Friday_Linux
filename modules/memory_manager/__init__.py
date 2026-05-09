from .plugin import MemoryManagerPlugin


def setup(app):
    return MemoryManagerPlugin(app)
