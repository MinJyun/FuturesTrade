from .base import BaseStrategy
from ..core.notification import NotificationManager
from ..trading.order import OrderManager
from ..data.quote import QuoteManager
from ..utils.gsheet import GoogleSheetClient
from shioaji.constant import Action, OrderType, FuturesPriceType
import shioaji as sj
import time
import os
from datetime import datetime

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
        
        # Google Sheet Init
        self.gs_client = None
        self.gs_url = os.getenv("GOOGLE_SHEET_URL")
        self.gs_tab = os.getenv("GOOGLE_SHEET_TAB_RECORDS")
        if self.gs_url and self.gs_tab:
            self.gs_client = GoogleSheetClient()

        # State tracking
        self.tp_order_id = None
        self.sl_order_id = None
        self.position_closed = False
        
        # Trade Data
        self.entry_price = 0.0
        self.entry_date = ""

    def run(self):
        self.is_running = True
        self.notifier.notify(
            "Strategy Started",
            f"Monitoring {self.symbol} ({self.direction.upper()})\nQty: {self.qty}\nSL: {self.sl_price}\nTP: {self.tp_price}"
        )
        
        # 0. Check Initial Position & Capture Entry Data
        try:
            position = self.order_manager.get_futures_position(self.symbol)
            if not position:
                raise ValueError(f"No position found for {self.symbol}. Strategy aborted.")
            
            # Check Quantity
            pos_qty = abs(position["quantity"])
            if pos_qty < self.qty:
                raise ValueError(f"Insufficient position. Held: {pos_qty}, Required: {self.qty}")
                
            # Check Direction
            pos_dir = "long" if position["direction"] == Action.Buy or position["quantity"] > 0 else "short"
            if pos_dir != self.direction:
                raise ValueError(f"Position direction mismatch. Held: {pos_dir}, Strategy: {self.direction}")
            
            # Capture Entry Data
            self.entry_price = float(position["price"])
            # Date: defaulting to Today as position object date is tricky/unavailable in basic view
            self.entry_date = datetime.now().strftime("%Y/%m/%d") 
            
            print(f"Position verified: {pos_dir.upper()} {pos_qty} @ {self.entry_price}")
            
        except Exception as e:
            self.notifier.notify("❌ Position Check Failed", str(e))
            self.stop()
            return

        # 1. Place Initial TP Order (Limit ROD)
        try:
            if self.direction == "long":
                self._place_tp_order(Action.Sell)
            else:
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
             if current_price <= self.sl_price:
                 self.notifier.notify("⚡ Stop Loss Triggered", f"Price {current_price} <= SL {self.sl_price}")
                 self._trigger_sl_execution(Action.Sell, current_price)
                 
        else: # Short
             if current_price >= self.sl_price:
                 self.notifier.notify("⚡ Stop Loss Triggered", f"Price {current_price} >= SL {self.sl_price}")
                 self._trigger_sl_execution(Action.Buy, current_price)

    def _trigger_sl_execution(self, action: Action, price: float):
        self.position_closed = True 
        
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
             trade = self.order_manager.place_futures_order(
                 code=self.symbol,
                 action=action,
                 price=price, 
                 quantity=self.qty,
                 price_type=FuturesPriceType.MKT,
                 order_type=OrderType.ROD 
             )
             self.sl_order_id = trade.status.id
             self.notifier.notify("SL Order Sent", "Market Order Placed successfully.")
        except Exception as e:
             self.notifier.notify("❌ SL Order Execution Failed", str(e))

    # Callback for Trade execution
    def on_trade(self, trade):
         if not self.is_running:
             return

         order_id = trade.order.id
         deal_price = float(trade.price)
         
         # Case 1: TP Filled
         if self.tp_order_id and order_id == self.tp_order_id:
             self.notifier.notify("🚀 Take Profit Executed!", f"Order {order_id} filled at {deal_price}.")
             self._log_trade_record(deal_price)
             self.position_closed = True
             self.stop()
             
         # Case 2: SL Filled
         elif self.sl_order_id and order_id == self.sl_order_id:
             self.notifier.notify("⚡ Stop Loss Executed!", f"Order {order_id} filled at {deal_price}.")
             self._log_trade_record(deal_price)
             self.position_closed = True
             self.stop()

    def _log_trade_record(self, exit_price: float):
        if not self.gs_client:
            return
            
        try:
            self.notifier.notify("Logging", "Writing trade record to Google Sheet...")
            
            # Format: 平倉日, 下單日, 產品, 口數, 方向, 買點數, 賣點數
            close_date = datetime.now().strftime("%Y/%m/%d")
            direction_str = "多" if self.direction == "long" else "空"
            
            buy_price = self.entry_price if self.direction == "long" else exit_price
            sell_price = exit_price if self.direction == "long" else self.entry_price
            
            record = [
                close_date,          # 平倉日
                self.entry_date,     # 下單日
                self.symbol,         # 產品
                self.qty,            # 口數
                direction_str,       # 方向
                buy_price,           # 買點數 (Raw Float)
                sell_price           # 賣點數 (Raw Float)
            ]
            
            self.gs_client.add_trading_record(record, self.gs_url, self.gs_tab)
            self.notifier.notify("Log Success", "Trade recorded.")
            
        except Exception as e:
            self.notifier.notify("❌ Log Failed", str(e))
