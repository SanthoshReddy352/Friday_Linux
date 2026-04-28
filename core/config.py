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

    def set(self, key_path, value):
        """Set a configuration value using dot notation for nested dicts."""
        keys = key_path.split(".")
        target = self.config
        for key in keys[:-1]:
            if not isinstance(target.get(key), dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value
        return value

    def save(self):
        """Persist the current configuration to disk."""
        directory = os.path.dirname(os.path.abspath(self.config_path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as file:
            yaml.safe_dump(self.config, file, sort_keys=False)
