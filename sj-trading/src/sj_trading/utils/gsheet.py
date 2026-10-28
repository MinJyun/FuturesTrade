import gspread
import pandas as pd
import os
import re
import requests
from pathlib import Path
from typing import Optional

# Contract code prefix -> product name used by the record sheet (column J fee formula matches on these)
PRODUCT_NAMES = {
    "TMF": "微型台指",
    "MXF": "小型台指",
    "TXF": "台指期貨",
}
BROKER = "永豐"

# Index option code: product(TX?) + strike + month letter + year digit.
# Month letter A-L = call (Jan-Dec), M-X = put (Jan-Dec), per TAIFEX coding.
OPTION_CODE = re.compile(r"^TX.\d+([A-X])\d$")
OPTION_POINT_VALUE = 50

# Sheet product name -> row name in TAIFEX margin table
TAIFEX_MARGIN_URL = "https://www.taifex.com.tw/cht/5/indexMarging"
TAIFEX_NAMES = {
    "微型台指": "微型臺指期貨",
    "小型台指": "小型臺指",
    "台指期貨": "臺股期貨",
}


class GoogleSheetClient:
    def __init__(self):
        self.gc = None
        self._authenticate()

    def _authenticate(self):
        # gspread looks for GOOGLE_APPLICATION_CREDENTIALS automatically
        # or we can manually specify
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
        if not Path(cred_path).exists():
             print(f"Warning: Credential file {cred_path} not found.")
             return

        try:
            self.gc = gspread.service_account(filename=cred_path)
            print("Google Sheet Service Account Authenticated.")
        except Exception as e:
            print(f"Failed to authenticate Google Sheet: {e}")

    def update_sheet(self, df: pd.DataFrame, url: str, worksheet_name: str):
        if not self.gc:
            print("Google Sheet Client not authenticated. Skipping update.")
            return

        try:
            sh = self.gc.open_by_url(url)
            
            # Check if worksheet exists
            try:
                ws = sh.worksheet(worksheet_name)
            except gspread.WorksheetNotFound:
                print(f"Worksheet '{worksheet_name}' not found. Creating it.")
                ws = sh.add_worksheet(title=worksheet_name, rows=len(df)+100, cols=len(df.columns))

            print(f"Updating worksheet: {worksheet_name}...")
            
            # Clear existing content
            ws.clear()
            
            # Prepare data: Header + Rows
            # Replace NaN with empty string for JSON compatibility
            df_filled = df.fillna("")
            data = [df_filled.columns.values.tolist()] + df_filled.values.tolist()
            
            # Update
            ws.update(data)
            print("Google Sheet Updated Successfully!")
            
        except gspread.exceptions.APIError as e:
            error_details = e.response.json().get('error', {})
            code = error_details.get('code')
            message = error_details.get('message')
            status = error_details.get('status')
            
            print(f"❌ Google Sheet API Error!")
            print(f"   Status Code: {code} ({status})")
            print(f"   Message: {message}")
            
            if code == 429:
                 print("   ⚠️ Quota Exceeded. You might be sending requests too fast.")
            elif code == 403:
                 print("   ⚠️ Permission Denied. Check if the service account has edit access.")
                 
        except Exception as e:
            print(f"❌ Unexpected error updating Google Sheet: {e}")

    def add_trading_record(self, record: list, url: str, worksheet_name: str):
        """
        Add a trading record to the sheet.
        Finds the first empty row in Column A (to preserve formulas in later columns)
        and writes data to A:G, plus L:O (current TAIFEX 原始保證金, 獲利, 獲利率 formulas and 期貨商).
        H:K are pre-filled formulas in the sheet and are left untouched.
        L is also left as pre-filled if the margin can't be fetched.
        Options: pre-filled I:K are futures values, so I:K are written as point value,
        per-side fee from the optional round-trip costs (record[7:9]) and a tax formula,
        and L is the premium paid.
        """
        costs = record[7:9]
        record = to_sheet_record(record)
        if not self.gc:
            return

        try:
            sh = self.gc.open_by_url(url)
            try:
                ws = sh.worksheet(worksheet_name)
            except gspread.WorksheetNotFound:
                ws = sh.add_worksheet(title=worksheet_name, rows=100, cols=20)

            # Logic: Find first empty row in Col A
            col_a_values = ws.col_values(1) # List of values in Col A
            next_row = len(col_a_values) + 1
            
            # Record length check (should be 7)
            # data range: A{row}:G{row}
            # G is 7th letter
            end_col_letter = chr(ord('A') + len(record) - 1)
            range_name = f"A{next_row}:{end_col_letter}{next_row}"
            
            print(f"Logging record to {range_name}...")
            ws.update(range_name, [record], value_input_option='USER_ENTERED')
            r = next_row
            if is_option(record[2]) and len(costs) == 2:
                fee, _ = costs
                # Option tax is 0.1% of premium per side; M doubles K, so K is the per-side average
                tax = f"=(ROUND(F{r}*I{r}*0.001,0)+ROUND(G{r}*I{r}*0.001,0))/2"
                ws.update(f"I{r}:K{r}", [[OPTION_POINT_VALUE, fee / 2, tax]], value_input_option='USER_ENTERED')
            tail = [f"=H{r}*I{r}-2*(J{r}+K{r})", f"=M{r}/L{r}", BROKER]
            if is_option(record[2]):
                # Option buyers pay premium instead of margin: 買點數 × 點值
                margin = f"=F{r}*I{r}"
            else:
                margin = fetch_initial_margin(record[2])
            if margin is not None:
                ws.update(f"L{r}:O{r}", [[margin] + tail], value_input_option='USER_ENTERED')
            else:
                print(f"⚠️ Margin for {record[2]} not found on TAIFEX, keeping pre-filled L{r}.")
                ws.update(f"M{r}:O{r}", [tail], value_input_option='USER_ENTERED')
            print("Trading record logged successfully!")

        except Exception as e:
            print(f"❌ Error logging trading record: {e}")

    def get_record_keys(self, url: str, worksheet_name: str) -> set:
        """Keys (A:G) of records already in the sheet, for duplicate checks."""
        if not self.gc:
            return set()
        ws = self.gc.open_by_url(url).worksheet(worksheet_name)
        return {record_key(row[:7]) for row in ws.get("A2:G") if len(row) >= 7}


def product_name(code: str) -> str:
    code = str(code)
    if code[:3] in PRODUCT_NAMES:
        return PRODUCT_NAMES[code[:3]]
    m = OPTION_CODE.match(code)
    if m:
        return "台指買權" if m.group(1) <= "L" else "台指賣權"
    return code


def is_option(product: str) -> bool:
    return product in ("台指買權", "台指賣權")


def to_sheet_record(record: list) -> list:
    """A:G columns only, with product code mapped to the sheet's product name."""
    record = list(record[:7])
    record[2] = product_name(record[2])
    return record


def record_key(record: list) -> tuple:
    """Normalize a record so sheet-formatted values ('46,901.00') match raw ones (46901.0)."""
    def num(v):
        try:
            return float(str(v).replace(",", ""))
        except ValueError:
            return str(v)
    close_date, entry_date, product, qty, direction, buy, sell = to_sheet_record(record)[:7]
    return (str(close_date), str(entry_date), str(product), num(qty), str(direction), num(buy), num(sell))


def fetch_initial_margin(product: str) -> Optional[int]:
    """Current 原始保證金 per contract from TAIFEX's index futures margin table."""
    name = TAIFEX_NAMES.get(product)
    if not name:
        return None
    try:
        page = requests.get(TAIFEX_MARGIN_URL, timeout=20).text
    except requests.RequestException as e:
        print(f"Failed to fetch TAIFEX margin: {e}")
        return None
    # Row: <td>name</td> 結算 維持 原始
    cell = r'\s*<td[^>]*>([\d,]+)</td>'
    m = re.search(rf"<td>{re.escape(name)}</td>{cell}{cell}{cell}", page)
    return int(m.group(3).replace(",", "")) if m else None
