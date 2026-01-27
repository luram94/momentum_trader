"""
Session State Helpers
======================
Manage Streamlit session state for the HQM Scanner app.
"""

import streamlit as st
from typing import Any, Optional


def init_session_state() -> None:
    """Initialize default session state values."""

    defaults = {
        # Authentication state
        'user_id': None,
        'user_email': None,
        'is_authenticated': False,
        'access_token': None,
        'refresh_token': None,

        # Scan state
        'scan_results': None,
        'scan_summary': None,
        'last_scan_time': None,

        # Backtest state
        'backtest_results': None,
        'backtest_running': False,

        # Filter defaults
        'portfolio_size': 10000,
        'num_positions': 8,
        'sma10_filter_enabled': False,
        'max_sma10_distance': 15.0,
        'rsi_filter_enabled': False,
        'rsi_min': 0,
        'rsi_max': 70,
        'volume_filter_enabled': False,
        'min_volume': 500000,
        'atr_filter_enabled': False,
        'max_atr_percent': 10.0,
        'diversification_enabled': False,
        'max_per_sector': 3,
        'sector_filter': [],

        # Operation status
        'operation_status': 'idle',  # idle, refreshing, scanning, backtesting
        'operation_progress': 0,
        'operation_message': '',
    }

    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def get_state(key: str, default: Any = None) -> Any:
    """
    Get a value from session state.

    Args:
        key: State key to retrieve
        default: Default value if key doesn't exist

    Returns:
        Value from session state or default
    """
    return st.session_state.get(key, default)


def set_state(key: str, value: Any) -> None:
    """
    Set a value in session state.

    Args:
        key: State key to set
        value: Value to store
    """
    st.session_state[key] = value


def update_operation_status(
    status: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None
) -> None:
    """
    Update operation status in session state.

    Args:
        status: Operation status (idle, refreshing, scanning, backtesting)
        progress: Progress percentage (0-100)
        message: Status message
    """
    if status is not None:
        st.session_state.operation_status = status
    if progress is not None:
        st.session_state.operation_progress = progress
    if message is not None:
        st.session_state.operation_message = message


def clear_scan_results() -> None:
    """Clear scan results from session state."""
    st.session_state.scan_results = None
    st.session_state.scan_summary = None
    st.session_state.last_scan_time = None


def clear_backtest_results() -> None:
    """Clear backtest results from session state."""
    st.session_state.backtest_results = None
    st.session_state.backtest_running = False
