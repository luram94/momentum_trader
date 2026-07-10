"""
Tests for PR 3: scanner/backtest alignment and strategy assumptions.

- The backtest uses the scanner's configured min-percentile threshold
  (previously hardcoded to a looser 20).
- No fabricated returns: stocks need a real year of history; missing 6M/1Y
  returns are never substituted with shorter horizons.
- Rebalancing is two-sided: overweight positions are trimmed.
- The backtest universe is deterministic (market cap desc, ticker tiebreak).
- Cash checks include commission, so cash can't go negative.
"""

import sys
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import backtest
import database
from backtest import BacktestEngine, get_backtest_universe
from config_loader import get_config


def make_ohlc(closes: dict, days: int) -> dict:
    """Build an ohlc_data dict in the engine's expected shape."""
    idx = pd.bdate_range('2023-01-02', periods=days)
    close = pd.DataFrame(closes, index=idx)
    return {'Close': close, 'High': close * 1.01, 'Low': close * 0.99}


def growth_series(daily_return: float, days: int, start: float = 100.0) -> np.ndarray:
    return start * np.cumprod(np.full(days, 1 + daily_return))


# =============================================================================
# Threshold alignment
# =============================================================================

class TestThresholdAlignment:
    def test_engine_defaults_to_scanner_config_threshold(self):
        engine = BacktestEngine()
        assert engine.min_percentile == get_config().strategy.min_percentile_threshold

    def test_threshold_filters_at_configured_level(self):
        # 10 tickers with strictly increasing momentum. Percentile ranks with
        # kind='mean' are 5, 15, ..., 95, so a threshold of 25 keeps exactly
        # the 8 tickers at percentile >= 25.
        days = 260
        closes = {f'T{i}': growth_series(0.001 * (i + 1), days) for i in range(10)}
        ohlc = make_ohlc(closes, days)

        engine = BacktestEngine(num_positions=10, min_percentile=25)
        df = engine._calculate_hqm_scores(ohlc, date_idx=days - 1)

        assert len(df) == 8
        assert 'T0' not in df['Ticker'].values
        assert 'T1' not in df['Ticker'].values
        # Strongest momentum ranks first
        assert df.iloc[0]['Ticker'] == 'T9'

    def test_min_percentile_reported_in_parameters(self):
        engine = BacktestEngine(min_percentile=25)
        engine.portfolio_history = [
            {'date': pd.Timestamp('2024-01-02'), 'total_value': 10000,
             'cash': 10000, 'invested': 0, 'positions': 0},
            {'date': pd.Timestamp('2024-01-03'), 'total_value': 10000,
             'cash': 10000, 'invested': 0, 'positions': 0},
        ]
        results = engine._calculate_results()
        assert results['parameters']['min_percentile'] == 25


# =============================================================================
# No fabricated returns
# =============================================================================

class TestNoFabricatedReturns:
    def test_short_history_ticker_excluded(self):
        # FULL has a year of history; IPO only ~120 days. Previously IPO's
        # missing 6M/1Y returns were faked from its 3M return; now it must
        # simply be excluded.
        days = 260
        full = growth_series(0.002, days)
        ipo = np.full(days, np.nan)
        ipo[-120:] = growth_series(0.05, 120)  # explosive recent listing
        others = {f'F{i}': growth_series(0.0005 * (i + 1), days) for i in range(6)}

        ohlc = make_ohlc({'FULL': full, 'IPO': ipo, **others}, days)
        engine = BacktestEngine(num_positions=8, min_percentile=0)
        df = engine._calculate_hqm_scores(ohlc, date_idx=days - 1)

        assert 'IPO' not in df['Ticker'].values
        assert 'FULL' in df['Ticker'].values

    def test_all_returns_are_real(self):
        days = 300
        closes = {f'T{i}': growth_series(0.001 * (i + 1), days) for i in range(5)}
        ohlc = make_ohlc(closes, days)

        engine = BacktestEngine(num_positions=5, min_percentile=0)
        df = engine._calculate_hqm_scores(ohlc, date_idx=days - 1)

        for col in ['Return_1M', 'Return_3M', 'Return_6M', 'Return_1Y']:
            assert df[col].notna().all()
        # Horizons must differ (constant growth: longer horizon, larger
        # return) -- identical values would indicate fallback substitution
        row = df[df['Ticker'] == 'T4'].iloc[0]
        assert row['Return_1Y'] > row['Return_6M'] > row['Return_3M'] > row['Return_1M']

    def test_insufficient_history_returns_empty(self):
        days = 200  # below the 252-day requirement
        ohlc = make_ohlc({'AAA': growth_series(0.001, days)}, days)
        engine = BacktestEngine()
        assert engine._calculate_hqm_scores(ohlc, date_idx=days - 1).empty


# =============================================================================
# Two-sided rebalancing
# =============================================================================

def _seed_position(engine, ticker, shares, entry_price):
    engine.positions[ticker] = {
        'shares': shares,
        'initial_shares': shares,
        'entry_price': entry_price,
        'entry_date': pd.Timestamp('2023-06-01'),
        'entry_day_low': entry_price * 0.95,
        'stop_price': 0,
        'stop_type': 'initial',
        'partial_exit_done': False,
        'days_held': 10,
    }


class TestTwoSidedRebalancing:
    def test_overweight_position_is_trimmed(self):
        days = 260
        ohlc = make_ohlc({'A': np.full(days, 100.0), 'B': np.full(days, 100.0)}, days)

        engine = BacktestEngine(
            initial_capital=10000, num_positions=2,
            slippage_pct=0, commission=0, use_stop_loss=False,
        )
        engine.cash = 0
        _seed_position(engine, 'A', 80, 100.0)  # $8,000 -- overweight
        _seed_position(engine, 'B', 20, 100.0)  # $2,000 -- underweight

        engine._execute_rebalance(
            pd.Timestamp('2023-12-29'), {'A': 0.5, 'B': 0.5}, ohlc, days - 1
        )

        assert engine.positions['A']['shares'] == 50
        assert engine.positions['B']['shares'] == 50

        trims = [t for t in engine.trades
                 if t['action'] == 'SELL' and t.get('exit_reason') == 'rebalance_trim']
        assert len(trims) == 1
        assert trims[0]['ticker'] == 'A'
        assert trims[0]['shares'] == 30

        buys = [t for t in engine.trades if t['action'] == 'BUY']
        assert len(buys) == 1
        assert buys[0]['ticker'] == 'B'
        assert buys[0]['shares'] == 30

    def test_trim_does_not_close_position_entirely(self):
        days = 260
        ohlc = make_ohlc({'A': np.full(days, 100.0)}, days)

        engine = BacktestEngine(slippage_pct=0, commission=0, use_stop_loss=False)
        engine.cash = 0
        _seed_position(engine, 'A', 80, 100.0)

        # Target keeps A but at a much smaller weight
        engine._execute_rebalance(
            pd.Timestamp('2023-12-29'), {'A': 0.2}, ohlc, days - 1
        )

        assert 'A' in engine.positions
        assert engine.positions['A']['shares'] == 16  # 20% of $8,000 at $100
        assert engine.positions['A']['initial_shares'] == 16

    def test_cash_check_includes_commission(self):
        days = 260
        ohlc = make_ohlc({'A': np.full(days, 100.0)}, days)

        engine = BacktestEngine(
            initial_capital=1000, slippage_pct=0, commission=50,
            use_stop_loss=False,
        )
        # Cash covers 10 shares at $100 but NOT shares + commission;
        # previously this went through and drove cash to -$50
        engine._execute_rebalance(
            pd.Timestamp('2023-12-29'), {'A': 1.0}, ohlc, days - 1
        )

        assert engine.cash >= 0


# =============================================================================
# Deterministic universe
# =============================================================================

class TestDeterministicUniverse:
    @pytest.fixture
    def seeded_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / 'universe.db'
        monkeypatch.setattr(database, 'DB_PATH', db_path)
        database.init_database()

        conn = sqlite3.connect(db_path)
        rows = [
            ('SMALL', 1e9), ('BIG', 100e9), ('MID', 10e9),
            ('TIE_B', 5e9), ('TIE_A', 5e9),
        ]
        for ticker, mcap in rows:
            conn.execute(
                '''INSERT INTO stocks (ticker, exchange, market_cap, price,
                   return_1m, return_3m, return_6m, return_1y)
                   VALUES (?, 'NYSE', ?, 10, 0.1, 0.1, 0.1, 0.1)''',
                (ticker, mcap),
            )
        conn.commit()
        conn.close()
        return db_path

    def test_ordered_by_market_cap_with_ticker_tiebreak(self, seeded_db):
        assert get_backtest_universe() == ['BIG', 'MID', 'TIE_A', 'TIE_B', 'SMALL']

    def test_limit_keeps_largest(self, seeded_db):
        assert get_backtest_universe(limit=2) == ['BIG', 'MID']

    def test_repeated_calls_identical(self, seeded_db):
        assert get_backtest_universe() == get_backtest_universe()
