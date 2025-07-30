import shioaji as sj
from shioaji.constant import (
    Action,
    StockPriceType,
    OrderType,
    FuturesPriceType,
    FuturesOCType,
)
import os

import time
from sj_trading.quote import QuoteManager


def testing_stock_ordering():
    # 測試環境登入
    api = sj.Shioaji(simulation=True)
    accounts = api.login(
        api_key=os.environ["API_KEY"],
        secret_key=os.environ["SECRET_KEY"],
    )
    # 顯示所有可用的帳戶
    print(f"Available accounts: {accounts}")
    api.activate_ca(
        ca_path=os.environ["CA_CERT_PATH"],
        ca_passwd=os.environ["CA_PASSWORD"],
    )

    # 準備下單的 Contract
    # 使用 2890 永豐金為例
    contract = api.Contracts.Stocks["2890"]
    print(f"Contract: {contract}")

    # 建立委託下單的 Order
    order = sj.order.StockOrder(
        action=Action.Buy,  # 買進
        price=contract.reference,  # 以平盤價買進
        quantity=1,  # 下單數量
        price_type=StockPriceType.LMT,  # 限價單
        order_type=OrderType.ROD,  # 當日有效單
        account=api.stock_account,  # 使用預設的帳戶
    )
    print(f"Order: {order}")

    # 送出委託單
    trade = api.place_order(contract=contract, order=order)
    print(f"Trade: {trade}")

    # 更新狀態
    api.update_status()
    print(f"Status: {trade.status}")


def testing_futures_ordering():
    # 測試環境登入
    api = sj.Shioaji(simulation=True)
    accounts = api.login(
        api_key=os.environ["API_KEY"],
        secret_key=os.environ["SECRET_KEY"],
    )
    # 顯示所有可用的帳戶
    print(f"Available accounts: {accounts}")
    api.activate_ca(
        ca_path=os.environ["CA_CERT_PATH"],
        ca_passwd=os.environ["CA_PASSWORD"],
    )

    # 取得合約 使用台指期近月為例
    contract = api.Contracts.Futures["TXFR1"]
    print(f"Contract: {contract}")

    # 建立期貨委託下單的 Order
    order = sj.order.FuturesOrder(
        action=Action.Buy,  # 買進
        price=contract.reference,  # 以平盤價買進
        quantity=1,  # 下單數量
        price_type=FuturesPriceType.LMT,  # 限價單
        order_type=OrderType.ROD,  # 當日有效單
        octype=FuturesOCType.Auto,  # 自動選擇新平倉
        account=api.futopt_account,  # 使用預設的帳戶
    )
    print(f"Order: {order}")

    # 送出委託單
    trade = api.place_order(contract=contract, order=order)
    print(f"Trade: {trade}")

    # 更新狀態
    api.update_status()
    print(f"Status: {trade.status}")


def futures_quote():
    """
    持續接收期貨報價並顯示。
    - 訂閱微台近一 (TMFR1)
    - 首次印出回補的歷史資料
    - 進入主迴圈，每秒檢查並印出新的Tick資料
    - 使用 try...finally 來確保程式結束時能正確登出
    """
    api = sj.Shioaji()
    api.login(
        api_key=os.environ["API_KEY"],
        secret_key=os.environ["SECRET_KEY"],
    )

    quote_manager = QuoteManager(api)
    
    try:
        # 訂閱微台近一，並回補歷史資料
        quote_manager.subscribe_fop_tick(["TMFR1"], recover=True)
        
        # 處理並印出第一次回補的資料
        last_printed_rows = 0
        df_ticks = quote_manager.get_df_fop()
        if not df_ticks.is_empty():
            print(f"歷史資料回補完成，共 {len(df_ticks)} 筆 ticks:")
            print(df_ticks)
            last_printed_rows = len(df_ticks)
        
        print("\n>>> 開始接收即時報價 (按 Ctrl+C 結束) <<<\n")

        while True:
            # 獲取最新的 DataFrame
            df_ticks = quote_manager.get_df_fop()
            
            # 如果有新的資料進來，就印出新的部分
            if len(df_ticks) > last_printed_rows:
                new_ticks = df_ticks.slice(last_printed_rows)
                print(new_ticks)
                last_printed_rows = len(df_ticks)
            
            time.sleep(0.5) # 每0.5秒檢查一次

    except KeyboardInterrupt:
        print("\n程式被手動中斷。")
    finally:
        # 程式結束前，取消所有訂閱並登出
        print("正在取消報價訂閱並登出...")
        quote_manager.unsubscribe_all_fop_tick()
        api.logout()
        print("已成功登出。")


def automated_trading_loop():
    """
    一個自動化交易的範例主迴圈。
    - 持續接收期貨報價
    - 計算5筆tick的移動平均線 (MA)
    - 當價格由下往上突破MA時，下達買單
    - 使用 try...finally 來確保程式結束時能正確登出
    """
    api = sj.Shioaji(simulation=True)
    api.login(
        api_key=os.environ["API_KEY"],
        secret_key=os.environ["SECRET_KEY"],
    )
    api.activate_ca(
        ca_path=os.environ["CA_CERT_PATH"],
        ca_passwd=os.environ["CA_PASSWORD"],
    )

    quote_manager = QuoteManager(api)
    # 訂閱微台近一的即時報價，並回補當日歷史資料
    quote_manager.subscribe_fop_tick(["TMFR1"], recover=True)

    # 交易狀態旗標，確保只下單一次
    order_placed = False
    last_tick_count = 0  # 用於追蹤已處理的 tick 數量

    try:
        while not order_placed:
            # 1. 獲取最新的報價 DataFrame
            df_ticks = quote_manager.get_df_fop()

            # 只有在新報價進來時才處理和印出
            if len(df_ticks) > last_tick_count:
                last_tick_count = len(df_ticks)

                if len(df_ticks) < 5:
                    print(f"資料不足5筆，無法計算5MA。目前共 {len(df_ticks)} 筆。")
                else:
                    # 2. 定義並檢查交易條件
                    # 計算最近5筆tick的移動平均價
                    ma_5 = df_ticks["price"].tail(5).mean()
                    current_price = df_ticks["price"].tail(1).item()
                    previous_price = df_ticks["price"].tail(2).head(1).item()

                    print(
                        f"時間: {df_ticks['datetime'].tail(1).item()} | 最新價: {current_price:.2f} | 5MA: {ma_5:.2f} | 上一筆價: {previous_price:.2f}"
                    )

                    # 交易條件：價格從下方突破5期均線
                    if previous_price < ma_5 and current_price > ma_5:
                        print("\n>>> 觸發下單條件：價格突破5期均線！ <<<")

                        # 3. 執行下單
                        contract = api.Contracts.Futures["TMFR1"]
                        order = sj.order.FuturesOrder(
                            action=Action.Buy,
                            price=round(current_price, 2),  # 以當前價格下限價單
                            quantity=1,
                            price_type=FuturesPriceType.LMT,
                            order_type=OrderType.ROD,
                            octype=FuturesOCType.Auto,
                            account=api.futopt_account,
                        )

                        trade = api.place_order(contract=contract, order=order)
                        print(f"\n下單成功: {trade}")
                        order_placed = True  # 設定旗標，避免重複下單

            # 4. 短暫休眠，每0.5秒檢查一次
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n程式被手動中斷。")
    finally:
        # 5. 程式結束前，取消所有訂閱並登出
        print("正在取消報價訂閱並登出...")
        quote_manager.unsubscribe_all_fop_tick()
        api.logout()
        print("已成功登出。")

