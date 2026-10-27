"""
Integration tests for the real scan and backtest paths.

These import the actual application modules and drive their full pipelines
against a temporary SQLite database, with only the external network calls
(Yahoo screener and price downloads) replaced by shaped fakes.
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
# Refresh pipeline (fetch_and_store_data with faked Yahoo screener/downloads)
# =============================================================================

# Small stand-in for yfinance's sector -> industries map
_INDUSTRY_MAP = {
    'Technology': {'Software—Infrastructure'},
    'Healthcare': {'Biotechnology'},
    'Financial Services': {'Banks - Regional'},
}


class _FakeQuery:
    """Records EquityQuery operands so the fake screener can read them."""

    def __init__(self, operator, operands):
        self.operator = operator
        self.operands = operands

    def industry(self):
        for operand in self.operands:
            if isinstance(operand, _FakeQuery) and operand.operands[0] == 'industry':
                return operand.operands[1]
        return None


def _quote(symbol, exchange='NMS', **overrides):
    quote = {
        'symbol': symbol,
        'exchange': exchange,
        'marketCap': 5e9,
        'regularMarketPrice': 50.0,
        'regularMarketVolume': 400_000,
        'averageDailyVolume3Month': 2_500_000,
    }
    quote.update(overrides)
    return quote


_DEFAULT_QUOTES = {
    'Software—Infrastructure': [_quote('MSFT')],
    'Biotechnology': [_quote('BIIB', averageDailyVolume3Month=1_100_000)],
    'Banks - Regional': [_quote('JPM', exchange='NYQ')],
}


def _fake_screen(quotes_by_industry, calls=None):
    def screen(query, size=25, offset=0, **kwargs):
        industry = query.industry()
        if calls is not None:
            calls.append((industry, offset))
        quotes = quotes_by_industry.get(industry, [])
        return {'quotes': quotes[offset:offset + size], 'total': len(quotes)}
    return screen


def _closes(tickers, start=100.0, end=200.0):
    """13 months of business-day closes rising linearly from start to end."""
    index = pd.bdate_range(end='2026-10-23', periods=280)
    prices = np.linspace(start, end, len(index))
    return pd.DataFrame({t: prices for t in tickers}, index=index)


def _fake_download(closes):
    def download(tickers, **kwargs):
        frame = closes[[t for t in tickers if t in closes.columns]]
        return pd.concat({'Close': frame}, axis=1)
    return download


@pytest.fixture
def fake_yahoo(monkeypatch):
    """Fake Yahoo endpoints; returns a setter to override screener/prices."""
    # No published snapshot: these tests drive the live refresh
    monkeypatch.setattr(database.snapshot, 'load_fresh', lambda url: None)
    monkeypatch.setattr(database, 'EquityQuery', _FakeQuery)
    monkeypatch.setattr(database, 'EQUITY_SCREENER_EQ_MAP', {'industry': _INDUSTRY_MAP})

    def install(quotes=None, closes=None, calls=None):
        quotes = _DEFAULT_QUOTES if quotes is None else quotes
        closes = _closes(['MSFT', 'BIIB', 'JPM']) if closes is None else closes
        monkeypatch.setattr(database.yf, 'screen', _fake_screen(quotes, calls))
        monkeypatch.setattr(database.yf, 'download', _fake_download(closes))

    install()
    return install


def _stored(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = {r['ticker']: dict(r) for r in conn.execute('SELECT * FROM stocks')}
    conn.close()
    return rows


class TestRefreshPipeline:
    def test_stores_screened_universe_with_computed_returns(self, temp_db, fake_yahoo):
        stats = database.fetch_and_store_data()

        assert stats['total_stored'] == 3
        assert stats['nyse_count'] == 1 and stats['nasdaq_count'] == 2
        rows = _stored(temp_db)
        assert rows['MSFT']['exchange'] == 'NASDAQ'
        assert rows['JPM']['exchange'] == 'NYSE'
        # Yahoo's em-dash industry names are stored in FinViz's spelling
        assert rows['MSFT']['industry'] == 'Software - Infrastructure'
        # FinViz's sector name is kept so stored history lines up
        assert rows['JPM']['sector'] == 'Financial'
        # Real average volume, not the daily volume
        assert rows['MSFT']['avg_volume'] == 2_500_000
        assert rows['BIIB']['avg_volume'] == 1_100_000
        # Linear 100 -> 200 rise: every window is positive, longer is larger
        msft = rows['MSFT']
        assert 0 < msft['return_1m'] < msft['return_3m'] < msft['return_6m'] < msft['return_1y']
        assert database.get_data_age_hours() < 0.1
        assert stats['source'] == 'live'

    def test_pages_through_large_industries(self, temp_db, fake_yahoo, monkeypatch):
        monkeypatch.setattr(database, '_SCREEN_PAGE_SIZE', 1)
        tickers = ['AAA', 'BBB', 'CCC']
        calls = []
        fake_yahoo(
            quotes={'Software—Infrastructure': [_quote(t) for t in tickers]},
            closes=_closes(tickers),
            calls=calls,
        )

        stats = database.fetch_and_store_data()

        assert stats['total_stored'] == 3
        assert ('Software—Infrastructure', 2) in calls

    def test_missing_avg_volume_degrades_to_null(self, temp_db, fake_yahoo):
        quote = _quote('MSFT')
        del quote['averageDailyVolume3Month']
        fake_yahoo(quotes={'Software—Infrastructure': [quote]})

        database.fetch_and_store_data()

        assert _stored(temp_db)['MSFT']['avg_volume'] is None

    def test_short_history_is_dropped(self, temp_db, fake_yahoo):
        # A recent IPO has no close a year back, so no 1Y return
        closes = _closes(['MSFT', 'BIIB', 'JPM'])
        closes.loc[:closes.index[-100], 'BIIB'] = np.nan
        fake_yahoo(closes=closes)

        stats = database.fetch_and_store_data()

        assert stats['total_stored'] == 2
        assert 'BIIB' not in _stored(temp_db)

    def test_screener_error_keeps_existing_data(self, temp_db, fake_yahoo, monkeypatch):
        _seed_stocks(temp_db, count=3)
        before = database.get_stock_count()

        def blocked(*args, **kwargs):
            raise ConnectionError('429 Too Many Requests')
        monkeypatch.setattr(database.yf, 'screen', blocked)

        with pytest.raises(RuntimeError, match='screener failed'):
            database.fetch_and_store_data()

        assert database.get_stock_count() == before

    def test_empty_screen_keeps_existing_data(self, temp_db, fake_yahoo):
        _seed_stocks(temp_db, count=3)
        before = database.get_stock_count()
        fake_yahoo(quotes={})

        with pytest.raises(RuntimeError, match='returned no stocks'):
            database.fetch_and_store_data()

        assert database.get_stock_count() == before

    def test_failed_downloads_keep_existing_data(self, temp_db, fake_yahoo):
        _seed_stocks(temp_db, count=3)
        before = database.get_stock_count()
        # Price history unavailable for every ticker -- the refresh must
        # fail loudly instead of committing an emptied table
        fake_yahoo(closes=_closes([]))

        with pytest.raises(RuntimeError, match='no stocks with complete return data'):
            database.fetch_and_store_data()

        assert database.get_stock_count() == before


class TestCalculateReturns:
    def test_uses_calendar_month_look_backs(self):
        index = pd.date_range('2025-01-01', '2026-01-01', freq='D')
        closes = pd.DataFrame({'X': np.arange(len(index), dtype=float) + 100}, index=index)

        returns = database._calculate_returns(closes).loc['X']

        last = closes['X'].iloc[-1]
        assert returns['Return_1M'] == pytest.approx(last / closes.loc['2025-12-01', 'X'] - 1)
        assert returns['Return_1Y'] == pytest.approx(last / closes.loc['2025-01-01', 'X'] - 1)

    def test_history_shorter_than_window_is_nan(self):
        index = pd.date_range('2025-10-01', '2026-01-01', freq='D')
        closes = pd.DataFrame({'X': 100.0}, index=index)

        returns = database._calculate_returns(closes).loc['X']

        assert returns['Return_3M'] == pytest.approx(0.0)
        assert np.isnan(returns['Return_6M']) and np.isnan(returns['Return_1Y'])


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
