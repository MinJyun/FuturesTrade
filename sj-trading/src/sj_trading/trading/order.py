import shioaji as sj
from shioaji.constant import (
    Action,
    StockPriceType,
    OrderType,
    FuturesPriceType,
    FuturesOCType,
)
from typing import List, Optional

class OrderManager:
    def __init__(self, api: sj.Shioaji):
        self.api = api

    def place_stock_order(
        self,
        code: str,
        action: Action,
        price: float,
        quantity: int,
        price_type: StockPriceType = StockPriceType.LMT,
        order_type: OrderType = OrderType.ROD,
    ):
        contract = self.api.Contracts.Stocks[code]
        if not contract:
            raise ValueError(f"Stock contract not found for code: {code}")

        order = sj.order.StockOrder(
            action=action,
            price=price,
            quantity=quantity,
            price_type=price_type,
            order_type=order_type,
            account=self.api.stock_account,
        )
        
        trade = self.api.place_order(contract=contract, order=order)
        return trade

    def place_futures_order(
        self,
        code: str,
        action: Action,
        price: float,
        quantity: int,
        price_type: FuturesPriceType = FuturesPriceType.LMT,
        order_type: OrderType = OrderType.ROD,
        octype: FuturesOCType = FuturesOCType.Auto,
    ):
        contract = self.api.Contracts.Futures[code]
        if not contract:
            raise ValueError(f"Futures contract not found for code: {code}")

        order = sj.order.FuturesOrder(
            action=action,
            price=price,
            quantity=quantity,
            price_type=price_type,
            order_type=order_type,
            octype=octype,
            account=self.api.futopt_account,
        )
        
        trade = self.api.place_order(contract=contract, order=order)
        return trade

    def update_status(self):
        self.api.update_status()

    def list_trades(self) -> List:
        self.update_status()
        return self.api.list_trades()

    def update_order_price(self, order_id: str, new_price: float):
        self.update_status()
        trades = self.api.list_trades()
        target_trade = next((t for t in trades if t.status.id == order_id), None)
        
        if not target_trade:
            raise ValueError(f"Order ID {order_id} not found.")

        self.api.update_order_price(trade=target_trade, price=new_price)
        self.api.update_status(trade=target_trade)
        return target_trade

    def cancel_order(self, order_id: str):
        self.update_status()
        trades = self.api.list_trades()
        target_trade = next((t for t in trades if t.status.id == order_id), None)
        
        if not target_trade:
            # If not found in active trades, it might be already filled or cancelled.
            # We assume if not found, we can't cancel it.
            print(f"Warning: Order ID {order_id} not found for cancellation.")
            return

        self.api.update_status(trade=target_trade, action=Action.Cancel)
        print(f"Order {order_id} cancellation sent.")

    def get_futures_position(self, code: str) -> Optional[dict]:
        """
        Get current futures position for a specific code.
        Returns dict with 'quantity' (positive for long, negative for short) and 'price'.
        Returns None if no position found.
        """
        # Note: Shioaji implementation details for list_positions might VARY by version.
        # Standard approach: api.list_positions(account)
        self.api.update_status() # Ensure account data is synced? often needed for trades, maybe positions too.
        positions = self.api.list_positions(self.api.futopt_account)
        
        target = next((p for p in positions if p.code == code), None)
        if not target:
            return None
            
        return {
            "quantity": float(target.quantity), # Shioaji usually returns signed quantity or direction
            "price": float(target.price),
            "direction": target.direction # Action.Buy or Action.Sell usually
        }
