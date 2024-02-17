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
from app.core.ccxt_ext.bitkub import bitkub

logger = logging.getLogger(__name__)


class MarketHandler(metaclass=Singleton):
    config = {}

    exchange_list = ['BINANCE', 'KUCOIN', 'BITKUB']
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

        # Init connection to exchanges
        for mkt in self.exchange_list:
            api_key = os.getenv(mkt + '_API_KEY')
            api_secret = os.getenv(mkt + '_API_SECRET')
            if api_key != "" and api_secret != "":
                if mkt == 'BINANCE':
                    self.exchange[mkt] = ccxt.binance({
                        'apiKey': api_key,
                        'secret': api_secret,
                        'enableRateLimit': True,
                    })
                elif mkt == 'KUCOIN':
                    self.exchange[mkt] = ccxt.kucoin({
                        'apiKey': api_key,
                        'secret': api_secret,
                        'password': os.getenv(mkt + '_PASSPHRASE'),
                        'enableRateLimit': True,
                    })
                elif mkt == 'BITKUB':
                    self.exchange[mkt] = bitkub({
                        'apiKey': api_key,
                        'secret': api_secret,
                        'enableRateLimit': True,
                    })
                else:
                    logger.error('Unknown CEX')
                # Init portfolio if not error
                if mkt in self.exchange:
                    self.portfolio[mkt] = CryptoPortfolio(self.config[mkt], self.exchange[mkt], mkt)

    def get_portfolio(self, name) -> Portfolio:
        """
        Get the portfolio for a specific exchange.

        Args:
            name (str): Name of the exchange.

        Returns:
            Portfolio: The portfolio object for the specified exchange.
        """
        if name in self.portfolio:
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
        total = {}
        for mkt in self.exchange_list:
            try:
                portfolio = self.get_portfolio(mkt)
                if portfolio:
                    exchange[mkt] = portfolio.get_portfolio_balance()
                    base_asset = portfolio.get_base_asset()
                    if base_asset not in total:
                        total[base_asset] = 0
                    total[base_asset] += exchange[mkt]['total'][base_asset]
                else:
                    exchange[mkt] = 'Cannot connect'
            except:
                logging.error(traceback.format_exc())
                exchange[mkt] = 'Error'
        total = {k: round(v, 2) for k, v in total.items()}
        result = {'total': total, 'exchanges': exchange}
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
