"""
Tests for risk metrics data fetching and the percentage display convention.

Covers PR 1 acceptance criteria:
- get_historical_prices works with both modern (auto_adjust, no 'Adj Close')
  and legacy yfinance column layouts.
- calculate_all_risk_metrics returns real values with data_available=True,
  and an explicit unavailable state (None values) when data cannot be fetched
  -- never default 0 / 1.0 presented as computed.
- The keys the Scanner reads ('volatility', 'max_drawdown') exist.
- Returns are stored as decimal fractions and converted to percent exactly
  once, via the formatting helpers.
"""


import numpy as np
import pandas as pd
import pytest


from hqm.formatting import frac_to_pct, format_pct, frac_cols_to_pct
import hqm.risk_metrics as risk_metrics


# =============================================================================
# Formatting convention
# =============================================================================

class TestFormatting:
    """The single display convention: fractions in, percent out, once."""

    def test_fraction_to_percent_string(self):
        # 0.0523 stored means 5.23%. This fails both if a caller multiplies
        # by 100 twice (would need 0.000523) and if it never multiplies
        # (would render 0.05%).
        assert format_pct(0.0523) == "5.23%"
        assert format_pct(0.0523, decimals=1) == "5.2%"

    def test_negative_and_large_values(self):
        assert format_pct(-0.1) == "-10.00%"
        assert format_pct(1.5) == "150.00%"  # a 150% return, not 1.5%

    def test_signed_formatting(self):
        assert format_pct(0.05, decimals=1, signed=True) == "+5.0%"
        assert format_pct(-0.05, decimals=1, signed=True) == "-5.0%"

    def test_missing_values_render_na(self):
        assert format_pct(None) == "N/A"
        assert format_pct(float('nan')) == "N/A"

    def test_frac_to_pct_scalar_and_series(self):
        assert frac_to_pct(0.0523) == pytest.approx(5.23)
        series = pd.Series([0.01, -0.02, np.nan])
        out = frac_to_pct(series)
        assert out.iloc[0] == pytest.approx(1.0)
        assert out.iloc[1] == pytest.approx(-2.0)
        assert np.isnan(out.iloc[2])

    def test_frac_cols_to_pct_scales_only_listed_columns(self):
        df = pd.DataFrame({'Return_1M': [0.05], 'Price': [100.0]})
        out = frac_cols_to_pct(df, ['Return_1M', 'NotAColumn'])
        assert out['Return_1M'].iloc[0] == pytest.approx(5.0)
        assert out['Price'].iloc[0] == pytest.approx(100.0)
        # Original DataFrame must not be mutated
        assert df['Return_1M'].iloc[0] == pytest.approx(0.05)


# =============================================================================
# get_historical_prices
# =============================================================================

def _multiindex_frame(tickers, price_field='Close', days=300, extra_fields=('High', 'Low')):
    """Build a yfinance-shaped download result with MultiIndex columns."""
    idx = pd.bdate_range('2024-01-02', periods=days)
    rng = np.random.default_rng(42)
    data = {}
    for ticker in tickers:
        prices = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, days))
        data[(price_field, ticker)] = prices
        for field in extra_fields:
            data[(field, ticker)] = prices
    frame = pd.DataFrame(data, index=idx)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns, names=['Price', 'Ticker'])
    return frame


class TestGetHistoricalPrices:
    """Must work with modern yfinance (no 'Adj Close') and legacy layouts."""

    def test_modern_yfinance_close_only(self, monkeypatch):
        # yfinance >= 0.2.51 / 1.x: auto_adjust=True, no 'Adj Close' column
        frame = _multiindex_frame(['AAA', 'BBB'], price_field='Close')
        monkeypatch.setattr(risk_metrics.yf, 'download', lambda *a, **k: frame)

        prices = risk_metrics.get_historical_prices(['AAA', 'BBB'])

        assert sorted(prices.columns) == ['AAA', 'BBB']
        assert len(prices) == 300
        assert not prices.isna().any().any()

    def test_legacy_yfinance_prefers_adj_close(self, monkeypatch):
        # Legacy layout has both fields; 'Adj Close' must be preferred
        frame = _multiindex_frame(['AAA'], price_field='Close')
        adj = frame['Close']['AAA'] * 0.9
        frame[('Adj Close', 'AAA')] = adj
        monkeypatch.setattr(risk_metrics.yf, 'download', lambda *a, **k: frame)

        prices = risk_metrics.get_historical_prices(['AAA'])

        assert list(prices.columns) == ['AAA']
        pd.testing.assert_series_equal(
            prices['AAA'], adj, check_names=False
        )

    def test_single_ticker_flat_columns(self, monkeypatch):
        # Oldest layout: flat columns for a single ticker
        idx = pd.bdate_range('2024-01-02', periods=50)
        frame = pd.DataFrame({'Close': np.linspace(100, 110, 50)}, index=idx)
        monkeypatch.setattr(risk_metrics.yf, 'download', lambda *a, **k: frame)

        prices = risk_metrics.get_historical_prices(['AAA'])

        assert list(prices.columns) == ['AAA']
        assert len(prices) == 50

    def test_failed_ticker_does_not_wipe_others(self, monkeypatch):
        # One ticker with no data at all must be dropped, not zero out
        # every row for the others
        frame = _multiindex_frame(['AAA', 'BBB'], price_field='Close')
        frame[('Close', 'BBB')] = np.nan
        monkeypatch.setattr(risk_metrics.yf, 'download', lambda *a, **k: frame)

        prices = risk_metrics.get_historical_prices(['AAA', 'BBB'])

        assert list(prices.columns) == ['AAA']
        assert len(prices) == 300

    def test_empty_download_returns_empty(self, monkeypatch):
        monkeypatch.setattr(risk_metrics.yf, 'download', lambda *a, **k: pd.DataFrame())
        assert risk_metrics.get_historical_prices(['AAA']).empty

    def test_no_tickers_returns_empty(self):
        assert risk_metrics.get_historical_prices([]).empty


# =============================================================================
# calculate_all_risk_metrics
# =============================================================================

def _price_frame(columns, days=252):
    idx = pd.bdate_range('2024-01-02', periods=days)
    return pd.DataFrame(columns, index=idx)


class TestCalculateAllRiskMetrics:
    """Metrics must be real when data exists, honestly absent when not."""

    def test_metrics_computed_with_scanner_keys(self, monkeypatch):
        rng = np.random.default_rng(7)
        days = 252
        benchmark = risk_metrics.config.risk.benchmark
        prices = _price_frame({
            'AAA': 100 * np.cumprod(1 + rng.normal(0.001, 0.02, days)),
            'BBB': 50 * np.cumprod(1 + rng.normal(0.0005, 0.015, days)),
            benchmark: 400 * np.cumprod(1 + rng.normal(0.0004, 0.01, days)),
        }, days=days)
        monkeypatch.setattr(risk_metrics, 'get_historical_prices', lambda *a, **k: prices)

        metrics = risk_metrics.calculate_all_risk_metrics(['AAA', 'BBB'], [0.5, 0.5], 10000)

        assert metrics['data_available'] is True
        # Exactly the keys the Scanner page reads
        assert isinstance(metrics['volatility'], float)
        assert metrics['volatility'] > 0
        assert isinstance(metrics['max_drawdown'], float)
        assert metrics['max_drawdown'] <= 0
        assert isinstance(metrics['sharpe_ratio'], float)
        assert isinstance(metrics['portfolio_beta'], float)
        assert metrics['var_95'] >= 0
        assert metrics['var_99'] >= metrics['var_95']

    def test_unavailable_when_no_data(self, monkeypatch):
        monkeypatch.setattr(risk_metrics, 'get_historical_prices', lambda *a, **k: pd.DataFrame())

        metrics = risk_metrics.calculate_all_risk_metrics(['AAA'], [1.0], 10000)

        assert metrics['data_available'] is False
        # Never fake defaults: no 0-Sharpe or 1.0-beta presented as computed
        assert metrics['sharpe_ratio'] is None
        assert metrics['portfolio_beta'] is None
        assert metrics['volatility'] is None
        assert metrics['max_drawdown'] is None

    def test_unavailable_when_only_benchmark_has_data(self, monkeypatch):
        rng = np.random.default_rng(3)
        benchmark = risk_metrics.config.risk.benchmark
        prices = _price_frame({
            benchmark: 400 * np.cumprod(1 + rng.normal(0.0004, 0.01, 252)),
        })
        monkeypatch.setattr(risk_metrics, 'get_historical_prices', lambda *a, **k: prices)

        metrics = risk_metrics.calculate_all_risk_metrics(['AAA', 'BBB'], [0.5, 0.5], 10000)

        assert metrics['data_available'] is False

    def test_missing_ticker_keeps_weights_aligned(self, monkeypatch):
        # Tickers AAA and CCC have data, BBB (middle of the list) does not.
        # AAA returns exactly +1% per day, CCC exactly 0%. After dropping BBB
        # and renormalizing, weights are 0.5/0.5 so the portfolio must earn
        # 0.5% per day. The old positional truncation would instead apply
        # BBB's weight to CCC (0.4/0.2 unnormalized -> wrong return).
        days = 252
        rng = np.random.default_rng(11)
        benchmark = risk_metrics.config.risk.benchmark
        prices = _price_frame({
            'AAA': 100 * (1.01 ** np.arange(days)),
            'CCC': np.full(days, 50.0),
            benchmark: 400 * np.cumprod(1 + rng.normal(0.0004, 0.01, days)),
        }, days=days)
        monkeypatch.setattr(risk_metrics, 'get_historical_prices', lambda *a, **k: prices)

        metrics = risk_metrics.calculate_all_risk_metrics(
            ['AAA', 'BBB', 'CCC'], [0.4, 0.2, 0.4], 10000
        )

        assert metrics['data_available'] is True
        # 0.5% daily * 252 days * 100 = 126% annualized
        assert metrics['annualized_return'] == pytest.approx(126.0, rel=0.01)
