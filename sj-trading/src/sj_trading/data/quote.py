import shioaji as sj
from typing import List, Set, Literal
import polars as pl
from shioaji.contracts import BaseContract
import datetime as dt


MarketType = Literal["stk", "fop"]


class QuoteManager:
    """Unified quote manager for both stock and futures/options tick data."""
    
    def __init__(self, api: sj.Shioaji):
        self.api = api
        self.api.quote.set_on_tick_stk_v1_callback(self._on_tick_handler)
        self.api.quote.set_on_tick_fop_v1_callback(self._on_tick_handler)
        
        # Unified tick storage
        self._ticks: dict[MarketType, list] = {"stk": [], "fop": []}
        self._subscribed: dict[MarketType, Set[str]] = {"stk": set(), "fop": set()}
        
        # DataFrame schema (shared)
        self._schema = [
            ("datetime", pl.Datetime),
            ("code", pl.Utf8),
            ("price", pl.Float64),
            ("volume", pl.Int64),
            ("tick_type", pl.Int8),
        ]
        self._df: dict[MarketType, pl.DataFrame] = {
            "stk": pl.DataFrame([], schema=self._schema),
            "fop": pl.DataFrame([], schema=self._schema),
        }
    
    # ─────────────────────────────────────────────────────────────
    # Callbacks (unified)
    # ─────────────────────────────────────────────────────────────
    
    def _on_tick_handler(self, _exchange: sj.Exchange, tick):
        """Unified tick handler for both stk and fop."""
        # Determine market type from tick class name
        market_type: MarketType = "stk" if "STK" in type(tick).__name__ else "fop"
        self._ticks[market_type].append(tick)
    
    # For backward compatibility
    def on_stk_v1_tick_handler(self, exchange: sj.Exchange, tick: sj.TickSTKv1):
        self._ticks["stk"].append(tick)
    
    def on_fop_v1_tick_handler(self, exchange: sj.Exchange, tick: sj.TickFOPv1):
        self._ticks["fop"].append(tick)
    
    # ─────────────────────────────────────────────────────────────
    # DataFrame getters (unified)
    # ─────────────────────────────────────────────────────────────
    
    def _get_df(self, market_type: MarketType) -> pl.DataFrame:
        """Get accumulated tick DataFrame for the specified market."""
        ticks = self._ticks[market_type]
        self._ticks[market_type] = []  # Clear processed ticks
        
        if ticks:
            df = pl.DataFrame([tick.to_dict() for tick in ticks]).select(
                pl.col("datetime", "code"),
                pl.col("close").cast(pl.Float64).alias("price"),
                pl.col("volume").cast(pl.Int64),
                pl.col("tick_type").cast(pl.Int8),
            )
            self._df[market_type] = self._df[market_type].vstack(df)
        
        return self._df[market_type]
    
    def get_df_stk(self) -> pl.DataFrame:
        """Get stock tick DataFrame."""
        return self._get_df("stk")
    
    def get_df_fop(self) -> pl.DataFrame:
        """Get futures/options tick DataFrame."""
        return self._get_df("fop")
    
    # ─────────────────────────────────────────────────────────────
    # K-bar aggregation
    # ─────────────────────────────────────────────────────────────
    
    def get_df_stk_kbar(self, unit: str = "1m", exprs: List[pl.Expr] = []) -> pl.DataFrame:
        """Aggregate stock ticks into K-bars."""
        df = self.get_df_stk()
        return self._aggregate_kbar(df, unit, exprs)
    
    def _aggregate_kbar(self, df: pl.DataFrame, unit: str, exprs: List[pl.Expr]) -> pl.DataFrame:
        """Aggregate tick data into OHLCV K-bars."""
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
    
    # ─────────────────────────────────────────────────────────────
    # Historical tick fetching
    # ─────────────────────────────────────────────────────────────
    
    def fetch_ticks(self, contract: BaseContract) -> pl.DataFrame:
        """Fetch historical ticks with automatic night session handling."""
        code = contract.target_code
        
        # Fetch main trading session
        ticks_main = self.api.ticks(contract)
        df_main = pl.DataFrame(ticks_main.dict())
        
        # Check for night session gap
        now = dt.datetime.now()
        df_night = pl.DataFrame()
        
        cutoff = now.replace(hour=15, minute=0, second=0, microsecond=0).timestamp() * 1e9
        needs_night = (
            now.hour >= 15 and 
            (df_main.is_empty() or df_main["ts"][-1] < cutoff)
        )
        
        if needs_night:
            print("偵測到夜盤時段，正在額外抓取今日TICK...")
            ticks_night = self.api.ticks(contract, date=now.strftime("%Y-%m-%d"))
            if ticks_night.ts:
                df_night = pl.DataFrame(ticks_night.dict())
        
        # Merge data
        if not df_night.is_empty():
            df = pl.concat([df_main, df_night]).unique(subset=["ts"], keep="first").sort("ts")
        else:
            df = df_main
        
        if df.is_empty():
            return pl.DataFrame()
        
        # Transform to standard format
        return df.select(
            pl.from_epoch("ts", time_unit="ns").dt.cast_time_unit("us").alias("datetime"),
            pl.lit(code).alias("code"),
            pl.col("close").alias("price"),
            pl.col("volume").cast(pl.Int64),
            pl.col("tick_type").cast(pl.Int8),
        )
    
    # ─────────────────────────────────────────────────────────────
    # Subscription (unified)
    # ─────────────────────────────────────────────────────────────
    
    def _get_contract(self, code: str, market_type: MarketType) -> BaseContract | None:
        """Get contract by code and market type."""
        if market_type == "stk":
            return self.api.Contracts.Stocks[code]
        return self.api.Contracts.Futures[code]
    
    def _subscribe(self, codes: List[str], market_type: MarketType, recover: bool = False):
        """Unified subscription logic."""
        for code in codes:
            contract = self._get_contract(code, market_type)
            if contract is None or code in self._subscribed[market_type]:
                continue
            
            if market_type == "fop":
                print(f"Contract: {contract}")
            
            self.api.quote.subscribe(contract, "tick")
            self._subscribed[market_type].add(code)
            
            if recover:
                self._recover_ticks(code, contract, market_type)
    
    def _recover_ticks(self, code: str, contract: BaseContract, market_type: MarketType):
        """Recover historical ticks and merge with live data."""
        df = self.fetch_ticks(contract)
        if df.is_empty():
            return
        
        # Filter out ticks that overlap with live data
        ticks = self._ticks[market_type]
        code_ticks = [t for t in ticks if t.code == code]
        
        if code_ticks:
            t_first = code_ticks[0].datetime
            df = df.filter(pl.col("datetime") < t_first)
        
        self._df[market_type] = self._df[market_type].vstack(df)
    
    def subscribe_stk_tick(self, codes: List[str], recover: bool = False):
        """Subscribe to stock tick data."""
        self._subscribe(codes, "stk", recover)
    
    def subscribe_fop_tick(self, codes: List[str], recover: bool = False):
        """Subscribe to futures/options tick data."""
        self._subscribe(codes, "fop", recover)
    
    # ─────────────────────────────────────────────────────────────
    # Unsubscription (unified)
    # ─────────────────────────────────────────────────────────────
    
    def _unsubscribe(self, codes: List[str], market_type: MarketType):
        """Unified unsubscription logic."""
        for code in codes:
            if code not in self._subscribed[market_type]:
                continue
            contract = self._get_contract(code, market_type)
            if contract:
                self.api.quote.unsubscribe(contract, "tick")
            self._subscribed[market_type].remove(code)
    
    def _unsubscribe_all(self, market_type: MarketType):
        """Unsubscribe all codes for a market type."""
        for code in list(self._subscribed[market_type]):
            contract = self._get_contract(code, market_type)
            if contract:
                self.api.quote.unsubscribe(contract, "tick")
        self._subscribed[market_type].clear()
    
    def unsubscribe_stk_tick(self, codes: List[str]):
        self._unsubscribe(codes, "stk")
    
    def unsubscribe_fop_tick(self, codes: List[str]):
        self._unsubscribe(codes, "fop")
    
    def unsubscribe_all_stk_tick(self):
        self._unsubscribe_all("stk")
    
    def unsubscribe_all_fop_tick(self):
        self._unsubscribe_all("fop")
