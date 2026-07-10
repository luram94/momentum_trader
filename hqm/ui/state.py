"""
Session State Helpers
======================
Initialize Streamlit session state for the HQM Scanner app.

Filter and portfolio defaults come from config.yaml (single source of
truth); widgets bind to these keys and never pass their own defaults.
"""

import streamlit as st

from hqm.config_loader import get_config


def init_session_state() -> None:
    """Initialize default session state values from configuration."""
    config = get_config()

    defaults = {
        # Scan state
        'scan_results': None,
        'scan_summary': None,
        'last_scan_time': None,

        # Backtest state
        'backtest_results': None,

        # Portfolio defaults
        'portfolio_size': int(config.portfolio.default_size),
        'num_positions': int(config.portfolio.default_positions),

        # Filter defaults (filters themselves are opt-in checkboxes)
        'sma10_filter_enabled': False,
        'max_sma10_distance': float(config.scanner_filters.max_sma10_distance),
        'rsi_filter_enabled': False,
        'rsi_min': int(config.scanner_filters.min_rsi),
        'rsi_max': int(config.scanner_filters.max_rsi),
        'volume_filter_enabled': False,
        'min_volume': int(config.scanner_filters.min_avg_volume),
        'atr_filter_enabled': False,
        'max_atr_percent': float(config.scanner_filters.max_atr_percent),
        'diversification_enabled': False,
        'max_per_sector': int(config.scanner_filters.max_per_sector),
        'sector_filter': [],
    }

    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value
