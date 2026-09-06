"""Momentum Trader research dashboard."""

import pandas as pd
import streamlit as st

from hqm.config_loader import get_config
from hqm.database import (
    init_database, get_data_age_hours, get_last_refresh,
    get_stock_count, get_sector_breakdown,
)
from hqm.ui.state import init_session_state
from hqm.ui.banner import render_regime_banner
from hqm.ui.design import page_header, freshness_label, research_note
from hqm.ui.charts import create_sector_performance_chart

st.set_page_config(page_title="Overview · Momentum Trader", page_icon="📈", layout="wide")
init_database()
init_session_state()


def main():
    config = get_config()
    count = get_stock_count()
    age = get_data_age_hours()
    refreshed = get_last_refresh()
    status = freshness_label(count, age, config.data.cache_expiry_hours)
    sectors = get_sector_breakdown()

    page_header("Find strength. Research with discipline.",
                "A clear view of market momentum, sector leadership, and your next research ideas. "
                "Start with the market context, then narrow your universe.", "Overview")
    with st.sidebar:
        st.markdown("**Universe snapshot**")
        st.metric("Stocks available", f"{count:,}")
        st.caption(f"Data status: {status}")
        if refreshed:
            st.caption(f"Refreshed {refreshed:%d %b %Y · %H:%M} (server time)")
        st.page_link("pages/1_Scanner.py", label="Open scanner →")
        st.divider()
        st.caption("FinViz · Stock universe and returns\n\nYahoo Finance · Historical prices")

    actions = st.columns([1, 1, 2])
    with actions[0]:
        st.page_link("pages/1_Scanner.py", label="Open momentum scanner")
    with actions[1]:
        st.page_link("pages/5_Backtest.py", label="Test a strategy")
    st.write("")
    metrics = st.columns(4)
    metrics[0].metric("Research universe", f"{count:,}", help="Stocks in the cached FinViz universe.")
    metrics[1].metric("Sectors covered", len(sectors))
    metrics[2].metric("Momentum windows", "4", help="1 month, 3 months, 6 months, and 1 year.")
    metrics[3].metric("Snapshot status", status)
    if count and status != "Fresh":
        st.warning("The universe snapshot needs a refresh. Open Scanner and refresh data before researching current setups.")
    st.write("")
    render_regime_banner()

    st.subheader("Sector pulse")
    st.caption("Average stock returns within each sector of the cached universe · Equal weight · 3 months")
    if sectors:
        frame = pd.DataFrame(sectors)
        valid = frame.dropna(subset=['Avg_Return_3M'])
        if not valid.empty:
            chart, context = st.columns([2, 1])
            with chart:
                st.plotly_chart(create_sector_performance_chart(valid.to_dict('records')), use_container_width=True)
            with context:
                leader = valid.loc[valid['Avg_Return_3M'].idxmax()]
                with st.container(border=True):
                    st.caption("SECTOR LEADER · 3M")
                    st.subheader(leader['Sector'])
                    st.metric("Average return", f"{leader['Avg_Return_3M'] * 100:+.1f}%")
                    st.caption(f"Across {int(leader['Count']):,} stocks. Sector averages can hide large differences between individual stocks.")
                with st.container(border=True):
                    positive = int((valid['Avg_Return_3M'] > 0).sum())
                    st.metric("Sectors with positive returns", f"{positive} / {len(valid)}")
                    st.page_link("pages/4_Sectors.py", label="Explore sectors & industries →")
        else:
            st.info("Sector returns are unavailable in this snapshot. Refresh data in Scanner.")
    else:
        with st.container(border=True):
            st.subheader("Build your first research snapshot")
            st.write("Open Scanner, refresh the stock universe, then run a scan. Refreshing may take a few minutes; the snapshot is reused across pages.")
            st.page_link("pages/1_Scanner.py", label="Get started in Scanner →")

    st.subheader("Your research workflow")
    workflows = [
        ("01 / Discover", "Screen for consistent momentum", "Rank stocks across four return windows and refine your shortlist with technical filters.", "pages/1_Scanner.py", "Launch scanner"),
        ("02 / Follow", "Turn a shortlist into a watchlist", "Track target entry prices and keep notes alongside the stocks you are researching.", "pages/2_Watchlist.py", "Open watchlist"),
        ("03 / Evaluate", "Understand exposure and outcomes", "Review portfolio allocation or use the strategy lab to inspect historical drawdowns.", "pages/3_Portfolio.py", "Review portfolio"),
    ]
    for column, (step, title, text, page, label) in zip(st.columns(3), workflows):
        with column, st.container(border=True):
            st.caption(step)
            st.markdown(f"#### {title}")
            st.write(text)
            st.page_link(page, label=f"{label} →")
    with st.expander("Methodology & data limitations"):
        st.write(f"HQM is the average of percentile ranks for 1-month, 3-month, 6-month, and 1-year returns. "
                 f"Stocks must meet the configured minimum {config.strategy.min_percentile_threshold:g}th percentile "
                 "in every window before optional filters are applied. Selected stocks receive equal target allocations, rounded to whole shares.")
        st.write("Rankings depend on the selected universe. Data providers may be delayed or unavailable, and missing indicators can exclude stocks. "
                 "Historical simulations cannot guarantee future results. Watchlist and portfolio records are shared on the public demo and may reset on redeploy.")
    research_note()


if __name__ == "__main__":
    main()
