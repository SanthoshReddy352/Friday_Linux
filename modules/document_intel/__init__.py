from .plugin import DocumentIntelPlugin


def setup(app):
    return DocumentIntelPlugin(app)
