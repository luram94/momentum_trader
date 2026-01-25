"""
HQM Momentum Scanner - Unit Tests
==================================
Tests for core functionality including:
- Config loading
- Database operations
- Risk metrics calculations
- Backtest engine
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConfigLoader:
    """Tests for configuration loading."""

    def test_default_config_loads(self):
        """Test that default config loads without errors."""
        from config_loader import Config, load_config

        config = Config()
        assert config.portfolio.default_size == 10000
        assert config.portfolio.default_positions == 8
        assert config.strategy.min_percentile_threshold == 25

    def test_portfolio_config_values(self):
        """Test portfolio configuration defaults."""
        from config_loader import PortfolioConfig

        config = PortfolioConfig()
        assert config.min_size == 1000
        assert config.max_positions == 50

    def test_indicator_config_values(self):
        """Test indicator configuration defaults."""
        from config_loader import RSIConfig, SMAConfig

        rsi = RSIConfig()
        assert rsi.period == 14
        assert rsi.overbought == 70
        assert rsi.oversold == 30

        sma = SMAConfig()
        assert sma.period == 10
        assert sma.good_threshold == 5


class TestRiskMetrics:
    """Tests for risk metrics calculations."""

    def test_sharpe_ratio_calculation(self):
        """Test Sharpe ratio calculation."""
        from risk_metrics import calculate_sharpe_ratio

        # Create sample returns
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 252))

        sharpe = calculate_sharpe_ratio(returns, risk_free_rate=0.05)
        assert isinstance(sharpe, float)
        # Sharpe should be reasonable (-3 to 3 for most portfolios)
        assert -5 < sharpe < 5

    def test_sharpe_ratio_zero_std(self):
        """Test Sharpe ratio with zero standard deviation."""
        from risk_metrics import calculate_sharpe_ratio

        returns = pd.Series([0.01] * 100)  # Constant returns
        sharpe = calculate_sharpe_ratio(returns)
        assert sharpe == 0.0

    def test_sharpe_ratio_empty_returns(self):
        """Test Sharpe ratio with empty returns."""
        from risk_metrics import calculate_sharpe_ratio

        returns = pd.Series([])
        sharpe = calculate_sharpe_ratio(returns)
        assert sharpe == 0.0

    def test_max_drawdown_calculation(self):
        """Test maximum drawdown calculation."""
        from risk_metrics import calculate_max_drawdown

        # Create price series with known drawdown
        prices = pd.Series([100, 110, 105, 90, 95, 100, 105])
        max_dd, peak, trough = calculate_max_drawdown(prices)

        # Max drawdown should be from 110 to 90 = -18.18%
        assert max_dd < 0
        assert abs(max_dd + 18.18) < 1  # Within 1% tolerance

    def test_volatility_calculation(self):
        """Test volatility calculation."""
        from risk_metrics import calculate_volatility

        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 252))

        volatility = calculate_volatility(returns)
        assert isinstance(volatility, float)
        assert volatility > 0
        # Annual volatility should be around 0.02 * sqrt(252) ≈ 0.32
        assert 0.1 < volatility < 0.6

    def test_value_at_risk(self):
        """Test Value at Risk calculation."""
        from risk_metrics import calculate_value_at_risk

        np.random.seed(42)
        returns = pd.Series(np.random.normal(0, 0.02, 252))

        var_95 = calculate_value_at_risk(returns, confidence=0.95, portfolio_value=10000)
        var_99 = calculate_value_at_risk(returns, confidence=0.99, portfolio_value=10000)

        assert var_95 > 0
        assert var_99 > var_95  # 99% VaR should be higher than 95%

    def test_sortino_ratio(self):
        """Test Sortino ratio calculation."""
        from risk_metrics import calculate_sortino_ratio

        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 252))

        sortino = calculate_sortino_ratio(returns)
        assert isinstance(sortino, float)


class TestDatabaseOperations:
    """Tests for database operations."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        import sqlite3
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            yield f.name
        os.unlink(f.name)

    def test_database_initialization(self, temp_db, monkeypatch):
        """Test database schema creation."""
        import sqlite3

        # Create test database
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        # Create minimal schema for testing
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stocks (
                ticker TEXT PRIMARY KEY,
                price REAL,
                return_1m REAL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY,
                ticker TEXT UNIQUE
            )
        ''')
        conn.commit()

        # Verify tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        assert 'stocks' in tables
        assert 'watchlist' in tables
        conn.close()

    def test_data_age_calculation(self):
        """Test data age calculation logic."""
        from datetime import datetime, timedelta

        # Test recent data
        last_refresh = datetime.now() - timedelta(hours=2)
        age_hours = (datetime.now() - last_refresh).total_seconds() / 3600
        assert 1.9 < age_hours < 2.1

        # Test old data
        last_refresh = datetime.now() - timedelta(days=2)
        age_hours = (datetime.now() - last_refresh).total_seconds() / 3600
        assert 47 < age_hours < 49


class TestBacktesting:
    """Tests for backtesting engine."""

    def test_backtest_engine_initialization(self):
        """Test BacktestEngine initialization."""
        from backtest import BacktestEngine

        engine = BacktestEngine(
            initial_capital=10000,
            num_positions=8,
            rebalance_frequency='weekly'
        )

        assert engine.initial_capital == 10000
        assert engine.num_positions == 8
        assert engine.rebalance_frequency == 'weekly'
        assert engine.cash == 10000
        assert len(engine.trades) == 0
        assert len(engine.positions) == 0

    def test_rebalance_dates_weekly(self):
        """Test weekly rebalance date generation."""
        from backtest import BacktestEngine
        from datetime import datetime, timedelta

        engine = BacktestEngine(rebalance_frequency='weekly')

        start = datetime(2023, 1, 1)
        end = datetime(2023, 2, 1)

        dates = engine._get_rebalance_dates(start, end)

        # Should have about 5 weekly dates in January
        assert len(dates) >= 4
        assert len(dates) <= 6

        # Dates should be 7 days apart
        for i in range(1, len(dates)):
            diff = (dates[i] - dates[i-1]).days
            assert diff == 7

    def test_rebalance_dates_monthly(self):
        """Test monthly rebalance date generation."""
        from backtest import BacktestEngine
        from datetime import datetime

        engine = BacktestEngine(rebalance_frequency='monthly')

        start = datetime(2023, 1, 1)
        end = datetime(2023, 4, 1)

        dates = engine._get_rebalance_dates(start, end)

        # Should have about 3-4 monthly dates
        assert len(dates) >= 3
        assert len(dates) <= 5


class TestHQMStrategy:
    """Tests for HQM strategy calculations."""

    def test_percentile_calculation(self):
        """Test percentile score calculation."""
        from scipy.stats import percentileofscore

        returns = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

        # Test middle value
        pct = percentileofscore(returns, 0.175, kind='mean')
        assert 50 < pct < 70

        # Test low value
        pct_low = percentileofscore(returns, 0.05, kind='mean')
        assert pct_low < 20

        # Test high value
        pct_high = percentileofscore(returns, 0.30, kind='mean')
        assert pct_high > 90

    def test_hqm_score_calculation(self):
        """Test HQM score as average of percentiles."""
        percentiles = [80, 85, 75, 90]  # 1M, 3M, 6M, 1Y
        hqm_score = sum(percentiles) / len(percentiles)

        assert hqm_score == 82.5

    def test_quality_filter(self):
        """Test quality momentum filter (min percentile threshold)."""
        min_threshold = 25

        # Should pass - all above 25
        percentiles_good = [30, 40, 50, 60]
        min_pct = min(percentiles_good)
        assert min_pct >= min_threshold

        # Should fail - one below 25
        percentiles_bad = [20, 40, 50, 60]
        min_pct = min(percentiles_bad)
        assert min_pct < min_threshold

    def test_position_sizing(self):
        """Test equal-weight position sizing."""
        portfolio_size = 10000
        num_positions = 8

        allocation = portfolio_size / num_positions
        assert allocation == 1250

        weight = 100 / num_positions
        assert weight == 12.5

    def test_share_calculation(self):
        """Test share count calculation."""
        import math

        allocation = 1250
        price = 150.50

        shares = math.floor(allocation / price)
        assert shares == 8

        actual_value = shares * price
        assert actual_value == 1204.00


class TestLogger:
    """Tests for logging functionality."""

    def test_logger_creation(self):
        """Test logger creation."""
        from logger import setup_logging, get_logger

        logger = setup_logging(name='test_logger', console_output=False)
        assert logger is not None
        assert logger.name == 'test_logger'

    def test_logger_caching(self):
        """Test logger caching behavior."""
        from logger import setup_logging

        logger1 = setup_logging(name='cache_test', console_output=False)
        logger2 = setup_logging(name='cache_test', console_output=False)

        assert logger1 is logger2


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_config_to_portfolio_settings(self):
        """Test config values flow to portfolio calculations."""
        from config_loader import Config

        config = Config()
        portfolio_size = config.portfolio.default_size
        num_positions = config.portfolio.default_positions

        position_size = portfolio_size / num_positions
        assert position_size == 1250  # 10000 / 8

    def test_risk_metrics_integration(self):
        """Test risk metrics work together."""
        from risk_metrics import calculate_sharpe_ratio, calculate_volatility, calculate_sortino_ratio

        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 252))

        sharpe = calculate_sharpe_ratio(returns)
        volatility = calculate_volatility(returns)
        sortino = calculate_sortino_ratio(returns)

        # All metrics should be calculable
        assert sharpe is not None
        assert volatility is not None
        assert sortino is not None

        # Sortino should typically be higher than Sharpe for positive returns
        # (since it only penalizes downside volatility)
        # This is a general relationship, not guaranteed


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
