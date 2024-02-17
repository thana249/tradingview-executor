"""
This code defines a class called CryptoPortfolio that represents a portfolio of cryptocurrencies. It includes methods for managing the portfolio balance, fetching balances and prices from an exchange, sending buy and sell orders, and calculating holding weights. The class uses the ccxt library for interacting with the exchange.

The main features of the CryptoPortfolio class are:
- Initializing the portfolio with configuration settings and an exchange object.
- Getting the portfolio balance, including the base asset and individual cryptocurrency assets.
- Getting the balance of a specific asset.
- Getting the price of a specific asset.
- Computing the holding weights of the assets in the portfolio.
- Sending buy and sell orders, either as market orders or limit orders.
- Handling limit orders asynchronously using threads.
- Checking if any limit order threads are running.
- Sending notifications using the Line Notify service.

The code also includes helper functions for removing dictionary entries with values close to zero and getting the order ID from an order object.

Note: The code includes some commented out sections that are not used in the current implementation.
"""
import logging
from time import sleep, time
import threading
from ccxt import OrderNotFound
import traceback
from app.core.limit_order_calculation import calculate_limit_buy_price, calculate_limit_sell_price, \
    adjust_price_for_profit
from app.services.notification_service import send_line_notify
from app.core.portfolio import Portfolio
from app.core.config import Config

logger = logging.getLogger(__name__)


def get_order_id(order):
    if order is None:
        return ''
    return order['id']


def remove_close_to_zero(dictionary, threshold=1e-4):
    keys_to_remove = []
    for key, value in dictionary.items():
        if abs(value) < threshold:
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del dictionary[key]


def precision_to_tick_size(precision) -> float:
    """
    Calculates the tick size based on the price precision.
    """
    return precision if precision < 1 else 10 ** -precision


def calculate_initial_buy_price(order_book, base_amount, tick_size, limit_order_strategy):
    """
    Calculates the initial buy price based on the order book and the available base amount.
    """
    price = calculate_limit_buy_price(order_book, limit_order_strategy, tick_size)
    amount = base_amount / price
    price = adjust_price_for_profit(price, order_book['bids'], tick_size, is_buy=True,
                                    quantity_threshold=amount * 0.01)
    amount = base_amount / price
    return price, amount


def calculate_initial_sell_price(order_book, quote_amount, limit_order_strategy, tick_size):
    """
    Calculates the initial sell price based on the order book and the available quote amount.
    """
    price = calculate_limit_sell_price(order_book, limit_order_strategy)
    price = adjust_price_for_profit(price, order_book['asks'], tick_size, is_buy=False,
                                    quantity_threshold=quote_amount * 0.01)
    return price


def calculate_target_price(order_book, remaining, order, tick_size, limit_order_strategy):
    """
    Calculates the target price and amount for updating a limit order.
    """
    if order['side'] == 'buy':
        target_price = calculate_limit_buy_price(order_book, limit_order_strategy, tick_size, order)
        target_price = adjust_price_for_profit(target_price, order_book['bids'], tick_size, is_buy=True,
                                               current_order=order, quantity_threshold=remaining * 0.01)
    else:
        target_price = calculate_limit_sell_price(order_book, limit_order_strategy, tick_size, order)
        target_price = adjust_price_for_profit(target_price, order_book['asks'], tick_size, is_buy=False,
                                               current_order=order, quantity_threshold=remaining * 0.01)
    return target_price


def should_update_order(order, target_price: str):
    """
    Checks if the order should be updated based on the target price.
    """
    should_update = str(order["price"]) != target_price
    if should_update:
        logger.info(f'Current order price: {order["price"]}, target price: {target_price},'
                    f' should update: {should_update}')
    return should_update


def print_order_book_levels(order_book, is_buy, target_price, current_order=None):
    # Log the weighted average price and order book levels
    levels = order_book['bids'] if is_buy else order_book['asks']
    found_price = False
    weights = Config().get_orderbook_weights()
    for i in range(min(len(weights), len(levels))):
        level = f'level[{i}]: {levels[i]}'
        if current_order:
            if levels[i][0] == current_order['price']:
                level += f" <= remaining: {current_order['remaining']}"
                found_price = True
            if not found_price:
                if is_buy and levels[i][0] < current_order['price']:
                    logger.info(f"           [{current_order['price']}] <= remaining: {current_order['remaining']}")
                    found_price = True
                elif not is_buy and levels[i][0] > current_order['price']:
                    logger.info(f"           [{current_order['price']}] <= remaining: {current_order['remaining']}")
                    found_price = True
        logger.info(level)
    if current_order:
        logger.info(f"Current order price: {current_order['price']} => {target_price}")


class CryptoPortfolio(Portfolio):
    holding_weight = {}
    total_holding_weight = 0

    threads = {}
    stop_worker = {}

    last_notify_time = {}

    def __init__(self, config, exchange, exchange_name):
        self.exchange_name = exchange_name
        self.config = config
        self.fee = config['fee']
        self.base_asset = self.config['base_asset']
        self.universe = self.config['universe']

        self.exchange = exchange
        self.market_info = self.exchange.load_markets()
        self.allocation = {}
        for symbol in self.universe:  # equal weight
            self.allocation[symbol] = 1 / len(self.universe)

    def get_base_asset(self):
        return self.base_asset

    def get_portfolio_balance(self):
        """
        Returns the current balance of the portfolio, including the base asset and individual cryptocurrency assets.
        """
        if len(self.universe) > 1:
            self.compute_holding_weight()
        # asset_list = self.universe.copy()
        # asset_list.append(self.base_asset)
        balances = self.get_n_balance()
        asset_list = list(balances.keys())
        if 'USDT' in asset_list:
            asset_list.remove('USDT')
        if 'BUSD' in asset_list:
            asset_list.remove('BUSD')
        if 'USD' in asset_list:
            asset_list.remove('USD')
        if 'THB' in asset_list:
            asset_list.remove('THB')
        result = {self.base_asset: round(balances[self.base_asset] if self.base_asset in balances else 0, 2)}
        total = result[self.base_asset]
        asset_prices = self.get_n_price(asset_list)
        for asset in asset_list:
            if asset not in asset_prices:
                continue
            b = balances[asset] if balances[asset] > 0.00005 else 0
            price = asset_prices[asset]
            value = round(b * price, 2)
            if value < 1:
                continue
            result[asset] = {'amount': b, 'price': price, 'value': value}
            if len(asset_list) > 1 and asset in self.holding_weight:
                result[asset]['weight'] = round(self.holding_weight[asset], 2)
            total += b * price
        result['total'] = {self.base_asset: round(total, 2)}
        return result

    def get_balance(self, asset) -> float:
        """
        Returns the balance of a specific asset.
        """
        r = self.exchange.fetch_balance()
        if asset in r:
            return r[asset]['free']
        if 'balances' in r['info']:  # BINANCE
            balance = [i['free'] for i in r['info']['balances'] if i['asset'] == asset]
        elif 'data' in r['info']:  # KUCOIN
            balance = [i['available'] for i in r['info']['data'] if i['currency'] == asset]
        else:
            logging.info(r['info'])
            return 0
        return float(balance[0]) if len(balance) > 0 else 0

    def get_n_balance(self, asset_list=None) -> float:
        """
        Returns the balances of multiple assets.
        """
        r = self.exchange.fetch_balance()
        # r: {'info': {'THB': {'available': '9990.68', 'reserved': '10'}, 'BTC': {'available': '0', 'reserved': '0'}, 'ETH': {'available': '0', 'reserved': '0'}, 'WAN': {'available': '0', 'reserved': '0'}, 'ADA': {'available': '0', 'reserved': '0'}, 'OMG': {'available': '0', 'reserved': '0'}, 'BCH': {'available': '0', 'reserved': '0'}, 'USDT': {'available': '0', 'reserved': '0'}, 'XRP': {'available': '0', 'reserved': '0'}, 'ZIL': {'available': '0', 'reserved': '0'}, 'SNT': {'available': '0', 'reserved': '0'}, 'CVC': {'available': '0', 'reserved': '0'}, 'LINK': {'available': '0', 'reserved': '0'}, 'IOST': {'available': '0', 'reserved': '0'}, 'ZRX': {'available': '0', 'reserved': '0'}, 'KNC': {'available': '0', 'reserved': '0'}, 'ABT': {'available': '0', 'reserved': '0'}, 'MANA': {'available': '0', 'reserved': '0'}, 'CTXC': {'available': '0', 'reserved': '0'}, 'XLM': {'available': '0', 'reserved': '0'}, 'SIX': {'available': '0', 'reserved': '0'}, 'JFIN': {'available': '0', 'reserved': '0'}, 'BNB': {'available': '0', 'reserved': '...
        balance = {}
        if asset_list is None:
            if 'balances' in r['info']:  # BINANCE
                balance = {i['asset']: float(i['free']) for i in r['info']['balances'] if float(i['free']) > 0.0001}
            elif 'data' in r['info']:
                if 'list' in r['info']['data']:  # HUOBI
                    balance = {i['currency'].upper(): float(i['balance']) for i in r['info']['data']['list'] if
                               i['type'] == 'trade' and float(i['balance']) > 0.00005}
                else:  # KUCOIN
                    balance = {i['currency']: float(i['available']) for i in r['info']['data'] if
                               float(i['available']) > 0.00005}
            else:
                balance = r['free']
        else:
            if 'balances' in r['info']:  # BINANCE
                balance = {i['asset']: float(i['free']) for i in r['info']['balances'] if i['asset'] in asset_list}
            elif 'data' in r['info']:
                if 'list' in r['info']['data']:  # HUOBI
                    balance = {i['currency'].upper(): float(i['balance']) for i in r['info']['data']['list'] if
                               i['currency'] in asset_list and i['type'] == 'trade'}
                else:  # KUCOIN
                    balance = {i['currency']: float(i['available']) for i in r['info']['data'] if
                               i['currency'] in asset_list}
            else:
                balance = {symbol: r['free'][symbol] for symbol in r['free'] if symbol in asset_list}
            for asset in asset_list:
                if asset not in balance:
                    balance[asset] = 0
        return balance

    def get_price(self, asset) -> float:
        """
        Returns the current price of a specific asset.
        """
        t = self.exchange.fetch_ticker(asset + '/' + self.base_asset)
        return t['last']

    def get_n_price(self, asset_list):
        """
        Returns the current prices of multiple assets.
        """
        tickers = [x + '/' + self.base_asset for x in asset_list]
        t = self.exchange.fetch_tickers(tickers)
        result = {}
        for asset in asset_list:
            ticker = asset.upper() + '/' + self.base_asset
            if ticker in t:
                result[asset] = t[ticker]['last']
        return result

    def compute_holding_weight(self) -> None:
        """
        Computes the holding weights of the assets in the portfolio.
        """
        base_balance = self.get_balance(self.base_asset)

        total_asset_value = base_balance
        market_value = {}
        asset_balance = self.get_n_balance(self.universe)
        asset_price = self.get_n_price(self.universe)
        for asset in self.universe:
            balance = asset_balance[asset]
            avg_price = asset_price[asset]
            market_value[asset] = balance * avg_price
            total_asset_value += market_value[asset]

        self.total_holding_weight = 0
        for asset in market_value:
            self.holding_weight[asset] = market_value[asset] / total_asset_value if total_asset_value > 0 else 0
            self.total_holding_weight += self.holding_weight[asset]
        logger.info('Balance: ' + str(base_balance) + ' ' + self.base_asset + ', holding_weight: ' + str(
            self.holding_weight))
        logger.info('total_holding_weight=' + str(self.total_holding_weight))

    def get_available_base_balance_for_asset(self, asset) -> float:
        """
        Returns the available base balance that can be used to buy a specific asset.
        """
        if self.holding_weight[asset] > self.allocation[asset] * 0.99:
            return 0
        elif self.allocation[asset] > self.holding_weight[asset]:
            base_balance = self.get_balance(self.base_asset)
            available_weight = 1 - self.total_holding_weight
            # logger.info('allocation['+asset+']=' + str(self.allocation[asset]))
            # logger.info('holding_weight[' + asset + ']=' + str(self.holding_weight[asset]))
            # logger.info('available_weight[' + asset + ']=' + str(available_weight))
            w = min(1, (self.allocation[asset] - self.holding_weight[asset]) / available_weight)
            return w * base_balance

    def get_min_trade_amount(self, asset, base_asset) -> tuple:
        """
        Returns the minimum trade amount for a specific asset.
        """
        symbol = f'{asset}/{base_asset}'
        min_amount = self.market_info[symbol]['limits']['amount']['min']
        min_cost = self.market_info[symbol]['limits']['cost']['min']
        return min_amount, min_cost

    def send_order(self, data, limit_order_strategy) -> None:
        """
        Sends a buy or sell order based on the provided data and limit order strategy.
        """
        asset = data['symbol'].replace(self.base_asset, '')
        symbol = f'{asset}/{self.base_asset}'
        side = data['side']

        # Stop any running threads for the asset
        if asset in self.threads and self.threads[asset] is not None:
            logger.info(asset + ' thread is running, try to stop it')
            self.stop_worker[asset] = True
            while asset in self.threads and self.threads[asset] is not None:
                sleep(1)

        # Cancel all open limit orders of the asset
        if self.exchange.has['fetchOpenOrders']:
            orders = self.exchange.fetch_open_orders(symbol)
            for order in orders:
                order_side = order['side']
                cancel_order_params = {'sd': side} if self.exchange_name == 'BITKUB' else {}
                logger.info(f'Cancel order, id={order["id"]}, symbol={symbol}, side={order_side}')
                try:
                    self.exchange.cancel_order(order['id'], symbol, cancel_order_params)
                except Exception as e:
                    logger.warning(f'Unable to cancel order, id={order["id"]}, error={e}')
                    # logger.error(traceback.format_exc())
                sleep(1/50)

        if data['side'] == 'buy':
            # Check if the asset is in the universe
            if asset not in self.universe:
                logger.warning(f'{asset} is not in the universe')
                send_line_notify(f'{asset} is not in the universe')
                return
            self.compute_holding_weight()
            # Deduct commission fee from the available base balance
            base_amount = self.get_available_base_balance_for_asset(asset) * (1 - self.fee)
            # Initial check for available base balance
            # If the available base balance is less than the minimum trade amount, do not send the order
            price = self.get_price(asset)
            amount = base_amount / price
            logger.info('[' + asset + '] available_balance=' + str(base_amount) + ' ' + self.base_asset)
            logger.info('[' + asset + '] current price=' + str(price) + ' ' + self.base_asset)
            logger.info('[' + asset + '] buy amount=' + str(amount) + ' ' + asset)
            min_amount, min_cost = self.get_min_trade_amount(asset, self.base_asset)
            # Check if the amount is greater than the minimum trade amount
            # or the cost is greater than the minimum cost + 20% for price fluctuation
            if (min_amount and amount > min_amount) or (min_cost and base_amount > min_cost*1.2):
                self.__send_order(asset, side, base_amount, limit_order_strategy)
        elif data['side'] == 'sell':
            # Can sell any asset even if it's not in the universe
            self.compute_holding_weight()
            quote_amount = self.get_balance(asset)
            price = self.get_price(asset)
            # Initial check for available quote balance
            # If the available quote balance is less than the minimum trade amount, do not send the order
            logger.info('[' + asset + '] holding_weight=' + str(self.holding_weight[asset]))
            logger.info('[' + asset + '] current price=' + str(price) + ' ' + self.base_asset)
            logger.info('[' + asset + '] sell amount=' + str(quote_amount) + ' ' + asset)
            min_amount, min_cost = self.get_min_trade_amount(asset, self.base_asset)
            # Check if the amount is greater than the minimum trade amount
            # or the cost is greater than the minimum cost + 20% for price fluctuation
            if (min_amount and quote_amount > min_amount) or (min_cost and quote_amount*price > min_cost*1.2):
                self.__send_order(asset, side, quote_amount, limit_order_strategy)

    def __send_order(self, asset, side, amount, limit_order_strategy) -> None:
        """
        Sends a buy or sell order, either as a market order or a limit order.
        """
        if self.exchange.has['fetchOrder']:
            self.send_limit_order(asset, side, amount, limit_order_strategy)
        else:
            self.send_market_order(asset, side, amount)

    def send_market_order(self, asset, side, amount) -> None:
        """
        Sends a market order to buy or sell a specific asset.
        """
        logger.info('Sending: ' + asset + ' ' + side + ' ' + str(amount))
        try:
            order = self.exchange.create_order(asset + '/' + self.base_asset, 'market', side, float(amount))
            send_line_notify(str(order))
            logger.info(f'Exchange Response: {order}')
            order_id = get_order_id(order)
            send_line_notify('Order is matched, id=' + str(order_id))
        except Exception as e:
            logger.error(traceback.format_exc())
            send_line_notify('Unable to create limit order, send market order instead')

    def send_limit_order(self, asset, side, amount, limit_order_strategy) -> None:
        """
        Sends a limit order to buy or sell a specific asset.
        """
        # Create a thread to handle limit order
        t = threading.Thread(target=self.__limit_order_worker, args=[asset, side, amount, limit_order_strategy])
        self.threads[asset] = t
        self.stop_worker[asset] = False
        t.daemon = True
        t.start()

    def __limit_order_worker(self, asset, side, amount, limit_order_strategy):
        """
        Worker function for handling limit orders.
        :param asset:
        :param side:
        :param amount: base amount for buy, quote amount for sell
        :param limit_order_strategy:
        :return:
        """
        symbol = f'{asset}/{self.base_asset}'
        precision = self.__get_price_precision(symbol)
        tick_size = precision_to_tick_size(precision)

        order_side_params = {'sd': side} if self.exchange_name == 'BITKUB' else {}

        order_book = self.exchange.fetch_order_book(symbol)
        if side == 'buy':
            # Calculate initial buy price and amount
            # Since the amount is base amount, we need to calculate the amount based on the price
            price, remaining = calculate_initial_buy_price(order_book, amount, tick_size, limit_order_strategy)
        else:
            # Calculate initial sell price
            # Since the amount is quote amount, we don't need to calculate the amount
            price = calculate_initial_sell_price(order_book, amount, limit_order_strategy, tick_size)
            remaining = amount

        order = self.__create_limit_order(symbol, side, remaining, price)
        if not order:
            self.threads[asset] = None
            return
        send_line_notify(f'{symbol} Order info: {order["info"]}')

        sleep(0.75)  # Wait for order book to be updated

        fully_filled = False
        while not self.stop_worker[asset]:
            order_book = self.exchange.fetch_order_book(symbol)
            target_price = calculate_target_price(order_book, remaining, order,
                                                  tick_size, limit_order_strategy)
            target_price = self.exchange.price_to_precision(symbol, target_price)
            if should_update_order(order, target_price):
                # Print the order book levels for debugging
                # self.__print_order_book_levels(order_book, side == 'buy', target_price, order)

                # Update the order with the target price and amount
                # For buy order, we need to calculate the amount based on the price
                target_amount = remaining * order['price'] / float(target_price) if side == 'buy' else remaining
                if side == 'buy':
                    logger.info(f'Amount {remaining} => {target_amount} {asset}')
                order = self.__update_order(symbol, side, order, target_price, target_amount, order_side_params)
                # If the order is not updated due to missing previous order, check balance and recalculate amount
                if order is None:
                    order, remaining = self.__handle_order_completion(asset, side, target_price)
                    if remaining == 0:
                        fully_filled = True
                        break
                sleep(0.75)  # Wait for order book to be updated
            else:
                order = self.__refresh_order_status(order, symbol, side, order_side_params)
                if order is None:
                    order, remaining = self.__handle_order_completion(asset, side, target_price)
                    if remaining == 0:
                        fully_filled = True
                        break
                    else:
                        sleep(0.75)  # Wait for order book to be updated
                else:
                    sleep(1/50)

        if fully_filled:
            unit = self.base_asset if side == 'buy' else asset
            logger.info(f'Order is fully matched, {side} {symbol} => {amount} {unit}')
            send_line_notify(f'Order is fully matched, {side} {symbol} => {amount} {unit}')

        self.threads[asset] = None

    def __get_price_precision(self, symbol) -> int:
        """
        Returns the price precision for a specific symbol.
        """
        return self.exchange.markets[symbol]['precision']['price']

    def __create_limit_order(self, symbol, side, amount, price):
        """
        Creates a limit order with the specified symbol, side, amount, and price.
        """
        price = self.exchange.price_to_precision(symbol, price)
        try:
            logger.info(f'Open limit order, {side} {symbol} => {amount} * {price} = {float(amount) * float(price)}')
            order = self.exchange.create_order(symbol, 'limit', side, float(amount), float(price))
            logger.info(f'Exchange Response: {order}')
            return order
        except Exception as e:
            logger.error(f'Failed to create limit order: {e}')
            logger.info(f'Params: {symbol}, {side}, {amount}, {price}')
            logger.debug(traceback.format_exc())
            send_line_notify(f'Failed to create limit order: {e}')
            return None

    def __refresh_order_status(self, order, symbol, side, order_side_params={}):
        """
        Refreshes the status of the specified order and returns the updated order object.
        """
        try:
            order = self.exchange.fetch_order(order['id'], symbol, order_side_params)
            if order['status'] == 'closed':
                logger.info(f'Order is closed, id={order["id"]}')
                return None
            return order
        except OrderNotFound:
            logger.info(f'Order not found, id={order["id"]}')
            return None
        except Exception as e:
            logger.error(f'Failed to fetch order: {e}')
            logger.debug(traceback.format_exc())
            return order

    def __update_order(self, symbol, side, order, target_price, target_amount, order_side_params={}):
        """
        Updates the specified order with the target price and amount.
        """
        fetch_all_orders = False
        try:
            self.exchange.cancel_order(order['id'], symbol, order_side_params)
        except Exception as e:
            logger.error(f'Failed to cancel order: {e}')
            logger.debug(order)
            fetch_all_orders = True

        if fetch_all_orders:
            logger.info('Fetch all orders to find the order to cancel')
            orders = self.exchange.fetch_open_orders(symbol)
            logger.info(f'All open orders: {orders}')
            for o in orders:
                # Find the order to cancel
                if o['side'] == side:
                    logger.info(f'Cancel order, id={o["id"]}, symbol={symbol}, side={side}')
                    try:
                        self.exchange.cancel_order(o['id'], symbol, order_side_params)
                    except Exception as e:
                        logger.error(f'Failed to cancel order: {e}')
                        logger.debug(o)
                    sleep(1/50)
            return None  # Return None to check remaining balance and create a new order

        try:
            order = self.exchange.create_order(symbol, 'limit', side, target_amount, target_price)
            logger.info(f'Exchange Response: {order}')
            return order
        except Exception as e:
            logger.error(f'Failed to update order: {e}')
            logger.info(f'Params: {symbol}, {side}, {target_amount}, {target_price}')
            # logger.error(traceback.format_exc())
            send_line_notify(f'Failed to update order: {e}, {symbol}, {side}, {target_amount}, {target_price}')
            return None  # Return None to check remaining balance and create a new order

    def __handle_order_completion(self, asset, side, target_price):
        """
        Checks the remaining balance for an asset and decides whether to mark an order as matched
        or create a new one.
        :param asset: The asset for which the order is being placed.
        :param side: The side of the order ('buy' or 'sell').
        :param target_price: The target price at which a new order should be placed if necessary.
        :return: A tuple containing the updated order and a flag indicating whether the order was matched.
        """
        remaining = self.__get_remaining_amount(asset, target_price, side)
        if remaining == 0:
            # Order is fully matched
            return None, 0
        else:
            # Create a new order with the remaining balance
            symbol = f'{asset}/{self.base_asset}'
            order = self.__create_limit_order(symbol, side, remaining, target_price)
            return order, remaining

    def __get_remaining_amount(self, asset, target_price, side):
        """
        Returns the remaining amount of the specified asset.
        """
        if side == 'buy':
            base_balance = self.get_available_base_balance_for_asset(asset) * (1 - self.fee)
            remaining = base_balance / float(target_price)
            min_amount, min_cost = self.get_min_trade_amount(asset, self.base_asset)
            if (min_amount and remaining < min_amount) or (min_cost and base_balance < min_cost):
                return 0
        else:
            quote_balance = self.get_balance(asset)
            remaining = quote_balance
            min_amount, min_cost = self.get_min_trade_amount(asset, self.base_asset)
            if (min_amount and remaining < min_amount) or (min_cost and quote_balance * float(target_price) < min_cost):
                return 0
        return remaining

    def is_thread_running(self) -> bool:
        """
        Checks if any limit order threads are running.
        """
        for asset in self.universe:
            if asset in self.threads and self.threads[asset] is not None:
                return True
        return False

    def send_line_notify_with_delay(self, asset, msg, delay=5) -> None:
        """
        Sends a Line Notify message with a delay between notifications for a specific asset.
        """
        if asset not in self.last_notify_time:
            send_line_notify(msg)
            self.last_notify_time[asset] = time()
            return
        seconds = time() - self.last_notify_time[asset]
        if seconds > delay:
            send_line_notify(msg)
            self.last_notify_time[asset] = time()
