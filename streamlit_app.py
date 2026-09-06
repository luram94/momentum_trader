"""Daily research briefing for Momentum Trader."""
from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st

from hqm.config_loader import get_config
from hqm.database import init_database, get_data_age_hours, get_last_refresh, get_stock_count, get_sector_breakdown
from hqm.ui.state import init_session_state
from hqm.ui.banner import render_regime_banner
from hqm.ui.design import apply_style, markup, freshness_label, section_heading, stat_strip, empty_workspace, research_note
from hqm.ui.charts import create_sector_performance_chart, create_momentum_heatmap

st.set_page_config(page_title="Overview · Momentum Trader", page_icon="↗", layout="wide")
init_database()
init_session_state()


def main():
    config = get_config()
    count = get_stock_count()
    age = get_data_age_hours()
    refreshed = get_last_refresh()
    status = freshness_label(count, age, config.data.cache_expiry_hours)
    sectors = get_sector_breakdown()
    frame = pd.DataFrame(sectors)
    valid = frame.dropna(subset=['Avg_Return_3M']) if sectors else pd.DataFrame()
    apply_style()
    markup(f'<div class="mt-topline"><b>Workspace / Overview</b><span>{datetime.now():%A, %d %B %Y} · Server date</span></div>')
    if not valid.empty:
        leader = valid.loc[valid['Avg_Return_3M'].idxmax()]
        feature = (f'<div class="mt-kicker">Sector leader · 3 month average</div><strong>{escape(leader["Sector"])}</strong>'
                   f'<div class="mt-large">{leader["Avg_Return_3M"] * 100:+.1f}%</div>'
                   f'<span>Across {int(leader["Count"]):,} stocks in the cached universe.<br>Equal-weight stock returns, not an ETF return.</span>')
    else:
        feature = '<div class="mt-kicker">The HQM approach</div><strong>Strength over time.</strong><span>One month. Three months. Six months. One year.<br>Four perspectives on consistent momentum.</span>'
    markup('<div class="mt-hero"><div><div class="mt-kicker">The momentum briefing</div>'
           '<h1>A clearer view.<br><em>A stronger shortlist.</em></h1>'
           '<p>See where strength is building. Compare market leadership, find consistent momentum, and research your next move.</p></div>'
           f'<div class="mt-hero-aside">{feature}</div></div>')
    render_regime_banner()
    actions = st.columns([1, 1, 2])
    with actions[0]:
        if st.button("Find momentum stocks →", type="primary", use_container_width=True):
            st.switch_page("pages/1_Scanner.py")
    with actions[1]:
        st.page_link("pages/5_Backtest.py", label="Explore the strategy lab ↗")
    positive = int((valid['Avg_Return_3M'] > 0).sum()) if not valid.empty else 0
    stat_strip([
        ("STOCK UNIVERSE", f"{count:,}", "NYSE & NASDAQ · Cached snapshot"),
        ("SECTORS ADVANCING · 3M", f"{positive} / {len(valid)}" if not valid.empty else "—", "Sectors with positive average returns"),
        ("MOMENTUM WINDOWS", "1 / 3 / 6 / 12", "Monthly return windows for HQM ranking"),
        ("DATA STATUS", status, f"Updated {refreshed:%d %b · %H:%M}" if refreshed else "Refresh the universe to get started"),
    ])
    with st.sidebar:
        markup('<div class="mt-nav-label">Data connection</div>')
        st.caption(f"Universe: {count:,} stocks · {status}")
        if refreshed:
            st.caption(f"Snapshot {refreshed:%d %b %Y, %H:%M} (server time)")
        st.caption("FinViz / Universe & returns\n\nYahoo Finance / Price history")
    if count and status != "Fresh":
        st.warning("Refresh the universe in Scanner before researching current setups. This snapshot is out of date or its age is unknown.")
    section_heading("Where strength is building", "01 / Sector intelligence")
    if not valid.empty:
        chart, briefing = st.columns([2.25, 1], gap="large")
        with chart, st.container(border=True):
            period = st.radio("Compare sector returns", ["1 month", "3 months", "6 months", "1 year"], index=1, horizontal=True)
            window = {"1 month": "1M", "3 months": "3M", "6 months": "6M", "1 year": "1Y"}[period]
            st.plotly_chart(create_sector_performance_chart(sectors, window=window), use_container_width=True, config={'displayModeBar': False})
            st.caption("Equal-weight average of available stock returns in each sector. Hover to compare.")
        with briefing:
            with st.container(border=True):
                st.caption("THE LEADERSHIP SPREAD · 3M")
                laggard = valid.loc[valid['Avg_Return_3M'].idxmin()]
                spread = (leader['Avg_Return_3M'] - laggard['Avg_Return_3M']) * 100
                st.metric("Strongest to weakest sector", f"{spread:.1f} pp")
                st.write(f"**{leader['Sector']}** leads the universe; **{laggard['Sector']}** has the lowest average three-month return.")
                st.caption("Percentage-point difference between sector averages. It is not a forecast.")
                st.page_link("pages/4_Sectors.py", label="Explore sectors & industries →")
            with st.container(border=True):
                st.caption("RESEARCH PROMPT")
                st.markdown("#### Look beyond the leader.")
                st.write("Compare all four windows below. A strong three-month return can coexist with a weak longer-term trend.")

        section_heading("The bigger picture", "02 / Momentum across time")
        with st.container(border=True):
            st.plotly_chart(create_momentum_heatmap(sectors), use_container_width=True, config={'displayModeBar': False})
            st.caption("Sector average stock returns (%) · Green = positive · Terracotta = negative · Blank = unavailable")
    else:
        empty_workspace("Build your first market briefing", "Open the scanner and refresh the stock universe. Your sector charts and leadership insights will appear here once data is available.")
        st.page_link("pages/1_Scanner.py", label="Open scanner →")

    section_heading("Move from signal to research", "03 / Your workspace")
    for col, step, title, description, page, label in zip(
        st.columns(3), ['01 / DISCOVER', '02 / FOLLOW', '03 / EVALUATE'],
        ['Find consistent strength', 'Keep your ideas close', 'Put the strategy to work'],
        ['Screen across four timeframes, refine technical filters, and export a focused shortlist.',
         'Track target prices and keep your research notes with the stocks that matter to you.',
         'Inspect historical outcomes, trading costs, and drawdowns in the strategy lab.'],
        ['pages/1_Scanner.py', 'pages/2_Watchlist.py', 'pages/5_Backtest.py'],
        ['Open scanner', 'Open watchlist', 'Open strategy lab'],
    ):
        with col, st.container(border=True):
            st.caption(step)
            st.markdown(f"#### {title}")
            st.write(description)
            st.page_link(page, label=f"{label} →")
    with st.expander("Methodology & data limitations"):
        st.write(f"HQM averages percentile ranks for 1-month, 3-month, 6-month, and 1-year returns. "
                 f"Stocks must meet the configured minimum {config.strategy.min_percentile_threshold:g}th percentile "
                 "in every window before optional filters. Allocations target equal weights rounded to whole shares.")
        st.write("Rankings depend on the universe. Data can be delayed or unavailable; missing indicators can exclude stocks. "
                 "Public demo watchlists and portfolios use shared storage and may reset on redeploy.")
    research_note()


if __name__ == "__main__":
    main()
