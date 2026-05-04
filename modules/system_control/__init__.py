from .plugin import SystemControlPlugin

def setup(app):
    return SystemControlPlugin(app)
