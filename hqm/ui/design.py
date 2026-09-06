"""Shared presentation for the research workspace."""

from html import escape
import math

import streamlit as st


def freshness_label(stock_count: int, age: float, expiry: float) -> str:
    if not stock_count:
        return "No data"
    if not math.isfinite(age):
        return "Unknown age"
    return "Fresh" if age < expiry else "Refresh needed"


def apply_style() -> None:
    """Use stable Streamlit element selectors; keep native navigation accessible."""
    with st.sidebar:
        st.markdown("### Momentum Trader")
        st.caption("HIGH QUALITY MOMENTUM")
        for page, label in [
            ("streamlit_app.py", "Overview"),
            ("pages/1_Scanner.py", "Momentum scanner"),
            ("pages/2_Watchlist.py", "Watchlist"),
            ("pages/3_Portfolio.py", "Portfolio"),
            ("pages/4_Sectors.py", "Sector intelligence"),
            ("pages/5_Backtest.py", "Strategy lab"),
        ]:
            st.page_link(page, label=label, use_container_width=True)
        st.divider()
    st.markdown("""<style>
    .block-container {max-width: 1440px; padding-top: 2.5rem; padding-bottom: 3rem;}
    h1, h2, h3 {letter-spacing: -.035em;}
    h1 {font-weight: 750 !important;}
    [data-testid="stMetric"] {background: #111f32; border: 1px solid #26364a;
        border-radius: 12px; padding: 18px 20px; height: 100%;}
    [data-testid="stMetricLabel"] {color: #a8b8ce;}
    [data-testid="stMetricValue"] {font-variant-numeric: tabular-nums;}
    [data-testid="stSidebar"] {border-right: 1px solid #26364a;}
    [data-testid="stButton"] button, [data-testid="stDownloadButton"] button {
        border-radius: 8px; min-height: 2.7rem;}
    [data-testid="stDataFrame"] {border: 1px solid #26364a; border-radius: 10px;}
    .hqm-eyebrow {color: #5eead4; font-size: .75rem; font-weight: 700;
        letter-spacing: .16em; text-transform: uppercase; margin-bottom: .6rem;}
    .hqm-description {color: #a8b8ce; max-width: 760px; font-size: 1.05rem;
        line-height: 1.7; margin-bottom: 1.8rem;}
    @media (max-width: 640px) {
        .block-container {padding: 4rem 1rem 2rem;}
        h1 {font-size: 2rem !important;}
        [data-testid="stMetric"] {padding: 12px;}
    }
    </style>""", unsafe_allow_html=True)


def page_header(title: str, description: str, section: str = "Research workspace") -> None:
    apply_style()
    st.markdown(f'<div class="hqm-eyebrow">Momentum Trader / {escape(section)}</div>',
                unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="hqm-description">{escape(description)}</div>',
                unsafe_allow_html=True)


def research_note() -> None:
    st.caption("Research only · Prices are cached snapshots, not live quotes. "
               "HQM scores rank relative momentum; they do not predict future returns.")
