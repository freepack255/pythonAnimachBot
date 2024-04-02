import datetime
from collections.abc import Mapping
from pathlib import Path

import yaml

from animachBot.logger.logger import logger


# Using read-only dict from collections
class ConfigDict(Mapping):
    def __init__(self, data):
        self.data = data

    # Abstract methods
    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]
        raise KeyError(key)

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)

    # Make all nested dictionaries and lists are immutable via calling itself class to create nested Mapping-like dicts
    @classmethod
    def make_read_only(cls, obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                obj[key] = cls.make_read_only(value)
            return cls(obj)
        elif isinstance(obj, list):
            return [cls.make_read_only(item) for item in obj]
        else:
            return obj


def read_yaml_config(yaml_filename):
    with open(yaml_filename, encoding='utf-8') as f:
        return yaml.load(f, yaml.SafeLoader)


class Config(dict):
    def __init__(self, path=None):
        if path is None:
            # Default path to the config file
            path = Path(__file__).parents[1] / "config" / "config.yml"
        self.path = path
        self.__root = "animachBot"
        config = ConfigDict.make_read_only(read_yaml_config(self.path)[self.__root])

        if 'bot_token' not in config['telegram'].keys():
            logger.fatal("Telegram bot token not found. Please set the 'bot_token' under 'telegram' section.")

        try:
            if not isinstance(config['rsshub_feed_scraper']['check_after_date'], datetime.datetime):
                logger.fatal(msg=f"rsshub_feed_scraper.check_after_date config parameter is not in ISO 8601 format.")
        except KeyError:
            logger.fatal(msg=f"rsshub_feed_scraper.check_after_date config parameter is not presented in the config.")

        self.__config_dict = config
        super().__init__()

    # Constructor / destructor referencing against private __config_dict__
    def __getitem__(self, key):
        if key in self.__config_dict:
            return self.__config_dict[key]
        raise KeyError(key)