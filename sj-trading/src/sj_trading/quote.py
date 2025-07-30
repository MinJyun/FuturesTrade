import shioaji as sj
from typing import List, Set
import polars as pl
# import polars_talib as plta
from shioaji.contracts import BaseContract
import datetime as dt

class QuoteManager:
    def __init__(self, api: sj.Shioaji):
        self.api = api
        self.api.quote.set_on_tick_stk_v1_callback(self.on_stk_v1_tick_handler)
        self.api.quote.set_on_tick_fop_v1_callback(self.on_fop_v1_tick_handler)
        self.ticks_stk_v1: List[sj.TickSTKv1] = []
        self.ticks_fop_v1: List[sj.TickFOPv1] = []
        self.subscribed_stk_tick: Set[str] = set()
        self.subscribed_fop_tick: Set[str] = set()
        self.df_stk: pl.DataFrame = pl.DataFrame(
            [],
            schema=[
                ("datetime", pl.Datetime),
                ("code", pl.Utf8),
                ("price", pl.Float64),
                ("volume", pl.Int64),
                ("tick_type", pl.Int8),
            ],
        )
        self.df_fop: pl.DataFrame = pl.DataFrame(
            [],
            schema=[
                ("datetime", pl.Datetime),
                ("code", pl.Utf8),
                ("price", pl.Float64),
                ("volume", pl.Int64),
                ("tick_type", pl.Int8),
            ],
        )

    def on_stk_v1_tick_handler(self, _exchange: sj.Exchange, tick: sj.TickSTKv1):
        self.ticks_stk_v1.append(tick)

    def on_fop_v1_tick_handler(self, _exchange: sj.Exchange, tick: sj.TickFOPv1):
        self.ticks_fop_v1.append(tick)
    
    def fetch_ticks(self, contract: BaseContract) -> pl.DataFrame:
        """
        抓取歷史Ticks，並智能處理交易日與夜盤的資料缺口問題。
        1. 抓取最近一個完整交易日的TICK (api.ticks預設行為)
        2. 判斷當前時間是否為夜盤時段 (15:00後)
        3. 如果是夜盤，則額外抓取今天的TICK資料
        4. 合併兩份資料，確保資料連續性
        """
        code = contract.target_code
        
        # 1. 抓取最近一個完整交易日的資料
        ticks_main = self.api.ticks(contract)
        df_main = pl.DataFrame(ticks_main.dict())

        # 2. 判斷是否需要補抓夜盤資料
        now = dt.datetime.now()
        df_night = pl.DataFrame() # 預設為空的DataFrame

        # 如果當前時間是下午3點後，且主要資料的最後一筆是在下午3點前，代表有夜盤缺口
        if now.hour >= 15 and (df_main.is_empty() or df_main["ts"][-1] < now.replace(hour=15, minute=0, second=0, microsecond=0).timestamp() * 1e9):
            print("偵測到夜盤時段，正在額外抓取今日TICK...")
            ticks_night = self.api.ticks(contract, date=now.strftime("%Y-%m-%d"))
            if ticks_night.ts:
                df_night = pl.DataFrame(ticks_night.dict())

        # 3. 合併資料
        if not df_night.is_empty():
            df = pl.concat([df_main, df_night]).unique(subset=["ts"], keep="first").sort("ts")
        else:
            df = df_main

        if df.is_empty():
            return pl.DataFrame()

        # 4. 整理成標準格式
        df = df.select(
            pl.from_epoch("ts", time_unit="ns").dt.cast_time_unit("us").alias("datetime"),
            pl.lit(code).alias("code"),
            pl.col("close").alias("price"),
            pl.col("volume").cast(pl.Int64),
            pl.col("tick_type").cast(pl.Int8),
        )
        return df
        
    def get_df_stk(self) -> pl.DataFrame:
        poped_ticks, self.ticks_stk_v1 = self.ticks_stk_v1, []
        if poped_ticks:
            df = pl.DataFrame([tick.to_dict() for tick in poped_ticks]).select(
                pl.col("datetime", "code"),
                pl.col("close").cast(pl.Float64).alias("price"),
                pl.col("volume").cast(pl.Int64),
                pl.col("tick_type").cast(pl.Int8),
            )
            self.df_stk = self.df_stk.vstack(df)
        return self.df_stk

    def get_df_fop(self) -> pl.DataFrame:
        poped_ticks, self.ticks_fop_v1 = self.ticks_fop_v1, []
        if poped_ticks:
            df = pl.DataFrame([tick.to_dict() for tick in poped_ticks]).select(
                pl.col("datetime", "code"),
                pl.col("close").cast(pl.Float64).alias("price"),
                pl.col("volume").cast(pl.Int64),
                pl.col("tick_type").cast(pl.Int8),
            )
            self.df_fop = self.df_fop.vstack(df)
        return self.df_fop

    def get_df_stk_kbar(
        self, unit: str = "1m", exprs: List[pl.Expr] = []
    ) -> pl.DataFrame:
        df = self.get_df_stk()
        df = df.group_by(
            pl.col("datetime").dt.truncate(unit),
            pl.col("code"),
            maintain_order=True,
        ).agg(
            pl.col("price").first().alias("open"),
            pl.col("price").max().alias("high"),
            pl.col("price").min().alias("low"),
            pl.col("price").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
        )
        if exprs:
            df = df.with_columns(exprs)
        return df

    def subscribe_stk_tick(self, codes: List[str], recover: bool = False):
        for code in codes:
            contract = self.api.Contracts.Stocks[code]
            if contract is not None and code not in self.subscribed_stk_tick:
                self.api.quote.subscribe(contract, "tick")
                self.subscribed_stk_tick.add(code)
                if recover:
                    df = self.fetch_ticks(contract)
                    if not df.is_empty():
                        code_ticks = [t for t in self.ticks_stk_v1 if t.code == code]
                        if code_ticks:
                            t_first = code_ticks[0].datetime
                            df = df.filter(pl.col("datetime") < t_first)
                            self.df_stk = self.df_stk.vstack(df)
                        else:
                            self.df_stk = self.df_stk.vstack(df)


    def subscribe_fop_tick(self, codes: List[str], recover: bool = False):
        for code in codes:
            contract = self.api.Contracts.Futures[code]
            print(f"Contract: {contract}")
            if contract is not None and code not in self.subscribed_fop_tick:
                self.api.quote.subscribe(contract, "tick")
                self.subscribed_fop_tick.add(code)
                if recover:
                    df = self.fetch_ticks(contract)
                    if not df.is_empty():
                        code_ticks = [t for t in self.ticks_fop_v1 if t.code == code]
                        if code_ticks:
                            t_first = code_ticks[0].datetime
                            df = df.filter(pl.col("datetime") < t_first)
                            self.df_fop = self.df_fop.vstack(df)
                        else:
                            self.df_fop = self.df_fop.vstack(df)


    def unsubscribe_stk_tick(self, codes: List[str]):
        for code in codes:
            contract = self.api.Contracts.Stocks[code]
            if contract is not None and code in self.subscribed_stk_tick:
                self.api.quote.unsubscribe(contract, "tick")
                self.subscribed_stk_tick.remove(code)

    def unsubscribe_fop_tick(self, codes: List[str]):
        for code in codes:
            contract = self.api.Contracts.Futures[code]
            if contract is not None and code in self.subscribed_fop_tick:
                self.api.quote.unsubscribe(contract, "tick")
                self.subscribed_fop_tick.remove(code)

    def unsubscribe_all_stk_tick(self):
        for code in self.subscribed_stk_tick:
            contract = self.api.Contracts.Stocks[code]
            if contract is not None:
                self.api.quote.unsubscribe(contract, "tick")
        self.subscribed_stk_tick.clear()

    def unsubscribe_all_fop_tick(self):
        for code in self.subscribed_fop_tick:
            contract = self.api.Contracts.Futures[code]
            if contract is not None:
                self.api.quote.unsubscribe(contract, "tick")
        self.subscribed_fop_tick.clear()