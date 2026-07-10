"""
Integration tests for the real scan and backtest paths.

These import the actual application modules and drive their full pipelines
against a temporary SQLite database, with only the external network calls
(FinViz screeners, yfinance downloads) replaced by shaped fakes.
"""

import sqlite3

import numpy as np
import pandas as pd
import pytest


import hqm.backtest as backtest
import hqm.database as database
from hqm.config_loader import load_config, get_config


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point database.py at a fresh temporary SQLite file."""
    db_path = tmp_path / 'integration.db'
    monkeypatch.setattr(database, 'DB_PATH', db_path)
    database.init_database()
    return db_path


def _seed_stocks(db_path, count=40):
    """Deterministic universe: higher index = stronger momentum."""
    conn = sqlite3.connect(db_path)
    for i in range(count):
        ret = 0.01 * i
        sector = 'Tech' if i % 2 == 0 else 'Healthcare'
        industry = 'Software' if i % 2 == 0 else 'Biotech'
        conn.execute('''
            INSERT INTO stocks (ticker, exchange, sector, industry, market_cap,
                                price, volume, avg_volume,
                                return_1m, return_3m, return_6m, return_1y)
            VALUES (?, 'NYSE', ?, ?, ?, 10.0, 2e6, 1e6, ?, ?, ?, ?)
        ''', (f'T{i:02d}', sector, industry, 1e9 * (count - i), ret, ret, ret, ret))
    conn.commit()
    conn.close()


# =============================================================================
# Refresh pipeline (fetch_and_store_data with faked FinViz screeners)
# =============================================================================

class _FakeScreener:
    def __init__(self, frame):
        self._frame = frame

    def set_filter(self, filters_dict):
        self.filters = filters_dict

    def screener_view(self, limit=-1, verbose=0, columns=None, sleep_sec=1):
        return self._frame.copy()


def _custom_frame(**overrides):
    """Shaped like the FinViz Custom view with the columns the app requests."""
    frame = pd.DataFrame({
        'Ticker': ['AAA', 'BBB'],
        'Sector': ['Technology', 'Healthcare'],
        'Industry': ['Software', 'Biotech'],
        'Market Cap': [5e9, 8e9],
        'Perf Month': [0.05, 0.02],
        'Perf Quart': [0.15, 0.08],
        'Perf Half': [0.30, 0.12],
        'Perf Year': [0.60, 0.25],
        'Avg Volume': [2_500_000.0, 1_100_000.0],
        'Price': [50.0, 120.0],
        'Volume': [400_000.0, 900_000.0],
    })
    for column, values in overrides.items():
        if values is None:
            frame = frame.drop(columns=column)
        else:
            frame[column] = values
    return frame


class TestRefreshPipeline:
    def test_fetch_and_store_stores_real_avg_volume(self, temp_db, monkeypatch):
        monkeypatch.setattr(database, 'Custom', lambda: _FakeScreener(_custom_frame()))

        stats = database.fetch_and_store_data()

        assert stats['total_stored'] == 2
        conn = sqlite3.connect(temp_db)
        rows = dict(conn.execute('SELECT ticker, avg_volume FROM stocks').fetchall())
        conn.close()
        # Real average volume, not the daily volume
        assert rows['AAA'] == 2_500_000.0
        assert rows['BBB'] == 1_100_000.0
        assert database.get_stock_count() == 2
        assert database.get_data_age_hours() < 0.1

    def test_missing_avg_volume_column_degrades_to_null(self, temp_db, monkeypatch):
        # FinViz layout change: no 'Avg Volume' column -- refresh must not crash
        frame = _custom_frame(**{'Avg Volume': None})
        monkeypatch.setattr(database, 'Custom', lambda: _FakeScreener(frame))

        stats = database.fetch_and_store_data()

        assert stats['total_stored'] == 2
        conn = sqlite3.connect(temp_db)
        avg = conn.execute('SELECT avg_volume FROM stocks').fetchone()[0]
        conn.close()
        assert avg is None  # NULL, never the daily volume in disguise

    def test_all_returns_missing_keeps_existing_data(self, temp_db, monkeypatch):
        _seed_stocks(temp_db, count=3)
        before = database.get_stock_count()
        # FinViz layout change: a return column vanishes entirely -- the
        # refresh must fail loudly instead of committing an emptied table
        frame = _custom_frame(**{'Perf Year': [None, None]})
        monkeypatch.setattr(database, 'Custom', lambda: _FakeScreener(frame))

        with pytest.raises(RuntimeError, match='no stocks with complete return data'):
            database.fetch_and_store_data()

        assert database.get_stock_count() == before


# =============================================================================
# Scan pipeline (run_hqm_scan_from_db end-to-end incl. history writes)
# =============================================================================

class TestScanPipeline:
    def test_scan_writes_history_and_sector_read_path(self, temp_db, monkeypatch):
        _seed_stocks(temp_db)
        monkeypatch.setattr(
            database, 'get_technical_indicators',
            lambda tickers, progress_callback=None: {
                t: {'sma10_distance': 2.0, 'rsi': 55.0, 'atr': 0.4, 'atr_percent': 3.0}
                for t in tickers
            },
        )

        result = database.run_hqm_scan_from_db(
            portfolio_size=10000, num_positions=6, save_scan=True,
        )

        assert result['success']
        assert len(result['results']) == 6
        assert result['summary']['scan_id'] is not None

        # History rows actually landed
        conn = sqlite3.connect(temp_db)
        counts = {
            table: conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in ['scans', 'scan_positions', 'hqm_history',
                          'sector_performance', 'industry_performance']
        }
        conn.close()
        assert counts['scans'] == 1
        assert counts['scan_positions'] == 6
        assert counts['hqm_history'] == 6
        assert counts['sector_performance'] >= 1
        assert counts['industry_performance'] >= 1

        # And the real read paths the Sectors page uses return them
        sector_scores = database.get_sector_hqm_scores()
        assert len(sector_scores) >= 1
        assert all(s['avg_hqm'] > 0 for s in sector_scores)
        industry_scores = database.get_industry_hqm_scores()
        assert len(industry_scores) >= 1

    def test_selection_respects_configured_quality_threshold(self, temp_db, monkeypatch):
        _seed_stocks(temp_db, count=20)
        monkeypatch.setattr(
            database, 'get_technical_indicators',
            lambda tickers, progress_callback=None: {t: {} for t in tickers},
        )

        result = database.run_hqm_scan_from_db(
            portfolio_size=10000, num_positions=20, save_scan=False,
        )

        assert result['success']
        threshold = get_config().strategy.min_percentile_threshold
        # With 20 equally spaced stocks, percentiles are 2.5, 7.5, ..., 97.5;
        # exactly those >= threshold survive the quality filter
        expected = sum(1 for i in range(20) if (i * 5 + 2.5) >= threshold)
        assert result['summary']['after_quality_filter'] == expected


# =============================================================================
# Backtest pipeline (BacktestEngine.run end-to-end incl. results persistence)
# =============================================================================

def _fake_yf_frame(tickers, days=320):
    idx = pd.bdate_range('2023-01-02', periods=days)
    data = {}
    for rank, ticker in enumerate(tickers):
        prices = 100 * np.cumprod(np.full(days, 1 + 0.0005 * (rank + 1)))
        data[('Close', ticker)] = prices
        data[('High', ticker)] = prices * 1.01
        data[('Low', ticker)] = prices * 0.99
    frame = pd.DataFrame(data, index=idx)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    return frame


class TestBacktestPipeline:
    def test_engine_run_end_to_end(self, temp_db, monkeypatch):
        tickers = [f'T{i:02d}' for i in range(12)]
        frame = _fake_yf_frame(tickers)
        monkeypatch.setattr(backtest.yf, 'download', lambda *a, **k: frame)

        engine = backtest.BacktestEngine(
            initial_capital=10000, num_positions=4,
            rebalance_frequency='weekly', use_stop_loss=False,
        )
        results = engine.run(tickers, start_date='2024-02-01', end_date='2024-03-20')

        assert results['success']
        assert results['num_trades'] > 0
        assert results['final_value'] > 0
        assert results['universe_requested'] == 12
        assert results['universe_with_history'] == 12
        assert results['universe_capped'] is False
        assert results['parameters']['min_percentile'] == \
            get_config().strategy.min_percentile_threshold
        assert len(results['portfolio_history']) > 0

        # Results were persisted through the real read path
        history = backtest.get_backtest_history(limit=1)
        assert len(history) == 1
        assert history[0]['initial_capital'] == 10000
        assert history[0]['num_trades'] == results['num_trades']

    def test_run_backtest_uses_deterministic_universe(self, temp_db, monkeypatch):
        _seed_stocks(temp_db, count=10)
        captured = {}

        def fake_run(self, tickers, start_date, end_date, progress_callback=None):
            captured['tickers'] = tickers
            return {'success': True}

        monkeypatch.setattr(backtest.BacktestEngine, 'run', fake_run)

        assert backtest.run_backtest()['success']
        # Largest market cap first (seed gives T00 the largest cap)
        assert captured['tickers'] == [f'T{i:02d}' for i in range(10)]


# =============================================================================
# Config: only real keys, backward compatible with old files
# =============================================================================

class TestConfigIntegration:
    def test_repo_config_yaml_loads_with_expected_values(self):
        config = load_config()
        assert config.scanner_filters.max_rsi == 70
        assert config.scanner_filters.min_avg_volume == 500000
        assert config.strategy.min_percentile_threshold == 25
        assert config.database.path == 'data/hqm_data.db'
        assert config.risk.sharpe_period_days == 252

    def test_old_config_file_with_removed_keys_still_loads(self, tmp_path):
        old = tmp_path / 'old_config.yaml'
        old.write_text('''
portfolio:
  default_size: 20000
indicators:
  rsi:
    period: 14
    overbought: 70
sectors:
  excluded_sectors: []
strategy:
  min_percentile_threshold: 30
  timeframes: [1M, 3M]
rate_limits:
  finviz_delay_seconds: 1
  max_retries: 3
''')
        config = load_config(old)
        # Known keys apply, removed/unknown keys are ignored, rest defaults
        assert config.portfolio.default_size == 20000
        assert config.strategy.min_percentile_threshold == 30
        assert config.scanner_filters.max_rsi == 70
        assert config.rate_limits.yfinance_batch_size == 50
