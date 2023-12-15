from enum import Enum
from decimal import Decimal
from app.core.config import Config


class LimitOrderStrategy(Enum):
    # Enumeration for different limit order strategies
    BEST_BID_OR_ASK = 'best_bid_or_ask'
    BETTER_THAN_BEST_PRICE = 'better_than_best_price'
    WEIGHTED_AVERAGE = 'weighted_average'


def adjust_price_for_profit(price, order_book_side, tick_size, is_buy):
    """
    Adjusts the price for profitability by finding the nearest better price.

    :param price: The calculated weighted average price.
    :param order_book_side: List of tuples (price, quantity) for bids or asks from the order book.
    :param tick_size: The tick size for adjustment.
    :param is_buy: Boolean indicating if it's a buy operation.
    :return: Adjusted price for profitability.
    """

    if is_buy:
        # For buy orders, find a price lower than the calculated price and adjust by tick size
        for ob_price, _ in order_book_side:
            if ob_price < price:
                adjusted_price = ob_price + tick_size
                break
        # Convert to Decimal only for the final adjustment
        return float(Decimal(adjusted_price).quantize(Decimal(str(tick_size))))
    else:
        # For sell orders, find a price higher than the calculated price and adjust by tick size
        for ob_price, _ in order_book_side:
            if ob_price > price:
                adjusted_price = ob_price - tick_size
                break
        # Convert to Decimal only for the final adjustment
        return float(Decimal(adjusted_price).quantize(Decimal(str(tick_size))))


def calculate_weighted_average_price(levels, tick_size, is_buy):
    """
    Calculates the weighted average price for limit orders based on order book levels.

    :param levels: Order book levels (price and quantity pairs).
    :param tick_size: The tick size for price adjustment.
    :param is_buy: Boolean indicating if it's a buy operation.
    :return: Weighted average price adjusted for profitability.
    """
    # Retrieve order book weights from configuration
    weights = Config().get_orderbook_weights()
    weighted_price_sum = 0
    weighted_quantity_sum = 0

    # Calculate the weighted sum of prices and quantities
    for i in range(min(len(weights) - 1, len(levels))):
        price, quantity = levels[i]
        weighted_price_sum += price * quantity * weights[i + 1]
        weighted_quantity_sum += quantity * weights[i + 1]

    # Adjust the best price based on whether it's a buy or sell order
    adjusted_best_price = levels[0][0] + tick_size if is_buy else levels[0][0] - tick_size
    adjusted_best_quantity = weighted_quantity_sum / sum(weights[1:])
    weighted_price_sum += adjusted_best_price * adjusted_best_quantity * weights[0]
    weighted_quantity_sum += adjusted_best_quantity * weights[0]

    # Calculate the final weighted average price
    weighted_average_price = weighted_price_sum / weighted_quantity_sum
    # Adjust the final price for profitability
    if is_buy:
        weighted_average_price += tick_size
        return adjust_price_for_profit(weighted_average_price, levels, tick_size, is_buy=True)
    else:
        weighted_average_price -= tick_size
        return adjust_price_for_profit(weighted_average_price, levels, tick_size, is_buy=False)


def calculate_limit_buy_price(order_book, strategy=LimitOrderStrategy.BEST_BID_OR_ASK, tick_size=0.01):
    """
    Calculates the limit buy price based on the selected strategy.

    :param order_book: The order book data.
    :param strategy: The chosen limit order strategy.
    :param tick_size: The tick size for price adjustment.
    :return: Calculated limit buy price.
    """
    bids = order_book['bids']

    # Apply the selected strategy to calculate the limit buy price
    if strategy == LimitOrderStrategy.BEST_BID_OR_ASK:
        highest_bid = bids[0][0]
        return highest_bid

    elif strategy == LimitOrderStrategy.BETTER_THAN_BEST_PRICE:
        highest_bid = bids[0][0]
        return highest_bid + tick_size

    elif strategy == LimitOrderStrategy.WEIGHTED_AVERAGE:
        return calculate_weighted_average_price(bids, tick_size, is_buy=True)

    else:
        raise ValueError("Unknown strategy")


def calculate_limit_sell_price(order_book, strategy=LimitOrderStrategy.BEST_BID_OR_ASK, tick_size=0.01):
    """
    Calculates the limit sell price based on the selected strategy.

    :param order_book: The order book data.
    :param strategy: The chosen limit order strategy.
    :param tick_size: The tick size for price adjustment.
    :return: Calculated limit sell price.
    """
    asks = order_book['asks']

    # Apply the selected strategy to calculate the limit sell price
    if strategy == LimitOrderStrategy.BEST_BID_OR_ASK:
        lowest_ask = asks[0][0]
        return lowest_ask


