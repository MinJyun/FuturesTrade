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
        authenticated_client.add_trading_record(record, "https://example.com", "Records")
        
        # Should write to row 3 (after 2 existing rows)
        mock_ws.update.assert_called_once()
        call_args = mock_ws.update.call_args
        assert "A3:G3" in call_args[0][0]
