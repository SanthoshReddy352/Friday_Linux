import os
import importlib
import inspect
from core.logger import logger

class PluginManager:
    def __init__(self, app):
        self.app = app
        self.plugins = []
        self.modules_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'modules')

    def load_plugins(self):
        """
        Dynamically find and load all plugins in the modules/ directory.
        A plugin is a class that inherits from FridayPlugin.
        """
        if not os.path.exists(self.modules_dir):
            logger.warning(f"Modules directory {self.modules_dir} not found.")
            return

        for item in sorted(os.listdir(self.modules_dir)):
            if item.startswith('__') or not os.path.isdir(os.path.join(self.modules_dir, item)):
                continue
                
            # Attempt to load __init__.py of each package inside modules/
            module_name = f"modules.{item}"
            try:
                module = importlib.import_module(module_name)
                # Find the setup function
                if hasattr(module, 'setup'):
                    plugin_instance = module.setup(self.app)
                    if plugin_instance:
                        self.plugins.append(plugin_instance)
                        logger.info(f"Successfully loaded plugin: {item}")
            except Exception as e:
                logger.error(f"Failed to load plugin {item}: {e}")

class FridayPlugin:
    """
    Base class for all FRIDAY plugins.
    """
    def __init__(self, app):
        self.app = app
        self.name = "BasePlugin"

    def on_load(self):
        """Called when the plugin is loaded."""
        pass
