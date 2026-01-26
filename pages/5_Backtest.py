"""
Backtest Page
==============
Historical backtesting of the HQM momentum strategy.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from logger import get_logger
from config_loader import get_config
from database import get_stock_count
from backtest import run_backtest, get_backtest_history
from components.state import init_session_state
from components.charts import (
    create_equity_curve,
    create_drawdown_chart,
)

logger = get_logger('backtest_page')
config = get_config()

st.set_page_config(
    page_title="Backtest - HQM Momentum",
    page_icon="📈",
    layout="wide",
)

init_session_state()

st.title("Strategy Backtesting")
st.markdown("Test the HQM momentum strategy on historical data.")


def execute_backtest(
    start_date: str,
    end_date: str,
    initial_capital: float,
    num_positions: int,
    rebalance_frequency: str
):
    """Execute backtest with progress display."""
    progress_bar = st.progress(0)
    status_text = st.empty()

    def progress_callback(pct: int, msg: str):
        progress_bar.progress(pct / 100)
        status_text.text(msg)

    try:
        results = run_backtest(
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            num_positions=num_positions,
            rebalance_frequency=rebalance_frequency,
            progress_callback=progress_callback,
        )

        progress_bar.empty()
        status_text.empty()

        return results

    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        logger.error(f"Backtest failed: {e}")
        return {'success': False, 'error': str(e)}


# Sidebar - Backtest configuration
with st.sidebar:
    st.header("Backtest Settings")

    with st.form("backtest_form"):
        # Date range
        st.subheader("Date Range")

        default_end = datetime.now()
        default_start = default_end - timedelta(days=config.backtest.default_period_days)

        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", value=default_start)
        with col2:
            end_date = st.date_input("End Date", value=default_end)

        st.divider()

        # Portfolio settings
        st.subheader("Portfolio")

        initial_capital = st.number_input(
            "Initial Capital ($)",
            min_value=1000,
            max_value=1000000,
            value=config.backtest.initial_capital,
            step=1000,
        )

        num_positions = st.number_input(
            "Number of Positions",
            min_value=1,
            max_value=20,
            value=config.portfolio.default_positions,
            step=1,
        )

        rebalance_frequency = st.selectbox(
            "Rebalance Frequency",
            options=['daily', 'weekly', 'monthly'],
            index=['daily', 'weekly', 'monthly'].index(config.backtest.rebalance_frequency),
        )

        st.divider()

        submitted = st.form_submit_button("Run Backtest", type="primary", use_container_width=True)

        if submitted:
            if get_stock_count() == 0:
                st.error("No market data. Refresh data first.")
            elif start_date >= end_date:
                st.error("Start date must be before end date")
            else:
                results = execute_backtest(
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d'),
                    initial_capital=initial_capital,
                    num_positions=num_positions,
                    rebalance_frequency=rebalance_frequency,
                )

                if results['success']:
                    st.session_state.backtest_results = results
                    st.success("Backtest complete!")
                    st.rerun()
                else:
                    st.error(results.get('error', 'Backtest failed'))


# Main content - Results display
if st.session_state.backtest_results:
    results = st.session_state.backtest_results

    st.subheader("Backtest Results")

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Return",
            f"{results['total_return']:.2f}%",
            help="Total percentage return over the backtest period"
        )

    with col2:
        st.metric(
            "Sharpe Ratio",
            f"{results['sharpe_ratio']:.2f}",
            help="Risk-adjusted return (higher is better)"
        )

    with col3:
        st.metric(
            "Max Drawdown",
            f"{results['max_drawdown']:.2f}%",
            help="Largest peak-to-trough decline"
        )

    with col4:
        st.metric(
            "Final Value",
            f"${results['final_value']:,.2f}",
            delta=f"${results['final_value'] - results['initial_capital']:,.2f}",
        )

    st.divider()

    # Secondary metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Initial Capital", f"${results['initial_capital']:,}")

    with col2:
        st.metric("Total Trades", results['num_trades'])

    with col3:
        st.metric("Win Rate", f"{results['win_rate']:.1f}%")

    with col4:
        st.metric("Commission Paid", f"${results['total_commission']:,.2f}")

    st.divider()

    # Charts
    if results.get('portfolio_history'):
        st.subheader("Performance Charts")

        tab1, tab2 = st.tabs(["Equity Curve", "Drawdown"])

        with tab1:
            fig = create_equity_curve(results['portfolio_history'])
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            fig = create_drawdown_chart(results['portfolio_history'])
            st.plotly_chart(fig, use_container_width=True)

    # Trade details
    if results.get('trades'):
        st.divider()
        st.subheader("Trade History")

        with st.expander(f"View All Trades ({len(results['trades'])} trades)"):
            df_trades = pd.DataFrame(results['trades'])

            # Format date column
            if 'date' in df_trades.columns:
                df_trades['date'] = pd.to_datetime(df_trades['date']).dt.strftime('%Y-%m-%d')

            st.dataframe(
                df_trades,
                column_config={
                    'date': 'Date',
                    'ticker': 'Ticker',
                    'action': 'Action',
                    'shares': 'Shares',
                    'price': st.column_config.NumberColumn('Price', format="$%.2f"),
                    'value': st.column_config.NumberColumn('Value', format="$%.2f"),
                },
                hide_index=True,
                use_container_width=True,
            )

    # Parameters used
    if results.get('parameters'):
        st.divider()
        with st.expander("Backtest Parameters"):
            params = results['parameters']
            col1, col2 = st.columns(2)

            with col1:
                st.write(f"**Initial Capital:** ${params['initial_capital']:,}")
                st.write(f"**Positions:** {params['num_positions']}")

            with col2:
                st.write(f"**Rebalance:** {params['rebalance_frequency']}")
                st.write(f"**Slippage:** {params['slippage_pct']}%")
                st.write(f"**Commission:** ${params['commission']}")

else:
    # No results yet
    st.info("Configure backtest settings in the sidebar and click 'Run Backtest' to test the strategy.")

    # Show historical backtests
    history = get_backtest_history(limit=5)

    if history:
        st.divider()
        st.subheader("Recent Backtests")

        df_history = pd.DataFrame(history)

        display_cols = ['run_date', 'start_date', 'end_date', 'initial_capital', 'total_return', 'sharpe_ratio', 'max_drawdown']
        available_cols = [c for c in display_cols if c in df_history.columns]

        st.dataframe(
            df_history[available_cols],
            column_config={
                'run_date': 'Run Date',
                'start_date': 'Start',
                'end_date': 'End',
                'initial_capital': st.column_config.NumberColumn('Capital', format="$%d"),
                'total_return': st.column_config.NumberColumn('Return', format="%.2f%%"),
                'sharpe_ratio': st.column_config.NumberColumn('Sharpe', format="%.2f"),
                'max_drawdown': st.column_config.NumberColumn('Max DD', format="%.2f%%"),
            },
            hide_index=True,
            use_container_width=True,
        )

# Information about backtesting
st.divider()

with st.expander("About HQM Backtesting", expanded=False):
    st.markdown("""
    ### How the Backtest Works

    1. **Universe**: Uses all stocks from the database
    2. **Selection**: Calculates HQM scores at each rebalance date
    3. **Ranking**: Selects top N stocks by HQM score
    4. **Allocation**: Equal-weight across all positions
    5. **Rebalancing**: Adjusts portfolio at specified frequency

    ### Key Assumptions

    - **Slippage**: 0.1% per trade (configurable)
    - **Commission**: $0 per trade (configurable)
    - **No partial fills**: All orders execute completely
    - **End-of-day execution**: Trades at close prices

    ### Limitations

    - **Survivorship bias**: Only includes currently tradable stocks
    - **Look-ahead bias**: Uses data available at backtest runtime
    - **Market impact**: Does not account for large position sizes

    ### Interpreting Results

    - **Sharpe > 1.0**: Generally considered good risk-adjusted return
    - **Max Drawdown < 20%**: Acceptable for most strategies
    - **Win Rate**: Less important than profit factor
    """)
