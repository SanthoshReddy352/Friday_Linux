from .plugin import WeatherPlugin


def setup(app):
    return WeatherPlugin(app)
