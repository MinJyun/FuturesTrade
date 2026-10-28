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
    file_path: str = typer.Option(None, help="Custom file path"),
    download: bool = typer.Option(False, help="Download the latest stock/ETF files from TWSE first")
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
             if download:
                 im.download_stock_data()
             im.reload_stock_data(file_path)
             print("Stock info reloaded.")

    except Exception as e:
        print(f"Error reloading data: {e}")
        raise typer.Exit(1)

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
def quote(
    codes: List[str],
    type: str = "future",
    sim: bool = typer.Option(True, help="Set --no-sim for real trading"),
    chart: str = typer.Option("table", help="Display mode: 'table', 'line', or 'kbar'"),
):
    """
    Subscribe and print quotes for given codes.
    Type: 'future' or 'stock'. Chart: 'table' (default), 'line', or 'kbar'.
    """
    import polars as pl
    from datetime import datetime, timedelta

    client = ShioajiClient(simulation=sim)
    qm = QuoteManager(client.api)

    print(f"Subscribing to {codes}...")
    if type == "future":
        qm.subscribe_fop_tick(codes, recover=True)
    else:
        qm.subscribe_stk_tick(codes, recover=True)

    def _filter_recent(df: pl.DataFrame, minutes: int = 30) -> pl.DataFrame:
        """Only keep ticks from the last N minutes to avoid recover data gap."""
        if df.is_empty():
            return df
        cutoff = df["datetime"].max() - timedelta(minutes=minutes)
        return df.filter(pl.col("datetime") >= cutoff)

    try:
        last_count = 0
        while True:
            df = qm.get_df_fop() if type == "future" else qm.get_df_stk()

            if chart == "table":
                if len(df) > last_count:
                    print(df.slice(last_count))
                    last_count = len(df)

            elif chart == "line":
                import plotext as plt
                if df.is_empty():
                    time.sleep(1)
                    continue
                plt.clf()
                plt.theme("dark")
                actual_codes = df["code"].unique().to_list()
                for code in actual_codes:
                    code_df = _filter_recent(df.filter(pl.col("code") == code)).tail(200)
                    if not code_df.is_empty():
                        plt.plot(code_df["price"].to_list(), label=code)
                plt.title("Live Price")
                plt.xlabel("Ticks")
                plt.ylabel("Price")
                print("\033[H", end="")
                plt.show()
                # Clear any leftover lines from previous taller frame
                print("\033[J", end="")

            elif chart == "kbar":
                import plotext as plt
                if df.is_empty():
                    time.sleep(1)
                    continue
                plt.clf()
                plt.theme("dark")
                plt.date_form("H:M")
                actual_codes = df["code"].unique().to_list()
                for code in actual_codes:
                    code_df = _filter_recent(df.filter(pl.col("code") == code), minutes=60)
                    if not code_df.is_empty():
                        kbar = qm._aggregate_kbar(code_df, "1m", []).sort("datetime")
                        if not kbar.is_empty():
                            kbar = kbar.tail(60)
                            dates = kbar["datetime"].dt.strftime("%H:%M").to_list()
                            ohlc = {
                                "Open": kbar["open"].to_list(),
                                "High": kbar["high"].to_list(),
                                "Low": kbar["low"].to_list(),
                                "Close": kbar["close"].to_list(),
                            }
                            plt.candlestick(dates, ohlc)
                plt.title("1m K-Bar")
                print("\033[H", end="")
                plt.show()
                print("\033[J", end="")

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

@app.command("record-trades")
def record_trades(
    start: str = typer.Argument(None, help="Start date YYYY-MM-DD (default: 6 days before end)"),
    end: str = typer.Argument(None, help="End date YYYY-MM-DD (default: same as start, or today if start is omitted)"),
    write: bool = typer.Option(False, "--write", help="Append to Google Sheet (default: preview only)"),
    sim: bool = typer.Option(True, help="Set --no-sim for real trading")
):
    """
    Record closed futures trades (incl. manual ones) to the trade record sheet.
    Dates are trade dates: night session trades belong to the next trading day
    (Friday night -> Monday). With no dates, covers the last 7 days up to today,
    so a weekly run on Monday after the day session covers Tue..Mon without gaps.
    Rows already in the sheet are skipped.
    """
    import os
    from datetime import date, timedelta
    from .utils.gsheet import GoogleSheetClient, record_key, to_sheet_record

    if start is None:
        end_d = date.fromisoformat(end) if end else date.today()
        start, end = (end_d - timedelta(days=6)).isoformat(), end_d.isoformat()
    end = end or start

    url = os.getenv("GOOGLE_SHEET_URL")
    tab = os.getenv("GOOGLE_SHEET_TAB_RECORDS")
    if not url or not tab:
        print("GOOGLE_SHEET_URL / GOOGLE_SHEET_TAB_RECORDS not set.")
        raise typer.Exit(1)

    client = ShioajiClient(simulation=sim)
    om = OrderManager(client.api)

    print(f"Closed futures trades {start} ~ {end}")
    records = om.list_futures_closed_records(start, end)
    if not records:
        print("No closed futures trades found.")
        return

    gs = GoogleSheetClient()
    existing = gs.get_record_keys(url, tab)
    new_records = []
    print("平倉日 | 下單日 | 產品 | 口數 | 方向 | 買點數 | 賣點數")
    for r in records:
        dup = record_key(r) in existing
        print(" | ".join(str(v) for v in to_sheet_record(r)) + ("  (already in sheet, skip)" if dup else ""))
        if not dup:
            new_records.append(r)

    if not write:
        print(f"\nPreview only ({len(new_records)} new rows). Add --write to append to Google Sheet.")
        return

    for r in new_records:
        gs.add_trading_record(r, url, tab)
    print(f"Wrote {len(new_records)} new rows.")

@app.command()
def version():
    import shioaji
    print(f"Shioaji Version: {shioaji.__version__}")

if __name__ == "__main__":
    app()
