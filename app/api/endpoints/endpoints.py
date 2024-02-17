# Python code from file endpoints.py

import json
import logging
import os

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from app.services.trading_service import get_balance
from app.services import notification_service, trading_service

router = APIRouter()


# Route to check if the API is online
@router.get('/')
def root():
    return 'online'


# Route to get the account balance
@router.get('/balance')
def balance():
    result = get_balance()
    # Serialize the result to a JSON string with indentation
    beautified_json = json.dumps(result, indent=4)
    return Response(content=beautified_json, media_type="application/json")


# Webhook route to receive data and send notifications
@router.post('/webhook')
async def webhook(request: Request):
    try:
        data = await request.json()

        data_without_secret = data.copy()
        if 'secret' in data_without_secret:
            data_without_secret.pop('secret')

        # Send notifications based on the received data
        if 'line_token' in data:
            token = data['line_token']
            data_without_secret.pop('line_token')
            msg = json.dumps(data_without_secret, sort_keys=True, indent=4).replace('"', '')
            notification_service.send_line_notify(msg, token)
        else:
            msg = json.dumps(data_without_secret, sort_keys=True, indent=4).replace('"', '')
            notification_service.send_line_notify(msg)
    except Exception as e:
        logging.error(e)
        msg = await request.body()
        notification_service.send_line_notify(msg.decode())
        return JSONResponse(content={}, status_code=200)

    # Send order if specified in the data

    if data['send_order']:
        secret = os.getenv('ORDER_EXECUTION_SECRET')
        if secret != '':
            if 'secret' not in data:
                # return error if the secret is not provided
                notification_service.send_line_notify('Secret not provided')
                return JSONResponse(content={'error': 'Secret not provided'}, status_code=401)
            elif data['secret'] != secret:
                # return error if the secret is incorrect
                notification_service.send_line_notify('Incorrect secret')
                return JSONResponse(content={'error': 'Incorrect secret'}, status_code=401)
        trading_service.send_order(data)

    return JSONResponse(content={}, status_code=200)
