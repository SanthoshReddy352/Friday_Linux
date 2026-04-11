from .plugin import GreeterPlugin

def setup(app):
    return GreeterPlugin(app)
