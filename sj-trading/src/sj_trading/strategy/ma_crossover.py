import time
from .base import BaseStrategy
from shioaji.constant import Action, FuturesPriceType

class MACrossoverStrategy(BaseStrategy):
    def run(self, symbol: str = "TMFR1"):
        print(f"Starting MA Crossover Strategy on {symbol}...")
        
        # Subscribe and recover
        self.quote_manager.subscribe_fop_tick([symbol], recover=True)
        
        order_placed = False
        last_tick_count = 0
        
        try:
            while not order_placed:
                df_ticks = self.quote_manager.get_df_fop()
                
                if len(df_ticks) > last_tick_count:
                    last_tick_count = len(df_ticks)
                    
                    if len(df_ticks) < 5:
                        print(f"Not enough data for 5MA. Count: {len(df_ticks)}")
                    else:
                        ma_5 = df_ticks["price"].tail(5).mean()
                        current_price = df_ticks["price"].tail(1).item()
                        previous_price = df_ticks["price"].tail(2).head(1).item()
                        
                        last_time = df_ticks['datetime'].tail(1).item()
                        print(
                            f"Time: {last_time} | Current: {current_price:.2f} | 5MA: {ma_5:.2f} | Prev: {previous_price:.2f}"
                        )
                        
                        if previous_price < ma_5 and current_price > ma_5:
                            print("\n>>> Signal: Price crossed above 5MA! <<<")
                            
                            trade = self.order_manager.place_futures_order(
                                code=symbol,
                                action=Action.Buy,
                                price=round(current_price, 2),
                                quantity=1,
                                price_type=FuturesPriceType.LMT
                            )
                            print(f"\nOrder Placed: {trade}")
                            order_placed = True
                
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\nStrategy interrupted by user.")
        finally:
            self.stop()
            
    def stop(self):
        print("Stopping strategy, unsubscribing...")
        self.quote_manager.unsubscribe_all_fop_tick()
