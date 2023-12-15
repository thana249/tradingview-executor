# Python code from file endpoints.py

import json
import logging
from fastapi import APIRouter, Request
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
    return JSONResponse(content=result)


# Webhook route to receive data and send notifications
@router.post('/webhook')
async def webhook(request: Request):
    try:
        data = await request.json()

        # Send notifications based on the received data
        if 'line_token' in data:
            token = data['line_token']
            data.pop('line_token')
            msg = json.dumps(data, sort_keys=True, indent=4).replace('"', '')
            notification_service.send_line_notify(msg, token)
        else:
            msg = json.dumps(data, sort_keys=True, indent=4).replace('"', '')
            notification_service.send_line_notify(msg)
    except Exception as e:
        logging.error(e)
        msg = await request.body()
        notification_service.send_line_notify(msg.decode())
        return JSONResponse(content={}, status_code=200)

    # Send order if specified in the data
    if data['send_order']:
        trading_service.send_order(data)

    return JSONResponse(content={}, status_code=200)
