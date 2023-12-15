"""This code file contains functions for interacting with a trading service. It includes a function to retrieve the
balance from the market handler and a function to send orders to the exchange using ccxt. The send_order function
utilizes the MarketHandler class and uses the Weighted Average limit order strategy. """

from app.core.market_handler import MarketHandler
from app.core.limit_order_calculation import LimitOrderStrategy


def get_balance():
    mh = MarketHandler()
    return mh.get_balance()


def send_order(data):
    """
    This function sends the order to the exchange using ccxt.
    :param data: python dict, with keys as the API parameters.
    :return: the response from the exchange.
    """

    mh = MarketHandler()
    return mh.send_order(data, LimitOrderStrategy.WEIGHTED_AVERAGE)
