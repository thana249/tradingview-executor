"""This is a Python code file named main.py. It is a FastAPI application that sets up logging, includes API
endpoints, and runs a server using uvicorn. The code initializes a logger, sets up logging handlers for both file and
stream, and includes a router for API endpoints. It also loads environment variables from a .env file. The main
function initializes a MarketHandler object, sets the server port to 8000, and runs the FastAPI server using uvicorn.
Note: This code assumes that the necessary modules and packages are imported and installed. """
from fastapi import FastAPI
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
import uvicorn
from app.core.market_handler import MarketHandler
from app.api.endpoints import endpoints


def setup_log():
    log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s')

    # File Handler for logging to a file
    log_file = 'log/tradingview_executor.log'
    file_handler = RotatingFileHandler(log_file, mode='a', maxBytes=5 * 1024 * 1024,
                                       backupCount=2, encoding=None, delay=0)
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)

    # Stream Handler for logging to stdout
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)
    stream_handler.setLevel(logging.INFO)

    # Get the root logger and set the level and handlers
    app_log = logging.getLogger()
    app_log.setLevel(logging.INFO)
    app_log.addHandler(file_handler)
    app_log.addHandler(stream_handler)


logger = logging.getLogger('TradingViewExecutor')

app = FastAPI()
app.include_router(endpoints.router)

setup_log()
load_dotenv()
logger.info('TradingViewExecutor')
mh = MarketHandler()

if __name__ == '__main__':
    port = 8000
    logger.info('Serve port: ' + str(port))
    uvicorn.run(app, host="0.0.0.0", port=8000)
