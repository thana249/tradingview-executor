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
from app.core.limit_order_calculation import calculate_limit_buy_price, calculate_limit_sell_price
from app.services.notification_service import send_line_notify
from app.core.portfolio import Portfolio
from app.core.limit_order_calculation import LimitOrderStrategy

logger = logging.getLogger(__name__)


def get_order_id(order):
    if order is None:
        return ''
    if 'orderId' in order['info']:  # Binance
        return order['info']['orderId']
    else:  # FTX
        return order['info']['id']


def remove_close_to_zero(dictionary, threshold=1e-4):
    keys_to_remove = []
    for key, value in dictionary.items():
        if abs(value) < threshold:
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del dictionary[key]


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

    def get_portfolio_balance(self):
        """
        Returns the current balance of the portfolio, including the base asset and individual cryptocurrency assets.
        """
        if len(self.universe) > 1:
            self.compute_holding_weight()
        # asset_list = self.universe.copy()
        # asset_list.append(self.base_asset)
        balance = self.get_n_balance()
        asset_list = list(balance.keys())
        if 'USDT' in asset_list:
            asset_list.remove('USDT')
        if 'BUSD' in asset_list:
            asset_list.remove('BUSD')
        if 'USD' in asset_list:
            asset_list.remove('USD')
        result = {self.base_asset: round(balance[self.base_asset] if self.base_asset in balance else 0, 2)}
        total = result[self.base_asset]
        asset_price = self.get_n_price(asset_list)
        for asset in asset_list:
            if asset not in asset_price:
                continue
            b = balance[asset] if balance[asset] > 0.00005 else 0
            price = asset_price[asset]
            value = round(b * price, 2)
            if value < 1:
                continue
            result[asset] = {'amount': b, 'price': price, 'value': value}
            if len(asset_list) > 1 and asset in self.holding_weight:
                result[asset]['weight'] = round(self.holding_weight[asset], 2)
            total += b * price
        result['total'] = round(total, 2)
        return result

    def get_balance(self, asset) -> float:
        """
        Returns the balance of a specific asset.
        """
        r = self.exchange.fetch_balance()
        if 'balances' in r['info']:  # BINANCE
            balance = [i['free'] for i in r['info']['balances'] if i['asset'] == asset]
        elif 'result' in r['info']:  # FTX
            balance = [i['free'] for i in r['info']['result'] if i['coin'] == asset]
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
        balance = {}
        if asset_list is None:
            if 'balances' in r['info']:  # BINANCE
                balance = {i['asset']: float(i['free']) for i in r['info']['balances'] if float(i['free']) > 0.0001}
            elif 'result' in r['info']:  # FTX
                balance = {i['coin']: float(i['free']) for i in r['info']['result'] if float(i['usdValue']) > 0.00005}
            elif 'data' in r['info']:
                if 'list' in r['info']['data']:  # HUOBI
                    balance = {i['currency'].upper(): float(i['balance']) for i in r['info']['data']['list'] if
                               i['type'] == 'trade' and float(i['balance']) > 0.00005}
                else:  # KUCOIN
                    balance = {i['currency']: float(i['available']) for i in r['info']['data'] if
                               float(i['available']) > 0.00005}
        else:
            if 'balances' in r['info']:  # BINANCE
                balance = {i['asset']: float(i['free']) for i in r['info']['balances'] if i['asset'] in asset_list}
            elif 'result' in r['info']:  # FTX
                balance = {i['coin']: float(i['free']) for i in r['info']['result'] if i['coin'] in asset_list}
            elif 'data' in r['info']:
                if 'list' in r['info']['data']:  # HUOBI
                    balance = {i['currency'].upper(): float(i['balance']) for i in r['info']['data']['list'] if
                               i['currency'] in asset_list and i['type'] == 'trade'}
                else:  # KUCOIN
                    balance = {i['currency']: float(i['available']) for i in r['info']['data'] if
                               i['currency'] in asset_list}
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

    def get_min_trade_amount(self, asset, base_asset) -> float:
        """
        Returns the minimum trade amount for a specific asset.
        """
        return self.market_info[asset + '/' + base_asset]['limits']['amount']['min']

    def send_order(self, data, limit_order_strategy) -> None:
        """
        Sends a buy or sell order based on the provided data and limit order strategy.
        """
        symbol = data['symbol']
        asset = symbol.replace(self.base_asset, '')
        side = data['side']
        if data['side'] == 'buy':
            if asset not in self.universe:
                logger.warning(asset + ' is not in the universe')
                return
            self.compute_holding_weight()
            # deduct commission 0.11% (actual binance 0.1%, ftx 0.07%)
            available_balance = self.get_available_base_balance_for_asset(asset) * (1 - self.fee)
            average_price = self.get_price(asset)
            amount = available_balance / average_price
            logger.info('[' + asset + '] available_balance=' + str(available_balance) + ' ' + self.base_asset)
            logger.info('[' + asset + '] average_price=' + str(average_price) + ' ' + self.base_asset)
            logger.info('[' + asset + '] buy amount=' + str(amount) + ' ' + asset)
            if float(amount) > self.get_min_trade_amount(asset, self.base_asset):
                self.__send_order(asset, side, amount, limit_order_strategy)
        elif data['side'] == 'sell':
            self.compute_holding_weight()
            amount = self.get_balance(asset)
            logger.info('[' + asset + '] holding_weight=' + str(self.holding_weight[asset]))
            logger.info('[' + asset + '] sell amount=' + str(amount) + ' ' + asset)
            if float(amount) > self.get_min_trade_amount(asset, self.base_asset):
                self.__send_order(asset, side, amount, limit_order_strategy)

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
        amount = self.exchange.amount_to_precision(asset + '/' + self.base_asset, amount)
        logger.info('Sending: ' + asset + ' ' + side + ' ' + str(amount))
        try:
            order = self.exchange.create_order(asset + '/' + self.base_asset, 'market', side, amount)
            logger.info('Exchange Response: ' + str(order))
            send_line_notify(str(order))
            order_id = get_order_id(order)
            send_line_notify('Order is matched, id=' + str(order_id))
        except Exception as e:
            logger.error(traceback.format_exc())
            send_line_notify('Unable to create limit order, send market order instead')

    def send_limit_order(self, asset, side, amount, limit_order_strategy) -> None:
        """
        Sends a limit order to buy or sell a specific asset.
        """
        if asset in self.threads and self.threads[asset] is not None:
            logger.info(asset + ' thread is running, try to stop it')
        while asset in self.threads and self.threads[asset] is not None:
            self.stop_worker[asset] = True
            sleep(1)

        # Create a thread to handle limit order
        t = threading.Thread(target=self.__limit_order_worker, args=[asset, side, amount, limit_order_strategy])
        self.threads[asset] = t
        self.stop_worker[asset] = False
        t.daemon = True
        t.start()

    def __limit_order_worker(self, asset, side, amount, limit_order_strategy) -> None:
        """
        Worker function for handling limit orders asynchronously.
        """
        remaining = amount
        amount = self.exchange.amount_to_precision(asset + '/' + self.base_asset, amount)
        symbol = asset + '/' + self.base_asset
        order_book = self.exchange.fetch_order_book(symbol)
        precision = self.market_info[symbol]['precision']['price']
        if precision < 1:
            tick_size = precision
        else:
            tick_size = 1 / pow(10, precision)
        if side == 'buy':
            price = calculate_limit_buy_price(order_book, limit_order_strategy)
        elif side == 'sell':
            price = calculate_limit_sell_price(order_book, limit_order_strategy)
        price = self.exchange.price_to_precision(symbol, price)
        try:
            logger.info(
                'Open limit order, ' + side + ' ' + symbol + '=>' + str(amount) + '*' + str(price) + '=' + str(
                    float(amount) * float(price)))
            order = self.exchange.create_order(symbol, 'limit', side, amount, price)
            send_line_notify('Exchange Response: ' + str(order))
        except Exception as e:
            logger.error(traceback.format_exc())
            send_line_notify('Unable to create order')
            self.threads[asset] = None
            return

        error_count = 0
        while True:
            order_id = get_order_id(order)
            if order_id != '':
                order = self.exchange.fetch_order(order_id, symbol)
                if order['remaining'] == 0:  # match all
                    logger.info('Order is matched, id=' + str(order_id))
                    send_line_notify('1 Order is matched, id=' + str(order_id))
                    break

            order_book = self.exchange.fetch_order_book(symbol)
            if side == 'buy':
                bid_volume = order_book['bids'][0][1]
                target_price = calculate_limit_buy_price(order_book, limit_order_strategy, tick_size)
                target_price = self.exchange.price_to_precision(symbol, target_price)
                if order is None \
                        or float(order['info']['price']) < float(target_price) \
                        or (limit_order_strategy == LimitOrderStrategy.BETTER_THAN_BEST_PRICE
                            and bid_volume > order['remaining']):
                    if order is None:
                        orders = self.exchange.fetch_open_orders()
                        if len(orders) > 0:
                            for o in orders:
                                if o['symbol'] == symbol and o['side'] == side:
                                    order = o
                                    break
                    if order is not None:
                        try:
                            logger.info('Sending cancel_order, id=' + str(order_id) + ', symbol=' + symbol)
                            self.exchange.cancel_order(order_id, symbol)
                            sleep(0.01)
                        except OrderNotFound:
                            logger.error(traceback.format_exc())
                            logger.warning('Cancel order but order not found, id=' + str(order_id))
                            # check balance
                            self.compute_holding_weight()
                            if self.holding_weight[asset] > self.allocation[asset] * 0.99:  # hold > 99% of allocation
                                send_line_notify('2 Order is matched, id=' + str(order_id))
                                break
                        order = None
                    try:
                        if order:
                            if float(order['filled']) > 0:
                                remaining -= float(order['filled'])
                            order_price = float(order['info']['price'])
                        else:
                            order_price = float(price)
                        amount = (remaining * order_price) / float(target_price)  # recalculate amount
                        # logger.debug(remaining, '*', order_price, '/', float(target_price), '=', amount)
                        if float(amount) * float(target_price) < 1:  # value < 1 base asset
                            send_line_notify('3 Order is matched, id=' + str(order_id))
                            break
                        amount = self.exchange.amount_to_precision(asset + '/' + self.base_asset, amount)
                        logger.info(
                            'Open new limit order, buy ' + symbol + '=>' + str(target_price) + ' amount=' + str(
                                amount) + ' total=' + str(float(amount) * float(target_price)))
                        if float(amount) < self.get_min_trade_amount(asset, self.base_asset):
                            logger.info('Order size is too low, exit')
                            break
                        order = self.exchange.create_order(symbol, 'limit', side, amount, target_price)
                        self.send_line_notify_with_delay(asset,
                                                         'Open new limit order, buy ' + symbol + '=>' + str(
                                                             target_price) + ' amount=' + str(
                                                             amount) + ' total=' + str(
                                                             float(amount) * float(target_price)))
                        logger.info(str(order))
                        price = target_price
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        error_count += 1
                        if error_count > 10:
                            send_line_notify('Unable to create order')
                            break
                        order = None
                        available_balance = self.get_available_base_balance_for_asset(asset) * (1 - self.fee)
                        remaining = available_balance / float(target_price)  # recalculate amount
                        sleep(1)
            elif side == 'sell':
                ask_volume = order_book['asks'][0][1]
                target_price = calculate_limit_sell_price(order_book, limit_order_strategy, tick_size)
                target_price = self.exchange.price_to_precision(symbol, target_price)
                if order is None \
                        or float(order['info']['price']) > float(target_price) \
                        or (limit_order_strategy == LimitOrderStrategy.BETTER_THAN_BEST_PRICE
                            and ask_volume > self.get_balance(asset)):
                    if order is None:
                        orders = self.exchange.fetch_open_orders()
                        if len(orders) > 0:
                            for o in orders:
                                if o['symbol'] == symbol and o['side'] == side:
                                    order = o
                                    break
                    if order is not None:
                        try:
                            logger.info('Sending cancel_order, id=' + str(order_id) + ', symbol=' + symbol)
                            self.exchange.cancel_order(order_id, symbol)
                            sleep(0.01)
                        except OrderNotFound:
                            logger.error(traceback.format_exc())
                            logger.warning('Cancel order but order not found, id=' + str(order_id))
                            self.compute_holding_weight()
                            if self.holding_weight[asset] < self.allocation[asset] * 0.01:  # hold < 1% of allocation
                                send_line_notify('4 Order is matched, id=' + str(order_id))
                                break
                        order = None
                    try:
                        amount = self.get_balance(asset)
                        logger.info(
                            f'Selling exchange={self.exchange} symbol={symbol} amount={amount} price={target_price} value={float(amount) * float(target_price)}')
                        if float(amount) * float(target_price) < 1:  # value < 1 base asset
                            send_line_notify('5 Order is matched, id=' + str(order_id))
                            break
                        amount = self.exchange.amount_to_precision(asset + '/' + self.base_asset, amount)
                        logger.info(
                            'Open new limit order, sell ' + symbol + '=' + str(target_price) + ' amount=' + str(
                                amount) + ' total=' + str(float(amount) * float(target_price)))
                        if float(amount) < self.get_min_trade_amount(asset, self.base_asset):
                            logger.info('Order size is too low, exit')
                            send_line_notify('Order size is too low, exit')
                            break
                        order = self.exchange.create_order(symbol, 'limit', side, amount, target_price)
                        self.send_line_notify_with_delay(asset,
                                                         'Open new limit order, sell ' + symbol + '=' + str(
                                                             target_price) + ' amount=' + str(
                                                             amount) + ' total=' + str(
                                                             float(amount) * float(target_price)))
                        logger.info(str(order))
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        error_count += 1
                        if error_count > 4:
                            send_line_notify('Unable to create order')
                            break
                        order = None
                        sleep(1)
            if self.stop_worker[asset]:
                self.stop_worker[asset] = False
                break
            sleep(1)
        self.threads[asset] = None

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
