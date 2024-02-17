from enum import Enum
from decimal import Decimal
from app.core.config import Config
import logging

logger = logging.getLogger(__name__)


class LimitOrderStrategy(Enum):
    # Enumeration for different limit order strategies
    BEST_BID_OR_ASK = 'best_bid_or_ask'
    BETTER_THAN_BEST_PRICE = 'better_than_best_price'
    WEIGHTED_AVERAGE = 'weighted_average'


def adjust_price_for_profit(price, order_book_side, tick_size, is_buy, current_order=None, quantity_threshold=0):
    """
    Adjusts the price for profitability by finding the nearest better price.
    :param price: The calculated weighted average price.
    :param order_book_side: List of tuples (price, quantity) for bids or asks from the order book.
    :param tick_size: The tick size for adjustment.
    :param is_buy: Boolean indicating if it's a buy operation.
    :param current_order: The current order data.
    :param quantity_threshold: The quantity threshold for the order.
    :return: Adjusted price for profitability.
    """
    adjusted_price = 0
    if current_order is None:
        if is_buy:
            # For buy orders, find a price lower than the calculated price and adjust by tick size
            for ob_price, ob_quantity in order_book_side:
                if ob_price < price and ob_quantity >= quantity_threshold:
                    adjusted_price = ob_price + tick_size
                    break
        else:
            # For sell orders, find a price higher than the calculated price and adjust by tick size
            for ob_price, ob_quantity in order_book_side:
                if ob_price > price and ob_quantity >= quantity_threshold:
                    adjusted_price = ob_price - tick_size
                    break
    else:
        current_order_price = current_order['price']
        current_order_remaining = current_order['remaining']
        if is_buy:
            # For buy orders, find a price lower than the calculated price and adjust by tick size
            for ob_price, ob_quantity in order_book_side:
                if ob_price == current_order_price:
                    ob_quantity -= current_order_remaining
                if ob_quantity <= quantity_threshold:
                    continue
                if ob_price < price and ob_quantity >= quantity_threshold:
                    adjusted_price = ob_price + tick_size
                    break
        else:
            # For sell orders, find a price higher than the calculated price and adjust by tick size
            for ob_price, ob_quantity in order_book_side:
                if ob_price == current_order_price:
                    ob_quantity -= current_order_remaining
                if ob_quantity <= quantity_threshold:
                    continue
                if ob_price > price and ob_quantity >= quantity_threshold:
                    adjusted_price = ob_price - tick_size
                    break
    # Convert to Decimal only for the final adjustment
    return float(Decimal(adjusted_price).quantize(Decimal(str(tick_size))))


def calculate_weighted_average_price(levels, tick_size, is_buy, current_order=None):
    """
    Calculates the weighted average price for limit orders based on order book levels.

    :param levels: Order book levels (price and quantity pairs).
    :param tick_size: The tick size for price adjustment.
    :param is_buy: Boolean indicating if it's a buy operation.
    :param current_order: The current order data.
    :return: Weighted average price adjusted for profitability.
    """
    # Retrieve order book weights from configuration
    weights = Config().get_orderbook_weights()
    weighted_price_sum = 0
    weighted_quantity_sum = 0

    # Calculate the weighted sum of prices and quantities
    wi = 0  # weight index
    # First order book level that is not our current order
    # Initialize to -1 to indicate that we haven't found it yet
    first_order_book_level = -1
    for i in range(min(len(weights) - 1, len(levels))):
        price, quantity = levels[i]
        if current_order and price == current_order['price']:
            quantity -= current_order['remaining']
            if quantity < current_order['remaining']*0.01:
                continue
        if first_order_book_level == -1:
            first_order_book_level = i
        weighted_price_sum += price * quantity * weights[wi + 1]
        weighted_quantity_sum += quantity * weights[wi + 1]
        wi += 1

    # Adjust the best price based on whether it's a buy or sell order
    if is_buy:
        adjusted_best_price = levels[first_order_book_level][0] + tick_size
    else:
        adjusted_best_price = levels[first_order_book_level][0] - tick_size
    adjusted_best_quantity = weighted_quantity_sum / sum(weights[1:])
    weighted_price_sum += adjusted_best_price * adjusted_best_quantity * weights[0]
    weighted_quantity_sum += adjusted_best_quantity * weights[0]

    # Calculate the final weighted average price
    weighted_average_price = weighted_price_sum / weighted_quantity_sum

    # round weighted_average_price to the nearest tick size
    if is_buy:  # round up
        weighted_average_price = (weighted_average_price // tick_size + 1) * tick_size
    else:  # round down
        weighted_average_price = (weighted_average_price // tick_size) * tick_size

    return weighted_average_price


def calculate_limit_buy_price(order_book, strategy=LimitOrderStrategy.BEST_BID_OR_ASK, tick_size=0.01,
                              current_order=None):
    """
    Calculates the limit buy price based on the selected strategy.

    :param order_book: The order book data.
    :param strategy: The chosen limit order strategy.
    :param tick_size: The tick size for price adjustment.
    :param current_order: The current order data.
    :return: Calculated limit buy price.
    """
    bids = order_book['bids']

    # Apply the selected strategy to calculate the limit buy price
    if strategy == LimitOrderStrategy.BEST_BID_OR_ASK:
        return bids[0][0]

    elif strategy == LimitOrderStrategy.BETTER_THAN_BEST_PRICE:
        # if current_order is already at the best price, don't adjust the price
        if current_order and current_order['price'] == bids[0][0]:
            return bids[0][0]
        return bids[0][0] + tick_size

    elif strategy == LimitOrderStrategy.WEIGHTED_AVERAGE:
        return calculate_weighted_average_price(bids, tick_size, is_buy=True, current_order=current_order)

    else:
        raise ValueError("Unknown strategy")


def calculate_limit_sell_price(order_book, strategy=LimitOrderStrategy.BEST_BID_OR_ASK, tick_size=0.01,
                               current_order=None):
    """
    Calculates the limit sell price based on the selected strategy.

    :param order_book: The order book data.
    :param strategy: The chosen limit order strategy.
    :param tick_size: The tick size for price adjustment.
    :param current_order: The current order data.
    :return: Calculated limit sell price.
    """
    asks = order_book['asks']

    # Apply the selected strategy to calculate the limit sell price
    if strategy == LimitOrderStrategy.BEST_BID_OR_ASK:
        return asks[0][0]

    elif strategy == LimitOrderStrategy.BETTER_THAN_BEST_PRICE:
        # if current_order is already at the best price, don't adjust the price
        if current_order and current_order['price'] == asks[0][0]:
            return asks[0][0]
        return asks[0][0] - tick_size

    elif strategy == LimitOrderStrategy.WEIGHTED_AVERAGE:
        return calculate_weighted_average_price(asks, tick_size, is_buy=False, current_order=current_order)

    else:
        raise ValueError("Unknown strategy")
