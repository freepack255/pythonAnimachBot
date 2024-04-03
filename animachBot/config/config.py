import yaml
from pathlib import Path
from typing import Any


class Config:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self._config_data = self._load_config()

    def _load_config(self) -> dict:
        """Loads the configuration from the file."""
        try:
            with self.config_path.open('r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file was not found: {self.config_path}")
        except yaml.YAMLError as e:
            raise RuntimeError(f"Error while reading the YAML file: {e}")

    def get(self, path: str, default: Any = None) -> Any:
        """Getting values in format 'section.subsection.key'."""
        keys = path.split('.')
        value = self._config_data

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value
