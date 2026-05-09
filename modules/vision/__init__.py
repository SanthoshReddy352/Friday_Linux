from .plugin import VisionPlugin


def setup(app):
    return VisionPlugin(app)
