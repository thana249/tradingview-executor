"""
Python code to send a notification using LINE Notify API.

This code defines a function `send_line_notify` that sends a message via LINE Notify. It uses the `requests` library
to make a POST request to the LINE Notify API with the provided message. The function requires a token, which can be
passed as an argument or retrieved from the environment variable `LINE_NOTIFY_TOKEN`.

Example usage:
send_line_notify("Hello, world!")
"""

import requests
import os
import logging

logger = logging.getLogger(__name__)


def send_line_notify(msg, token=None):
    if not token:
        token = os.getenv('LINE_NOTIFY_TOKEN')
    url = 'https://notify-api.line.me/api/notify'
    headers = {'content-type': 'application/x-www-form-urlencoded', 'Authorization': 'Bearer ' + token}

    r = requests.post(url, headers=headers, data={'message': msg})
    logger.info('Line notify response: '+r.text)
