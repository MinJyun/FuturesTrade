"""Tests for data.quote module."""
import pytest
from unittest.mock import Mock, MagicMock
import polars as pl


class TestQuoteManager:
    """Test QuoteManager class functionality."""
    
    @pytest.fixture
    def mock_api(self):
        """Create a mock Shioaji API."""
        api = MagicMock()
        api.quote = MagicMock()
        api.Contracts = MagicMock()
        # Use MagicMock for Stocks and Futures so __getitem__ can be mocked
        api.Contracts.Stocks = MagicMock()
        api.Contracts.Futures = MagicMock()
        return api
    
    @pytest.fixture
    def quote_manager(self, mock_api):
        """Create QuoteManager with mocked API."""
        from sj_trading.data.quote import QuoteManager
        return QuoteManager(mock_api)
    
    def test_init_sets_callbacks(self, mock_api, quote_manager):
        """Should set tick callbacks on initialization."""
        mock_api.quote.set_on_tick_stk_v1_callback.assert_called_once()
        mock_api.quote.set_on_tick_fop_v1_callback.assert_called_once()
    
    def test_init_empty_dataframes(self, quote_manager):
        """Should initialize with empty DataFrames."""
        assert quote_manager.get_df_stk().is_empty()
        assert quote_manager.get_df_fop().is_empty()
    
    def test_get_df_stk_returns_polars_dataframe(self, quote_manager):
        """Should return a Polars DataFrame."""
        df = quote_manager.get_df_stk()
        assert isinstance(df, pl.DataFrame)
    
    def test_get_df_fop_returns_polars_dataframe(self, quote_manager):
        """Should return a Polars DataFrame."""
        df = quote_manager.get_df_fop()
        assert isinstance(df, pl.DataFrame)
    
    def test_subscribe_stk_tick_adds_to_subscribed(self, mock_api, quote_manager):
        """Should track subscribed stock codes."""
        mock_contract = MagicMock()
        mock_api.Contracts.Stocks.__getitem__.return_value = mock_contract
        
        quote_manager.subscribe_stk_tick(["2330"])
        
        assert "2330" in quote_manager._subscribed["stk"]
        mock_api.quote.subscribe.assert_called_once_with(mock_contract, "tick")
    
    def test_subscribe_fop_tick_adds_to_subscribed(self, mock_api, quote_manager):
        """Should track subscribed futures codes."""
        mock_contract = MagicMock()
        mock_api.Contracts.Futures.__getitem__.return_value = mock_contract
        
        quote_manager.subscribe_fop_tick(["TXFR1"])
        
        assert "TXFR1" in quote_manager._subscribed["fop"]
    
    def test_unsubscribe_all_stk_clears_subscriptions(self, mock_api, quote_manager):
        """Should clear all stock subscriptions."""
        mock_contract = MagicMock()
        mock_api.Contracts.Stocks.__getitem__.return_value = mock_contract
        
        quote_manager.subscribe_stk_tick(["2330", "2317"])
        quote_manager.unsubscribe_all_stk_tick()
        
        assert len(quote_manager._subscribed["stk"]) == 0
    
    def test_unsubscribe_all_fop_clears_subscriptions(self, mock_api, quote_manager):
        """Should clear all fop subscriptions."""
        mock_contract = MagicMock()
        mock_api.Contracts.Futures.__getitem__.return_value = mock_contract
        
        quote_manager.subscribe_fop_tick(["TXFR1"])
        quote_manager.unsubscribe_all_fop_tick()
        
        assert len(quote_manager._subscribed["fop"]) == 0
    
    def test_on_tick_handler_appends_stk_tick(self, quote_manager):
        """Should append STK ticks to correct list."""
        mock_tick = MagicMock()
        mock_tick.__class__.__name__ = "TickSTKv1"
        
        quote_manager._on_tick_handler(None, mock_tick)
        
        assert mock_tick in quote_manager._ticks["stk"]
    
    def test_on_tick_handler_appends_fop_tick(self, quote_manager):
        """Should append FOP ticks to correct list."""
        mock_tick = MagicMock()
        mock_tick.__class__.__name__ = "TickFOPv1"
        
        quote_manager._on_tick_handler(None, mock_tick)
        
        assert mock_tick in quote_manager._ticks["fop"]
