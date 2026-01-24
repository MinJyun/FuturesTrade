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
def version():
    import shioaji
    print(f"Shioaji Version: {shioaji.__version__}")

if __name__ == "__main__":
    app()
