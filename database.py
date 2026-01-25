"""
HQM Database Module
====================
SQLite storage for stock data, enabling:
- Fast scans without repeated API calls
- Historical tracking of HQM scores
- Watchlist management
- Portfolio tracking
- Backtesting capabilities
"""

from __future__ import annotations

import sqlite3
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import percentileofscore
from finvizfinance.screener.performance import Performance
from finvizfinance.screener.overview import Overview

from logger import get_logger
from config_loader import get_config

# Initialize logger
logger = get_logger('database')

# Get config
config = get_config()

# Database file path
DB_PATH = Path(__file__).parent / config.database.path


def get_connection() -> sqlite3.Connection:
    """
    Get database connection with row factory.

    Returns:
        SQLite connection with Row factory enabled.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    """Initialize database schema with all required tables."""
    conn = get_connection()
    cursor = conn.cursor()

    # Stocks table - current snapshot of all stocks
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            ticker TEXT PRIMARY KEY,
            exchange TEXT,
            sector TEXT,
            industry TEXT,
            market_cap REAL,
            price REAL,
            volume REAL,
            avg_volume REAL,
            return_1m REAL,
            return_3m REAL,
            return_6m REAL,
            return_1y REAL,
            rsi REAL,
            atr REAL,
            atr_percent REAL,
            beta REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # HQM History table - track scores over time for backtesting
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hqm_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            date DATE,
            hqm_score REAL,
            pct_1m REAL,
            pct_3m REAL,
            pct_6m REAL,
            pct_1y REAL,
            price REAL,
            rsi REAL,
            sma10_distance REAL,
            UNIQUE(ticker, date)
        )
    ''')

    # Scans table - log of portfolio scans
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            portfolio_size REAL,
            num_positions INTEGER,
            total_invested REAL,
            cash_remaining REAL,
            filters_applied TEXT,
            sharpe_ratio REAL,
            expected_return REAL
        )
    ''')

    # Scan positions - stocks selected in each scan
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scan_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER,
            ticker TEXT,
            hqm_score REAL,
            shares INTEGER,
            value REAL,
            weight REAL,
            entry_price REAL,
            sector TEXT,
            FOREIGN KEY (scan_id) REFERENCES scans(id)
        )
    ''')

    # Metadata table for tracking refresh times
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Watchlist table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT UNIQUE,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            target_entry_price REAL,
            notes TEXT,
            alert_enabled INTEGER DEFAULT 0,
            alert_threshold REAL
        )
    ''')

    # Portfolio tracking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            shares INTEGER,
            entry_price REAL,
            entry_date DATE,
            exit_price REAL,
            exit_date DATE,
            status TEXT DEFAULT 'open',
            notes TEXT,
            hqm_score_at_entry REAL,
            UNIQUE(ticker, entry_date)
        )
    ''')

    # Portfolio history for tracking value over time
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE UNIQUE,
            total_value REAL,
            cash REAL,
            invested REAL,
            daily_return REAL,
            cumulative_return REAL
        )
    ''')

    # Backtest results table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            start_date DATE,
            end_date DATE,
            initial_capital REAL,
            final_value REAL,
            total_return REAL,
            sharpe_ratio REAL,
            max_drawdown REAL,
            win_rate REAL,
            num_trades INTEGER,
            parameters TEXT
        )
    ''')

    # Sector performance tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sector_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            sector TEXT,
            avg_hqm_score REAL,
            stock_count INTEGER,
            avg_return_1m REAL,
            avg_return_3m REAL,
            UNIQUE(date, sector)
        )
    ''')

    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")


def get_last_refresh() -> Optional[datetime]:
    """
    Get timestamp of last data refresh.

    Returns:
        Datetime of last refresh or None if never refreshed.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM metadata WHERE key = 'last_refresh'")
    row = cursor.fetchone()
    conn.close()

    if row:
        return datetime.fromisoformat(row['value'])
    return None


def set_last_refresh(timestamp: Optional[datetime] = None) -> None:
    """
    Set last refresh timestamp.

    Args:
        timestamp: Timestamp to set. Uses current time if None.
    """
    if timestamp is None:
        timestamp = datetime.now()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_refresh', ?)
    ''', (timestamp.isoformat(),))
    conn.commit()
    conn.close()


def get_data_age_hours() -> float:
    """
    Get age of data in hours.

    Returns:
        Hours since last refresh, or infinity if never refreshed.
    """
    last_refresh = get_last_refresh()
    if last_refresh is None:
        return float('inf')
    return (datetime.now() - last_refresh).total_seconds() / 3600


def fetch_and_store_data(
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Dict[str, Any]:
    """
    Fetch fresh data from FinViz and store in database.

    Args:
        progress_callback: Optional function(progress, message) for UI updates

    Returns:
        dict with stats about the refresh
    """
    init_database()

    stats: Dict[str, Any] = {
        'nyse_count': 0,
        'nasdaq_count': 0,
        'total_stored': 0,
        'duration_seconds': 0
    }

    start_time = datetime.now()

    def update_progress(pct: int, msg: str) -> None:
        if progress_callback:
            progress_callback(pct, msg)
        logger.debug(f"Progress {pct}%: {msg}")

    update_progress(5, 'Connecting to FinViz...')

    exchanges = config.data.exchanges
    all_data: List[pd.DataFrame] = []

    for i, exchange in enumerate(exchanges):
        update_progress(10 + (i * 35), f'Fetching {exchange} data...')
        logger.info(f"Fetching data for {exchange}")

        try:
            # Get Overview data (includes sector)
            filters = {'Exchange': exchange, 'Market Cap.': config.data.min_market_cap}

            screener_overview = Overview()
            screener_overview.set_filter(filters_dict=filters)
            df_overview = screener_overview.screener_view(verbose=0)
            df_base = df_overview[['Ticker', 'Market Cap', 'Price', 'Volume', 'Sector', 'Industry']].copy()

            update_progress(20 + (i * 35), f'Fetching {exchange} performance...')

            # Get Performance data
            screener_perf = Performance()
            screener_perf.set_filter(filters_dict=filters)
            df_perf = screener_perf.screener_view(verbose=0)

            perf_columns = ['Ticker', 'Perf Month', 'Perf Quart', 'Perf Half', 'Perf Year']
            df_returns = df_perf[perf_columns].copy()

            # Merge
            df_merged = pd.merge(df_base, df_returns, on='Ticker', how='inner')
            df_merged.columns = [
                'Ticker', 'Market_Cap', 'Price', 'Volume', 'Sector', 'Industry',
                'Return_1M', 'Return_3M', 'Return_6M', 'Return_1Y'
            ]
            df_merged['Exchange'] = exchange

            all_data.append(df_merged)

            if exchange == 'NYSE':
                stats['nyse_count'] = len(df_merged)
            else:
                stats['nasdaq_count'] = len(df_merged)

            logger.info(f"Fetched {len(df_merged)} stocks from {exchange}")

        except Exception as e:
            logger.error(f"Error fetching {exchange}: {e}")
            raise

    update_progress(80, 'Storing data in database...')

    # Combine and deduplicate
    combined_df = pd.concat(all_data, ignore_index=True)
    df = combined_df.drop_duplicates(subset='Ticker', keep='first')

    # Remove rows with missing return data
    return_columns = ['Return_1M', 'Return_3M', 'Return_6M', 'Return_1Y']
    df = df.dropna(subset=return_columns)

    # Store in database
    conn = get_connection()
    cursor = conn.cursor()

    # Clear existing stocks and insert fresh data
    cursor.execute('DELETE FROM stocks')

    for _, row in df.iterrows():
        cursor.execute('''
            INSERT INTO stocks (ticker, exchange, sector, industry, market_cap, price,
                              volume, avg_volume, return_1m, return_3m, return_6m, return_1y, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            row['Ticker'],
            row['Exchange'],
            row.get('Sector', ''),
            row.get('Industry', ''),
            row['Market_Cap'],
            row['Price'],
            row.get('Volume', 0),
            row.get('Volume', 0),  # Use Volume as fallback for Avg Volume (not available in overview)
            row['Return_1M'],
            row['Return_3M'],
            row['Return_6M'],
            row['Return_1Y'],
            datetime.now().isoformat()
        ))

    conn.commit()
    conn.close()

    # Update metadata
    set_last_refresh()

    stats['total_stored'] = len(df)
    stats['duration_seconds'] = (datetime.now() - start_time).total_seconds()

    update_progress(100, 'Data refresh complete!')
    logger.info(f"Data refresh complete: {stats['total_stored']} stocks stored")

    return stats


def get_stock_count() -> int:
    """
    Get count of stocks in database.

    Returns:
        Number of stocks in database.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM stocks')
    row = cursor.fetchone()
    conn.close()
    return row['count'] if row else 0


def get_technical_indicators(
    tickers: List[str],
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Dict[str, Dict[str, Optional[float]]]:
    """
    Calculate technical indicators for a list of tickers.

    Calculates:
    - SMA10 distance
    - RSI (14-day)
    - ATR (14-day)

    Args:
        tickers: List of ticker symbols
        progress_callback: Optional progress callback function

    Returns:
        Dict mapping ticker to indicator values
    """
    if not tickers:
        return {}

    results: Dict[str, Dict[str, Optional[float]]] = {}
    batch_size = config.rate_limits.yfinance_batch_size

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        batch_str = ' '.join(batch)

        try:
            # Download last 30 days of data
            data = yf.download(batch_str, period='1mo', progress=False, threads=True)

            if data.empty:
                continue

            # Handle single ticker case
            if len(batch) == 1:
                ticker = batch[0]
                results[ticker] = _calculate_single_ticker_indicators(data, ticker, single=True)
            else:
                # Multiple tickers
                for ticker in batch:
                    results[ticker] = _calculate_single_ticker_indicators(data, ticker, single=False)

        except Exception as e:
            logger.warning(f"Error fetching indicators for batch: {e}")
            continue

    return results


def _calculate_single_ticker_indicators(
    data: pd.DataFrame,
    ticker: str,
    single: bool = False
) -> Dict[str, Optional[float]]:
    """
    Calculate indicators for a single ticker from downloaded data.

    Args:
        data: Downloaded price data
        ticker: Ticker symbol
        single: Whether this is single-ticker data (different structure)

    Returns:
        Dict with indicator values
    """
    result: Dict[str, Optional[float]] = {
        'sma10_distance': None,
        'rsi': None,
        'atr': None,
        'atr_percent': None
    }

    try:
        if single:
            if 'Close' not in data.columns or len(data) < 14:
                return result
            closes = data['Close']
            highs = data['High']
            lows = data['Low']
        else:
            if ('Close', ticker) not in data.columns:
                return result
            closes = data['Close'][ticker].dropna()
            highs = data['High'][ticker].dropna()
            lows = data['Low'][ticker].dropna()

            if len(closes) < 14:
                return result

        current_price = closes.iloc[-1]

        # SMA10 distance
        if len(closes) >= 10:
            sma10 = closes.rolling(window=10).mean().iloc[-1]
            if sma10 > 0:
                result['sma10_distance'] = round(((current_price - sma10) / sma10) * 100, 2)

        # RSI (14-day)
        if len(closes) >= 15:
            delta = closes.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            result['rsi'] = round(rsi.iloc[-1], 2)

        # ATR (14-day)
        if len(closes) >= 15:
            high_low = highs - lows
            high_close = np.abs(highs - closes.shift())
            low_close = np.abs(lows - closes.shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=14).mean().iloc[-1]
            result['atr'] = round(atr, 2)
            result['atr_percent'] = round((atr / current_price) * 100, 2)

    except Exception as e:
        logger.debug(f"Error calculating indicators for {ticker}: {e}")

    return result


def run_hqm_scan_from_db(
    portfolio_size: float,
    num_positions: int,
    save_scan: bool = True,
    max_sma10_distance: Optional[float] = None,
    rsi_filter: Optional[Tuple[float, float]] = None,
    min_volume: Optional[int] = None,
    max_atr_percent: Optional[float] = None,
    sector_filter: Optional[List[str]] = None,
    max_per_sector: Optional[int] = None
) -> Dict[str, Any]:
    """
    Run HQM scan using cached database data with advanced filters.

    Args:
        portfolio_size: Portfolio value in USD
        num_positions: Number of stocks to select
        save_scan: Whether to save scan to history
        max_sma10_distance: Max allowed distance from SMA10
        rsi_filter: Tuple of (min_rsi, max_rsi) to filter
        min_volume: Minimum average volume filter
        max_atr_percent: Maximum ATR as percent of price
        sector_filter: List of sectors to include (None = all)
        max_per_sector: Maximum positions per sector

    Returns:
        dict with results and summary
    """
    conn = get_connection()

    # Load all stocks from database
    df = pd.read_sql_query('''
        SELECT ticker as Ticker, exchange as Exchange, sector as Sector,
               market_cap as Market_Cap, price as Price,
               volume as Volume, avg_volume as Avg_Volume,
               return_1m as Return_1M, return_3m as Return_3M,
               return_6m as Return_6M, return_1y as Return_1Y
        FROM stocks
    ''', conn)

    if len(df) == 0:
        conn.close()
        logger.warning("No data in database")
        return {'success': False, 'error': 'No data in database. Please refresh data first.'}

    logger.info(f"Running HQM scan: {len(df)} stocks, ${portfolio_size:,.0f} portfolio, {num_positions} positions")

    # Apply volume filter early if specified
    if min_volume is not None and 'Avg_Volume' in df.columns:
        before_vol = len(df)
        df = df[df['Avg_Volume'] >= min_volume]
        logger.debug(f"Volume filter: {before_vol} -> {len(df)}")

    # Apply sector filter if specified
    if sector_filter is not None and len(sector_filter) > 0:
        df = df[df['Sector'].isin(sector_filter)]

    # Calculate percentile scores
    return_columns = ['Return_1M', 'Return_3M', 'Return_6M', 'Return_1Y']
    percentile_columns = ['Pct_1M', 'Pct_3M', 'Pct_6M', 'Pct_1Y']

    for return_col, pct_col in zip(return_columns, percentile_columns):
        valid_returns = df[return_col].dropna()
        df[pct_col] = df[return_col].apply(
            lambda x: percentileofscore(valid_returns, x, kind='mean')
            if pd.notna(x) else np.nan
        )

    # Calculate HQM Score
    df['HQM_Score'] = df[percentile_columns].mean(axis=1)
    df['Min_Percentile'] = df[percentile_columns].min(axis=1)

    # Quality filter (min percentile in all timeframes)
    total_before_filter = len(df)
    min_pct = config.strategy.min_percentile_threshold
    df = df[df['Min_Percentile'] >= min_pct]
    filtered_out = total_before_filter - len(df)

    logger.debug(f"Quality filter: {total_before_filter} -> {len(df)} (removed {filtered_out})")

    # Sort by HQM Score
    df = df.sort_values('HQM_Score', ascending=False)

    # Get more candidates than needed to allow for filtering
    candidates_multiplier = 3 if any([max_sma10_distance, rsi_filter, max_atr_percent]) else 1.5
    candidates_count = min(int(num_positions * candidates_multiplier), len(df))
    df_candidates = df.head(candidates_count).copy()

    # Calculate technical indicators for candidates
    tickers = df_candidates['Ticker'].tolist()
    indicators = get_technical_indicators(tickers)

    # Add indicators to dataframe
    df_candidates['SMA10_Distance'] = df_candidates['Ticker'].map(
        lambda t: indicators.get(t, {}).get('sma10_distance')
    )
    df_candidates['RSI'] = df_candidates['Ticker'].map(
        lambda t: indicators.get(t, {}).get('rsi')
    )
    df_candidates['ATR_Percent'] = df_candidates['Ticker'].map(
        lambda t: indicators.get(t, {}).get('atr_percent')
    )

    # Apply filters
    filtered_by_sma10 = 0
    filtered_by_rsi = 0
    filtered_by_atr = 0

    if max_sma10_distance is not None:
        before = len(df_candidates)
        df_candidates = df_candidates[
            (df_candidates['SMA10_Distance'].isna()) |
            (df_candidates['SMA10_Distance'] <= max_sma10_distance)
        ]
        filtered_by_sma10 = before - len(df_candidates)

    if rsi_filter is not None:
        min_rsi, max_rsi = rsi_filter
        before = len(df_candidates)
        df_candidates = df_candidates[
            (df_candidates['RSI'].isna()) |
            ((df_candidates['RSI'] >= min_rsi) & (df_candidates['RSI'] <= max_rsi))
        ]
        filtered_by_rsi = before - len(df_candidates)

    if max_atr_percent is not None:
        before = len(df_candidates)
        df_candidates = df_candidates[
            (df_candidates['ATR_Percent'].isna()) |
            (df_candidates['ATR_Percent'] <= max_atr_percent)
        ]
        filtered_by_atr = before - len(df_candidates)

    # Apply sector diversification if specified
    if max_per_sector is not None and max_per_sector > 0:
        df_diversified = pd.DataFrame()
        sector_counts: Dict[str, int] = {}

        for _, row in df_candidates.iterrows():
            sector = row.get('Sector', 'Unknown')
            if sector_counts.get(sector, 0) < max_per_sector:
                df_diversified = pd.concat([df_diversified, row.to_frame().T])
                sector_counts[sector] = sector_counts.get(sector, 0) + 1

            if len(df_diversified) >= num_positions:
                break

        df_candidates = df_diversified

    # Select top N from remaining candidates
    df = df_candidates.head(num_positions)

    if len(df) == 0:
        conn.close()
        return {'success': False, 'error': 'No stocks passed all filters. Try relaxing filter criteria.'}

    # Calculate position sizes
    allocation_per_stock = portfolio_size / len(df)
    df['Allocation'] = allocation_per_stock
    df['Weight'] = 100 / len(df)
    df['Shares'] = df['Price'].apply(
        lambda price: math.floor(allocation_per_stock / price) if price > 0 else 0
    )
    df['Value'] = df['Shares'] * df['Price']

    total_invested = df['Value'].sum()
    cash_remaining = portfolio_size - total_invested

    # Format market cap
    def format_market_cap(value: float) -> str:
        if pd.isna(value):
            return '-'
        value_billions = value / 1e9
        if value_billions >= 1000:
            return f"{value_billions / 1000:.1f}T"
        return f"{value_billions:.1f}B"

    df['Market_Cap_Display'] = df['Market_Cap'].apply(format_market_cap)

    # Round values
    for col in ['Return_1M', 'Return_3M', 'Return_6M', 'Return_1Y']:
        df[col] = df[col].round(4)
    for col in ['Pct_1M', 'Pct_3M', 'Pct_6M', 'Pct_1Y', 'HQM_Score']:
        df[col] = df[col].round(1)
    df['Weight'] = df['Weight'].round(1)
    df['Value'] = df['Value'].round(2)

    # Save scan to history if requested
    scan_id = None
    if save_scan:
        cursor = conn.cursor()

        # Build filters applied string
        filters_applied = []
        if max_sma10_distance:
            filters_applied.append(f"SMA10<={max_sma10_distance}%")
        if rsi_filter:
            filters_applied.append(f"RSI {rsi_filter[0]}-{rsi_filter[1]}")
        if min_volume:
            filters_applied.append(f"Vol>={min_volume:,}")
        if max_atr_percent:
            filters_applied.append(f"ATR<={max_atr_percent}%")
        if max_per_sector:
            filters_applied.append(f"Max {max_per_sector}/sector")

        # Save scan metadata
        cursor.execute('''
            INSERT INTO scans (portfolio_size, num_positions, total_invested, cash_remaining, filters_applied)
            VALUES (?, ?, ?, ?, ?)
        ''', (portfolio_size, num_positions, total_invested, cash_remaining, ', '.join(filters_applied)))
        scan_id = cursor.lastrowid

        # Save positions
        for _, row in df.iterrows():
            cursor.execute('''
                INSERT INTO scan_positions (scan_id, ticker, hqm_score, shares, value, weight, entry_price, sector)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (scan_id, row['Ticker'], row['HQM_Score'], row['Shares'], row['Value'], row['Weight'], row['Price'], row.get('Sector', '')))

        # Save HQM history
        today = datetime.now().date().isoformat()
        for _, row in df.iterrows():
            cursor.execute('''
                INSERT OR REPLACE INTO hqm_history
                (ticker, date, hqm_score, pct_1m, pct_3m, pct_6m, pct_1y, price, rsi, sma10_distance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (row['Ticker'], today, row['HQM_Score'],
                  row['Pct_1M'], row['Pct_3M'], row['Pct_6M'], row['Pct_1Y'], row['Price'],
                  row.get('RSI'), row.get('SMA10_Distance')))

        # Update sector performance
        sector_stats = df.groupby('Sector').agg({
            'HQM_Score': 'mean',
            'Ticker': 'count',
            'Return_1M': 'mean',
            'Return_3M': 'mean'
        }).reset_index()

        for _, sector_row in sector_stats.iterrows():
            cursor.execute('''
                INSERT OR REPLACE INTO sector_performance
                (date, sector, avg_hqm_score, stock_count, avg_return_1m, avg_return_3m)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (today, sector_row['Sector'], sector_row['HQM_Score'],
                  sector_row['Ticker'], sector_row['Return_1M'], sector_row['Return_3M']))

        conn.commit()

    conn.close()

    # Prepare results
    result_columns = [
        'Ticker', 'Price', 'Market_Cap_Display', 'Exchange', 'Sector',
        'Return_1M', 'Pct_1M', 'Return_3M', 'Pct_3M',
        'Return_6M', 'Pct_6M', 'Return_1Y', 'Pct_1Y',
        'HQM_Score', 'SMA10_Distance', 'RSI', 'ATR_Percent',
        'Shares', 'Value', 'Weight'
    ]

    # Only include columns that exist
    available_columns = [c for c in result_columns if c in df.columns]
    results = df[available_columns].to_dict('records')

    # Get data age
    last_refresh = get_last_refresh()
    data_age_hours = get_data_age_hours()

    summary = {
        'total_scanned': get_stock_count(),
        'after_quality_filter': total_before_filter - filtered_out,
        'filtered_out': filtered_out,
        'filtered_by_sma10': filtered_by_sma10,
        'filtered_by_rsi': filtered_by_rsi,
        'filtered_by_atr': filtered_by_atr,
        'max_sma10_distance': max_sma10_distance,
        'selected': len(df),
        'total_invested': round(total_invested, 2),
        'cash_remaining': round(cash_remaining, 2),
        'portfolio_size': portfolio_size,
        'allocation_per_stock': round(allocation_per_stock, 2),
        'data_age_hours': round(data_age_hours, 1),
        'last_refresh': last_refresh.isoformat() if last_refresh else None,
        'scan_id': scan_id
    }

    logger.info(f"Scan complete: {len(df)} stocks selected, ${total_invested:,.2f} invested")

    return {'success': True, 'results': results, 'summary': summary}


def get_scan_history(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get recent scan history.

    Args:
        limit: Maximum number of scans to return

    Returns:
        List of scan records
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, scan_date, portfolio_size, num_positions, total_invested,
               cash_remaining, filters_applied
        FROM scans
        ORDER BY scan_date DESC
        LIMIT ?
    ''', (limit,))

    scans = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return scans


def get_hqm_history(ticker: str, days: int = 30) -> List[Dict[str, Any]]:
    """
    Get HQM score history for a ticker.

    Args:
        ticker: Stock ticker symbol
        days: Number of days of history

    Returns:
        List of history records
    """
    conn = get_connection()

    df = pd.read_sql_query('''
        SELECT date, hqm_score, pct_1m, pct_3m, pct_6m, pct_1y, price, rsi, sma10_distance
        FROM hqm_history
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT ?
    ''', conn, params=(ticker, days))

    conn.close()
    return df.to_dict('records')


# =============================================================================
# WATCHLIST FUNCTIONS
# =============================================================================

def add_to_watchlist(
    ticker: str,
    target_price: Optional[float] = None,
    notes: Optional[str] = None,
    alert_enabled: bool = False,
    alert_threshold: Optional[float] = None
) -> bool:
    """
    Add a ticker to the watchlist.

    Args:
        ticker: Stock ticker symbol
        target_price: Target entry price
        notes: User notes
        alert_enabled: Whether to enable alerts
        alert_threshold: Alert threshold (e.g., SMA distance)

    Returns:
        True if successful, False if already exists
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO watchlist (ticker, target_entry_price, notes, alert_enabled, alert_threshold)
            VALUES (?, ?, ?, ?, ?)
        ''', (ticker.upper(), target_price, notes, 1 if alert_enabled else 0, alert_threshold))
        conn.commit()
        logger.info(f"Added {ticker} to watchlist")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"{ticker} already in watchlist")
        return False
    finally:
        conn.close()


def remove_from_watchlist(ticker: str) -> bool:
    """
    Remove a ticker from the watchlist.

    Args:
        ticker: Stock ticker symbol

    Returns:
        True if removed, False if not found
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM watchlist WHERE ticker = ?', (ticker.upper(),))
    removed = cursor.rowcount > 0
    conn.commit()
    conn.close()

    if removed:
        logger.info(f"Removed {ticker} from watchlist")
    return removed


def get_watchlist() -> List[Dict[str, Any]]:
    """
    Get all watchlist items with current data.

    Returns:
        List of watchlist items with stock data
    """
    conn = get_connection()

    df = pd.read_sql_query('''
        SELECT w.*, s.price, s.return_1m, s.return_3m, s.sector
        FROM watchlist w
        LEFT JOIN stocks s ON w.ticker = s.ticker
        ORDER BY w.added_date DESC
    ''', conn)

    conn.close()
    return df.to_dict('records')


# =============================================================================
# PORTFOLIO TRACKING FUNCTIONS
# =============================================================================

def add_portfolio_position(
    ticker: str,
    shares: int,
    entry_price: float,
    entry_date: Optional[str] = None,
    hqm_score: Optional[float] = None,
    notes: Optional[str] = None
) -> int:
    """
    Add a position to portfolio tracking.

    Args:
        ticker: Stock ticker symbol
        shares: Number of shares
        entry_price: Entry price per share
        entry_date: Entry date (defaults to today)
        hqm_score: HQM score at entry
        notes: User notes

    Returns:
        Position ID
    """
    if entry_date is None:
        entry_date = datetime.now().date().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO portfolio_positions
        (ticker, shares, entry_price, entry_date, hqm_score_at_entry, notes, status)
        VALUES (?, ?, ?, ?, ?, ?, 'open')
    ''', (ticker.upper(), shares, entry_price, entry_date, hqm_score, notes))

    position_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"Added portfolio position: {shares} shares of {ticker} at ${entry_price}")
    return position_id


def close_portfolio_position(
    position_id: int,
    exit_price: float,
    exit_date: Optional[str] = None
) -> bool:
    """
    Close a portfolio position.

    Args:
        position_id: Position ID to close
        exit_price: Exit price per share
        exit_date: Exit date (defaults to today)

    Returns:
        True if successful
    """
    if exit_date is None:
        exit_date = datetime.now().date().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE portfolio_positions
        SET exit_price = ?, exit_date = ?, status = 'closed'
        WHERE id = ?
    ''', (exit_price, exit_date, position_id))

    success = cursor.rowcount > 0
    conn.commit()
    conn.close()

    if success:
        logger.info(f"Closed position {position_id} at ${exit_price}")
    return success


def get_portfolio_positions(include_closed: bool = False) -> List[Dict[str, Any]]:
    """
    Get portfolio positions.

    Args:
        include_closed: Whether to include closed positions

    Returns:
        List of position records
    """
    conn = get_connection()

    status_filter = '' if include_closed else "WHERE pp.status = 'open'"

    df = pd.read_sql_query(f'''
        SELECT pp.*, s.price as current_price, s.return_1m, s.sector
        FROM portfolio_positions pp
        LEFT JOIN stocks s ON pp.ticker = s.ticker
        {status_filter}
        ORDER BY pp.entry_date DESC
    ''', conn)

    conn.close()

    # Calculate P&L for each position
    results = df.to_dict('records')
    for pos in results:
        if pos.get('current_price') and pos.get('entry_price'):
            pos['unrealized_pnl'] = (pos['current_price'] - pos['entry_price']) * pos['shares']
            pos['unrealized_pnl_pct'] = ((pos['current_price'] / pos['entry_price']) - 1) * 100
        if pos.get('exit_price') and pos.get('entry_price'):
            pos['realized_pnl'] = (pos['exit_price'] - pos['entry_price']) * pos['shares']
            pos['realized_pnl_pct'] = ((pos['exit_price'] / pos['entry_price']) - 1) * 100

    return results


def get_portfolio_summary() -> Dict[str, Any]:
    """
    Get portfolio summary statistics.

    Returns:
        Dict with portfolio statistics
    """
    positions = get_portfolio_positions(include_closed=False)

    if not positions:
        return {
            'total_value': 0,
            'total_cost': 0,
            'total_pnl': 0,
            'total_pnl_pct': 0,
            'position_count': 0,
            'winning_positions': 0,
            'losing_positions': 0
        }

    total_value = sum(p.get('current_price', 0) * p['shares'] for p in positions if p.get('current_price'))
    total_cost = sum(p['entry_price'] * p['shares'] for p in positions)
    total_pnl = sum(p.get('unrealized_pnl', 0) for p in positions)

    winning = sum(1 for p in positions if p.get('unrealized_pnl', 0) > 0)
    losing = sum(1 for p in positions if p.get('unrealized_pnl', 0) < 0)

    return {
        'total_value': round(total_value, 2),
        'total_cost': round(total_cost, 2),
        'total_pnl': round(total_pnl, 2),
        'total_pnl_pct': round((total_pnl / total_cost * 100) if total_cost > 0 else 0, 2),
        'position_count': len(positions),
        'winning_positions': winning,
        'losing_positions': losing
    }


# =============================================================================
# SECTOR ANALYSIS FUNCTIONS
# =============================================================================

def get_sector_breakdown() -> List[Dict[str, Any]]:
    """
    Get sector breakdown from current scan results.

    Returns:
        List of sector statistics
    """
    conn = get_connection()

    df = pd.read_sql_query('''
        SELECT
            sector as Sector,
            COUNT(*) as Count,
            AVG(return_1m) as Avg_Return_1M,
            AVG(return_3m) as Avg_Return_3M,
            AVG(return_6m) as Avg_Return_6M,
            AVG(return_1y) as Avg_Return_1Y
        FROM stocks
        WHERE sector IS NOT NULL AND sector != ''
        GROUP BY sector
        ORDER BY Avg_Return_3M DESC
    ''', conn)

    conn.close()
    return df.to_dict('records')


def get_sector_hqm_scores() -> List[Dict[str, Any]]:
    """
    Get average HQM scores by sector from recent history.

    Returns:
        List of sector HQM statistics
    """
    conn = get_connection()

    df = pd.read_sql_query('''
        SELECT
            sector,
            AVG(avg_hqm_score) as avg_hqm,
            SUM(stock_count) as total_stocks,
            AVG(avg_return_1m) as avg_return_1m,
            AVG(avg_return_3m) as avg_return_3m
        FROM sector_performance
        WHERE date >= date('now', '-7 days')
        GROUP BY sector
        ORDER BY avg_hqm DESC
    ''', conn)

    conn.close()
    return df.to_dict('records')


# Initialize database on module import
init_database()
