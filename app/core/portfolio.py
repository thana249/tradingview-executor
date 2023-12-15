from abc import ABC, abstractmethod


class Portfolio(ABC):
    """
    Abstract base class for portfolio objects.
    """

    @abstractmethod
    def send_order(self, data, limit_order_strategy) -> None:
        """
        Sends an order based on the provided data and limit order strategy.
        """
        pass

    @abstractmethod
    def get_portfolio_balance(self):
        """
        Retrieves the balance of the portfolio.
        """
        pass

    @abstractmethod
    def is_thread_running(self) -> bool:
        """
        Checks if a thread is running.
        """
        pass
