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
            
        except Exception as e:
            print(f"Error updating Google Sheet: {e}")
