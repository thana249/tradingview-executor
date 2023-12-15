# TradingView Executor

## Project Overview

TradingView Executor is a robust and efficient application designed to automate the process of executing orders on cryptocurrency exchanges based on alerts from TradingView webhooks. It supports major exchanges like Binance, FTX, and Kucoin. Additionally, it integrates with LINE for instant notifications, enhancing the user's trading experience.

### Key Features

- **Webhook Reception**: Receives and processes webhooks from TradingView.
- **Order Execution**: Executes orders on Binance, FTX, or Kucoin based on the received webhook data.
- **Line Notifications**: Sends notifications through LINE for updates and alerts.
- **Dynamic Configuration**: Utilizes `.env` for sensitive credentials and `config.json` for user-defined trading configurations.

## Configuration

### Environment Variables

Sensitive information such as exchange API keys, secrets, and LINE tokens are securely read from a `.env` file. An example of this file can be found in `example.env`.

### Trading Configuration

Trading configurations like exchange-specific settings, base assets, and the universe of symbols to trade are stored in `config.json`. An example structure of this file is provided in `example.config.json`.

#### `config.json` Structure

```json
{
  "orderbook_weights": [4, 2, 1, 1, 0, 0],
  "BINANCE": {
    "fee": 0.0011,
    "base_asset": "USDT",
    "universe": [
      "BTC"
    ]
  }
}
```

### Order Execution Strategy
The application uses the orderbook_weights from config.json to calculate the limit order price based on the WEIGHTED_AVERAGE strategy.

## Running the Application

TradingView Executor is containerized, making it easy to run using Docker. Ensure you have Docker and Docker Compose installed on your system.

### Starting the Application
To start the application, navigate to the project directory and run:

```bash
docker-compose up
```
This command builds the Docker image and starts the container. The application will then be up and running, ready to receive and process webhooks.

## Contributing

Contributions to the TradingView Executor project are welcome. If you have suggestions for improvements or encounter any issues, please feel free to open an issue or submit a pull request.

---

**Note**: This application is designed for demonstration purposes and should be thoroughly tested before being used in a live trading environment. Always review and understand any code that you intend to run and execute, especially when it involves financial transactions.