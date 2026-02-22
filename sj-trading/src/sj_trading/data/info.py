import pandas as pd
import polars as pl
from pathlib import Path
from typing import Optional, Dict

class InfoManager:
    DATA_PATH = Path("file/2_stockinfo.ods")
    CACHE_PATH = Path("file/contract_info.parquet")
    
    STOCK_DATA_PATH = Path("file/C_public.html")  # TWSE listed stocks
    OTC_STOCK_DATA_PATH = Path("file/C_public_4.html")  # OTC stocks
    STOCK_CACHE_PATH = Path("file/stock_info.parquet")

    def __init__(self):
        pass
    
    def reload_data(self, file_path: Optional[str] = None) -> pl.DataFrame:
        """Reload Futures/Options Contracts (ODS)"""
        path = file_path if file_path else self.DATA_PATH
        if not Path(path).exists():
            raise FileNotFoundError(f"File not found: {path}")

        print(f"Reading ODS file: {path}...")
        
        # Using header=1 because the first row seems to be a title
        df_pd = pd.read_excel(path, engine="odf", header=1)
        
        # Clean up column names (strip whitespace)
        df_pd.columns = df_pd.columns.str.strip()
        
        # Deduplicate column names manualy
        cols = pd.Series(df_pd.columns)
        for dup in cols[cols.duplicated()].unique(): 
            cols[cols[cols == dup].index.values.tolist()] = [dup + '.' + str(i) if i != 0 else dup for i in range(sum(cols == dup))]
        df_pd.columns = cols
        
        print("Pandas DF Info (Futures):")
        print(df_pd.info())

        # Logic to determine type: "標準型證券股數/受益權單位"
        unit_col = "標準型證券股數/受益權單位"
        if unit_col in df_pd.columns:
            def get_type(val):
                try:
                    v = float(val)
                    if v == 2000:
                        return "股票期貨"
                    elif v == 100:
                        return "微型股票期貨"
                    elif v == 10: 
                        return "小型股票期貨" 
                    else:
                        return "其他"
                except (ValueError, TypeError):
                    return "未知"
            
            df_pd["類型"] = df_pd[unit_col].apply(get_type)

        df_pd = df_pd.astype(str)
        df = pl.from_pandas(df_pd)
        
        # Save to parquet
        self.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(self.CACHE_PATH)
        print(f"Futures data saved to {self.CACHE_PATH}")
        return df

    def _parse_stock_html(self, path: Path) -> Optional[pd.DataFrame]:
        """Parse a single stock HTML file and return a pandas DataFrame.
        
        Returns None if the file doesn't exist.
        """
        if not path.exists():
            print(f"File not found, skipping: {path}")
            return None
            
        print(f"Reading HTML file: {path}...")
        
        # C_public.html and C_public_4.html usually use Big5 or CP950 encoding.
        try:
            dfs = pd.read_html(str(path), encoding='cp950', header=0)
        except (UnicodeDecodeError, LookupError):
            # Fallback to big5 or utf-8 if needed
            dfs = pd.read_html(str(path), encoding='big5', header=0)
            
        if not dfs:
            print(f"No tables found in {path}")
            return None
            
        return dfs[0]

    def reload_stock_data(self, file_path: Optional[str] = None) -> pl.DataFrame:
        """Reload Stock/ETF info from HTML files.
        
        Parses both TWSE listed stocks (C_public.html) and OTC stocks (C_public_4.html),
        combines them, filters out warrants, and syncs to Google Sheet if configured.
        
        Args:
            file_path: Optional path to override the default TWSE file. If provided,
                       only this file will be parsed (OTC file will be skipped).
        """
        dfs_to_combine = []
        
        if file_path:
            # Custom file path provided, parse only that file
            df_pd = self._parse_stock_html(Path(file_path))
            if df_pd is not None:
                dfs_to_combine.append(df_pd)
        else:
            # Parse both TWSE and OTC files
            for stock_path in [self.STOCK_DATA_PATH, self.OTC_STOCK_DATA_PATH]:
                df_pd = self._parse_stock_html(stock_path)
                if df_pd is not None:
                    dfs_to_combine.append(df_pd)
        
        if not dfs_to_combine:
            raise ValueError("No stock data files found or parsed successfully.")
        
        # Combine all dataframes
        df_pd = pd.concat(dfs_to_combine, ignore_index=True)
        print(f"Combined {len(dfs_to_combine)} file(s), total rows: {len(df_pd)}")
        
        print("Pandas DF Info (Stock):")
        print(df_pd.info())
        
        target_col = "有價證券代號及名稱"
        if target_col in df_pd.columns:
            # Split Code and Name using regex or split
            # Format usually "1101 台泥" or "0050 元大台灣50"
            # Splitting by first whitespace (unicode space \u3000 or normal space)
            # Standardizing spaces first
            df_pd[target_col] = df_pd[target_col].astype(str).str.replace('　', ' ', regex=False)
            
            split_data = df_pd[target_col].str.split(n=1, expand=True)
            if split_data.shape[1] == 2:
                df_pd["證券代號"] = split_data[0]
                df_pd["股票名稱"] = split_data[1]
            else:
                # Handle edge case where split failed
                df_pd["證券代號"] = df_pd[target_col]
                df_pd["股票名稱"] = ""

        # Filter out Warrants using CFICode
        # Retain only Stocks (E...) and ETFs (C...)
        # Warrants usually start with R (RW...)
        if "CFICode" in df_pd.columns:
            df_pd = df_pd[df_pd["CFICode"].astype(str).str.startswith(('E', 'C', 'L'), na=False)] # L for ETN? Keeping E/C mainly. 
            # User asked for Stock and ETF. standard stocks are E, ETFs are C.
        
        # Select and reorder columns
        # Desired: 有價證券代號及名稱, 證券代號, 股票名稱, 上市日, 市場別, 產業別
        selected_cols = ["有價證券代號及名稱", "證券代號", "股票名稱", "上市日", "市場別", "產業別"]
        
        # Filter only existing columns just in case
        final_cols = [c for c in selected_cols if c in df_pd.columns]
        df_pd = df_pd[final_cols]

        # Ensure string type
        df_pd = df_pd.astype(str)
        df = pl.from_pandas(df_pd)
        
        self.STOCK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(self.STOCK_CACHE_PATH)
        print(f"Stock data saved to {self.STOCK_CACHE_PATH}")
        
        # Update Google Sheet if configured
        import os
        from ..utils.gsheet import GoogleSheetClient
        
        sheet_url = os.getenv("GOOGLE_SHEET_URL")
        sheet_tab = os.getenv("GOOGLE_SHEET_TAB")
        
        if sheet_url and sheet_tab:
            print("Syncing to Google Sheet...")
            gs = GoogleSheetClient()
            gs.update_sheet(df.to_pandas(), sheet_url, sheet_tab)
            
        return df

    def get_info(self) -> pl.DataFrame:
        if not self.CACHE_PATH.exists():
            print("Futures cache not found, reloading...")
            return self.reload_data()
        return pl.read_parquet(self.CACHE_PATH)

    def get_stock_info(self) -> pl.DataFrame:
        if not self.STOCK_CACHE_PATH.exists():
            print("Stock cache not found, reloading...")
            return self.reload_stock_data()
        return pl.read_parquet(self.STOCK_CACHE_PATH)

    def search(self, query: str) -> Dict[str, pl.DataFrame]:
        results = {}
        
        # 1. Search Futures
        df_futures = self.get_info()
        search_cols_f = [c for c in df_futures.columns if "代號" in c or "簡稱" in c or "證券" in c]
        if search_cols_f:
            filter_expr = pl.lit(False)
            for col in search_cols_f:
                 filter_expr = filter_expr | pl.col(col).cast(pl.Utf8).str.to_uppercase().str.contains(query.upper())
            results["Futures"] = df_futures.filter(filter_expr)
            
        # 2. Search Stocks
        df_stocks = self.get_stock_info()
        search_cols_s = ["有價證券代號及名稱", "證券代號", "股票名稱"] # Focusing on these
        # Filter existing columns only
        search_cols_s = [c for c in search_cols_s if c in df_stocks.columns]
        
        if search_cols_s:
            filter_expr = pl.lit(False)
            for col in search_cols_s:
                 filter_expr = filter_expr | pl.col(col).cast(pl.Utf8).str.to_uppercase().str.contains(query.upper())
            results["Stocks"] = df_stocks.filter(filter_expr)
            
        return results
