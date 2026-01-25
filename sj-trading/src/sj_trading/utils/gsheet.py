import gspread
import pandas as pd
import os
from pathlib import Path
from shioaji import Shioaji

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
            print(f"❌ specific Error updating Google Sheet: {e}")

    def add_trading_record(self, record: list, url: str, worksheet_name: str):
        """
        Add a trading record to the sheet.
        Finds the first empty row in Column A (to preserve formulas in later columns)
        and writes data to A:G.
        """
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
            print("Trading record logged successfully!")
            
        except Exception as e:
            print(f"❌ Error logging trading record: {e}")
