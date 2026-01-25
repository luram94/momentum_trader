"""
Risk Metrics Module
====================
Calculate portfolio risk metrics including:
- Sharpe Ratio
- Maximum Drawdown
- Beta vs Benchmark
- Volatility
- Value at Risk (VaR)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from logger import get_logger
from config_loader import get_config

logger = get_logger('risk_metrics')
config = get_config()


def get_historical_prices(
    tickers: List[str],
    period: str = '1y',
    interval: str = '1d'
) -> pd.DataFrame:
    """
    Get historical prices for a list of tickers.

    Args:
        tickers: List of ticker symbols
        period: Time period (1mo, 3mo, 6mo, 1y, 2y, 5y)
        interval: Data interval (1d, 1wk, 1mo)

    Returns:
        DataFrame with adjusted close prices
    """
    if not tickers:
        return pd.DataFrame()

    try:
        tickers_str = ' '.join(tickers)
        data = yf.download(tickers_str, period=period, interval=interval, progress=False)

        if data.empty:
            return pd.DataFrame()

        # Handle single vs multiple tickers
        if len(tickers) == 1:
            prices = data['Adj Close'].to_frame(name=tickers[0])
        else:
            prices = data['Adj Close']

        return prices.dropna()

    except Exception as e:
        logger.error(f"Error fetching historical prices: {e}")
        return pd.DataFrame()


def calculate_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate daily returns from prices.

    Args:
        prices: DataFrame of prices

    Returns:
        DataFrame of daily returns
    """
    return prices.pct_change().dropna()


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: Optional[float] = None,
    periods_per_year: int = 252
) -> float:
    """
    Calculate annualized Sharpe Ratio.

    Args:
        returns: Series of returns
        risk_free_rate: Annual risk-free rate (uses config default if None)
        periods_per_year: Trading periods per year (252 for daily)

    Returns:
        Sharpe Ratio
    """
    if risk_free_rate is None:
        risk_free_rate = config.risk.risk_free_rate

    if len(returns) == 0 or returns.std() == 0:
        return 0.0

    # Convert annual risk-free rate to per-period
    rf_per_period = (1 + risk_free_rate) ** (1 / periods_per_year) - 1

    excess_returns = returns - rf_per_period
    sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(periods_per_year)

    return round(sharpe, 3)


def calculate_portfolio_sharpe(
    tickers: List[str],
    weights: List[float],
    period: str = '1y'
) -> float:
    """
    Calculate Sharpe Ratio for a weighted portfolio.

    Args:
        tickers: List of ticker symbols
        weights: Portfolio weights (should sum to 1)
        period: Historical period for calculation

    Returns:
        Portfolio Sharpe Ratio
    """
    prices = get_historical_prices(tickers, period=period)
    if prices.empty:
        return 0.0

    returns = calculate_returns(prices)

    # Normalize weights
    weights = np.array(weights)
    weights = weights / weights.sum()

    # Calculate portfolio returns
    portfolio_returns = (returns * weights).sum(axis=1)

    return calculate_sharpe_ratio(portfolio_returns)


def calculate_max_drawdown(prices: pd.Series) -> Tuple[float, str, str]:
    """
    Calculate maximum drawdown from a price series.

    Args:
        prices: Series of prices

    Returns:
        Tuple of (max_drawdown_pct, peak_date, trough_date)
    """
    if len(prices) == 0:
        return 0.0, '', ''

    # Calculate running maximum
    running_max = prices.expanding().max()

    # Calculate drawdown
    drawdown = (prices - running_max) / running_max

    # Find maximum drawdown
    max_drawdown = drawdown.min()
    trough_idx = drawdown.idxmin()

    # Find the peak before the trough
    peak_idx = prices[:trough_idx].idxmax()

    return (
        round(max_drawdown * 100, 2),
        str(peak_idx.date()) if hasattr(peak_idx, 'date') else str(peak_idx),
        str(trough_idx.date()) if hasattr(trough_idx, 'date') else str(trough_idx)
    )


def calculate_portfolio_drawdown(
    tickers: List[str],
    weights: List[float],
    period: str = '1y'
) -> Dict[str, Any]:
    """
    Calculate maximum drawdown for a weighted portfolio.

    Args:
        tickers: List of ticker symbols
        weights: Portfolio weights
        period: Historical period

    Returns:
        Dict with drawdown metrics
    """
    prices = get_historical_prices(tickers, period=period)
    if prices.empty:
        return {'max_drawdown': 0, 'peak_date': '', 'trough_date': ''}

    returns = calculate_returns(prices)

    # Normalize weights
    weights = np.array(weights)
    weights = weights / weights.sum()

    # Calculate portfolio returns
    portfolio_returns = (returns * weights).sum(axis=1)

    # Calculate cumulative returns (price series)
    portfolio_value = (1 + portfolio_returns).cumprod()

    max_dd, peak, trough = calculate_max_drawdown(portfolio_value)

    return {
        'max_drawdown': max_dd,
        'peak_date': peak,
        'trough_date': trough
    }


def calculate_beta(
    ticker: str,
    benchmark: Optional[str] = None,
    period: str = '1y'
) -> float:
    """
    Calculate beta of a stock vs benchmark.

    Args:
        ticker: Stock ticker symbol
        benchmark: Benchmark ticker (uses config default if None)
        period: Historical period

    Returns:
        Beta coefficient
    """
    if benchmark is None:
        benchmark = config.risk.benchmark

    prices = get_historical_prices([ticker, benchmark], period=period)
    if prices.empty or ticker not in prices.columns or benchmark not in prices.columns:
        return 1.0

    returns = calculate_returns(prices)

    # Calculate covariance and variance
    covariance = returns[ticker].cov(returns[benchmark])
    variance = returns[benchmark].var()

    if variance == 0:
        return 1.0

    beta = covariance / variance
    return round(beta, 3)


def calculate_portfolio_beta(
    tickers: List[str],
    weights: List[float],
    benchmark: Optional[str] = None,
    period: str = '1y'
) -> float:
    """
    Calculate weighted portfolio beta.

    Args:
        tickers: List of ticker symbols
        weights: Portfolio weights
        benchmark: Benchmark ticker
        period: Historical period

    Returns:
        Portfolio beta
    """
    if benchmark is None:
        benchmark = config.risk.benchmark

    # Normalize weights
    weights = np.array(weights)
    weights = weights / weights.sum()

    # Calculate individual betas
    betas = [calculate_beta(ticker, benchmark, period) for ticker in tickers]

    # Weighted average beta
    portfolio_beta = sum(b * w for b, w in zip(betas, weights))

    return round(portfolio_beta, 3)


def calculate_volatility(
    returns: pd.Series,
    periods_per_year: int = 252
) -> float:
    """
    Calculate annualized volatility.

    Args:
        returns: Series of returns
        periods_per_year: Trading periods per year

    Returns:
        Annualized volatility (as decimal)
    """
    if len(returns) == 0:
        return 0.0

    volatility = returns.std() * np.sqrt(periods_per_year)
    return round(volatility, 4)


def calculate_value_at_risk(
    returns: pd.Series,
    confidence: float = 0.95,
    portfolio_value: float = 10000
) -> float:
    """
    Calculate Value at Risk (VaR) using historical method.

    Args:
        returns: Series of returns
        confidence: Confidence level (e.g., 0.95 for 95%)
        portfolio_value: Current portfolio value

    Returns:
        VaR in dollar terms
    """
    if len(returns) == 0:
        return 0.0

    var_pct = returns.quantile(1 - confidence)
    var_dollar = abs(var_pct * portfolio_value)

    return round(var_dollar, 2)


def calculate_sortino_ratio(
    returns: pd.Series,
    risk_free_rate: Optional[float] = None,
    periods_per_year: int = 252
) -> float:
    """
    Calculate Sortino Ratio (uses downside deviation only).

    Args:
        returns: Series of returns
        risk_free_rate: Annual risk-free rate
        periods_per_year: Trading periods per year

    Returns:
        Sortino Ratio
    """
    if risk_free_rate is None:
        risk_free_rate = config.risk.risk_free_rate

    if len(returns) == 0:
        return 0.0

    # Convert annual risk-free rate to per-period
    rf_per_period = (1 + risk_free_rate) ** (1 / periods_per_year) - 1

    excess_returns = returns - rf_per_period

    # Calculate downside deviation (only negative returns)
    negative_returns = excess_returns[excess_returns < 0]
    if len(negative_returns) == 0 or negative_returns.std() == 0:
        return 0.0

    downside_std = np.sqrt((negative_returns ** 2).mean()) * np.sqrt(periods_per_year)

    sortino = (excess_returns.mean() * periods_per_year) / downside_std

    return round(sortino, 3)


def calculate_all_risk_metrics(
    tickers: List[str],
    weights: List[float],
    portfolio_value: float = 10000,
    period: str = '1y'
) -> Dict[str, Any]:
    """
    Calculate comprehensive risk metrics for a portfolio.

    Args:
        tickers: List of ticker symbols
        weights: Portfolio weights
        portfolio_value: Current portfolio value
        period: Historical period for calculations

    Returns:
        Dict with all risk metrics
    """
    logger.info(f"Calculating risk metrics for {len(tickers)} stocks")

    prices = get_historical_prices(tickers + [config.risk.benchmark], period=period)

    if prices.empty:
        return {
            'sharpe_ratio': 0,
            'sortino_ratio': 0,
            'max_drawdown': 0,
            'portfolio_beta': 1.0,
            'volatility': 0,
            'var_95': 0,
            'var_99': 0
        }

    returns = calculate_returns(prices)

    # Normalize weights
    weights = np.array(weights)
    weights = weights / weights.sum()

    # Get only portfolio tickers (not benchmark)
    portfolio_tickers = [t for t in tickers if t in returns.columns]
    portfolio_weights = weights[:len(portfolio_tickers)]

    if len(portfolio_tickers) == 0:
        return {
            'sharpe_ratio': 0,
            'sortino_ratio': 0,
            'max_drawdown': 0,
            'portfolio_beta': 1.0,
            'volatility': 0,
            'var_95': 0,
            'var_99': 0
        }

    # Calculate portfolio returns
    portfolio_returns = (returns[portfolio_tickers] * portfolio_weights).sum(axis=1)

    # Calculate all metrics
    sharpe = calculate_sharpe_ratio(portfolio_returns)
    sortino = calculate_sortino_ratio(portfolio_returns)
    volatility = calculate_volatility(portfolio_returns)
    var_95 = calculate_value_at_risk(portfolio_returns, 0.95, portfolio_value)
    var_99 = calculate_value_at_risk(portfolio_returns, 0.99, portfolio_value)

    # Drawdown
    portfolio_value_series = (1 + portfolio_returns).cumprod() * portfolio_value
    max_dd, peak, trough = calculate_max_drawdown(portfolio_value_series)

    # Beta
    benchmark = config.risk.benchmark
    if benchmark in returns.columns:
        cov = portfolio_returns.cov(returns[benchmark])
        var = returns[benchmark].var()
        portfolio_beta = round(cov / var if var > 0 else 1.0, 3)
    else:
        portfolio_beta = calculate_portfolio_beta(portfolio_tickers, portfolio_weights, period=period)

    metrics = {
        'sharpe_ratio': sharpe,
        'sortino_ratio': sortino,
        'max_drawdown': max_dd,
        'max_drawdown_peak': peak,
        'max_drawdown_trough': trough,
        'portfolio_beta': portfolio_beta,
        'volatility': round(volatility * 100, 2),  # As percentage
        'var_95': var_95,
        'var_99': var_99,
        'annualized_return': round(portfolio_returns.mean() * 252 * 100, 2)  # As percentage
    }

    logger.info(f"Risk metrics calculated: Sharpe={sharpe}, Beta={portfolio_beta}, MaxDD={max_dd}%")

    return metrics


def get_individual_stock_metrics(
    ticker: str,
    period: str = '1y'
) -> Dict[str, Any]:
    """
    Get risk metrics for an individual stock.

    Args:
        ticker: Stock ticker symbol
        period: Historical period

    Returns:
        Dict with stock metrics
    """
    prices = get_historical_prices([ticker, config.risk.benchmark], period=period)

    if prices.empty or ticker not in prices.columns:
        return {
            'beta': 1.0,
            'volatility': 0,
            'sharpe': 0,
            'max_drawdown': 0
        }

    returns = calculate_returns(prices)

    stock_returns = returns[ticker]
    sharpe = calculate_sharpe_ratio(stock_returns)
    volatility = calculate_volatility(stock_returns)
    beta = calculate_beta(ticker, period=period)

    max_dd, _, _ = calculate_max_drawdown(prices[ticker])

    return {
        'beta': beta,
        'volatility': round(volatility * 100, 2),
        'sharpe': sharpe,
        'max_drawdown': max_dd
    }
