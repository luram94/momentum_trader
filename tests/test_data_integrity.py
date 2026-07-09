"""
Tests for PR 2: schema migration, real Avg Volume, fail-closed filters,
and portfolio duplicate handling.

These tests exercise database.py against a temporary SQLite file (DB_PATH is
monkeypatched), so they cover the real query paths, not a parallel schema.
"""

import sys
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import database


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point database.py at a fresh temporary SQLite file."""
    db_path = tmp_path / 'test_hqm.db'
    monkeypatch.setattr(database, 'DB_PATH', db_path)
    return db_path


# =============================================================================
# Schema migration
# =============================================================================

class TestSchemaMigration:
    """CREATE TABLE IF NOT EXISTS never upgrades old tables; migration must."""

    def test_rebuilds_stale_regenerable_table(self, temp_db):
        # The pre-sector stocks schema that shipped in older versions --
        # exactly what crashed 'no such column: sector' in production logs
        conn = sqlite3.connect(temp_db)
        conn.execute('''
            CREATE TABLE stocks (
                ticker TEXT PRIMARY KEY,
                exchange TEXT,
                market_cap REAL,
                price REAL,
                return_1m REAL,
                return_3m REAL,
                return_6m REAL,
                return_1y REAL,
                updated_at TIMESTAMP
            )
        ''')
        conn.execute("INSERT INTO stocks (ticker, price) VALUES ('OLD', 1.0)")
        conn.commit()
        conn.close()

        database.init_database()

        conn = sqlite3.connect(temp_db)
        cols = {row[1] for row in conn.execute('PRAGMA table_info(stocks)')}
        count = conn.execute('SELECT COUNT(*) FROM stocks').fetchone()[0]
        conn.close()

        assert 'sector' in cols
        assert 'industry' in cols
        assert 'avg_volume' in cols
        # Regenerable table is rebuilt empty; a refresh repopulates it
        assert count == 0

    def test_alters_user_table_preserving_rows(self, temp_db):
        # Old watchlist without the alert columns, holding user data
        conn = sqlite3.connect(temp_db)
        conn.execute('''
            CREATE TABLE watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT UNIQUE,
                added_date TIMESTAMP,
                target_entry_price REAL
            )
        ''')
        conn.execute(
            "INSERT INTO watchlist (ticker, target_entry_price) VALUES ('AAPL', 150.0)"
        )
        conn.commit()
        conn.close()

        database.init_database()

        conn = sqlite3.connect(temp_db)
        cols = {row[1] for row in conn.execute('PRAGMA table_info(watchlist)')}
        row = conn.execute(
            'SELECT ticker, target_entry_price, alert_enabled FROM watchlist'
        ).fetchone()
        conn.close()

        assert {'notes', 'alert_enabled', 'alert_threshold'} <= cols
        # User data must survive the upgrade
        assert row[0] == 'AAPL'
        assert row[1] == 150.0

    def test_noop_on_current_schema(self, temp_db):
        database.init_database()
        assert database.add_to_watchlist('MSFT', target_price=300.0)

        # Re-running init (every app start) must not disturb existing data
        database.init_database()

        watchlist = database.get_watchlist()
        assert len(watchlist) == 1
        assert watchlist[0]['ticker'] == 'MSFT'


# =============================================================================
# Portfolio duplicate handling
# =============================================================================

class TestPortfolioDuplicates:
    def test_duplicate_same_day_position_returns_none(self, temp_db):
        database.init_database()

        first = database.add_portfolio_position('AAPL', 10, 100.0, '2026-01-05')
        second = database.add_portfolio_position('AAPL', 5, 105.0, '2026-01-05')

        assert isinstance(first, int)
        assert second is None
        positions = database.get_portfolio_positions()
        assert len(positions) == 1
        assert positions[0]['shares'] == 10  # original untouched

    def test_same_ticker_different_day_allowed(self, temp_db):
        database.init_database()

        assert database.add_portfolio_position('AAPL', 10, 100.0, '2026-01-05')
        assert database.add_portfolio_position('AAPL', 5, 105.0, '2026-01-06')
        assert len(database.get_portfolio_positions()) == 2


# =============================================================================
# Fail-closed technical filters
# =============================================================================

def _seed_stocks(db_path, count=40, avg_volume=1_000_000):
    """Seed a deterministic universe: higher index = stronger momentum."""
    conn = sqlite3.connect(db_path)
    for i in range(count):
        ret = 0.01 * i  # fraction; identical across timeframes
        conn.execute('''
            INSERT INTO stocks (ticker, exchange, sector, industry, market_cap,
                                price, volume, avg_volume,
                                return_1m, return_3m, return_6m, return_1y)
            VALUES (?, 'NYSE', 'Tech', 'Software', 5e9, 10.0, 2e6, ?, ?, ?, ?, ?)
        ''', (f'T{i:02d}', avg_volume, ret, ret, ret, ret))
    conn.commit()
    conn.close()


class TestFailClosedFilters:
    def test_missing_indicators_are_excluded_and_counted(self, temp_db, monkeypatch):
        database.init_database()
        _seed_stocks(temp_db)

        # Even-indexed tickers get real indicators; odd-indexed ones simulate
        # failed yfinance downloads (all None)
        def fake_indicators(tickers, progress_callback=None):
            out = {}
            for t in tickers:
                if int(t[1:]) % 2 == 0:
                    out[t] = {'sma10_distance': 1.0, 'rsi': 50.0,
                              'atr': 0.5, 'atr_percent': 2.0}
                else:
                    out[t] = {'sma10_distance': None, 'rsi': None,
                              'atr': None, 'atr_percent': None}
            return out

        monkeypatch.setattr(database, 'get_technical_indicators', fake_indicators)

        result = database.run_hqm_scan_from_db(
            portfolio_size=10000, num_positions=4,
            save_scan=False, rsi_filter=(0, 70),
        )

        assert result['success']
        selected = [r['Ticker'] for r in result['results']]
        # No ticker with unknown RSI may pass an explicit RSI filter
        assert all(int(t[1:]) % 2 == 0 for t in selected)
        assert result['summary']['excluded_missing_indicators'] > 0

    def test_no_filters_still_selects_all_candidates(self, temp_db, monkeypatch):
        database.init_database()
        _seed_stocks(temp_db)
        monkeypatch.setattr(
            database, 'get_technical_indicators',
            lambda tickers, progress_callback=None: {
                t: {'sma10_distance': None, 'rsi': None,
                    'atr': None, 'atr_percent': None}
                for t in tickers
            },
        )

        # With no filters enabled, missing indicators must not exclude anyone
        result = database.run_hqm_scan_from_db(
            portfolio_size=10000, num_positions=4, save_scan=False,
        )

        assert result['success']
        assert len(result['results']) == 4
        assert result['summary']['excluded_missing_indicators'] == 0

    def test_missing_avg_volume_fails_closed_with_count(self, temp_db, monkeypatch):
        database.init_database()
        _seed_stocks(temp_db, count=30)
        # Simulate 10 stocks whose avg volume was unavailable at refresh time
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "UPDATE stocks SET avg_volume = NULL WHERE CAST(SUBSTR(ticker, 2) AS INT) < 10"
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(
            database, 'get_technical_indicators',
            lambda tickers, progress_callback=None: {t: {} for t in tickers},
        )

        result = database.run_hqm_scan_from_db(
            portfolio_size=10000, num_positions=4,
            save_scan=False, min_volume=500_000,
        )

        assert result['success']
        assert result['summary']['excluded_missing_avg_volume'] == 10
        selected = [r['Ticker'] for r in result['results']]
        assert all(int(t[1:]) >= 10 for t in selected)


# =============================================================================
# Indicator download column layouts
# =============================================================================

class TestIndicatorColumnLayouts:
    def test_single_ticker_multiindex_columns(self, monkeypatch):
        # Modern yfinance returns MultiIndex columns even for one ticker;
        # the old code treated len(batch)==1 as flat and computed nothing
        days = 30
        idx = pd.bdate_range('2024-01-02', periods=days)
        base = 100 + np.arange(days, dtype=float)
        frame = pd.DataFrame(
            {('Close', 'AAA'): base, ('High', 'AAA'): base + 1, ('Low', 'AAA'): base - 1},
            index=idx,
        )
        frame.columns = pd.MultiIndex.from_tuples(frame.columns)
        monkeypatch.setattr(database.yf, 'download', lambda *a, **k: frame)

        results = database.get_technical_indicators(['AAA'])

        assert results['AAA']['sma10_distance'] is not None
        assert results['AAA']['rsi'] is not None
        assert results['AAA']['atr_percent'] is not None
