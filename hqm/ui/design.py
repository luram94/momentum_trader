"""Presentation primitives for the Momentum Trader workspace."""
from html import escape
import math
from pathlib import Path

import streamlit as st

PAGES = [
    ("streamlit_app.py", "Overview", "01"),
    ("pages/1_Scanner.py", "Momentum scanner", "02"),
    ("pages/2_Watchlist.py", "Watchlist", "03"),
    ("pages/3_Portfolio.py", "Portfolio", "04"),
    ("pages/4_Sectors.py", "Sector intelligence", "05"),
    ("pages/5_Backtest.py", "Strategy lab", "06"),
]


def freshness_label(stock_count: int, age: float, expiry: float) -> str:
    if not stock_count:
        return "No data"
    if not math.isfinite(age):
        return "Unknown age"
    return "Fresh" if age < expiry else "Refresh needed"


def markup(content: str) -> None:
    st.markdown(content, unsafe_allow_html=True)


def apply_style() -> None:
    markup(f'<style>{Path(__file__).with_name("workspace.css").read_text()}</style>')
    with st.sidebar:
        markup('<div class="mt-brand"><span class="mt-mark">↗</span>momentum<span style="font-weight:400">trader</span></div>'
               '<div class="mt-nav-label">Research workspace</div>')
        for page, label, _ in PAGES:
            st.page_link(page, label=label, use_container_width=True)
        st.divider()


def page_header(title: str, description: str, section: str = "Research workspace") -> None:
    apply_style()
    number = next((n for _, label, n in PAGES if label.lower() == title.lower()), "02")
    markup(f'<div class="mt-topline"><b>Workspace / {escape(title)}</b><span>High quality momentum</span></div>'
           f'<div class="mt-page-heading"><div><h1>{escape(title)}</h1><p>{escape(description)}</p></div>'
           f'<span class="mt-page-number" aria-hidden="true">{number}</span></div>')


def section_heading(title: str, note: str = "") -> None:
    markup(f'<div class="mt-section"><h2>{escape(title)}</h2><span>{escape(note)}</span></div>')


def stat_strip(items: list[tuple[str, str, str]]) -> None:
    cards = ''.join(f'<div class="mt-stat"><div class="mt-stat-label">{escape(label)}</div>'
                    f'<div class="mt-stat-value">{escape(value)}</div><div class="mt-stat-note">{escape(note)}</div></div>'
                    for label, value, note in items)
    markup(f'<div class="mt-stat-grid">{cards}</div>')


def empty_workspace(title: str, description: str) -> None:
    markup(f'<div class="mt-empty"><span class="mt-badge">Your research starts here</span>'
           f'<h2>{escape(title)}</h2><p>{escape(description)}</p></div>')


def workflow_steps(items: list[tuple[str, str]]) -> None:
    cards = ''.join(f'<div class="mt-step"><b>0{i} /</b><h3>{escape(title)}</h3><p>{escape(text)}</p></div>'
                    for i, (title, text) in enumerate(items, 1))
    markup(f'<div class="mt-steps">{cards}</div>')


def research_note() -> None:
    markup('<div class="mt-footer">MOMENTUM TRADER &nbsp; / &nbsp; Research only. Prices are cached snapshots, '
           'not live quotes. HQM ranks relative momentum and does not predict future returns.</div>')
