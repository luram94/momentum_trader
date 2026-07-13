"""
Tests for the market regime layer (hqm/market_regime.py).

- classify_regime implements the documented rules with conservative
  precedence (Downtrend > Caution > Uptrend).
- classify_regime_series classifies whole price histories and returns
  UNKNOWN while the SMAs are warming up.
- apply_regime_to_targets scales rebalance targets and blocks new long
  entries in a downtrend.
- The backtest engine defaults its exposures from config and reports the
  regime settings and stats in its results.
"""

import numpy as np
import pandas as pd

from hqm.config_loader import get_config
from hqm.market_regime import (
    UPTREND,
    CAUTION,
    DOWNTREND,
    UNKNOWN,
    classify_regime,
    classify_regime_series,
    apply_regime_to_targets,
    regime_exposures_from_config,
)
from hqm.backtest import BacktestEngine


# =============================================================================
# Single-point classification rules
# =============================================================================

class TestClassifyRegime:
    def test_uptrend_all_conditions_met(self):
        # close above every SMA, SMA10 rising
        assert classify_regime(
            close=110, sma10=105, sma20=104, sma50=100, sma200=90,
            sma10_prev=100,
        ) == UPTREND

    def test_caution_sma10_falling(self):
        # above SMA200 and SMA50 but short-term momentum rolling over
        assert classify_regime(
            close=110, sma10=105, sma20=104, sma50=100, sma200=90,
            sma10_prev=106,
        ) == CAUTION

    def test_caution_close_below_sma20(self):
        # everything else bullish, but close slipped under the SMA20
        assert classify_regime(
            close=103, sma10=102, sma20=104, sma50=100, sma200=90,
            sma10_prev=101,
        ) == CAUTION

    def test_caution_below_sma50_but_sma10_rising(self):
        # below SMA50 alone is caution, not downtrend, while SMA10 rises
        assert classify_regime(
            close=98, sma10=97, sma20=99, sma50=100, sma200=90,
            sma10_prev=96,
        ) == CAUTION

    def test_downtrend_below_sma200(self):
        # close under SMA200 is a downtrend regardless of anything else
        assert classify_regime(
            close=85, sma10=86, sma20=87, sma50=88, sma200=90,
            sma10_prev=85,
        ) == DOWNTREND

    def test_downtrend_below_sma50_with_sma10_falling(self):
        # still above SMA200, but under SMA50 with falling SMA10
        assert classify_regime(
            close=95, sma10=96, sma20=97, sma50=100, sma200=90,
            sma10_prev=98,
        ) == DOWNTREND

    def test_unknown_on_missing_values(self):
        assert classify_regime(
            close=100, sma10=99, sma20=98, sma50=97, sma200=np.nan,
            sma10_prev=98,
        ) == UNKNOWN
        assert classify_regime(
            close=100, sma10=99, sma20=98, sma50=97, sma200=90,
            sma10_prev=None,
        ) == UNKNOWN


# =============================================================================
# Series classification
# =============================================================================

class TestClassifyRegimeSeries:
    def test_steady_rally_classifies_uptrend(self):
        idx = pd.bdate_range('2023-01-02', periods=300)
        closes = pd.Series(100 * np.cumprod(np.full(300, 1.002)), index=idx)

        regimes = classify_regime_series(closes)

        assert regimes.index.equals(idx)
        assert regimes.iloc[-1] == UPTREND
        # SMA200 needs 200 observations: everything before is UNKNOWN
        assert (regimes.iloc[:199] == UNKNOWN).all()

    def test_crash_classifies_downtrend(self):
        idx = pd.bdate_range('2023-01-02', periods=300)
        rally = 100 * np.cumprod(np.full(240, 1.002))
        crash = rally[-1] * np.cumprod(np.full(60, 0.99))
        closes = pd.Series(np.concatenate([rally, crash]), index=idx)

        regimes = classify_regime_series(closes)

        assert regimes.iloc[-1] == DOWNTREND

    def test_matches_single_point_classifier(self):
        # The series path must agree with classify_regime at every date
        idx = pd.bdate_range('2023-01-02', periods=260)
        rng = np.random.default_rng(7)
        closes = pd.Series(
            100 * np.cumprod(1 + rng.normal(0.0005, 0.01, 260)), index=idx
        )

        regimes = classify_regime_series(closes, slope_lookback=5)

        sma10 = closes.rolling(10).mean()
        expected_last = classify_regime(
            closes.iloc[-1],
            sma10.iloc[-1],
            closes.rolling(20).mean().iloc[-1],
            closes.rolling(50).mean().iloc[-1],
            closes.rolling(200).mean().iloc[-1],
            sma10.iloc[-6],
        )
        assert regimes.iloc[-1] == expected_last


# =============================================================================
# Exposure scaling at rebalance
# =============================================================================

class TestApplyRegimeToTargets:
    EXPOSURES = {UPTREND: 1.0, CAUTION: 0.5, DOWNTREND: 0.0}
    TARGETS = {'AAA': 0.5, 'BBB': 0.5}

    def test_uptrend_keeps_full_weights(self):
        out = apply_regime_to_targets(self.TARGETS, UPTREND, self.EXPOSURES, set())
        assert out == self.TARGETS

    def test_caution_scales_weights(self):
        out = apply_regime_to_targets(self.TARGETS, CAUTION, self.EXPOSURES, set())
        assert out == {'AAA': 0.25, 'BBB': 0.25}

    def test_downtrend_zero_exposure_goes_to_cash(self):
        out = apply_regime_to_targets(
            self.TARGETS, DOWNTREND, self.EXPOSURES, held_tickers={'AAA'}
        )
        assert out == {}

    def test_downtrend_blocks_new_entries_even_with_exposure(self):
        exposures = {UPTREND: 1.0, CAUTION: 0.5, DOWNTREND: 0.25}
        out = apply_regime_to_targets(
            self.TARGETS, DOWNTREND, exposures, held_tickers={'AAA'}
        )
        # BBB is a new entry: dropped. AAA is held: kept at scaled weight.
        assert out == {'AAA': 0.125}

    def test_unknown_regime_applies_no_constraint(self):
        out = apply_regime_to_targets(self.TARGETS, UNKNOWN, self.EXPOSURES, set())
        assert out == self.TARGETS


# =============================================================================
# Config and engine wiring
# =============================================================================

class TestConfigAndEngine:
    def test_config_defaults(self):
        cfg = get_config().market_regime
        assert cfg.proxy == 'QQQ'
        assert cfg.secondary_proxy == 'SPY'
        assert cfg.uptrend_max_exposure == 1.0
        assert cfg.caution_max_exposure == 0.5
        assert cfg.downtrend_max_exposure == 0.0

    def test_engine_defaults_exposures_from_config(self):
        engine = BacktestEngine(use_market_regime=True)
        assert engine.regime_exposures == regime_exposures_from_config()
        assert engine.regime_proxy == get_config().market_regime.proxy

    def test_results_report_regime_settings_and_stats(self):
        engine = BacktestEngine(use_market_regime=True)
        engine.regime_day_counts = {
            UPTREND: 40, CAUTION: 15, DOWNTREND: 5, UNKNOWN: 0
        }
        engine.baseline_stats = {'total_return': 4.0, 'max_drawdown': -12.0}
        engine.portfolio_history = [
            {'date': pd.Timestamp('2024-01-02'), 'total_value': 10000,
             'cash': 5000, 'invested': 5000, 'positions': 4},
            {'date': pd.Timestamp('2024-01-03'), 'total_value': 10000,
             'cash': 5000, 'invested': 5000, 'positions': 4},
        ]

        results = engine._calculate_results()

        assert results['regime_days'][UPTREND] == 40
        assert results['avg_exposure_pct'] == 50.0
        assert results['baseline_total_return'] == 4.0
        assert results['baseline_max_drawdown'] == -12.0
        assert results['parameters']['use_market_regime'] is True
        assert results['parameters']['regime_exposures'] == regime_exposures_from_config()

    def test_results_omit_regime_keys_when_disabled(self):
        engine = BacktestEngine()
        engine.portfolio_history = [
            {'date': pd.Timestamp('2024-01-02'), 'total_value': 10000,
             'cash': 10000, 'invested': 0, 'positions': 0},
        ]

        results = engine._calculate_results()

        assert 'regime_days' not in results
        assert results['parameters']['use_market_regime'] is False
