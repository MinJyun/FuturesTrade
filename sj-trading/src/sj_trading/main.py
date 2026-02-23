import typer
import time
from typing import List
from .core.client import ShioajiClient
from .data.quote import QuoteManager
from .data.info import InfoManager
from .trading.order import OrderManager
from .strategy.ma_crossover import MACrossoverStrategy
from shioaji.constant import Action

app = typer.Typer()

@app.command()
def reload_contracts(
    type: str = typer.Option("all", help="all, future, or stock"),
    file_path: str = typer.Option(None, help="Custom file path")
):
    """
    Reload contract info.
    Type: 'all' (default), 'future', 'stock'.
    """
    try:
        im = InfoManager()
        if type in ["all", "future"]:
             im.reload_data(file_path)
             print("Futures/Options info reloaded.")
        
        if type in ["all", "stock"]:
             im.reload_stock_data(file_path)
             print("Stock info reloaded.")
             
    except Exception as e:
        print(f"Error reloading data: {e}")

@app.command()
def info(query: str):
    """
    Search for contract info (Futures & Stocks).
    """
    try:
        im = InfoManager()
        results = im.search(query)
        
        found = False
        if "Futures" in results and not results["Futures"].is_empty():
            print(f"\n[Futures Results] ({len(results['Futures'])})")
            print(results["Futures"])
            found = True
            
        if "Stocks" in results and not results["Stocks"].is_empty():
            print(f"\n[Stock Results] ({len(results['Stocks'])})")
            print(results["Stocks"])
            found = True
            
        if not found:
            print(f"No results found for '{query}'.")

    except Exception as e:
        print(f"Error searching data: {e}")


@app.command()
def monitor_strategy(
    symbol: str, 
    qty: int, 
    sl: float, 
    tp: float, 
    direction: str = typer.Option("long", help="Position direction: 'long' or 'short'")
):
    """
    Start Stop Loss/Take Profit Strategy (OCO).
    1. Places TP Limit Order immediately.
    2. Monitors price.
    3. If SL hit -> Cancels TP -> Places SL Market Order.
    """
    client = ShioajiClient() 
    # Initialize APIs
    qm = QuoteManager(client.api)
    om = OrderManager(client.api)
    
    from .strategy.stop_loss import StopLossStrategy
    strategy = StopLossStrategy(qm, om, symbol, qty, sl, tp, direction)
    
    # Bind strategy to receive callbacks
    client.bind_strategy(strategy)
    
    try:
        strategy.run() # This blocks
    except KeyboardInterrupt:
        strategy.stop()
        print("Strategy stopped.")

@app.command()
def quote(codes: List[str], type: str = "future"):
    """
    Subscribe and print quotes for given codes.
    Type: 'future' or 'stock'
    """
    client = ShioajiClient(simulation=True)
    qm = QuoteManager(client.api)
    
    print(f"Subscribing to {codes}...")
    if type == "future":
        qm.subscribe_fop_tick(codes, recover=True)
    else:
        qm.subscribe_stk_tick(codes, recover=True)

    try:
        last_count = 0
        while True:
            if type == "future":
                df = qm.get_df_fop()
            else:
                df = qm.get_df_stk()
            
            if len(df) > last_count:
                print(df.slice(last_count))
                last_count = len(df)
            
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        client.api.logout()

@app.command()
def trade(strategy: str = "ma", symbol: str = "TMFR1"):
    """
    Run a trading strategy.
    """
    client = ShioajiClient(simulation=True)
    qm = QuoteManager(client.api)
    om = OrderManager(client.api)
    
    if strategy == "ma":
        strat = MACrossoverStrategy(qm, om)
        strat.run(symbol=symbol)
    else:
        print(f"Unknown strategy: {strategy}")

@app.command()
def test_order(type: str = "future"):
    """
    Place a test order (Simulation).
    Type: 'future' or 'stock'
    """
    client = ShioajiClient(simulation=True)
    om = OrderManager(client.api)
    
    if type == "future":
        print("Placing test Future order (TXFR1)...")
        # In simulation, we might need a valid code. 
        # Using TXFR1 as in original code.
        try:
            trade = om.place_futures_order(
                code="TXFR1",
                action=Action.Buy,
                price=20000, # Mock price, usually getting from contract.reference is better but fine for test
                quantity=1
            )
            print(f"Order Placed: {trade}")
        except Exception as e:
            print(f"Error: {e}")
            
    elif type == "stock":
        print("Placing test Stock order (2890)...")
        try:
            trade = om.place_stock_order(
                code="2890",
                action=Action.Buy,
                price=10.0,
                quantity=1
            )
            print(f"Order Placed: {trade}")
        except Exception as e:
            print(f"Error: {e}")

@app.command()
def order(
    code: str,
    action: str = typer.Option(..., help="Buy or Sell"),
    price: float = typer.Option(..., help="Order price"),
    qty: int = typer.Option(1, help="Quantity"),
    type: str = typer.Option("future", help="'future' or 'stock'"),
    sim: bool = typer.Option(True, help="Set --no-sim for real trading")
):
    """
    Place a real or simulated limit order.
    """
    client = ShioajiClient(simulation=sim)
    om = OrderManager(client.api)
    
    act_enum = Action.Buy if action.lower() == "buy" else Action.Sell
    msg_type = "SIMULATED" if sim else "REAL"
    print(f"Placing {msg_type} order: {act_enum.name} {qty} {code} @ {price}")
    
    try:
        if type.lower() == "future":
            from shioaji.constant import FuturesPriceType
            trade = om.place_futures_order(
                code=code, action=act_enum, price=price, quantity=qty, price_type=FuturesPriceType.LMT
            )
        else:
            from shioaji.constant import StockPriceType
            trade = om.place_stock_order(
                code=code, action=act_enum, price=price, quantity=qty, price_type=StockPriceType.LMT
            )
        print(f"Order Placed Successfully! ID: {trade.status.id}")
        print(f"Status: {trade.status.status.name}")
    except Exception as e:
        print(f"Failed to place order: {e}")

@app.command("list-orders")
def list_orders(sim: bool = typer.Option(True, help="Set --no-sim for real trading")):
    """
    List today's trades and orders.
    """
    client = ShioajiClient(simulation=sim)
    om = OrderManager(client.api)
    
    print(f"Fetching {'SIMULATED' if sim else 'REAL'} orders...")
    try:
        trades = om.list_trades()
        if not trades:
            print("No trades/orders found today.")
            return
            
        print(f"\n=== Active Trades/Orders ===")
        for t in trades:
            current_price = getattr(t.status, "modified_price", t.order.price)
            if current_price == 0:
                current_price = t.order.price
            print(f"ID: {t.status.id} | {t.contract.code} | {t.order.action.name} {t.order.quantity} @ {current_price} | Status: {t.status.status.name}")
    except Exception as e:
        print(f"Error fetching trades: {e}")

@app.command()
def update(
    order_id: str = typer.Argument(..., help="Order ID to update"),
    price: float = typer.Argument(..., help="New price"),
    sim: bool = typer.Option(True, help="Set --no-sim for real trading")
):
    """
    Update the price of an active order.
    """
    client = ShioajiClient(simulation=sim)
    om = OrderManager(client.api)
    
    print(f"Environment: {'SIMULATED' if sim else 'REAL'}")
    print(f"Updating Order ID: {order_id} to price: {price}...")
    
    try:
        om.update_order_price(order_id, price)
        print("Update request sent successfully.")
    except Exception as e:
        print(f"Failed to update order: {e}")

@app.command()
def bot(sim: bool = typer.Option(True, help="Set --no-sim for real trading")):
    """
    Start the Telegram Bot to listen for trading commands.
    """
    client = ShioajiClient(simulation=sim)
    om = OrderManager(client.api)
    
    from .core.telegram_bot import TelegramBotManager
    tg_bot = TelegramBotManager(order_manager=om, simulation=sim)
    
    try:
        tg_bot.run()
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    except Exception as e:
        print(f"Bot exited with error: {e}")

@app.command()
def cancel(
    order_id: str = typer.Option(None, "--id", help="Specific Order ID to cancel"),
    all: bool = typer.Option(False, "--all", help="Cancel ALL active orders"),
    sim: bool = typer.Option(True, help="Set --no-sim for real trading")
):
    """
    Cancel an order by ID or all active orders.
    """
    if not order_id and not all:
        print("Please specify an order ID (--id) or use --all to cancel all active orders.")
        return
        
    client = ShioajiClient(simulation=sim)
    om = OrderManager(client.api)
    
    print(f"Environment: {'SIMULATED' if sim else 'REAL'}")
    
    try:
        if all:
            print("Cancelling ALL active orders...")
            count = om.cancel_all_orders()
            print(f"Sent cancellation requests for {count} order(s).")
        else:
            print(f"Cancelling Order ID: {order_id}...")
            om.cancel_order(order_id)
            # update_status is called inside cancel_order
            print("Cancellation request sent.")
    except Exception as e:
        print(f"Failed to cancel order(s): {e}")

@app.command()
def version():
    import shioaji
    print(f"Shioaji Version: {shioaji.__version__}")

if __name__ == "__main__":
    app()
