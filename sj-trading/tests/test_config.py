"""Tests for core.config module."""
import pytest
import os


class TestConfig:
    """Test Config class functionality."""
    
    def test_validate_with_api_keys(self, monkeypatch):
        """Should pass validation when API_KEY and SECRET_KEY are set."""
        monkeypatch.setenv("API_KEY", "test_api_key")
        monkeypatch.setenv("SECRET_KEY", "test_secret_key")
        
        # Re-import to pick up new env vars
        from sj_trading.core.config import Config
        
        # Should not raise for simulation mode
        Config.validate(simulation=True)
    
    def test_validate_missing_api_key_raises(self, monkeypatch):
        """Should raise ValueError when API_KEY is missing."""
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        
        from sj_trading.core.config import Config
        # Force reload of class attributes
        Config.API_KEY = None
        Config.SECRET_KEY = None
        
        with pytest.raises(ValueError, match="API_KEY and SECRET_KEY must be set"):
            Config.validate(simulation=True)
    
    def test_validate_non_simulation_requires_ca(self, monkeypatch):
        """Should raise ValueError when CA credentials missing in non-simulation mode."""
        monkeypatch.setenv("API_KEY", "test_api_key")
        monkeypatch.setenv("SECRET_KEY", "test_secret_key")
        monkeypatch.delenv("CA_CERT_PATH", raising=False)
        monkeypatch.delenv("CA_PASSWORD", raising=False)
        
        from sj_trading.core.config import Config
        Config.API_KEY = "test_api_key"
        Config.SECRET_KEY = "test_secret_key"
        Config.CA_CERT_PATH = None
        Config.CA_PASSWORD = None
        
        with pytest.raises(ValueError, match="CA_CERT_PATH and CA_PASSWORD are required"):
            Config.validate(simulation=False)
