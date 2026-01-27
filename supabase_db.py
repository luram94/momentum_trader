"""
Supabase Database Module
=========================
User-scoped database operations for watchlist and portfolio using Supabase.
Row-Level Security (RLS) handles user data isolation automatically.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import streamlit as st

from components.auth import get_authenticated_client, get_current_user_id, is_authenticated
from logger import get_logger

logger = get_logger('supabase_db')


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
    Add a ticker to the user's watchlist.

    Args:
        ticker: Stock ticker symbol
        target_price: Target entry price
        notes: User notes
        alert_enabled: Whether to enable alerts
        alert_threshold: Alert threshold (e.g., SMA distance)

    Returns:
        True if successful, False if already exists or error.
    """
    if not is_authenticated():
        logger.warning("Attempted to add to watchlist without authentication")
        return False

    client = get_authenticated_client()
    if not client:
        return False

    user_id = get_current_user_id()

    try:
        data = {
            'user_id': user_id,
            'ticker': ticker.upper(),
            'target_entry_price': target_price,
            'notes': notes,
            'alert_enabled': alert_enabled,
            'alert_threshold': alert_threshold
        }

        response = client.table('watchlist').insert(data).execute()

        if response.data:
            logger.info(f"Added {ticker} to watchlist for user {user_id}")
            return True
        return False

    except Exception as e:
        error_msg = str(e)
        if 'duplicate' in error_msg.lower() or '23505' in error_msg:
            logger.warning(f"{ticker} already in watchlist")
        else:
            logger.error(f"Error adding to watchlist: {error_msg}")
        return False


def remove_from_watchlist(ticker: str) -> bool:
    """
    Remove a ticker from the user's watchlist.

    Args:
        ticker: Stock ticker symbol

    Returns:
        True if removed, False if not found or error.
    """
    if not is_authenticated():
        return False

    client = get_authenticated_client()
    if not client:
        return False

    user_id = get_current_user_id()

    try:
        response = client.table('watchlist').delete().eq(
            'user_id', user_id
        ).eq(
            'ticker', ticker.upper()
        ).execute()

        if response.data:
            logger.info(f"Removed {ticker} from watchlist for user {user_id}")
            return True
        return False

    except Exception as e:
        logger.error(f"Error removing from watchlist: {e}")
        return False


def get_watchlist() -> List[Dict[str, Any]]:
    """
    Get the user's watchlist items.

    Returns:
        List of watchlist items (RLS filters to current user automatically).
    """
    if not is_authenticated():
        return []

    client = get_authenticated_client()
    if not client:
        return []

    try:
        response = client.table('watchlist').select('*').order(
            'added_date', desc=True
        ).execute()

        watchlist = response.data or []

        # Enrich with stock data from SQLite (shared market data)
        if watchlist:
            from database import get_connection
            conn = get_connection()

            for item in watchlist:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT price, return_1m, return_3m, sector
                    FROM stocks WHERE ticker = ?
                ''', (item['ticker'],))
                row = cursor.fetchone()

                if row:
                    item['price'] = row['price']
                    item['return_1m'] = row['return_1m']
                    item['return_3m'] = row['return_3m']
                    item['sector'] = row['sector']

            conn.close()

        return watchlist

    except Exception as e:
        logger.error(f"Error fetching watchlist: {e}")
        return []


# =============================================================================
# PORTFOLIO FUNCTIONS
# =============================================================================

def add_portfolio_position(
    ticker: str,
    shares: int,
    entry_price: float,
    entry_date: Optional[str] = None,
    hqm_score: Optional[float] = None,
    notes: Optional[str] = None
) -> Optional[str]:
    """
    Add a position to the user's portfolio.

    Args:
        ticker: Stock ticker symbol
        shares: Number of shares
        entry_price: Entry price per share
        entry_date: Entry date (defaults to today)
        hqm_score: HQM score at entry
        notes: User notes

    Returns:
        Position ID if successful, None otherwise.
    """
    if not is_authenticated():
        logger.warning("Attempted to add position without authentication")
        return None

    client = get_authenticated_client()
    if not client:
        return None

    user_id = get_current_user_id()

    if entry_date is None:
        entry_date = datetime.now().date().isoformat()

    try:
        data = {
            'user_id': user_id,
            'ticker': ticker.upper(),
            'shares': shares,
            'entry_price': float(entry_price),
            'entry_date': entry_date,
            'hqm_score_at_entry': hqm_score,
            'notes': notes,
            'status': 'open'
        }

        response = client.table('portfolio_positions').insert(data).execute()

        if response.data:
            position_id = response.data[0]['id']
            logger.info(f"Added position: {shares} shares of {ticker} at ${entry_price}")
            return position_id
        return None

    except Exception as e:
        logger.error(f"Error adding position: {e}")
        return None


def close_portfolio_position(
    position_id: str,
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
        True if successful.
    """
    if not is_authenticated():
        return False

    client = get_authenticated_client()
    if not client:
        return False

    if exit_date is None:
        exit_date = datetime.now().date().isoformat()

    try:
        response = client.table('portfolio_positions').update({
            'exit_price': float(exit_price),
            'exit_date': exit_date,
            'status': 'closed'
        }).eq('id', position_id).execute()

        if response.data:
            logger.info(f"Closed position {position_id} at ${exit_price}")
            return True
        return False

    except Exception as e:
        logger.error(f"Error closing position: {e}")
        return False


def get_portfolio_positions(include_closed: bool = False) -> List[Dict[str, Any]]:
    """
    Get the user's portfolio positions.

    Args:
        include_closed: Whether to include closed positions

    Returns:
        List of position records (RLS filters to current user automatically).
    """
    if not is_authenticated():
        return []

    client = get_authenticated_client()
    if not client:
        return []

    try:
        query = client.table('portfolio_positions').select('*')

        if not include_closed:
            query = query.eq('status', 'open')

        response = query.order('entry_date', desc=True).execute()

        positions = response.data or []

        # Enrich with current prices from SQLite (shared market data)
        if positions:
            from database import get_connection
            conn = get_connection()

            for pos in positions:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT price, return_1m, sector
                    FROM stocks WHERE ticker = ?
                ''', (pos['ticker'],))
                row = cursor.fetchone()

                if row:
                    pos['current_price'] = row['price']
                    pos['return_1m'] = row['return_1m']
                    pos['sector'] = row['sector']

                # Calculate P&L
                if pos.get('current_price') and pos.get('entry_price'):
                    pos['unrealized_pnl'] = (pos['current_price'] - pos['entry_price']) * pos['shares']
                    pos['unrealized_pnl_pct'] = ((pos['current_price'] / pos['entry_price']) - 1) * 100

                if pos.get('exit_price') and pos.get('entry_price'):
                    pos['realized_pnl'] = (pos['exit_price'] - pos['entry_price']) * pos['shares']
                    pos['realized_pnl_pct'] = ((pos['exit_price'] / pos['entry_price']) - 1) * 100

            conn.close()

        return positions

    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        return []


def get_portfolio_summary() -> Dict[str, Any]:
    """
    Get portfolio summary statistics for the current user.

    Returns:
        Dict with portfolio statistics.
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

    total_value = sum(
        p.get('current_price', 0) * p['shares']
        for p in positions if p.get('current_price')
    )
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
