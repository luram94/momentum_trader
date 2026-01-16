"""
High Quality Momentum (HQM) Strategy
=====================================
Inspired by Qullamaggie's momentum trading approach.

This strategy identifies stocks with consistent "slow and steady" momentum
across multiple timeframes, filtering out low-quality momentum caused by
short-term news events.

Multi-timeframe approach:
- 1-month returns
- 3-month returns
- 6-month returns
- 1-year returns

Stocks must rank well across ALL timeframes (high quality momentum).
"""

import numpy as np
import pandas as pd
import math
from scipy.stats import percentileofscore
from finvizfinance.screener.performance import Performance
from finvizfinance.screener.overview import Overview

# =============================================================================
# CONFIGURATION - Adjust these for your portfolio
# =============================================================================

PORTFOLIO_SIZE = 10000          # Your portfolio size in USD
NUM_POSITIONS = 8               # Number of stocks to hold (7-10 recommended for $10k)
MIN_MARKET_CAP = '+Mid (over $2bln)'  # Filter: Mid-cap and above
EXCHANGES = ['NYSE', 'NASDAQ']  # Exchanges to scan
OUTPUT_FILE = 'hqm_portfolio.xlsx'  # Excel output filename

# =============================================================================
# DATA COLLECTION
# =============================================================================

def get_exchange_data(exchange_name, min_market_cap=MIN_MARKET_CAP):
    """
    Fetch stocks with Market Cap, Price, and multi-timeframe returns.

    Args:
        exchange_name: 'NYSE' or 'NASDAQ'
        min_market_cap: Market cap filter string for finviz

    Returns:
        DataFrame with ticker, market cap, price, and performance metrics
    """
    print(f"\n{'='*60}")
    print(f"Downloading {exchange_name} (Market Cap: {min_market_cap})")
    print(f"{'='*60}")

    filters = {'Exchange': exchange_name}
    if min_market_cap:
        filters['Market Cap.'] = min_market_cap

    # Get Market Cap and Price from Overview screener
    print("  Fetching Market Cap and Price...")
    screener_overview = Overview()
    screener_overview.set_filter(filters_dict=filters)
    df_overview = screener_overview.screener_view(verbose=0)
    df_base = df_overview[['Ticker', 'Market Cap', 'Price']].copy()
    print(f"  Found {len(df_base)} stocks")

    # Get Performance metrics (all timeframes)
    print("  Fetching Performance metrics...")
    screener_perf = Performance()
    screener_perf.set_filter(filters_dict=filters)
    df_perf = screener_perf.screener_view(verbose=0)

    # Select multi-timeframe returns
    perf_columns = ['Ticker', 'Perf Month', 'Perf Quart', 'Perf Half', 'Perf Year']
    df_returns = df_perf[perf_columns].copy()
    print(f"  Found {len(df_returns)} performance records")

    # Merge data
    print("  Merging datasets...")
    df_merged = pd.merge(df_base, df_returns, on='Ticker', how='inner')
    df_merged.columns = [
        'Ticker', 'Market_Cap', 'Price',
        'Return_1M', 'Return_3M', 'Return_6M', 'Return_1Y'
    ]
    df_merged['Exchange'] = exchange_name

    print(f"  Completed: {len(df_merged)} stocks with full data")

    return df_merged


def collect_all_stocks():
    """
    Collect stock data from all configured exchanges.

    Returns:
        DataFrame with all stocks, duplicates removed
    """
    all_data = []

    for exchange in EXCHANGES:
        df = get_exchange_data(exchange)
        all_data.append(df)

    print(f"\n{'='*60}")
    print("Combining data from all exchanges...")
    print(f"{'='*60}")

    combined_df = pd.concat(all_data, ignore_index=True)
    df_unique = combined_df.drop_duplicates(subset='Ticker', keep='first')

    duplicates_removed = len(combined_df) - len(df_unique)
    print(f"  Total unique tickers: {len(df_unique)}")
    print(f"  Duplicates removed: {duplicates_removed}")

    # Remove stocks with missing return data (required for HQM scoring)
    return_columns = ['Return_1M', 'Return_3M', 'Return_6M', 'Return_1Y']
    before_clean = len(df_unique)
    df_clean = df_unique.dropna(subset=return_columns)
    removed_missing = before_clean - len(df_clean)

    if removed_missing > 0:
        print(f"  Removed {removed_missing} stocks with missing return data")

    print(f"  Final count: {len(df_clean)} stocks with complete data")
    print(f"  Distribution: {dict(df_clean['Exchange'].value_counts())}")

    return df_clean


# =============================================================================
# HQM SCORING SYSTEM
# =============================================================================

def calculate_percentile_scores(df):
    """
    Calculate percentile scores for each momentum timeframe.

    High percentile = strong momentum relative to universe.
    Stocks ranking consistently high across all timeframes = High Quality Momentum.

    Args:
        df: DataFrame with return columns

    Returns:
        DataFrame with added percentile score columns
    """
    print(f"\n{'='*60}")
    print("Calculating HQM Percentile Scores...")
    print(f"{'='*60}")

    # Define timeframe columns
    return_columns = ['Return_1M', 'Return_3M', 'Return_6M', 'Return_1Y']
    percentile_columns = ['Pct_1M', 'Pct_3M', 'Pct_6M', 'Pct_1Y']

    df = df.copy()

    # Calculate percentile for each timeframe
    for return_col, pct_col in zip(return_columns, percentile_columns):
        # Remove NaN values for percentile calculation
        valid_returns = df[return_col].dropna()

        # Calculate percentile score (0-100)
        df[pct_col] = df[return_col].apply(
            lambda x: percentileofscore(valid_returns, x, kind='mean')
            if pd.notna(x) else np.nan
        )

        avg_pct = df[pct_col].mean()
        print(f"  {return_col} -> {pct_col}: avg percentile = {avg_pct:.1f}")

    return df, percentile_columns


def calculate_hqm_score(df, percentile_columns):
    """
    Calculate composite High Quality Momentum (HQM) score.

    HQM Score = Average of all percentile scores

    Qullamaggie insight: True momentum leaders show consistent strength
    across ALL timeframes, not just one lucky period.

    Args:
        df: DataFrame with percentile columns
        percentile_columns: List of percentile column names

    Returns:
        DataFrame with HQM_Score column added
    """
    print(f"\n{'='*60}")
    print("Calculating Composite HQM Score...")
    print(f"{'='*60}")

    df = df.copy()

    # HQM Score = mean of all percentile scores
    df['HQM_Score'] = df[percentile_columns].mean(axis=1)

    # Also calculate minimum percentile (identifies consistency)
    df['Min_Percentile'] = df[percentile_columns].min(axis=1)

    print(f"  HQM Score range: {df['HQM_Score'].min():.1f} - {df['HQM_Score'].max():.1f}")
    print(f"  Mean HQM Score: {df['HQM_Score'].mean():.1f}")

    return df


def filter_quality_momentum(df, num_positions=NUM_POSITIONS, min_percentile=25):
    """
    Filter for high quality momentum stocks.

    Selection criteria:
    1. Sort by HQM_Score (highest first)
    2. Require minimum percentile threshold across all timeframes
       (avoids stocks with one great period but otherwise weak)

    Args:
        df: DataFrame with HQM scores
        num_positions: Number of stocks to select
        min_percentile: Minimum percentile in ANY timeframe (quality filter)

    Returns:
        DataFrame with top HQM stocks
    """
    print(f"\n{'='*60}")
    print(f"Selecting Top {num_positions} HQM Stocks...")
    print(f"{'='*60}")

    df = df.copy()

    # Quality filter: Remove stocks weak in ANY timeframe
    # This is the Qullamaggie insight - consistency matters
    before_filter = len(df)
    df = df[df['Min_Percentile'] >= min_percentile]
    after_filter = len(df)

    print(f"  Quality filter (min {min_percentile}th pct in all TFs):")
    print(f"    Before: {before_filter} stocks")
    print(f"    After: {after_filter} stocks")
    print(f"    Removed: {before_filter - after_filter} inconsistent performers")

    # Sort by HQM Score and select top N
    df = df.sort_values('HQM_Score', ascending=False)
    df = df.head(num_positions)

    print(f"\n  Selected {len(df)} stocks for portfolio")

    return df


# =============================================================================
# PORTFOLIO CONSTRUCTION
# =============================================================================

def format_market_cap(value):
    """Format market cap for display (e.g., 150.5B, 1.2T)."""
    if pd.isna(value):
        return '-'
    value_billions = value / 1e9
    if value_billions >= 1000:
        return f"{value_billions / 1000:.1f}T"
    else:
        return f"{value_billions:.1f}B"


def calculate_position_sizes(df, portfolio_size=PORTFOLIO_SIZE):
    """
    Calculate number of shares to buy for each position.

    Uses equal-weight allocation for simplicity.
    Each position gets portfolio_size / num_positions.

    Args:
        df: DataFrame with selected stocks
        portfolio_size: Total portfolio value in USD

    Returns:
        DataFrame with position sizing columns
    """
    print(f"\n{'='*60}")
    print(f"Portfolio Construction (${portfolio_size:,.0f})")
    print(f"{'='*60}")

    df = df.copy()
    num_positions = len(df)

    # Equal weight allocation
    allocation_per_stock = portfolio_size / num_positions
    position_weight = 100 / num_positions

    print(f"  Positions: {num_positions}")
    print(f"  Allocation per stock: ${allocation_per_stock:,.2f} ({position_weight:.1f}%)")

    # Calculate shares to buy
    df['Allocation_USD'] = allocation_per_stock
    df['Position_Weight'] = position_weight
    df['Shares_to_Buy'] = df['Price'].apply(
        lambda price: math.floor(allocation_per_stock / price) if price > 0 else 0
    )
    df['Actual_Value'] = df['Shares_to_Buy'] * df['Price']

    # Calculate total invested vs cash left over
    total_invested = df['Actual_Value'].sum()
    cash_remaining = portfolio_size - total_invested

    print(f"\n  Total invested: ${total_invested:,.2f}")
    print(f"  Cash remaining: ${cash_remaining:,.2f}")

    return df


def prepare_output_dataframe(df):
    """
    Prepare final DataFrame for display and export.

    Args:
        df: DataFrame with all calculations

    Returns:
        Clean DataFrame ready for output
    """
    df = df.copy()

    # Format market cap for display
    df['Market_Cap_Display'] = df['Market_Cap'].apply(format_market_cap)

    # Round percentages for display
    for col in ['Return_1M', 'Return_3M', 'Return_6M', 'Return_1Y']:
        df[col] = df[col].round(2)

    for col in ['Pct_1M', 'Pct_3M', 'Pct_6M', 'Pct_1Y', 'HQM_Score']:
        df[col] = df[col].round(1)

    # Select and order columns for output
    output_columns = [
        'Ticker',
        'Price',
        'Market_Cap_Display',
        'Return_1M', 'Pct_1M',
        'Return_3M', 'Pct_3M',
        'Return_6M', 'Pct_6M',
        'Return_1Y', 'Pct_1Y',
        'HQM_Score',
        'Shares_to_Buy',
        'Actual_Value',
        'Position_Weight',
        'Exchange'
    ]

    df = df[output_columns].reset_index(drop=True)

    # Rename for cleaner display
    df.columns = [
        'Ticker', 'Price', 'Market Cap',
        '1M Return', '1M Pct',
        '3M Return', '3M Pct',
        '6M Return', '6M Pct',
        '1Y Return', '1Y Pct',
        'HQM Score',
        'Shares', 'Value', 'Weight %', 'Exchange'
    ]

    return df


# =============================================================================
# EXPORT
# =============================================================================

def export_to_excel(df, filename=OUTPUT_FILE):
    """
    Export portfolio to Excel with formatting.

    Args:
        df: Final portfolio DataFrame
        filename: Output filename
    """
    print(f"\n{'='*60}")
    print(f"Exporting to {filename}...")
    print(f"{'='*60}")

    # Create Excel writer with xlsxwriter engine
    writer = pd.ExcelWriter(filename, engine='xlsxwriter')
    df.to_excel(writer, sheet_name='HQM Portfolio', index=False)

    # Get workbook and worksheet
    workbook = writer.book
    worksheet = writer.sheets['HQM Portfolio']

    # Define formats
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#1a1a2e',
        'font_color': 'white',
        'border': 1,
        'align': 'center'
    })

    # Set column widths
    column_widths = {
        'A': 8,   # Ticker
        'B': 10,  # Price
        'C': 12,  # Market Cap
        'D': 10,  # 1M Return
        'E': 8,   # 1M Pct
        'F': 10,  # 3M Return
        'G': 8,   # 3M Pct
        'H': 10,  # 6M Return
        'I': 8,   # 6M Pct
        'J': 10,  # 1Y Return
        'K': 8,   # 1Y Pct
        'L': 10,  # HQM Score
        'M': 8,   # Shares
        'N': 12,  # Value
        'O': 10,  # Weight
        'P': 10,  # Exchange
    }

    for col, width in column_widths.items():
        worksheet.set_column(f'{col}:{col}', width)

    # Format header row
    for col_num, value in enumerate(df.columns.values):
        worksheet.write(0, col_num, value, header_format)

    writer.close()
    print(f"  Exported successfully!")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_hqm_strategy(portfolio_size=None, num_positions=None):
    """
    Execute the full HQM strategy pipeline.

    Args:
        portfolio_size: Override default portfolio size
        num_positions: Override default number of positions
    """
    # Use provided values or defaults
    port_size = portfolio_size if portfolio_size else PORTFOLIO_SIZE
    num_pos = num_positions if num_positions else NUM_POSITIONS

    print("\n" + "="*60)
    print("  HIGH QUALITY MOMENTUM (HQM) STRATEGY")
    print("  Inspired by Qullamaggie's momentum approach")
    print("="*60)
    print(f"\n  Portfolio Size: ${port_size:,}")
    print(f"  Target Positions: {num_pos}")
    print(f"  Position Size: ~{100/num_pos:.1f}% each")

    # Step 1: Collect data
    df = collect_all_stocks()

    # Step 2: Calculate percentile scores
    df, pct_cols = calculate_percentile_scores(df)

    # Step 3: Calculate HQM composite score
    df = calculate_hqm_score(df, pct_cols)

    # Step 4: Filter for quality momentum
    df = filter_quality_momentum(df, num_pos)

    # Step 5: Calculate position sizes
    df = calculate_position_sizes(df, port_size)

    # Step 6: Prepare output
    df_output = prepare_output_dataframe(df)

    # Step 7: Display results
    print(f"\n{'='*60}")
    print("HQM PORTFOLIO - TOP PICKS")
    print(f"{'='*60}\n")

    # Display key columns
    display_cols = ['Ticker', 'Price', 'HQM Score', '1Y Return', 'Shares', 'Value']
    print(df_output[display_cols].to_string(index=False))

    # Step 8: Export to Excel
    export_to_excel(df_output)

    print(f"\n{'='*60}")
    print("Strategy execution complete!")
    print(f"{'='*60}")

    return df_output


# =============================================================================
# RUN STRATEGY
# =============================================================================

if __name__ == "__main__":
    # Interactive mode - ask for portfolio size
    print("\n" + "="*60)
    print("  HQM MOMENTUM SCANNER")
    print("="*60)

    # Get portfolio size from user
    while True:
        try:
            user_input = input(f"\nEnter portfolio size (default ${PORTFOLIO_SIZE:,}): ").strip()
            if user_input == "":
                port_size = PORTFOLIO_SIZE
            else:
                port_size = float(user_input.replace(",", "").replace("$", ""))
            break
        except ValueError:
            print("Invalid input. Please enter a number.")

    # Get number of positions from user
    while True:
        try:
            user_input = input(f"Enter number of positions (default {NUM_POSITIONS}): ").strip()
            if user_input == "":
                num_pos = NUM_POSITIONS
            else:
                num_pos = int(user_input)
                if num_pos < 1 or num_pos > 50:
                    print("Please enter a number between 1 and 50.")
                    continue
            break
        except ValueError:
            print("Invalid input. Please enter a number.")

    # Run the strategy
    portfolio = run_hqm_strategy(port_size, num_pos)
