"""
Scanner Page
=============
HQM Momentum Scanner with filters and results display.
"""

import streamlit as st
from hqm.ui.design import page_header, research_note
import pandas as pd
from datetime import datetime
from urllib.parse import quote

from hqm.logger import get_logger
from hqm.config_loader import get_config
from hqm.database import (
    fetch_and_store_data,
    run_hqm_scan_from_db,
    get_data_age_hours,
    get_stock_count,
    get_sector_breakdown,
    get_last_refresh,
)
from hqm.risk_metrics import calculate_all_risk_metrics
from hqm.formatting import frac_cols_to_pct
from hqm.ui.state import init_session_state
from hqm.ui.design import freshness_label
from hqm.ui.banner import render_regime_banner
from hqm.ui.charts import (
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

page_header("Momentum scanner", "Find consistent strength across four timeframes. Build a shortlist with transparent, rules-based filters.")
research_note()

render_regime_banner()


SCAN_KEYS = (
    "portfolio_size", "num_positions", "sma10_filter_enabled", "max_sma10_distance",
    "rsi_filter_enabled", "rsi_min", "rsi_max", "volume_filter_enabled", "min_volume",
    "atr_filter_enabled", "max_atr_percent", "diversification_enabled",
    "max_per_sector", "sector_filter",
)


def scan_settings():
    return {key: st.session_state[key] for key in SCAN_KEYS}


def refresh_data():
    """Refresh market data from FinViz."""
    progress_bar = st.progress(0)
    status_text = st.empty()

    def progress_callback(pct: int, msg: str):
        progress_bar.progress(pct / 100)
        status_text.text(msg)

    try:
        stats = fetch_and_store_data(progress_callback)
        st.session_state.refresh_notice = f"Refreshed {stats['total_stored']:,} stocks in {stats['duration_seconds']:.1f}s"
        progress_bar.empty()
        status_text.empty()
        return True
    except Exception as e:
        st.error(f"Refresh failed: {str(e)}")
        logger.error(f"Data refresh failed: {e}")
        return False
    finally:
        progress_bar.empty()
        status_text.empty()


def run_scan():
    """Execute HQM scan with current filter settings."""
    if st.session_state.rsi_filter_enabled and st.session_state.rsi_min > st.session_state.rsi_max:
        st.error("Minimum RSI must be less than or equal to maximum RSI.")
        return
    st.session_state.scan_results = None
    st.session_state.scan_summary = None
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

            try:
                risk_metrics = calculate_all_risk_metrics(
                    tickers=tickers, weights=weights, portfolio_value=portfolio_size
                )
            except Exception:
                logger.exception("Risk metrics unavailable; preserving scan results")
                risk_metrics = {'data_available': False}

            result['summary']['risk_metrics'] = risk_metrics

            # Store results in session state
            st.session_state.scan_results = result['results']
            st.session_state.scan_summary = result['summary']
            st.session_state.last_scan_time = datetime.now()
            st.session_state.scan_settings_snapshot = scan_settings()

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
        if refresh_data():
            st.rerun()

    st.divider()

    # Portfolio settings
    st.subheader("Portfolio Settings")

    st.number_input(
        "Portfolio Size ($)",
        min_value=int(config.portfolio.min_size),
        max_value=1000000,
        step=1000,
        key="portfolio_size",
    )

    st.number_input(
        "Number of Positions",
        min_value=1,
        max_value=config.portfolio.max_positions,
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
            step=1.0,
            key="max_sma10_distance",
        )

    st.checkbox("RSI Filter", key="rsi_filter_enabled")
    if st.session_state.rsi_filter_enabled:
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Min RSI", 0, 100, key="rsi_min")
        with col2:
            st.number_input("Max RSI", 0, 100, key="rsi_max")

    st.checkbox("Volume Filter", key="volume_filter_enabled")
    if st.session_state.volume_filter_enabled:
        st.number_input(
            "Min Avg Volume",
            min_value=100000,
            max_value=10000000,
            step=100000,
            key="min_volume",
        )

    st.checkbox("ATR Filter", key="atr_filter_enabled")
    if st.session_state.atr_filter_enabled:
        st.slider(
            "Max ATR (%)",
            min_value=1.0,
            max_value=20.0,
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
            key="max_per_sector",
        )

    # Sector selection
    sectors = get_sector_breakdown()
    sector_names = [s['Sector'] for s in sectors if s['Sector']]
    st.multiselect(
        "Include Sectors (empty = all)",
        options=sector_names,
        key="sector_filter",
    )

    st.divider()

    # Run scan button
    if stock_count > 0:
        if st.button("Run Scan", type="primary", use_container_width=True):
            run_scan()
    else:
        st.button("Run Scan", type="primary", use_container_width=True, disabled=True)
        st.caption("Refresh data first")


# Main content area
if "refresh_notice" in st.session_state:
    st.success(st.session_state.pop("refresh_notice"))
if stock_count and freshness_label(stock_count, data_age, config.data.cache_expiry_hours) != "Fresh":
    st.warning("This stock snapshot needs a refresh. Results use cached prices, not live quotes.")
if st.session_state.scan_results:
    results = st.session_state.scan_results
    summary = st.session_state.scan_summary

    scanned_at = st.session_state.last_scan_time
    if scanned_at:
        st.caption(f"Scan completed {scanned_at:%d %b %Y · %H:%M:%S} (server time) · "
                   f"Source snapshot: {summary.get('last_refresh') or 'unknown'}")
    if st.session_state.get('scan_settings_snapshot') != scan_settings():
        st.warning("Settings have changed since this scan. Run Scan again to update the results.")
    current_refresh = get_last_refresh()
    if current_refresh and summary.get('last_refresh') != current_refresh.isoformat():
        st.warning("Market data has changed since this scan. Run Scan again to use the new snapshot.")

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
        risk = summary.get('risk_metrics') or {}
        sharpe = risk.get('sharpe_ratio')
        if risk.get('data_available') and isinstance(sharpe, (int, float)):
            st.metric("Est. Sharpe", f"{sharpe:.2f}")
        else:
            st.metric("Est. Sharpe", "N/A",
                      help="Not calculated: historical price data was unavailable.")

    # Disclose fail-closed exclusions so an enabled filter never silently
    # shrinks the candidate pool without explanation
    excl_ind = summary.get('excluded_missing_indicators', 0)
    excl_vol = summary.get('excluded_missing_avg_volume', 0)
    if excl_ind or excl_vol:
        notes = []
        if excl_ind:
            notes.append(
                f"{excl_ind} candidate(s) excluded because their RSI/SMA/ATR "
                f"indicators could not be computed"
            )
        if excl_vol:
            notes.append(
                f"{excl_vol} stock(s) excluded because average volume data "
                f"was unavailable"
            )
        st.caption("Filter note: " + "; ".join(notes) + ".")

    st.divider()

    # Results table
    st.subheader("Selected Positions")

    df = pd.DataFrame(results)

    # Create TradingView URL for each ticker
    def make_tradingview_url(row):
        ticker = row['Ticker']
        exchange = row.get('Exchange', 'NASDAQ')
        symbol = quote(f"{exchange}:{ticker}", safe="")
        return f"https://www.tradingview.com/chart/?symbol={symbol}"

    df['TradingView'] = df.apply(make_tradingview_url, axis=1)

    # Format columns for display
    display_columns = {
        'Ticker': 'Ticker',
        'Price': 'Price',
        'HQM_Score': 'HQM',
        'Shares': 'Shares',
        'Value': 'Value',
        'Weight': 'Weight %',
        'Sector': 'Sector',
        'Industry': 'Industry',
        'RSI': 'RSI',
        'SMA10_Distance': 'SMA10 %',
        'ATR_Percent': 'ATR %',
        'Return_1M': '1M %',
        'Return_3M': '3M %',
        'Return_6M': '6M %',
        'Return_1Y': '1Y %',
        'TradingView': 'Chart',
    }

    # Filter to available columns
    available_cols = [c for c in display_columns.keys() if c in df.columns]
    display_df = df[available_cols].copy()
    display_df.columns = [display_columns[c] for c in available_cols]

    # Returns are stored as decimal fractions; scale to percent for display
    display_df = frac_cols_to_pct(display_df, ['1M %', '3M %', '6M %', '1Y %'])

    # Format numeric columns
    st.dataframe(
        display_df,
        column_config={
            'Ticker': st.column_config.TextColumn(),
            'Price': st.column_config.NumberColumn(format="$%.2f"),
            'HQM': st.column_config.ProgressColumn(min_value=0, max_value=100, format='%.1f', help='Average percentile rank across four return windows.'),
            'RSI': st.column_config.NumberColumn(format='%.1f'),
            'SMA10 %': st.column_config.NumberColumn(format='%.1f%%'),
            'ATR %': st.column_config.NumberColumn(format='%.1f%%'),
            'Value': st.column_config.NumberColumn(format="$%.2f"),
            'Weight %': st.column_config.NumberColumn(format="%.1f%%"),
            '1M %': st.column_config.NumberColumn(format="%.2f%%"),
            '3M %': st.column_config.NumberColumn(format="%.2f%%"),
            '6M %': st.column_config.NumberColumn(format="%.2f%%"),
            '1Y %': st.column_config.NumberColumn(format="%.2f%%"),
            'Chart': st.column_config.LinkColumn(display_text="📈 View"),
        },
        hide_index=True,
        use_container_width=True,
    )

    st.divider()

    st.download_button(
        "Download scan · CSV", display_df.to_csv(index=False).encode("utf-8"),
        file_name=f"momentum-scan-{scanned_at:%Y%m%d-%H%M%S}.csv" if scanned_at else "momentum-scan.csv",
        mime="text/csv",
    )
    with st.expander("Scan context & selection funnel"):
        st.write(f"{summary.get('total_scanned', 0):,} stocks in the universe → "
                 f"{summary.get('after_quality_filter', 0):,} after the quality filter → "
                 f"{len(results)} selected positions.")
        st.caption("Optional filters and the position limit further narrow the selection. Technical fields appear when those indicators were calculated.")
        st.json(st.session_state.get('scan_settings_snapshot', {}))

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

        if not metrics.get('data_available'):
            st.warning(
                "Risk metrics could not be calculated: historical price data "
                "was unavailable. Scan results above are unaffected."
            )
        else:
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                beta = metrics.get('portfolio_beta')
                st.metric("Portfolio Beta", f"{beta:.2f}" if isinstance(beta, (int, float)) else "N/A")

            with col2:
                vol = metrics.get('volatility')
                st.metric("Annual Volatility", f"{vol:.1f}%" if isinstance(vol, (int, float)) else "N/A")

            with col3:
                var = metrics.get('var_95')
                st.metric("VaR (95%)", f"${var:,.0f}" if isinstance(var, (int, float)) else "N/A")

            with col4:
                max_dd = metrics.get('max_drawdown')
                st.metric("Max Drawdown (1Y)", f"{max_dd:.1f}%" if isinstance(max_dd, (int, float)) else "N/A")

else:
    # No results yet
    st.info("Configure your scan settings in the sidebar and click 'Run Scan' to find momentum stocks.")

    # Show data status
    if get_stock_count() == 0:
        st.warning("No market data available. Click 'Refresh Data' in the sidebar to load data from FinViz.")
    else:
        st.success(f"Ready to scan {get_stock_count():,} stocks.")
