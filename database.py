"""
HQM Database Module
====================
SQLite storage for stock data, enabling:
- Fast scans without repeated API calls
- Historical tracking of HQM scores
- Future backtesting capabilities
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from scipy.stats import percentileofscore
from finvizfinance.screener.performance import Performance
from finvizfinance.screener.overview import Overview
import yfinance as yf

# Database file path
DB_PATH = Path(__file__).parent / 'hqm_data.db'


def get_connection():
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    # Stocks table - current snapshot of all stocks
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            ticker TEXT PRIMARY KEY,
            exchange TEXT,
            market_cap REAL,
            price REAL,
            return_1m REAL,
            return_3m REAL,
            return_6m REAL,
            return_1y REAL,
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
            cash_remaining REAL
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

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


def get_last_refresh():
    """Get timestamp of last data refresh."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM metadata WHERE key = 'last_refresh'")
    row = cursor.fetchone()
    conn.close()

    if row:
        return datetime.fromisoformat(row['value'])
    return None


def set_last_refresh(timestamp=None):
    """Set last refresh timestamp."""
    if timestamp is None:
        timestamp = datetime.now()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_refresh', ?)
    ''', (timestamp.isoformat(),))
    conn.commit()
    conn.close()


def get_data_age_hours():
    """Get age of data in hours."""
    last_refresh = get_last_refresh()
    if last_refresh is None:
        return float('inf')
    return (datetime.now() - last_refresh).total_seconds() / 3600


def fetch_and_store_data(progress_callback=None):
    """
    Fetch fresh data from FinViz and store in database.

    Args:
        progress_callback: Optional function(progress, message) for UI updates

    Returns:
        dict with stats about the refresh
    """
    init_database()

    stats = {
        'nyse_count': 0,
        'nasdaq_count': 0,
        'total_stored': 0,
        'duration_seconds': 0
    }

    start_time = datetime.now()

    def update_progress(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)

    update_progress(5, 'Connecting to FinViz...')

    exchanges = ['NYSE', 'NASDAQ']
    all_data = []

    for i, exchange in enumerate(exchanges):
        update_progress(10 + (i * 35), f'Fetching {exchange} data...')

        try:
            # Get Overview data
            filters = {'Exchange': exchange, 'Market Cap.': '+Mid (over $2bln)'}

            screener_overview = Overview()
            screener_overview.set_filter(filters_dict=filters)
            df_overview = screener_overview.screener_view(verbose=0)
            df_base = df_overview[['Ticker', 'Market Cap', 'Price']].copy()

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
                'Ticker', 'Market_Cap', 'Price',
                'Return_1M', 'Return_3M', 'Return_6M', 'Return_1Y'
            ]
            df_merged['Exchange'] = exchange

            all_data.append(df_merged)

            if exchange == 'NYSE':
                stats['nyse_count'] = len(df_merged)
            else:
                stats['nasdaq_count'] = len(df_merged)

        except Exception as e:
            print(f"Error fetching {exchange}: {e}")
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
            INSERT INTO stocks (ticker, exchange, market_cap, price,
                              return_1m, return_3m, return_6m, return_1y, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            row['Ticker'],
            row['Exchange'],
            row['Market_Cap'],
            row['Price'],
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

    return stats


def get_stock_count():
    """Get count of stocks in database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM stocks')
    row = cursor.fetchone()
    conn.close()
    return row['count'] if row else 0


def get_sma10_distance(tickers, progress_callback=None):
    """
    Calculate the distance from current price to SMA10 for a list of tickers.

    Args:
        tickers: List of ticker symbols
        progress_callback: Optional function(pct, msg) for UI updates

    Returns:
        dict mapping ticker -> distance percentage (positive = above SMA10)
    """
    if not tickers:
        return {}

    results = {}
    batch_size = 50  # yfinance can handle batches

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        batch_str = ' '.join(batch)

        try:
            # Download last 20 days of data (need at least 10 for SMA10)
            data = yf.download(batch_str, period='1mo', progress=False, threads=True)

            if data.empty:
                continue

            # Handle single ticker case (different structure)
            if len(batch) == 1:
                ticker = batch[0]
                if 'Close' in data.columns and len(data) >= 10:
                    closes = data['Close']
                    sma10 = closes.rolling(window=10).mean().iloc[-1]
                    current_price = closes.iloc[-1]
                    if sma10 > 0:
                        distance = ((current_price - sma10) / sma10) * 100
                        results[ticker] = round(distance, 2)
            else:
                # Multiple tickers - data has MultiIndex columns
                for ticker in batch:
                    try:
                        if ('Close', ticker) in data.columns:
                            closes = data['Close'][ticker].dropna()
                            if len(closes) >= 10:
                                sma10 = closes.rolling(window=10).mean().iloc[-1]
                                current_price = closes.iloc[-1]
                                if sma10 > 0:
                                    distance = ((current_price - sma10) / sma10) * 100
                                    results[ticker] = round(distance, 2)
                    except Exception:
                        continue

        except Exception as e:
            print(f"Error fetching SMA10 data for batch: {e}")
            continue

    return results


def run_hqm_scan_from_db(portfolio_size, num_positions, save_scan=True, max_sma10_distance=None):
    """
    Run HQM scan using cached database data.

    This is FAST because it doesn't hit the API (except for SMA10 calculation).

    Args:
        portfolio_size: Portfolio value in USD
        num_positions: Number of stocks to select
        save_scan: Whether to save scan to history
        max_sma10_distance: Max allowed distance from SMA10 (e.g., 15 = filter out stocks >15% above SMA10)
                           Set to None to disable filtering (still shows the metric)

    Returns:
        dict with results and summary
    """
    conn = get_connection()

    # Load all stocks from database
    df = pd.read_sql_query('''
        SELECT ticker as Ticker, exchange as Exchange, market_cap as Market_Cap,
               price as Price, return_1m as Return_1M, return_3m as Return_3M,
               return_6m as Return_6M, return_1y as Return_1Y
        FROM stocks
    ''', conn)

    if len(df) == 0:
        conn.close()
        return {'success': False, 'error': 'No data in database. Please refresh data first.'}

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

    # Quality filter (min 25th percentile in all timeframes)
    total_before_filter = len(df)
    df = df[df['Min_Percentile'] >= 25]
    filtered_out = total_before_filter - len(df)

    # Sort by HQM Score
    df = df.sort_values('HQM_Score', ascending=False)

    # Get more candidates than needed to allow for SMA10 filtering
    candidates_multiplier = 3 if max_sma10_distance is not None else 1.5
    candidates_count = min(int(num_positions * candidates_multiplier), len(df))
    df_candidates = df.head(candidates_count).copy()

    # Calculate SMA10 distance for candidates
    tickers = df_candidates['Ticker'].tolist()
    sma10_distances = get_sma10_distance(tickers)

    # Add SMA10 distance to dataframe
    df_candidates['SMA10_Distance'] = df_candidates['Ticker'].map(
        lambda t: sma10_distances.get(t, None)
    )

    # Apply SMA10 filter if specified
    filtered_by_sma10 = 0
    if max_sma10_distance is not None:
        before_sma10_filter = len(df_candidates)
        # Keep stocks where SMA10_Distance is None (couldn't calculate) or within threshold
        df_candidates = df_candidates[
            (df_candidates['SMA10_Distance'].isna()) |
            (df_candidates['SMA10_Distance'] <= max_sma10_distance)
        ]
        filtered_by_sma10 = before_sma10_filter - len(df_candidates)

    # Select top N from remaining candidates
    df = df_candidates.head(num_positions)

    # Calculate position sizes
    import math
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
    def format_market_cap(value):
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

        # Save scan metadata
        cursor.execute('''
            INSERT INTO scans (portfolio_size, num_positions, total_invested, cash_remaining)
            VALUES (?, ?, ?, ?)
        ''', (portfolio_size, num_positions, total_invested, cash_remaining))
        scan_id = cursor.lastrowid

        # Save positions
        for _, row in df.iterrows():
            cursor.execute('''
                INSERT INTO scan_positions (scan_id, ticker, hqm_score, shares, value, weight)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (scan_id, row['Ticker'], row['HQM_Score'], row['Shares'], row['Value'], row['Weight']))

        # Save HQM history (for backtesting)
        today = datetime.now().date().isoformat()
        for _, row in df.iterrows():
            cursor.execute('''
                INSERT OR REPLACE INTO hqm_history
                (ticker, date, hqm_score, pct_1m, pct_3m, pct_6m, pct_1y, price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (row['Ticker'], today, row['HQM_Score'],
                  row['Pct_1M'], row['Pct_3M'], row['Pct_6M'], row['Pct_1Y'], row['Price']))

        conn.commit()

    conn.close()

    # Prepare results
    results = df[[
        'Ticker', 'Price', 'Market_Cap_Display', 'Exchange',
        'Return_1M', 'Pct_1M', 'Return_3M', 'Pct_3M',
        'Return_6M', 'Pct_6M', 'Return_1Y', 'Pct_1Y',
        'HQM_Score', 'SMA10_Distance', 'Shares', 'Value', 'Weight'
    ]].to_dict('records')

    # Get data age
    last_refresh = get_last_refresh()
    data_age_hours = get_data_age_hours()

    summary = {
        'total_scanned': get_stock_count(),
        'after_quality_filter': total_before_filter - filtered_out,
        'filtered_out': filtered_out,
        'filtered_by_sma10': filtered_by_sma10,
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

    return {'success': True, 'results': results, 'summary': summary}


def get_scan_history(limit=10):
    """Get recent scan history."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, scan_date, portfolio_size, num_positions, total_invested, cash_remaining
        FROM scans
        ORDER BY scan_date DESC
        LIMIT ?
    ''', (limit,))

    scans = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return scans


def get_hqm_history(ticker, days=30):
    """Get HQM score history for a ticker (for backtesting/charting)."""
    conn = get_connection()

    df = pd.read_sql_query('''
        SELECT date, hqm_score, pct_1m, pct_3m, pct_6m, pct_1y, price
        FROM hqm_history
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT ?
    ''', conn, params=(ticker, days))

    conn.close()
    return df.to_dict('records')


# Initialize database on module import
init_database()
