"""Tests for utils.gsheet module."""
import pytest
from unittest.mock import Mock, MagicMock, patch
import pandas as pd


class TestGoogleSheetClient:
    """Test GoogleSheetClient class functionality."""
    
    @pytest.fixture
    def mock_gspread(self):
        """Mock gspread module."""
        with patch("sj_trading.utils.gsheet.gspread") as mock:
            mock.service_account.return_value = MagicMock()
            yield mock
    
    @pytest.fixture
    def mock_credentials_exist(self, tmp_path, monkeypatch):
        """Create a temp credential file."""
        cred_file = tmp_path / "service_account.json"
        cred_file.write_text("{}")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(cred_file))
        return cred_file
    
    def test_init_authenticates_with_valid_credentials(self, mock_gspread, mock_credentials_exist):
        """Should authenticate when credentials file exists."""
        from sj_trading.utils.gsheet import GoogleSheetClient
        
        client = GoogleSheetClient()
        
        assert client.gc is not None
        mock_gspread.service_account.assert_called_once()
    
    def test_init_handles_missing_credentials(self, mock_gspread, monkeypatch, tmp_path):
        """Should handle missing credentials gracefully."""
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "nonexistent.json"))
        
        from sj_trading.utils.gsheet import GoogleSheetClient
        
        client = GoogleSheetClient()
        
        assert client.gc is None
    
    def test_update_sheet_skips_without_client(self, mock_gspread, monkeypatch, tmp_path, capsys):
        """Should skip update when not authenticated."""
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "nonexistent.json"))
        
        from sj_trading.utils.gsheet import GoogleSheetClient
        
        client = GoogleSheetClient()
        df = pd.DataFrame({"col": [1, 2, 3]})
        
        client.update_sheet(df, "https://example.com", "Sheet1")
        
        captured = capsys.readouterr()
        assert "not authenticated" in captured.out


class TestAddTradingRecord:
    """Test add_trading_record functionality."""
    
    @pytest.fixture
    def authenticated_client(self):
        """Create an authenticated client with mocked gc."""
        with patch("sj_trading.utils.gsheet.gspread") as mock_gspread:
            with patch("sj_trading.utils.gsheet.Path") as mock_path:
                mock_path.return_value.exists.return_value = True
                mock_gspread.service_account.return_value = MagicMock()
                
                from sj_trading.utils.gsheet import GoogleSheetClient
                client = GoogleSheetClient()
                yield client
    
    def test_add_record_to_sheet(self, authenticated_client):
        """Should add record to worksheet."""
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = ["Header", "Row1"]  # 2 existing rows
        
        mock_sh = MagicMock()
        mock_sh.worksheet.return_value = mock_ws
        
        authenticated_client.gc.open_by_url.return_value = mock_sh
        
        record = ["2024/01/01", "2024/01/01", "TXFR1", 1, "多", 18000, 18100]
        with patch("sj_trading.utils.gsheet.fetch_initial_margin", return_value=701000):
            authenticated_client.add_trading_record(record, "https://example.com", "Records")
        
        # Should write A:G and L:O to row 3 (after 2 existing rows)
        assert mock_ws.update.call_count == 2
        (rng, rows), _ = mock_ws.update.call_args_list[0]
        assert rng == "A3:G3"
        assert rows[0][2] == "台指期貨"  # TXFR1 mapped to sheet product name
        (rng, rows), _ = mock_ws.update.call_args_list[1]
        assert rng == "L3:O3"
        assert rows[0] == [701000, "=H3*I3-2*(J3+K3)", "=M3/L3", "永豐"]

    def test_add_record_keeps_prefilled_margin_when_not_found(self, authenticated_client):
        """Should leave L untouched if TAIFEX margin is unavailable."""
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = ["Header"]
        authenticated_client.gc.open_by_url.return_value.worksheet.return_value = mock_ws

        record = ["2024/01/01", "2024/01/01", "TXO", 1, "多", 10, 20]
        with patch("sj_trading.utils.gsheet.fetch_initial_margin", return_value=None):
            authenticated_client.add_trading_record(record, "https://example.com", "Records")

        (rng, _), _ = mock_ws.update.call_args_list[1]
        assert rng == "M2:O2"


TAIFEX_SAMPLE = """
<tr><td>小型臺指</td><td align="center">129,750</td><td align="center">134,500</td><td align="center">175,250</td></tr>
<tr><td>客製化小型臺指期貨</td><td align="center">1</td><td align="center">2</td><td align="center">3</td></tr>
<tr>
  <td>微型臺指期貨</td>
  <td align="center">25,950</td>
  <td align="center">26,900</td>
  <td align="center">35,050</td>
</tr>
"""


class TestFetchInitialMargin:
    @pytest.fixture(autouse=True)
    def mock_page(self):
        with patch("sj_trading.utils.gsheet.requests.get") as mock_get:
            mock_get.return_value.text = TAIFEX_SAMPLE
            yield

    def test_parses_initial_margin(self):
        from sj_trading.utils.gsheet import fetch_initial_margin
        assert fetch_initial_margin("微型台指") == 35050
        assert fetch_initial_margin("小型台指") == 175250

    def test_unknown_product(self):
        from sj_trading.utils.gsheet import fetch_initial_margin
        assert fetch_initial_margin("台指買權") is None


class TestRecordKey:
    def test_sheet_formatted_row_matches_raw_record(self):
        from sj_trading.utils.gsheet import record_key
        raw = ["2026/10/19", "2026/10/19", "TMFJ6", 1, "多", 46901.0, 46738.0]
        sheet = ["2026/10/19", "2026/10/19", "微型台指", "1", "多", "46,901.00", "46,738.00"]
        assert record_key(raw) == record_key(sheet)

    def test_option_record_matches_sheet_row(self):
        from sj_trading.utils.gsheet import record_key
        raw = ["2026/10/27", "2026/10/27", "TXY48000J6", 1, "多", 14.0, 13.0, 36, 2]
        sheet = ["2026/10/27", "2026/10/27", "台指買權", "1", "多", "14.00", "13.00"]
        assert record_key(raw) == record_key(sheet)


class TestProductName:
    def test_futures_and_options(self):
        from sj_trading.utils.gsheet import product_name
        assert product_name("TMFK6") == "微型台指"
        assert product_name("TXFR1") == "台指期貨"
        assert product_name("TXY48000J6") == "台指買權"   # J = Oct call
        assert product_name("TXO23000L6") == "台指買權"   # L = Dec call
        assert product_name("TXO23000M6") == "台指賣權"   # M = Jan put
        assert product_name("TX148000V6") == "台指賣權"   # V = Oct put
        assert product_name("台指買權") == "台指買權"     # already a sheet name
        assert product_name("XYZ") == "XYZ"


class TestAddOptionRecord:
    def test_option_writes_point_value_and_per_side_costs(self):
        with patch("sj_trading.utils.gsheet.gspread") as mock_gspread, \
             patch("sj_trading.utils.gsheet.Path") as mock_path, \
             patch("sj_trading.utils.gsheet.fetch_initial_margin", return_value=None):
            mock_path.return_value.exists.return_value = True
            from sj_trading.utils.gsheet import GoogleSheetClient
            client = GoogleSheetClient()
            mock_ws = MagicMock()
            mock_ws.col_values.return_value = ["Header"]
            client.gc.open_by_url.return_value.worksheet.return_value = mock_ws

            record = ["2026/10/27", "2026/10/27", "TXY48000J6", 1, "多", 14.0, 13.0, 36, 2]
            client.add_trading_record(record, "https://example.com", "Records")

        calls = {c.args[0]: c.args[1] for c in mock_ws.update.call_args_list}
        assert calls["A2:G2"][0] == ["2026/10/27", "2026/10/27", "台指買權", 1, "多", 14.0, 13.0]
        assert calls["I2:K2"] == [[50, 18.0, "=(ROUND(F2*I2*0.001,0)+ROUND(G2*I2*0.001,0))/2"]]
        assert calls["L2:O2"] == [["=F2*I2", "=H2*I2-2*(J2+K2)", "=M2/L2", "永豐"]]
