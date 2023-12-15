from app.core.limit_order_calculation import calculate_limit_buy_price, calculate_limit_sell_price, LimitOrderStrategy
from app.core.config import Config


def test_get_calculate_limit_price():
    Config().load_config()
    order_book = {'bids': [[42395.58, 0.94637], [42395.54, 0.12812], [42395.5, 0.17385], [42395.42, 0.00098],
                           [42395.3, 0.26086]],
                  'asks': [[42395.59, 16.90171], [42395.6, 0.00023], [42395.63, 0.00709], [42395.88, 0.54343],
                           [42395.89, 1.46666]]}

    # Using strategies for buy and sell orders
    buy_price = calculate_limit_buy_price(order_book, strategy=LimitOrderStrategy.WEIGHTED_AVERAGE)
    # print("Calculated Limit Buy Price:", buy_price)
    assert buy_price == 42395.59
    sell_price = calculate_limit_sell_price(order_book, strategy=LimitOrderStrategy.WEIGHTED_AVERAGE)
    # print("Calculated Limit Sell Price:", sell_price)
    assert sell_price == 42395.58
