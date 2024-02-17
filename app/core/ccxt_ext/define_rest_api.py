from ccxt.base.exchange import Exchange

from ccxt.base.errors import NotSupported

# eddsa signing
try:
    import axolotl_curve25519 as eddsa
except ImportError:
    eddsa = None

# -----------------------------------------------------------------------------

__all__ = [
    'DefineRestAPI',
]

# -----------------------------------------------------------------------------

import functools
from numbers import Number
import re


class DefineRestAPI():
    def __init__(self):
        if self.api:
            self.define_rest_api(self.api, 'request')

    def define_rest_api(self, api, method_name, paths=[]):
        for key, value in api.items():
            uppercase_method = key.upper()
            lowercase_method = key.lower()
            camelcase_method = lowercase_method.capitalize()
            if isinstance(value, list):
                for path in value:
                    self.define_rest_api_endpoint(method_name, uppercase_method, lowercase_method, camelcase_method, path, paths)
            # the options HTTP method conflicts with the 'options' API url path
            # elif re.search(r'^(?:get|post|put|delete|options|head|patch)$', key, re.IGNORECASE) is not None:
            elif re.search(r'^(?:get|post|put|delete|head|patch)$', key, re.IGNORECASE) is not None:
                for [endpoint, config] in value.items():
                    path = endpoint.strip()
                    if isinstance(config, dict):
                        self.define_rest_api_endpoint(method_name, uppercase_method, lowercase_method, camelcase_method, path, paths, config)
                    elif isinstance(config, Number):
                        self.define_rest_api_endpoint(method_name, uppercase_method, lowercase_method, camelcase_method, path, paths, {'cost': config})
                    else:
                        raise NotSupported(self.id + ' define_rest_api() API format not supported, API leafs must strings, objects or numbers')
            else:
                self.define_rest_api(value, method_name, paths + [key])

    def define_rest_api_endpoint(self, method_name, uppercase_method, lowercase_method, camelcase_method, path, paths, config={}):
        cls = type(self)
        entry = getattr(cls, method_name)  # returns a function (instead of a bound method)
        delimiters = re.compile('[^a-zA-Z0-9]')
        split_path = delimiters.split(path)
        lowercase_path = [x.strip().lower() for x in split_path]
        camelcase_suffix = ''.join([Exchange.capitalize(x) for x in split_path])
        underscore_suffix = '_'.join([x for x in lowercase_path if len(x)])
        camelcase_prefix = ''
        underscore_prefix = ''
        if len(paths):
            camelcase_prefix = paths[0]
            underscore_prefix = paths[0]
            if len(paths) > 1:
                camelcase_prefix += ''.join([Exchange.capitalize(x) for x in paths[1:]])
                underscore_prefix += '_' + '_'.join([x.strip() for p in paths[1:] for x in delimiters.split(p)])
                api_argument = paths
            else:
                api_argument = paths[0]
        camelcase = camelcase_prefix + camelcase_method + Exchange.capitalize(camelcase_suffix)
        underscore = underscore_prefix + '_' + lowercase_method + '_' + underscore_suffix.lower()

        def partialer():
            outer_kwargs = {'path': path, 'api': api_argument, 'method': uppercase_method, 'config': config}

            @functools.wraps(entry)
            def inner(_self, params=None, context=None):
                """
                Inner is called when a generated method (publicGetX) is called.
                _self is a reference to self created by function.__get__(exchange, type(exchange))
                https://en.wikipedia.org/wiki/Closure_(computer_programming) equivalent to functools.partial
                """
                inner_kwargs = dict(outer_kwargs)  # avoid mutation
                if params is not None:
                    inner_kwargs['params'] = params
                if context is not None:
                    inner_kwargs['context'] = params
                return entry(_self, **inner_kwargs)
            return inner
        to_bind = partialer()
        setattr(cls, camelcase, to_bind)
        setattr(cls, underscore, to_bind)
