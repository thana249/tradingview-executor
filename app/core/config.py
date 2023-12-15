"""
config.py

This file contains the Config class, which is responsible for loading and accessing configuration settings from a
JSON file. It utilizes the Singleton design pattern to ensure that only one instance of the class is created.
"""

import json
import logging

from app.core.singleton import Singleton


class Config(metaclass=Singleton):
    """
    Config class for loading and accessing configuration settings.
    """

    @classmethod
    def load_config(cls, config_file='config.json'):
        """
        Loads the configuration settings from the specified JSON file.

        Args:
            config_file (str): The path to the JSON configuration file.

        Returns:
            dict: The loaded configuration settings.

        """
        global ORDERBOOK_WEIGHTS
        with open(config_file, 'r') as file:
            cls.config = json.load(file)
            cls.orderbook_weights = cls.config.get('orderbook_weights', [4, 2, 1, 1, 0, 0])
            logging.info('orderbook weights: %s', cls.orderbook_weights)
            return cls.config
        return None

    @classmethod
    def get_orderbook_weights(cls):
        """
        Returns the orderbook weights.

        Returns:
            list: The orderbook weights.

        """
        return cls.orderbook_weights
