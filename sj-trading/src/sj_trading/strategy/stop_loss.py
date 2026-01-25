from .base import BaseStrategy
from ..core.notification import NotificationManager
from ..trading.order import OrderManager
from ..data.quote import QuoteManager
from shioaji.constant import Action, OrderType, FuturesPriceType
import shioaji as sj
import time

class StopLossStrategy(BaseStrategy):
    def __init__(
        self,
        quote_manager: QuoteManager,
        order_manager: OrderManager,
        symbol: str,
        qty: int,
        sl_price: float,
        tp_price: float,
        direction: str = "long"
    ):
        super().__init__(quote_manager, order_manager)
        self.symbol = symbol
        self.qty = qty
        self.sl_price = sl_price
        self.tp_price = tp_price
        self.direction = direction.lower() # "long" or "short"
        self.notifier = NotificationManager()
        self.is_running = False
        
        # State tracking
        self.tp_order_id = None
        self.position_closed = False

    def run(self):
        self.is_running = True
        self.notifier.notify(
            "Strategy Started",
            f"Monitoring {self.symbol} ({self.direction.upper()})\nQty: {self.qty}\nSL: {self.sl_price}\nTP: {self.tp_price}"
        )
        
        # 0. Check Initial Position
        try:
            position = self.order_manager.get_futures_position(self.symbol)
            if not position:
                raise ValueError(f"No position found for {self.symbol}. Strategy aborted.")
            
            # Check Quantity
            pos_qty = abs(position["quantity"])
            if pos_qty < self.qty:
                raise ValueError(f"Insufficient position. Held: {pos_qty}, Required: {self.qty}")
                
            # Check Direction
            # Shioaji Action.Buy is usually Long, Sell is Short. 
            # Or quantity > 0 is Long, < 0 is Short depending on API version.
            # Assuming Position.direction field is reliable (Action.Buy/Sell)
            pos_dir = "long" if position["direction"] == Action.Buy or position["quantity"] > 0 else "short"
            
            if pos_dir != self.direction:
                raise ValueError(f"Position direction mismatch. Held: {pos_dir}, Strategy: {self.direction}")
                
            print(f"Position verified: {pos_dir.upper()} {pos_qty} @ {position['price']}")
            
        except Exception as e:
            self.notifier.notify("❌ Position Check Failed", str(e))
            self.stop()
            return
        
        # 1. Place Initial TP Order (Limit ROD)
        try:
            if self.direction == "long":
                # Long position: TP is Sell High
                self._place_tp_order(Action.Sell)
            else:
                # Short position: TP is Buy Low
                self._place_tp_order(Action.Buy)
                
        except Exception as e:
            self.notifier.notify("❌ Failed to place TP Order", str(e))
            self.stop()
            return

        # 2. Subscribe and Monitor
        self.quote_manager.subscribe([self.symbol])
        print(f"Listening for ticks on {self.symbol}...")
        
        try:
            while self.is_running and not self.position_closed:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
            
    def stop(self):
        self.is_running = False
        print("Strategy process ended.")

    def _place_tp_order(self, action: Action):
        trade = self.order_manager.place_futures_order(
            code=self.symbol,
            action=action,
            price=self.tp_price,
            quantity=self.qty,
            price_type=FuturesPriceType.LMT,
            order_type=OrderType.ROD
        )
        self.tp_order_id = trade.status.id
        self.notifier.notify("TP Order Placed", f"Order ID: {self.tp_order_id}\nPrice: {self.tp_price}")

    # Callbacks
    def on_tick_fop_v1(self, exchange, tick):
        if self.position_closed or not self.is_running:
            return

        if tick.code != self.symbol:
            return
            
        current_price = float(tick.close)
        
        # OCO Logic
        if self.direction == "long":
             # Long: SL if Price <= SL
             if current_price <= self.sl_price:
                 self.notifier.notify("⚡ Stop Loss Triggered", f"Price {current_price} <= SL {self.sl_price}")
                 self._trigger_sl_execution(Action.Sell, current_price)
                 
        else: # Short
             # Short: SL if Price >= SL
             if current_price >= self.sl_price:
                 self.notifier.notify("⚡ Stop Loss Triggered", f"Price {current_price} >= SL {self.sl_price}")
                 self._trigger_sl_execution(Action.Buy, current_price)

    def _trigger_sl_execution(self, action: Action, price: float):
        self.position_closed = True # Prevent double trigger
        
        # 1. Cancel TP Order
        if self.tp_order_id:
            self.notifier.notify("Cancelling TP", f"ID: {self.tp_order_id}")
            try:
                self.order_manager.cancel_order(self.tp_order_id)
            except Exception as e:
                 print(f"Error cancelling TP: {e}")
        
        # 2. Place Market SL Order
        self.notifier.notify("Executing SL Market Order", f"Action: {action}, Qty: {self.qty}")
        try:
             self.order_manager.place_futures_order(
                 code=self.symbol,
                 action=action,
                 price=price, 
                 quantity=self.qty,
                 price_type=FuturesPriceType.MKT,
                 order_type=OrderType.ROD 
             )
             self.notifier.notify("SL Order Sent", "Market Order Placed successfully.")
        except Exception as e:
             self.notifier.notify("❌ SL Order Execution Failed", str(e))
             # Ideally we should retry or alert critical error here

    # Callback for Trade execution
    # If TP order is filled, we should stop monitoring.
    def on_trade(self, trade):
         if not self.is_running:
             return
             
         # If TP order filled
         if self.tp_order_id and trade.order.id == self.tp_order_id:
             self.notifier.notify("🚀 Take Profit Executed!", f"Order {self.tp_order_id} filled.")
             self.position_closed = True
             self.stop()
         else:
             # Just logging other trades 
             print(f"Trade update: {trade}")
