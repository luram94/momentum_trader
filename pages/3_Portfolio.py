"""
Portfolio Page
===============
Track and manage portfolio positions.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from logger import get_logger
from database import (
    add_portfolio_position,
    close_portfolio_position,
    get_portfolio_positions,
    get_portfolio_summary,
)
from components.state import init_session_state

logger = get_logger('portfolio_page')

st.set_page_config(
    page_title="Portfolio - HQM Momentum",
    page_icon="💼",
    layout="wide",
)

init_session_state()

st.title("Portfolio Tracking")
st.markdown("Track your positions and performance.")

# Sidebar - Add position form
with st.sidebar:
    st.header("Add Position")

    with st.form("add_position_form", clear_on_submit=True):
        ticker = st.text_input("Ticker Symbol", placeholder="AAPL").upper()
        shares = st.number_input("Shares", min_value=1, value=1, step=1)
        entry_price = st.number_input("Entry Price ($)", min_value=0.01, value=100.0, step=0.01)
        entry_date = st.date_input("Entry Date", value=datetime.now())
        hqm_score = st.number_input(
            "HQM Score (optional)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=0.1,
            help="Leave at 0 to skip"
        )
        notes = st.text_area("Notes", placeholder="Trade rationale...")

        submitted = st.form_submit_button("Add Position", type="primary", use_container_width=True)

        if submitted and ticker and shares > 0 and entry_price > 0:
            position_id = add_portfolio_position(
                ticker=ticker,
                shares=shares,
                entry_price=entry_price,
                entry_date=entry_date.isoformat(),
                hqm_score=hqm_score if hqm_score > 0 else None,
                notes=notes if notes else None,
            )

            if position_id:
                st.success(f"Added {shares} shares of {ticker}")
                st.rerun()
            else:
                st.error("Failed to add position")


# Main content
summary = get_portfolio_summary()

# Summary metrics
st.subheader("Portfolio Summary")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Value", f"${summary['total_value']:,.2f}")

with col2:
    st.metric("Total Cost", f"${summary['total_cost']:,.2f}")

with col3:
    pnl_color = "normal" if summary['total_pnl'] >= 0 else "inverse"
    st.metric(
        "Unrealized P&L",
        f"${summary['total_pnl']:,.2f}",
        delta=f"{summary['total_pnl_pct']:+.2f}%",
        delta_color=pnl_color
    )

with col4:
    st.metric(
        "Positions",
        summary['position_count'],
        delta=f"W: {summary['winning_positions']} / L: {summary['losing_positions']}"
    )

st.divider()

# Tabs for open and closed positions
tab1, tab2 = st.tabs(["Open Positions", "Closed Positions"])

with tab1:
    positions = get_portfolio_positions(include_closed=False)

    if positions:
        st.subheader(f"{len(positions)} Open Positions")

        for pos in positions:
            with st.container(border=True):
                col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])

                with col1:
                    # Create TradingView link for ticker
                    tv_url = f"https://es.tradingview.com/chart/EyK3ZRHL/?symbol=NASDAQ%3A{pos['ticker']}"
                    st.markdown(f"### [{pos['ticker']}]({tv_url})")
                    st.caption(f"{pos['shares']} shares @ ${pos['entry_price']:.2f}")

                with col2:
                    current = pos.get('current_price')
                    if current:
                        st.metric("Current Price", f"${current:.2f}")
                    else:
                        st.metric("Current Price", "N/A")

                with col3:
                    cost_basis = pos['shares'] * pos['entry_price']
                    st.metric("Cost Basis", f"${cost_basis:,.2f}")

                with col4:
                    pnl = pos.get('unrealized_pnl', 0)
                    pnl_pct = pos.get('unrealized_pnl_pct', 0)
                    if pnl is not None:
                        color = "normal" if pnl >= 0 else "inverse"
                        st.metric(
                            "P&L",
                            f"${pnl:,.2f}",
                            delta=f"{pnl_pct:+.2f}%",
                            delta_color=color
                        )
                    else:
                        st.metric("P&L", "N/A")

                with col5:
                    # Close position button with popover for exit price
                    with st.popover("Close"):
                        st.markdown(f"**Close {pos['ticker']}**")
                        exit_price = st.number_input(
                            "Exit Price",
                            min_value=0.01,
                            value=float(pos.get('current_price', pos['entry_price'])),
                            step=0.01,
                            key=f"exit_price_{pos['id']}"
                        )
                        if st.button("Confirm Close", key=f"close_{pos['id']}"):
                            success = close_portfolio_position(
                                position_id=pos['id'],
                                exit_price=exit_price
                            )
                            if success:
                                st.success("Position closed")
                                st.rerun()
                            else:
                                st.error("Failed to close position")

                # Additional details row
                details_col1, details_col2, details_col3 = st.columns(3)

                with details_col1:
                    if pos.get('sector'):
                        st.caption(f"Sector: {pos['sector']}")

                with details_col2:
                    if pos.get('hqm_score_at_entry'):
                        st.caption(f"HQM at entry: {pos['hqm_score_at_entry']:.1f}")

                with details_col3:
                    if pos.get('entry_date'):
                        st.caption(f"Opened: {pos['entry_date']}")

                if pos.get('notes'):
                    st.caption(f"Notes: {pos['notes']}")

        # Table view
        with st.expander("Table View"):
            df = pd.DataFrame(positions)
            display_cols = ['ticker', 'shares', 'entry_price', 'current_price', 'unrealized_pnl', 'unrealized_pnl_pct', 'sector']
            available_cols = [c for c in display_cols if c in df.columns]

            st.dataframe(
                df[available_cols],
                column_config={
                    'ticker': 'Ticker',
                    'shares': 'Shares',
                    'entry_price': st.column_config.NumberColumn('Entry', format="$%.2f"),
                    'current_price': st.column_config.NumberColumn('Current', format="$%.2f"),
                    'unrealized_pnl': st.column_config.NumberColumn('P&L', format="$%.2f"),
                    'unrealized_pnl_pct': st.column_config.NumberColumn('P&L %', format="%.2f%%"),
                    'sector': 'Sector',
                },
                hide_index=True,
                use_container_width=True,
            )

    else:
        st.info("No open positions. Add positions using the sidebar form.")

with tab2:
    closed_positions = get_portfolio_positions(include_closed=True)
    closed_positions = [p for p in closed_positions if p.get('status') == 'closed']

    if closed_positions:
        st.subheader(f"{len(closed_positions)} Closed Positions")

        df = pd.DataFrame(closed_positions)

        # Calculate realized P&L if not present
        if 'realized_pnl' not in df.columns:
            df['realized_pnl'] = (df['exit_price'] - df['entry_price']) * df['shares']
            df['realized_pnl_pct'] = ((df['exit_price'] / df['entry_price']) - 1) * 100

        display_cols = ['ticker', 'shares', 'entry_price', 'exit_price', 'realized_pnl', 'realized_pnl_pct', 'entry_date', 'exit_date']
        available_cols = [c for c in display_cols if c in df.columns]

        st.dataframe(
            df[available_cols],
            column_config={
                'ticker': 'Ticker',
                'shares': 'Shares',
                'entry_price': st.column_config.NumberColumn('Entry', format="$%.2f"),
                'exit_price': st.column_config.NumberColumn('Exit', format="$%.2f"),
                'realized_pnl': st.column_config.NumberColumn('P&L', format="$%.2f"),
                'realized_pnl_pct': st.column_config.NumberColumn('P&L %', format="%.2f%%"),
                'entry_date': 'Opened',
                'exit_date': 'Closed',
            },
            hide_index=True,
            use_container_width=True,
        )

        # Summary of closed trades
        total_realized = df['realized_pnl'].sum()
        winners = len(df[df['realized_pnl'] > 0])
        losers = len(df[df['realized_pnl'] < 0])
        win_rate = (winners / len(df) * 100) if len(df) > 0 else 0

        st.divider()

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Realized P&L", f"${total_realized:,.2f}")
        with col2:
            st.metric("Win Rate", f"{win_rate:.1f}%")
        with col3:
            st.metric("Winners / Losers", f"{winners} / {losers}")

    else:
        st.info("No closed positions yet.")
