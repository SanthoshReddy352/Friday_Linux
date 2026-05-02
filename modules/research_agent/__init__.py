from .plugin import ResearchAgentPlugin


def setup(app):
    return ResearchAgentPlugin(app)
