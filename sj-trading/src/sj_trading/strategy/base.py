from abc import ABC, abstractmethod
from typing import Any
from ..data.quote import QuoteManager
from ..trading.order import OrderManager

class BaseStrategy(ABC):
    def __init__(self, quote_manager: QuoteManager, order_manager: OrderManager):
        self.quote_manager = quote_manager
        self.order_manager = order_manager

    @abstractmethod
    def run(self, *args, **kwargs):
        pass

    @abstractmethod
    def stop(self):
        pass
