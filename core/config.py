import os
import yaml

class ConfigManager:
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self.config = {}

    def load(self):
        if not os.path.exists(self.config_path):
            print(f"Warning: Configuration file {self.config_path} not found.")
            return

        try:
            with open(self.config_path, 'r') as file:
                self.config = yaml.safe_load(file) or {}
        except Exception as e:
            print(f"Error loading {self.config_path}: {e}")

    def get(self, key_path, default=None):
        """
        Get a configuration value using dot notation for nested dicts.
        E.g. get('gui.window_width', 800)
        """
        keys = key_path.split('.')
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
