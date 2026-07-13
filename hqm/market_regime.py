"""
Market Regime Module
=====================
Qullamaggie-inspired, rule-based classification of the broad market trend
using an index ETF proxy (QQQ primary, SPY secondary). Purely rule-based
and transparent -- no ML.

Regimes and rules (evaluated on daily closes, precedence top to bottom):

- DOWNTREND: close < SMA200, or (close < SMA50 and SMA10 falling)
- CAUTION:   close > SMA200, but SMA10 falling or close below SMA20/SMA50
- UPTREND:   close > SMA50, close > SMA200, and SMA10 rising
             (SMA10 today > SMA10 N trading days ago, N configurable)
- UNKNOWN:   not enough history to compute the SMAs

Checking DOWNTREND before CAUTION before UPTREND makes the classifier err
conservative wherever the rules overlap. Exposure guidance per regime comes
from config.yaml (market_regime section).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

import pandas as pd
import yfinance as yf

from hqm.logger import get_logger
from hqm.config_loader import get_config

logger = get_logger('market_regime')
config = get_config()

# Regime labels (stable strings: stored in backtest results and parameters)
UPTREND = 'uptrend'
CAUTION = 'caution'
DOWNTREND = 'downtrend'
UNKNOWN = 'unknown'

REGIMES = (UPTREND, CAUTION, DOWNTREND, UNKNOWN)


def regime_exposures_from_config() -> Dict[str, float]:
    """Max long exposure per regime (fractions 0-1) from config.yaml."""
    cfg = config.market_regime
    return {
        UPTREND: cfg.uptrend_max_exposure,
        CAUTION: cfg.caution_max_exposure,
        DOWNTREND: cfg.downtrend_max_exposure,
    }


def classify_regime(
    close: float,
    sma10: float,
    sma20: float,
    sma50: float,
    sma200: float,
    sma10_prev: float,
) -> str:
    """
    Classify a single observation into a market regime.

    Args:
        close: Latest close of the market proxy
        sma10/sma20/sma50/sma200: Simple moving averages at the same date
        sma10_prev: SMA10 value N trading days earlier (slope reference)

    Returns:
        One of UPTREND, CAUTION, DOWNTREND, UNKNOWN
    """
    values = (close, sma10, sma20, sma50, sma200, sma10_prev)
    if any(v is None or pd.isna(v) for v in values):
        return UNKNOWN

    sma10_rising = sma10 > sma10_prev

    if close < sma200 or (close < sma50 and not sma10_rising):
        return DOWNTREND
    if close > sma200 and (not sma10_rising or close < sma20 or close < sma50):
        return CAUTION
    if close > sma50 and close > sma200 and sma10_rising:
        return UPTREND
    # Only reachable on exact-equality edge cases (e.g. close == sma200)
    return UNKNOWN


def classify_regime_series(
    closes: pd.Series,
    slope_lookback: Optional[int] = None,
) -> pd.Series:
    """
    Classify every date of a close-price series.

    Args:
        closes: Daily close prices of the market proxy, indexed by date
        slope_lookback: Trading days for the SMA10 slope test
            (defaults to config market_regime.slope_lookback_days)

    Returns:
        Series of regime labels aligned to the input index. Dates without
        enough history for the SMAs classify as UNKNOWN.
    """
    lookback = slope_lookback or config.market_regime.slope_lookback_days

    sma10 = closes.rolling(10).mean()
    sma20 = closes.rolling(20).mean()
    sma50 = closes.rolling(50).mean()
    sma200 = closes.rolling(200).mean()
    sma10_prev = sma10.shift(lookback)

    regimes = [
        classify_regime(c, s10, s20, s50, s200, s10p)
        for c, s10, s20, s50, s200, s10p in zip(
            closes, sma10, sma20, sma50, sma200, sma10_prev
        )
    ]
    return pd.Series(regimes, index=closes.index, name='regime')


def _fetch_proxy_closes(
    proxy: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    period: Optional[str] = None,
) -> pd.Series:
    """
    Download daily closes for the market proxy.

    Returns an empty Series on any failure -- callers degrade gracefully.
    """
    try:
        # threads=False: threaded downloads segfault the Streamlit Cloud
        # runtime (Python 3.14 + yfinance's curl backend)
        data = yf.download(
            proxy, start=start, end=end, period=period,
            progress=False, threads=False, timeout=30,
        )
        if data is None or data.empty:
            logger.warning(f"No data returned for market proxy {proxy}")
            return pd.Series(dtype=float)

        if isinstance(data.columns, pd.MultiIndex):
            field = 'Adj Close' if 'Adj Close' in data.columns.get_level_values(0) else 'Close'
            closes = data[field]
            if isinstance(closes, pd.DataFrame):
                closes = closes.iloc[:, 0]
        else:
            field = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
            closes = data[field]

        return closes.dropna()

    except Exception as e:
        logger.error(f"Failed to fetch market proxy {proxy}: {e}")
        return pd.Series(dtype=float)


def fetch_regime_history(
    proxy: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[pd.Series]:
    """
    Fetch proxy prices and classify the regime for every trading day.

    The window should start ~200 trading days before the first date whose
    regime matters, so the SMA200 is real (the backtest's 420-calendar-day
    buffer satisfies this).

    Returns:
        Series of regime labels indexed by date, or None if the proxy
        data could not be fetched.
    """
    proxy = proxy or config.market_regime.proxy
    closes = _fetch_proxy_closes(proxy, start=start_date, end=end_date)
    if closes.empty:
        return None
    return classify_regime_series(closes)


def get_market_regime(proxy: Optional[str] = None) -> Dict[str, Any]:
    """
    Snapshot of the current market regime for banner display.

    Returns a dict with the regime, the values behind the decision, and the
    configured max exposure. On fetch failure returns regime UNKNOWN with an
    'error' key -- never raises.
    """
    proxy = proxy or config.market_regime.proxy
    exposures = regime_exposures_from_config()

    closes = _fetch_proxy_closes(proxy, period='1y')
    if closes.empty or len(closes) < 200:
        return {
            'regime': UNKNOWN,
            'proxy': proxy,
            'error': f'Not enough {proxy} history to compute the SMA200',
        }

    lookback = config.market_regime.slope_lookback_days
    sma10 = closes.rolling(10).mean()
    close = float(closes.iloc[-1])
    snapshot = {
        'proxy': proxy,
        'as_of': closes.index[-1].strftime('%Y-%m-%d'),
        'close': close,
        'sma10': float(sma10.iloc[-1]),
        'sma20': float(closes.rolling(20).mean().iloc[-1]),
        'sma50': float(closes.rolling(50).mean().iloc[-1]),
        'sma200': float(closes.rolling(200).mean().iloc[-1]),
        'sma10_prev': float(sma10.iloc[-1 - lookback]),
    }
    snapshot['sma10_rising'] = snapshot['sma10'] > snapshot['sma10_prev']
    snapshot['regime'] = classify_regime(
        close, snapshot['sma10'], snapshot['sma20'],
        snapshot['sma50'], snapshot['sma200'], snapshot['sma10_prev'],
    )
    snapshot['max_exposure'] = exposures.get(snapshot['regime'], 1.0)
    return snapshot


def apply_regime_to_targets(
    target_positions: Dict[str, float],
    regime: str,
    exposures: Dict[str, float],
    held_tickers: Set[str],
) -> Dict[str, float]:
    """
    Scale rebalance target weights by the regime's max exposure.

    In DOWNTREND no new long entries are allowed: tickers not already held
    are dropped from the targets (their allocation stays in cash). UNKNOWN
    regime applies no constraint (exposure 1.0) -- absence of data is not a
    signal.

    Args:
        target_positions: {ticker: weight} the strategy wants (sums to ~1)
        regime: Regime label for the rebalance date
        exposures: {regime: max exposure fraction}
        held_tickers: Tickers currently held (allowed to remain in downtrend)

    Returns:
        Scaled {ticker: weight}; empty dict means go fully to cash.
    """
    exposure = exposures.get(regime, 1.0)
    if exposure <= 0:
        return {}
    if regime == DOWNTREND:
        target_positions = {
            t: w for t, w in target_positions.items() if t in held_tickers
        }
    return {t: w * exposure for t, w in target_positions.items()}
