"""
Watchlist Page
===============
Manage and track stocks of interest.
"""

import streamlit as st
import pandas as pd

from logger import get_logger
from database import (
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
)
from components.state import init_session_state

logger = get_logger('watchlist_page')

st.set_page_config(
    page_title="Watchlist - HQM Momentum",
    page_icon="👁️",
    layout="wide",
)

init_session_state()

st.title("Watchlist")
st.markdown("Track stocks you're interested in for potential entry.")


# Add to watchlist form
with st.sidebar:
    st.header("Add to Watchlist")

    with st.form("add_watchlist_form", clear_on_submit=True):
        ticker = st.text_input("Ticker Symbol", placeholder="AAPL").upper()
        target_price = st.number_input(
            "Target Entry Price ($)",
            min_value=0.0,
            value=0.0,
            step=0.01,
            help="Leave at 0 to skip"
        )
        notes = st.text_area("Notes", placeholder="Why are you watching this stock?")
        alert_enabled = st.checkbox("Enable Alerts")

        alert_threshold = None
        if alert_enabled:
            alert_threshold = st.number_input(
                "Alert Threshold (SMA Distance %)",
                min_value=0.0,
                max_value=20.0,
                value=5.0,
                step=0.5,
            )

        submitted = st.form_submit_button("Add to Watchlist", type="primary", use_container_width=True)

        if submitted and ticker:
            success = add_to_watchlist(
                ticker=ticker,
                target_price=target_price if target_price > 0 else None,
                notes=notes if notes else None,
                alert_enabled=alert_enabled,
                alert_threshold=alert_threshold,
            )

            if success:
                st.success(f"Added {ticker} to watchlist")
                st.rerun()
            else:
                st.error(f"{ticker} is already in watchlist")


# Main content - Watchlist display
watchlist = get_watchlist()

if watchlist:
    st.subheader(f"Watching {len(watchlist)} Stocks")

    # Convert to DataFrame for display
    df = pd.DataFrame(watchlist)

    # Calculate distance to target if both price and target exist
    if 'price' in df.columns and 'target_entry_price' in df.columns:
        df['distance_to_target'] = df.apply(
            lambda row: ((row['price'] - row['target_entry_price']) / row['target_entry_price'] * 100)
            if row.get('price') and row.get('target_entry_price') and row['target_entry_price'] > 0
            else None,
            axis=1
        )

    # Display as cards
    for i, row in df.iterrows():
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])

            with col1:
                # Create TradingView link for ticker
                tv_url = f"https://es.tradingview.com/chart/EyK3ZRHL/?symbol=NASDAQ%3A{row['ticker']}"
                st.markdown(f"### [{row['ticker']}]({tv_url})")
                if row.get('sector'):
                    st.caption(row['sector'])

            with col2:
                if row.get('price'):
                    st.metric("Current Price", f"${row['price']:.2f}")
                else:
                    st.metric("Current Price", "N/A")

            with col3:
                if row.get('target_entry_price') and row['target_entry_price'] > 0:
                    if row.get('distance_to_target') is not None:
                        delta = f"{row['distance_to_target']:+.1f}%"
                        st.metric(
                            "Target Price",
                            f"${row['target_entry_price']:.2f}",
                            delta=delta,
                            delta_color="inverse"
                        )
                    else:
                        st.metric("Target Price", f"${row['target_entry_price']:.2f}")
                else:
                    st.metric("Target Price", "Not set")

            with col4:
                if st.button("Remove", key=f"remove_{row['ticker']}"):
                    remove_from_watchlist(row['ticker'])
                    st.rerun()

            # Additional details
            details_col1, details_col2 = st.columns(2)

            with details_col1:
                if row.get('return_1m'):
                    color = "green" if row['return_1m'] > 0 else "red"
                    st.markdown(f"1M Return: :{color}[{row['return_1m']*100:.1f}%]")
                if row.get('return_3m'):
                    color = "green" if row['return_3m'] > 0 else "red"
                    st.markdown(f"3M Return: :{color}[{row['return_3m']*100:.1f}%]")

            with details_col2:
                if row.get('notes'):
                    st.markdown(f"**Notes:** {row['notes']}")
                if row.get('alert_enabled'):
                    st.markdown(f"🔔 Alert enabled (threshold: {row.get('alert_threshold', 5)}%)")

            if row.get('added_date'):
                st.caption(f"Added: {row['added_date']}")

    st.divider()

    # Table view option
    with st.expander("Table View"):
        display_cols = ['ticker', 'price', 'target_entry_price', 'return_1m', 'return_3m', 'sector', 'notes']
        available_cols = [c for c in display_cols if c in df.columns]

        st.dataframe(
            df[available_cols],
            column_config={
                'ticker': 'Ticker',
                'price': st.column_config.NumberColumn('Price', format="$%.2f"),
                'target_entry_price': st.column_config.NumberColumn('Target', format="$%.2f"),
                'return_1m': st.column_config.NumberColumn('1M %', format="%.2f%%"),
                'return_3m': st.column_config.NumberColumn('3M %', format="%.2f%%"),
                'sector': 'Sector',
                'notes': 'Notes',
            },
            hide_index=True,
            use_container_width=True,
        )

else:
    st.info("Your watchlist is empty. Add stocks using the form in the sidebar.")

    st.markdown("""
    ### Tips for Using the Watchlist

    1. **Track High HQM Stocks**: Add stocks from your scans that you want to monitor
    2. **Set Target Prices**: Define entry points based on SMA10 distance
    3. **Add Notes**: Record why you're interested in each stock
    4. **Enable Alerts**: Get notified when stocks approach your targets

    The watchlist will show current prices from the last data refresh.
    """)
