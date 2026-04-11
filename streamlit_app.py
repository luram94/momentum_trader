"""
HQM Momentum Scanner - Streamlit Application
==============================================
Interactive web interface for the High Quality Momentum strategy.
Built with Streamlit for free cloud hosting.
"""

import streamlit as st

from logger import get_logger
from config_loader import get_config
from database import (
    init_database,
    get_data_age_hours,
    get_last_refresh,
    get_stock_count,
)
from components.state import init_session_state

# Initialize logger and config
logger = get_logger('streamlit_app')
config = get_config()

# Page configuration
st.set_page_config(
    page_title="HQM Momentum Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize database
init_database()

# Initialize session state
init_session_state()


def main():
    """Main application entry point."""

    # Sidebar with app info
    with st.sidebar:
        st.title("HQM Scanner")
        st.markdown("---")

        # Data status
        st.subheader("Data Status")

        stock_count = get_stock_count()
        data_age = get_data_age_hours()
        last_refresh = get_last_refresh()

        if stock_count > 0:
            st.metric("Stocks in Database", f"{stock_count:,}")

            if data_age < float('inf'):
                age_color = "green" if data_age < 24 else "orange" if data_age < 48 else "red"
                st.markdown(f"Data Age: :{age_color}[{data_age:.1f} hours]")

            if last_refresh:
                st.caption(f"Last refresh: {last_refresh.strftime('%Y-%m-%d %H:%M')}")
        else:
            st.warning("No data loaded. Go to Scanner to refresh data.")

        st.markdown("---")

        # Navigation info
        st.subheader("Navigation")
        st.markdown("""
        - **Scanner**: Run HQM scans
        - **Watchlist**: Track stocks
        - **Portfolio**: Track positions
        - **Sectors & Industries**: Sector/industry analysis
        - **Backtest**: Historical testing
        """)

        st.markdown("---")
        st.caption("HQM Momentum Scanner v2.0")
        st.caption("Powered by Streamlit")

    # Main content
    st.title("HQM Momentum Scanner")
    st.markdown("### High Quality Momentum Strategy Scanner")

    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Portfolio Default",
            f"${config.portfolio.default_size:,}",
            help="Default portfolio size for scanning"
        )

    with col2:
        st.metric(
            "Default Positions",
            config.portfolio.default_positions,
            help="Default number of positions"
        )

    with col3:
        st.metric(
            "Stocks Available",
            f"{stock_count:,}" if stock_count > 0 else "N/A",
            help="Number of stocks in database"
        )

    with col4:
        status = "Fresh" if data_age < 24 else "Stale" if data_age < 48 else "Outdated"
        st.metric(
            "Data Status",
            status if stock_count > 0 else "No Data",
            help="Data freshness status"
        )

    st.markdown("---")

    # Feature cards
    st.subheader("Features")

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("#### Scanner")
            st.markdown("""
            Run HQM momentum scans with advanced filters:
            - SMA10 distance filter
            - RSI overbought filter
            - Volume filter
            - Sector diversification
            """)
            st.page_link("pages/1_Scanner.py", label="Go to Scanner", icon="🔍")

        with st.container(border=True):
            st.markdown("#### Portfolio Tracking")
            st.markdown("""
            Track your positions:
            - Add/close positions
            - P&L tracking
            - Performance metrics
            """)
            st.page_link("pages/3_Portfolio.py", label="Go to Portfolio", icon="💼")

    with col2:
        with st.container(border=True):
            st.markdown("#### Watchlist")
            st.markdown("""
            Monitor stocks of interest:
            - Add stocks to watch
            - Set target prices
            - Track price changes
            """)
            st.page_link("pages/2_Watchlist.py", label="Go to Watchlist", icon="👁️")

        with st.container(border=True):
            st.markdown("#### Backtesting")
            st.markdown("""
            Test strategy performance:
            - Historical backtesting
            - Custom date ranges
            - Performance metrics
            """)
            st.page_link("pages/5_Backtest.py", label="Go to Backtest", icon="📊")

    # Strategy info
    st.markdown("---")
    st.subheader("About HQM Strategy")

    with st.expander("How it works", expanded=False):
        st.markdown("""
        The **High Quality Momentum (HQM)** strategy selects stocks based on their
        relative momentum across multiple timeframes:

        1. **Calculate Returns**: 1-month, 3-month, 6-month, and 1-year returns
        2. **Percentile Ranking**: Rank each stock by percentile in each timeframe
        3. **HQM Score**: Average of all four percentile rankings
        4. **Quality Filter**: Only include stocks with minimum 25th percentile in ALL timeframes
        5. **Position Sizing**: Equal-weight allocation across top positions

        **Key Advantages:**
        - Captures momentum across multiple timeframes
        - Quality filter avoids momentum traps
        - Systematic, rules-based approach
        """)


if __name__ == "__main__":
    main()
