from ccxt.base.exchange import Exchange
from app.core.ccxt_ext.define_rest_api import DefineRestAPI
import hashlib
import json
import time
import hmac
from ccxt.base.types import Balances, Int, Market, OrderBook, OrderSide, OrderType, Str, Strings, Ticker, Tickers
from ccxt.base.errors import ExchangeError
from ccxt.base.errors import InvalidOrder
from ccxt.base.errors import OrderNotFound
from ccxt.base.errors import NotSupported
from ccxt.base.errors import DDoSProtection
from ccxt.base.errors import AuthenticationError
from ccxt.base.decimal_to_precision import DECIMAL_PLACES


class bitkub(Exchange, DefineRestAPI):

    def __init__(self, config={}):
        Exchange.__init__(self, config)
        DefineRestAPI.__init__(self)

    def describe(self):
        return self.deep_extend(super(bitkub, self).describe(), {
            'id': 'bitkub',
            'name': 'Bitkub',
            'countries': ['TH'],
            'has': {
                'CORS': None,
                'publicAPI': True,
                'privateAPI': True,
                'fetchTime': True,
                'fetchCurrencies': False,
                'fetchMarkets': True,
                'fetchBalance': True,
                'fetchTicker': False,
                'fetchTickers': True,
                'fetchOrderBook': True,
                'fetchOrderBooks': False,
                'fetchMyTrades': True,
                'createOrder': True,
                'createOrders': False,
                'cancelOrder': True,
                'cancelOrders': False,
                'fetchOpenOrders': True,
                'fetchOrder': True,
            },
            'timeframes': {
                '1m': 60,
                '5m': 300,
                '15m': 900,
                '30m': 1800,
                '1h': 3600,
                '4h': 14400,
                '1d': 86400,
            },
            'urls': {
                'logo': 'https://www.bitkub.com/static/images/logo-white.png',
                'api': {
                    'public': 'https://api.bitkub.com',
                    'private': 'https://api.bitkub.com',
                },
                'www': 'https://www.bitkub.com',
                'doc': 'https://github.com/bitkub/bitkub-official-api-docs',
                'fees': 'https://www.bitkub.com/fee/cryptocurrency',
            },
            'api': {
                # the API structure below will need 3-layer apidefs
                'public': {
                    # IP(api) request rate limit of 6000 per minute
                    # 1 IP(api) => cost = 0.2 =>(1000 / (50 * 0.2)) * 60 = 6000
                    'get': {
                        'api/v3/servertime': 0.4,
                        'api/market/symbols': 0.2,
                        'api/market/ticker': 0.2,
                        'api/market/depth': 0.02,
                    },
                },
                'private': {
                    'get': {
                        'api/v3/market/my-order-history': 0.3,
                        'api/v3/market/my-open-orders': 0.2,
                        'api/v3/market/order-info': 0.2,
                    },
                    'post': {
                        'api/v3/market/balances': 0.3,
                        'api/market/place-bid/test': 0.1,
                        'api/market/place-ask/test': 0.1,
                        'api/v3/market/place-bid': 0.1,
                        'api/v3/market/place-ask': 0.1,
                        'api/v3/market/cancel-order': 0.2,
                    },
                },
            },
            'timeout': 5000,
            'rateLimit': 1000,
            'precision': {
                'price': 2,
                'amount': 8,
                'cost': 2,
            },
            'fees': {
                'trading': {
                    # 'feeSide': 'get',
                    'tierBased': False,
                    'percentage': True,
                    'taker': self.parse_number('0.0025'),
                    'maker': self.parse_number('0.0025'),
                },
            },
            'precisionMode': DECIMAL_PLACES,
            # exchange-specific options
            'options': {
                'defaultType': 'spot',  # 'spot', 'future', 'margin', 'delivery', 'option'
                'defaultSubType': None,  # 'linear', 'inverse'
                'timeDifference': 0,  # the difference between system clock and Binance clock
            },
            # https://github.com/bitkub/bitkub-official-api-docs/blob/master/restful-api.md#error-codes
            'exceptions': {
                '0': 'No error',
                '1': 'Invalid JSON payload',
                '2': 'Missing X-BTK-APIKEY',
                '3': 'Invalid API key',
                '4': 'API pending for activation',
                '5': 'IP not allowed',
                '6': 'Missing/invalid signature',
                '7': 'Missing timestamp',
                '8': 'Invalid timestamp',
                '9': 'Invalid user',
                '10': 'Invalid parameter',
                '11': 'Invalid symbol',
                '12': 'Invalid amount',
                '13': 'Invalid rate',
                '14': 'Improper rate',
                '15': 'Amount too low',
                '16': 'Failed to get Balance',
                '17': 'Wallet is empty',
                '18': 'Insufficient balance',
                '19': 'Failed to insert into db',
                '20': 'Failed to deduct balance',
                '21': 'Invalid order for cancellation',
                '22': 'Invalid side',
                '23': 'Failed to update order status',
                '24': 'Invalid currency for withdrawal',
                '30': 'Limit exceeded',
                '40': 'Pending withdrawal exists',
                '43': 'Failed to deduct crypto',
                '44': 'Failed to dreate withdrawal record',
            },
        })

    def sign(self, path, api='public', method='GET', params={}, headers=None, body=None):
        urls = self.urls
        if not (api in urls['api']):
            raise NotSupported(self.id + ' does not have a testnet/sandbox URL for ' + api + ' endpoints')

        url = self.urls['api'][api] + '/' + path

        if api == 'private':
            if self.apiKey and self.secret:
                timestamp = str(int(time.time()*1000))

                headers = {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-BTK-TIMESTAMP': timestamp,
                    'X-BTK-APIKEY': self.apiKey,
                }

                # Preparing data for signature
                if method == 'GET':
                    query = self.urlencode(params)
                    signature_string = timestamp + method + '/' + path
                    if query:
                        signature_string += '?' + query
                        url += '?' + query
                else:
                    body = self.__json_encode(params)
                    signature_string = timestamp + method + '/' + path + body

                # Generating signature
                signature = hmac.new(self.secret.encode(), signature_string.encode(), hashlib.sha256).hexdigest()
                headers['X-BTK-SIGN'] = signature
            else:
                raise AuthenticationError(self.id + ' private endpoint requires `apiKey` and `secret` credentials')
        else:
            if params:
                url += '?' + self.urlencode(params)
        return {'url': url, 'method': method, 'body': body, 'headers': headers}

    def handle_errors(self, code, reason, url, method, headers, body, response, requestHeaders, requestBody):
        if (code == 418) or (code == 429):
            raise DDoSProtection(self.id + ' ' + str(code) + ' ' + reason + ' ' + body)
        if response is None:
            return None  # fallback to default error handler
        # checks against error codes
        error = self.safe_string(response, 'error')
        if error is not None:
            # https://github.com/ccxt/ccxt/issues/6501
            # https://github.com/ccxt/ccxt/issues/7742
            if error == '0':
                return None
            feedback = self.id + ' ' + body + ' ' + self.exceptions[error]
            self.throw_exactly_matched_exception(self.exceptions[error], error, feedback)
            raise ExchangeError(feedback)
        return None

    def fetch_time(self, params={}):
        """
        fetches the current integer timestamp in milliseconds from the exchange server
        :see: https://github.com/bitkub/bitkub-official-api-docs/blob/master/restful-api.md#get-apiv3servertime
        :param dict [params]: extra parameters specific to the exchange API endpoint
        :returns int: the current integer timestamp in milliseconds from the exchange server
        """
        return self.publicGetApiV3Servertime(params)

    def fetch_markets(self, params={}):
        """
        retrieves data on all markets for bitkub
        :see: https://binance-docs.github.io/apidocs/spot/en/#exchange-information         # spot
        :param dict [params]: extra parameters specific to the exchange API endpoint
        :returns dict[]: an array of objects representing market data
        """
        response = self.publicGetApiMarketSymbols(params)
        markets = response['result']
        result = []
        for market in markets:
            market_symbol = market.get('symbol')
            lowercase_id = market_symbol.lower()
            currency_symbol = market_symbol.split('_')
            base = currency_symbol[1]
            quote = currency_symbol[0]
            base_id = base
            quote_id = quote
            symbol = f"{base}/{quote}"
            market_info = {
                'id': market_symbol,
                'lowercaseId': lowercase_id,
                'symbol': symbol,
                'base': base,
                'quote': quote,
                'baseId': base_id,
                'quoteId': quote_id,
                'type': 'spot',
                'spot': True,
                'swap': False,
                'future': False,
                'option': False,
                'active': True,
                'limits': {
                    'amount': {
                        'min': None,
                        'max': None,
                    },
                    'price': {
                        'min': None,
                        'max': None,
                    },
                    'cost': {
                        'min': 10,
                        'max': None,
                    },
                },
                'info': market,
            }
            result.append(market_info)
        return result

    def __json_encode(self, payload):
        return json.dumps(payload, separators=(',', ':'), sort_keys=True)

    def fetch_balance(self, params={}) -> Balances:
        """
        query for balance and get the amount of funds available for trading or funds locked in orders
        :see: https://github.com/bitkub/bitkub-official-api-docs/blob/master/restful-api.md#post-apiv3marketbalances
        :returns dict: a `balance structure <https://docs.ccxt.com/#/?id=balance-structure>`
        """
        self.load_markets()
        request = {}
        response = self.private_post_api_v3_market_balances(self.extend(request, params))
        markets = response['result']
        result = {'info': markets}
        free = {}
        for key, market in markets.items():
            available = self.safe_float(market, 'available')
            reserved = self.safe_float(market, 'reserved')
            free[key] = available
            account = {
                'free': available,
                'used': reserved,
                'total': available + reserved,
            }
            result[key] = account
        return self.safe_balance(result)

    def parse_ticker(self, ticker, market: Market = None) -> Ticker:
        timestamp = self.safe_integer(ticker, 'closeTime')
        market_type = None
        if 'time' in ticker:
            market_type = 'contract'
        if market_type is None:
            market_type = 'spot' if ('bidQty' in ticker) else 'contract'
        market_id = self.safe_string(ticker, 'symbol')
        symbol = self.safe_symbol(market_id, market, None, market_type)
        last = self.safe_string(ticker, 'last')
        is_coin_m = ('baseVolume' in ticker)
        if is_coin_m:
            base_volume = self.safe_string(ticker, 'baseVolume')
            quote_volume = self.safe_string(ticker, 'volume')
        else:
            base_volume = self.safe_string(ticker, 'volume')
            quote_volume = self.safe_string_2(ticker, 'quoteVolume', 'amount')
        return self.safe_ticker({
            'symbol': symbol,
            'timestamp': timestamp,
            'datetime': self.iso8601(timestamp),
            'high': self.safe_string_2(ticker, 'highPrice', 'high'),
            'low': self.safe_string_2(ticker, 'lowPrice', 'low'),
            'bid': self.safe_string(ticker, 'bidPrice'),
            'bidVolume': self.safe_string(ticker, 'bidQty'),
            'ask': self.safe_string(ticker, 'askPrice'),
            'askVolume': self.safe_string(ticker, 'askQty'),
            'vwap': self.safe_string(ticker, 'weightedAvgPrice'),
            'open': self.safe_string_2(ticker, 'openPrice', 'open'),
            'close': last,
            'last': last,
            'previousClose': self.safe_string(ticker, 'prevClosePrice'),  # previous day close
            'change': self.safe_string(ticker, 'priceChange'),
            'percentage': self.safe_string(ticker, 'priceChangePercent'),
            'average': None,
            'baseVolume': base_volume,
            'quoteVolume': quote_volume,
            'info': ticker,
        }, market)

    def fetch_tickers(self, symbols: Strings = None, params={}) -> Tickers:
        """
        fetches price tickers for multiple markets, statistical information calculated over the past 24 hours for each market
        :see: https://github.com/bitkub/bitkub-official-api-docs/blob/master/restful-api.md#get-apimarketticker
        :param str[]|None symbols: unified symbols of the markets to fetch the ticker for, all market tickers are returned if not assigned
        :param dict [params]: extra parameters specific to the exchange API endpoint
        :returns dict: a dictionary of `ticker structures <https://docs.ccxt.com/#/?id=ticker-structure>`
        """
        self.load_markets()
        query = self.omit(params, 'type')
        default_method = 'publicGetApiMarketTicker'
        method = self.safe_string(self.options, 'fetchTickersMethod', default_method)
        response = getattr(self, method)(query)
        result = {}
        for _id, ticker in response.items():
            market = self.markets_by_id.get(_id)
            if len(market) > 0:
                symbol = market[0]['symbol']
                result[symbol] = self.parse_ticker(ticker, market[0])
        return self.parse_tickers(response, symbols)

    def fetch_order_book(self, symbol: str, limit: Int = None, params={}) -> OrderBook:
        """
        fetches information on open orders with bid(buy) and ask(sell) prices, volumes and other data
        :see: https://github.com/bitkub/bitkub-official-api-docs/blob/master/restful-api.md#get-apimarketdepth      # spot
        :param str symbol: unified symbol of the market to fetch the order book for
        :param int [limit]: the maximum amount of order book entries to return
        :param dict [params]: extra parameters specific to the exchange API endpoint
        :returns dict: A dictionary of `order book structures <https://docs.ccxt.com/#/?id=order-book-structure>` indexed by market symbols
        """
        self.load_markets()
        market = self.market(symbol)
        request = {
            'sym': market['id'],
        }
        if limit is None:
            limit = 100
        request['lmt'] = limit  # default 100, max 100
        response = self.publicGetApiMarketDepth(self.extend(request, params))
        timestamp = self.safe_integer(response, 'T')
        orderbook = self.parse_order_book(response, symbol, timestamp)
        orderbook['nonce'] = self.safe_integer_2(response, 'lastUpdateId', 'u')
        return orderbook

    def fetch_my_trades(self, symbol: Str = None, since: Int = None, limit: Int = None, params={}):
        """
        fetch all trades made by the user
        :see: https://github.com/bitkub/bitkub-official-api-docs/blob/master/restful-api.md#get-apiv3marketmy-order-history
        :param str symbol: unified market symbol
        :param int [since]: the earliest time in ms to fetch trades for
        :param int [limit]: the maximum number of trades structures to retrieve
        :param dict [params]: extra parameters specific to the exchange API endpoint
        :param boolean [params.paginate]: default False, when True will automatically paginate by calling self endpoint multiple times. See in the docs all the [availble parameters](https://github.com/ccxt/ccxt/wiki/Manual#pagination-params)
        :param int [params.until]: the latest time in ms to fetch entries for
        :returns Trade[]: a list of `trade structures <https://docs.ccxt.com/#/?id=trade-structure>`
        """
        self.load_markets()
        if symbol is not None:
            market = self.market(symbol)
            symbol = f'{market["baseId"]}_{market["quoteId"]}'
            request = {'sym': symbol}

        if since is not None:
            request['start'] = int(since / 1000)
            request['end'] = int(self.milliseconds() / 1000)

        if limit is not None:
            request['lmt'] = limit

        response = self.privateGetApiV3MarketMyOrderHistory(self.extend(request, params))
        trades = response['result']
        result = []
        for trade in trades:
            txn_id = self.safe_string(trade, 'txn_id')
            order = self.safe_string(trade, 'order_id')
            trade_type = self.safe_string(trade, 'type')
            side = self.safe_string(trade, 'side')
            taker_or_maker = 'taker' if self.safe_value(trade, 'taken_by_me') else 'maker'
            price = self.safe_float(trade, 'rate')
            amount = self.safe_float(trade, 'amount')
            cost = price * amount if price and amount else None
            fee = self.safe_float(trade, 'fee')
            timestamp = self.safe_timestamp(trade, 'ts')
            if timestamp:
                timestamp /= 1000

            result.append({
                'info': trade,
                'id': txn_id,
                'timestamp': timestamp,
                'datetime': self.iso8601(timestamp) if timestamp else None,
                'symbol': symbol,
                'order': order,
                'type': trade_type,
                'side': side,
                'takerOrMaker': taker_or_maker,
                'price': price,
                'amount': amount,
                'cost': cost,
                'fee': fee,
            })

        return result

    def create_order(self, symbol: str, type: OrderType, side: OrderSide, amount, price=None, params={}):
        """
        create a trade order
        :see: https://github.com/bitkub/bitkub-official-api-docs/blob/master/restful-api.md#post-apiv3marketplace-bid
        :see: https://github.com/bitkub/bitkub-official-api-docs/blob/master/restful-api.md#post-apiv3marketplace-ask
        :param str symbol: unified symbol of the market to create an order in
        :param str type: 'market' or 'limit' or 'STOP_LOSS' or 'STOP_LOSS_LIMIT' or 'TAKE_PROFIT' or 'TAKE_PROFIT_LIMIT' or 'STOP'
        :param str side: 'buy' or 'sell'
        :param float amount: how much of currency you want to trade in units of base currency
        :param float [price]: the price at which the order is to be fullfilled, in units of the quote currency, ignored in market orders
        :param dict [params]: extra parameters specific to the exchange API endpoint
        :param str [params.marginMode]: 'cross' or 'isolated', for spot margin trading
        :param boolean [params.sor]: *spot only* whether to use SOR(Smart Order Routing) or not, default is False
        :param boolean [params.test]: *spot only* whether to use the test endpoint or not, default is False
        :returns dict: an `order structure <https://docs.ccxt.com/#/?id=order-structure>`
        """
        if price is None:
            raise InvalidOrder(self.id + ' createOrder requires a price argument for both limit and market orders')
        self.load_markets()
        market = self.market(symbol)
        if side == 'buy':
            amt = amount * float(price)
        else:
            amt = amount
        request = {
            'sym': f'{market["baseId"]}_{market["quoteId"]}',
            'amt': amt,
            'rat': price,
            'typ': type,
        }
        method = 'private_post_api_v3_market_place_bid' if side == 'buy' else 'private_post_api_v3_market_place_ask'
        response = getattr(self, method)(self.extend(request, params))
        # Response: {
        #   "error": 0,
        #   "result": {
        #     "id": "1", // order id
        #     "hash": "fwQ6dnQWQPs4cbatF5Am2xCDP1J", // order hash
        #     "typ": "limit", // order type
        #     "amt": 1000, // spending amount
        #     "rat": 15000, // rate
        #     "fee": 2.5, // fee
        #     "cre": 2.5, // fee credit used
        #     "rec": 0.06666666, // amount to receive
        #     "ts": "1707220636" // timestamp
        #     "ci": "input_client_id" // input id for reference
        #   }
        # }
        order = response['result']
        order_id = self.safe_string(order, 'id')
        timestamp = self.safe_integer(order, 'ts')
        if timestamp:
            timestamp /= 1000
        amt = self.safe_float(order, 'amt')
        price = self.safe_float(order, 'rat')
        cost = amt if side == 'buy' else amt * price
        filled = self.safe_float(order, 'rec') if type == 'market' else 0
        rec = self.safe_float(order, 'rec')
        status = 'open'
        return {
            'id': order_id,
            'info': order,
            'timestamp': timestamp,
            'datetime': self.iso8601(timestamp),
            'symbol': symbol,
            'type': type,
            'side': side,
            'price': price,
            'amount': amount / price if side == 'buy' else amount,
            'cost': cost,
            'filled': filled,
            'remaining': rec if side == 'buy' else amt,
            'status': status,
        }

    def cancel_order(self, id: str, symbol: Str = None, params={}):
        """
        cancels an open order
        :see: https://github.com/bitkub/bitkub-official-api-docs/blob/master/restful-api.md#post-apiv3marketcancel-order
        :param str id: order id
        :param str symbol: unified symbol of the market the order was made in
        :param dict [params]: extra parameters specific to the exchange API endpoint
        :returns dict: An `order structure <https://docs.ccxt.com/#/?id=order-structure>`
        """
        self.load_markets()
        if symbol is not None:
            market = self.market(symbol)
            symbol = f'{market["baseId"]}_{market["quoteId"]}'
            request = {
                'sym': symbol,
                'id': id,
                'sd': params.get('sd'),
            }
        else:
            request = {'hash': id}
        return self.private_post_api_v3_market_cancel_order(self.extend(request, params))

    def fetch_open_orders(self, symbol: str = None, since: Int = None, limit: Int = None, params={}):
        """
        fetches all open orders made by the user
        :see: https://github.com/bitkub/bitkub-official-api-docs/blob/master/restful-api.md#get-apiv3marketmy-open-orders
        :param str symbol: unified symbol of the market to fetch the order book for
        :param int [since]: the earliest time in ms to fetch trades for
        :param int [limit]: the maximum number of trades structures to retrieve
        :param dict [params]: extra parameters specific to the exchange API endpoint
        :returns dict: A dictionary of `order book structures <https://docs.ccxt.com/#/?id=order-book-structure>` indexed by market symbols
        """
        self.load_markets()
        if symbol is not None:
            market = self.market(symbol)
            symbol = f'{market["baseId"]}_{market["quoteId"]}'
            request = {'sym': symbol}
        else:
            request = {}
        response = self.privateGetApiV3MarketMyOpenOrders(self.extend(request, params))
        orders = response['result']
        result = []
        for order in orders:
            # Example order: {'id': '278688757', 'hash': 'fwQ6dnQYKnqFPJ4gLt3NPLTLGWt', 'side': 'buy', 'type': 'limit',
            # 'rate': '10', 'fee': '0.03', 'credit': '0.03', 'amount': '10', 'receive': '1', 'parent_id': '0',
            # 'super_id': '0', 'client_id': '', 'ts': '1707299574000'}
            order_id = self.safe_string(order, 'id')
            side = self.safe_string(order, 'side')
            order_type = self.safe_string(order, 'type')
            rate = self.safe_float(order, 'rate')
            amount = self.safe_float(order, 'amount')
            timestamp = self.safe_integer(order, 'ts')
            if timestamp:
                timestamp /= 1000
            result.append({
                'id': order_id,
                'timestamp': timestamp,
                'datetime': self.iso8601(timestamp),
                'symbol': symbol,
                'type': order_type,
                'side': side,
                'price': rate,
                'amount': amount/rate if side == 'buy' else amount,
                'info': order,
            })
        return result

    def fetch_order(self, id: str, symbol: Str = None, params={}):
        """
        fetches an order by its id
        :see: https://github.com/bitkub/bitkub-official-api-docs/blob/master/restful-api.md#get-apiv3marketorder-info
        :param str id: order id
        :param str symbol: unified symbol of the market the order was made in
        :param dict [params]: extra parameters specific to the exchange API endpoint
        :returns dict: An `order structure <https://docs.ccxt.com/#/?id=order-structure>`
        """
        self.load_markets()
        if symbol is not None:
            market = self.market(symbol)
            symbol = f'{market["baseId"]}_{market["quoteId"]}'
            request = {
                'sym': symbol,
                'id': id,
            }
        else:
            request = {'hash': id}
        order = self.privateGetApiV3MarketOrderInfo(self.extend(request, params))
        if order['error'] != '0':
            raise OrderNotFound(self.id + ' ' + self.json(order))
        return self.parse_order(order['result'], {'symbol': symbol})

    def parse_order(self, order, market: Market = None):
        """
        parses an order from the exchange
        :param dict order: the order to parse
        :param Market [market]: the market the order was made in
        :returns dict: an `order structure <https://docs.ccxt.com/#/?id=order-structure>`
        """
        # Example order: {'amount': '10', 'client_id': '', 'credit': '0.03', 'fee': '0.03', 'filled': '0', 'first': '278688757', 'history': [], 'id': '278688757', 'last': '', 'parent': '0', 'partial_filled': False, 'post_only': False, 'rate': '10', 'remaining': '10', 'side': 'buy', 'status': 'unfilled', 'total': '10'}
        order_id = self.safe_string(order, 'id')
        symbol = self.safe_string(order, 'symbol')
        side = self.safe_string(order, 'side')
        order_type = self.safe_string(order, 'type')
        timestamp = self.safe_integer(order, 'ts')
        if timestamp:
            timestamp /= 1000
        price = self.safe_float(order, 'rate')
        amount = self.safe_float(order, 'amount')
        remaining = self.safe_float(order, 'remaining')
        filled = self.safe_float(order, 'filled')
        status = self.safe_string(order, 'status')
        cost = price * filled if price and filled else None
        return {
            'id': order_id,
            'info': order,
            'timestamp': timestamp,
            'datetime': self.iso8601(timestamp),
            'symbol': symbol,
            'type': order_type,
            'side': side,
            'price': price,
            'amount': amount/price if side == 'buy' else amount,
            'cost': cost,
            'filled': filled,
            'remaining': remaining/price if side == 'buy' else remaining,
            'status': status,
        }
