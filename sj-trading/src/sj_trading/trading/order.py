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

        self.api.cancel_order(trade=target_trade)
        print(f"Order {order_id} cancellation sent.")

    def cancel_all_orders(self) -> int:
        """Cancel all active (pending) orders. Returns number of cancelled orders."""
        self.update_status()
        trades = self.api.list_trades()
        cancel_count = 0
        
        # Pending Statuses: PendingSubmit, PreSubmitted, Submitted
        # Shioaji status names e.g. Submitted, PendingSubmit
        for t in trades:
            status_name = t.status.status.name
            if status_name in ["PendingSubmit", "PreSubmitted", "Submitted", "PartFilled"]:
                try:
                    self.api.cancel_order(trade=t)
                    print(f"Cancelled Order {t.status.id} ({t.contract.code} {t.order.action.name} {t.order.quantity})")
                    cancel_count += 1
                except Exception as e:
                    print(f"Failed to cancel {t.status.id}: {e}")
                    
        return cancel_count

    def list_futures_closed_records(self, begin_date: str, end_date: str) -> List[list]:
        """
        Closed futures trades in [begin_date, end_date] (YYYY-MM-DD), regardless of where they were placed.
        Row format matches the trade record sheet: 平倉日, 下單日, 產品, 口數, 方向, 買點數, 賣點數,
        followed by round-trip fee and tax.
        """
        def fmt(d: str) -> str:
            d = d.replace("-", "").replace("/", "")
            return f"{d[:4]}/{d[4:6]}/{d[6:8]}"

        account = self.api.futopt_account
        records = []
        for pl in self.api.list_profit_loss(account, begin_date, end_date):
            for d in self.api.list_profit_loss_detail(account, pl.id):
                is_long = d.direction == Action.Buy
                records.append([
                    fmt(pl.date),                                # 平倉日
                    fmt(d.date),                                 # 下單日
                    d.code,                                      # 產品
                    d.quantity,                                  # 口數
                    "多" if is_long else "空",                   # 方向
                    d.entry_price if is_long else d.cover_price, # 買點數
                    d.cover_price if is_long else d.entry_price, # 賣點數
                    d.fee,                                       # 手續費 (round trip)
                    d.tax,                                       # 交易稅 (round trip)
                ])
        return records

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
