# market_handler.py

# This is a Python script that implements a MarketHandler class. The MarketHandler is responsible for managing
# exchanges, portfolios, and sending orders.

import ccxt
import os
import logging
import traceback
from app.core.config import Config
from app.core.singleton import Singleton
from app.core.portfolio import Portfolio
from app.core.crypto_portfolio import CryptoPortfolio

logger = logging.getLogger(__name__)


class MarketHandler(metaclass=Singleton):
    config = {}

    exchange_list = ['BINANCE', 'FTX', 'KUCOIN']
    exchange = {}
    portfolio = {}

    def __init__(self):
        # load config from file
        self.config = Config().load_config()
        to_remove = []
        for e in self.exchange_list:
            if e not in self.config:
                logger.info('No config for exchange: ' + e)
                to_remove.append(e)
        for e in to_remove:
            self.exchange_list.remove(e)
        for e in self.exchange_list:
            self.exchange[e] = None
            self.portfolio[e] = None
        logger.debug(self.exchange_list)

    def get_portfolio(self, name) -> Portfolio:
        """
        Get the portfolio for a specific exchange.

        Args:
            name (str): Name of the exchange.

        Returns:
            Portfolio: The portfolio object for the specified exchange.
        """
        if name in self.exchange_list:
            if self.exchange[name] is None:
                api_key = os.getenv(name + '_API_KEY')
                api_secret = os.getenv(name + '_API_SECRET')
                if api_key != "" and api_secret != "":
                    if name == 'BINANCE':
                        self.exchange[name] = ccxt.binance({
                            'apiKey': api_key,
                            'secret': api_secret,
                            'enableRateLimit': True,
                        })
                    elif name == 'FTX':
                        self.exchange[name] = ccxt.ftx({
                            'apiKey': api_key,
                            'secret': api_secret,
                            'enableRateLimit': True,
                        })
                    elif name == 'KUCOIN':
                        self.exchange[name] = ccxt.kucoin({
                            'apiKey': api_key,
                            'secret': api_secret,
                            'password': os.getenv(name + '_PASSPHRASE'),
                            'enableRateLimit': True,
                        })
                else:
                    logger.error('API key or secret not found')
            if self.portfolio[name] is None:
                self.portfolio[name] = CryptoPortfolio(self.config[name], self.exchange[name], name)
            return self.portfolio[name]
        else:
            return None

    def send_order(self, data, limit_order_strategy) -> None:
        """
        Send an order to the specified exchange.

        Args:
            data (dict): Order data.
            limit_order_strategy: The limit order strategy to use.

        Returns:
            None
        """
        portfolio = self.get_portfolio(data['exchange'])
        if portfolio and data['send_order']:
            portfolio.send_order(data, limit_order_strategy)

    def get_balance(self):
        """
        Get the balance for each exchange.

        Returns:
            dict: A dictionary containing the total balance and balances for each exchange.
        """
        exchange = {}
        total = 0
        for mkt in self.exchange_list:
            try:
                portfolio = self.get_portfolio(mkt)
                if portfolio:
                    exchange[mkt] = portfolio.get_portfolio_balance()
                    total += exchange[mkt]['total']
                else:
                    exchange[mkt] = 'Cannot connect'
            except:
                logging.error(traceback.format_exc())
                exchange[mkt] = 'Cannot connect'
        result = {'total': round(total, 2), 'exchanges': exchange}
        return result

    def is_thread_running(self) -> bool:
        """
        Check if any portfolio thread is running.

        Returns:
            bool: True if a portfolio thread is running, False otherwise.
        """
        for mkt in self.exchange_list:
            portfolio = self.get_portfolio(mkt)
            if portfolio and portfolio.is_thread_running():
                return True
        return False
