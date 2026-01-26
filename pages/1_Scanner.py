"""
Scanner Page
=============
HQM Momentum Scanner with filters and results display.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from logger import get_logger
from config_loader import get_config
from database import (
    fetch_and_store_data,
    run_hqm_scan_from_db,
    get_data_age_hours,
    get_last_refresh,
    get_stock_count,
    get_sector_breakdown,
)
from risk_metrics import calculate_all_risk_metrics
from components.state import init_session_state
from components.charts import (
    create_allocation_chart,
    create_hqm_score_chart,
    create_returns_comparison_chart,
)

logger = get_logger('scanner_page')
config = get_config()

st.set_page_config(
    page_title="Scanner - HQM Momentum",
    page_icon="🔍",
    layout="wide",
)

init_session_state()

st.title("HQM Momentum Scanner")


def refresh_data():
    """Refresh market data from FinViz."""
    progress_bar = st.progress(0)
    status_text = st.empty()

    def progress_callback(pct: int, msg: str):
        progress_bar.progress(pct / 100)
        status_text.text(msg)

    try:
        stats = fetch_and_store_data(progress_callback)
        st.success(f"Refreshed {stats['total_stored']} stocks in {stats['duration_seconds']:.1f}s")
        progress_bar.empty()
        status_text.empty()
        return True
    except Exception as e:
        st.error(f"Refresh failed: {str(e)}")
        logger.error(f"Data refresh failed: {e}")
        return False


def run_scan():
    """Execute HQM scan with current filter settings."""
    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        status_text.text("Running HQM scan...")
        progress_bar.progress(0.1)

        # Get filter values from session state
        portfolio_size = st.session_state.portfolio_size
        num_positions = st.session_state.num_positions

        # Optional filters
        max_sma10_distance = None
        if st.session_state.sma10_filter_enabled:
            max_sma10_distance = st.session_state.max_sma10_distance

        rsi_filter = None
        if st.session_state.rsi_filter_enabled:
            rsi_filter = (st.session_state.rsi_min, st.session_state.rsi_max)

        min_volume = None
        if st.session_state.volume_filter_enabled:
            min_volume = st.session_state.min_volume

        max_atr_percent = None
        if st.session_state.atr_filter_enabled:
            max_atr_percent = st.session_state.max_atr_percent

        max_per_sector = None
        if st.session_state.diversification_enabled:
            max_per_sector = st.session_state.max_per_sector

        sector_filter = st.session_state.sector_filter if st.session_state.sector_filter else None

        progress_bar.progress(0.3)
        status_text.text("Calculating HQM scores...")

        result = run_hqm_scan_from_db(
            portfolio_size=portfolio_size,
            num_positions=num_positions,
            max_sma10_distance=max_sma10_distance,
            rsi_filter=rsi_filter,
            min_volume=min_volume,
            max_atr_percent=max_atr_percent,
            sector_filter=sector_filter,
            max_per_sector=max_per_sector,
        )

        if result['success']:
            # Calculate risk metrics
            progress_bar.progress(0.8)
            status_text.text("Calculating risk metrics...")

            tickers = [r['Ticker'] for r in result['results']]
            weights = [r['Weight'] / 100 for r in result['results']]

            risk_metrics = calculate_all_risk_metrics(
                tickers=tickers,
                weights=weights,
                portfolio_value=portfolio_size
            )

            result['summary']['risk_metrics'] = risk_metrics

            # Store results in session state
            st.session_state.scan_results = result['results']
            st.session_state.scan_summary = result['summary']
            st.session_state.last_scan_time = datetime.now()

            progress_bar.progress(1.0)
            status_text.text("Scan complete!")

            st.success(f"Found {len(result['results'])} stocks")
        else:
            st.error(result.get('error', 'Scan failed'))

        progress_bar.empty()
        status_text.empty()

    except Exception as e:
        st.error(f"Scan failed: {str(e)}")
        logger.error(f"Scan failed: {e}")
        progress_bar.empty()
        status_text.empty()


# Sidebar filters
with st.sidebar:
    st.header("Scan Settings")

    # Data refresh section
    st.subheader("Data Management")
    stock_count = get_stock_count()
    data_age = get_data_age_hours()

    if stock_count > 0:
        st.caption(f"{stock_count:,} stocks | {data_age:.1f}h old")
    else:
        st.warning("No data available")

    if st.button("Refresh Data", type="secondary", use_container_width=True):
        refresh_data()
        st.rerun()

    st.divider()

    # Portfolio settings
    st.subheader("Portfolio Settings")

    st.number_input(
        "Portfolio Size ($)",
        min_value=config.portfolio.min_size,
        max_value=1000000,
        value=st.session_state.portfolio_size,
        step=1000,
        key="portfolio_size",
    )

    st.number_input(
        "Number of Positions",
        min_value=1,
        max_value=config.portfolio.max_positions,
        value=st.session_state.num_positions,
        step=1,
        key="num_positions",
    )

    st.divider()

    # Technical filters
    st.subheader("Technical Filters")

    st.checkbox("SMA10 Distance Filter", key="sma10_filter_enabled")
    if st.session_state.sma10_filter_enabled:
        st.slider(
            "Max SMA10 Distance (%)",
            min_value=0.0,
            max_value=30.0,
            value=st.session_state.max_sma10_distance,
            step=1.0,
            key="max_sma10_distance",
        )

    st.checkbox("RSI Filter", key="rsi_filter_enabled")
    if st.session_state.rsi_filter_enabled:
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Min RSI", 0, 100, st.session_state.rsi_min, key="rsi_min")
        with col2:
            st.number_input("Max RSI", 0, 100, st.session_state.rsi_max, key="rsi_max")

    st.checkbox("Volume Filter", key="volume_filter_enabled")
    if st.session_state.volume_filter_enabled:
        st.number_input(
            "Min Avg Volume",
            min_value=100000,
            max_value=10000000,
            value=st.session_state.min_volume,
            step=100000,
            key="min_volume",
        )

    st.checkbox("ATR Filter", key="atr_filter_enabled")
    if st.session_state.atr_filter_enabled:
        st.slider(
            "Max ATR (%)",
            min_value=1.0,
            max_value=20.0,
            value=st.session_state.max_atr_percent,
            step=0.5,
            key="max_atr_percent",
        )

    st.divider()

    # Sector filters
    st.subheader("Sector Filters")

    st.checkbox("Sector Diversification", key="diversification_enabled")
    if st.session_state.diversification_enabled:
        st.number_input(
            "Max per Sector",
            min_value=1,
            max_value=10,
            value=st.session_state.max_per_sector,
            key="max_per_sector",
        )

    # Sector selection
    sectors = get_sector_breakdown()
    sector_names = [s['Sector'] for s in sectors if s['Sector']]
    st.multiselect(
        "Include Sectors (empty = all)",
        options=sector_names,
        default=st.session_state.sector_filter,
        key="sector_filter",
    )

    st.divider()

    # Run scan button
    if stock_count > 0:
        if st.button("Run Scan", type="primary", use_container_width=True):
            run_scan()
            st.rerun()
    else:
        st.button("Run Scan", type="primary", use_container_width=True, disabled=True)
        st.caption("Refresh data first")


# Main content area
if st.session_state.scan_results:
    results = st.session_state.scan_results
    summary = st.session_state.scan_summary

    # Summary metrics
    st.subheader("Scan Summary")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Stocks Scanned", f"{summary.get('total_scanned', 0):,}")

    with col2:
        st.metric("Selected", summary.get('selected', 0))

    with col3:
        st.metric("Total Invested", f"${summary.get('total_invested', 0):,.2f}")

    with col4:
        st.metric("Cash Remaining", f"${summary.get('cash_remaining', 0):,.2f}")

    with col5:
        if 'risk_metrics' in summary and summary['risk_metrics']:
            sharpe = summary['risk_metrics'].get('sharpe_ratio', 'N/A')
            if isinstance(sharpe, (int, float)):
                st.metric("Est. Sharpe", f"{sharpe:.2f}")
            else:
                st.metric("Est. Sharpe", sharpe)
        else:
            st.metric("Est. Sharpe", "N/A")

    st.divider()

    # Results table
    st.subheader("Selected Positions")

    df = pd.DataFrame(results)

    # Format columns for display
    display_columns = {
        'Ticker': 'Ticker',
        'Price': 'Price',
        'HQM_Score': 'HQM',
        'Shares': 'Shares',
        'Value': 'Value',
        'Weight': 'Weight %',
        'Sector': 'Sector',
        'Return_1M': '1M %',
        'Return_3M': '3M %',
        'Return_6M': '6M %',
        'Return_1Y': '1Y %',
    }

    # Filter to available columns
    available_cols = [c for c in display_columns.keys() if c in df.columns]
    display_df = df[available_cols].copy()
    display_df.columns = [display_columns[c] for c in available_cols]

    # Format numeric columns
    st.dataframe(
        display_df,
        column_config={
            'Price': st.column_config.NumberColumn(format="$%.2f"),
            'HQM': st.column_config.NumberColumn(format="%.1f"),
            'Value': st.column_config.NumberColumn(format="$%.2f"),
            'Weight %': st.column_config.NumberColumn(format="%.1f%%"),
            '1M %': st.column_config.NumberColumn(format="%.2f%%"),
            '3M %': st.column_config.NumberColumn(format="%.2f%%"),
            '6M %': st.column_config.NumberColumn(format="%.2f%%"),
            '1Y %': st.column_config.NumberColumn(format="%.2f%%"),
        },
        hide_index=True,
        use_container_width=True,
    )

    st.divider()

    # Charts
    st.subheader("Visualizations")

    tab1, tab2, tab3 = st.tabs(["Allocation", "HQM Scores", "Returns"])

    with tab1:
        fig = create_allocation_chart(results)
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        fig = create_hqm_score_chart(results)
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        fig = create_returns_comparison_chart(results)
        st.plotly_chart(fig, use_container_width=True)

    # Risk metrics details
    if 'risk_metrics' in summary and summary['risk_metrics']:
        st.divider()
        st.subheader("Risk Metrics")

        metrics = summary['risk_metrics']
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            beta = metrics.get('portfolio_beta', 'N/A')
            st.metric("Portfolio Beta", f"{beta:.2f}" if isinstance(beta, (int, float)) else beta)

        with col2:
            vol = metrics.get('annual_volatility', 'N/A')
            st.metric("Annual Volatility", f"{vol:.1f}%" if isinstance(vol, (int, float)) else vol)

        with col3:
            var = metrics.get('var_95', 'N/A')
            st.metric("VaR (95%)", f"${var:,.0f}" if isinstance(var, (int, float)) else var)

        with col4:
            max_dd = metrics.get('expected_max_drawdown', 'N/A')
            st.metric("Est. Max Drawdown", f"{max_dd:.1f}%" if isinstance(max_dd, (int, float)) else max_dd)

else:
    # No results yet
    st.info("Configure your scan settings in the sidebar and click 'Run Scan' to find momentum stocks.")

    # Show data status
    if get_stock_count() == 0:
        st.warning("No market data available. Click 'Refresh Data' in the sidebar to load data from FinViz.")
    else:
        st.success(f"Ready to scan {get_stock_count():,} stocks.")
