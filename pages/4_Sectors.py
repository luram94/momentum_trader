"""
Sectors & Industries Page
==========================
Sector and industry analysis and performance breakdown.
"""

import streamlit as st
from hqm.ui.design import page_header, research_note, section_heading
import pandas as pd

from hqm.logger import get_logger
from hqm.database import (
    get_sector_breakdown,
    get_sector_hqm_scores,
    get_industry_breakdown,
    get_industry_hqm_scores,
    get_stock_count,
    get_top_stocks_by_group,
)
from hqm.formatting import frac_cols_to_pct
from hqm.ui.state import init_session_state
from hqm.ui.charts import (
    create_sector_pie_chart,
    create_sector_performance_chart,
    create_industry_pie_chart,
    create_industry_performance_chart,
)

logger = get_logger('sectors_page')

st.set_page_config(
    page_title="Sectors & Industries - HQM Momentum",
    page_icon="📊",
    layout="wide",
)

init_session_state()

page_header("Sector intelligence", "Explore where momentum is concentrated across the stock universe.")


def render_top_ranked(group: str, options: list[str], label: str) -> None:
    """Render a focused top-five drilldown for a selected sector or industry."""
    section_heading(f"Top ranked stocks", f"{label} / HQM ranking")
    selected = st.selectbox(
        f"Choose a {label.lower()}", options, key=f"leaders_{group}",
        help="HQM scores are calculated against the full cached universe, then filtered to this group.",
    )
    leaders = get_top_stocks_by_group(group, selected, limit=5)
    if not leaders:
        st.info(f"No ranked stocks are available for {selected} in this snapshot.")
        return
    frame = pd.DataFrame(leaders)
    frame.insert(0, "Rank", range(1, len(frame) + 1))
    frame["HQM"] = frame["HQM_Score"].round(1)
    frame["Price"] = frame["Price"].round(2)
    for col in ["Return_1M", "Return_3M", "Return_6M", "Return_1Y"]:
        frame[col] = frame[col] * 100
    frame["Chart"] = frame.apply(
        lambda row: f"https://www.tradingview.com/chart/?symbol={row['Exchange']}%3A{row['Ticker']}", axis=1
    )
    display = frame[["Rank", "Ticker", "Price", "HQM", "Return_1M", "Return_3M", "Return_6M", "Return_1Y", "Chart"]]
    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Rank": st.column_config.NumberColumn("#", format="%d"),
            "Ticker": st.column_config.TextColumn("Ticker"),
            "Price": st.column_config.NumberColumn("Price", format="$%.2f"),
            "HQM": st.column_config.ProgressColumn("HQM score", min_value=0, max_value=100, format="%.1f"),
            "Return_1M": st.column_config.NumberColumn("1M", format="%+.1f%%"),
            "Return_3M": st.column_config.NumberColumn("3M", format="%+.1f%%"),
            "Return_6M": st.column_config.NumberColumn("6M", format="%+.1f%%"),
            "Return_1Y": st.column_config.NumberColumn("1Y", format="%+.1f%%"),
            "Chart": st.column_config.LinkColumn("Chart", display_text="View ↗"),
        },
    )
    st.caption("Ranked by average percentile across 1M, 3M, 6M, and 1Y returns. Percentiles use the full cached universe.")


# Check for data
stock_count = get_stock_count()

if stock_count == 0:
    st.warning("No market data available. Please refresh data from the Scanner page first.")
    st.stop()

# Main tabs
tab_sectors, tab_industries = st.tabs(["Sectors", "Industries"])


# =============================================================================
# SECTORS TAB
# =============================================================================
with tab_sectors:
    sector_breakdown = get_sector_breakdown()
    sector_hqm = get_sector_hqm_scores()

    if not sector_breakdown:
        st.info("No sector data available. Run a scan to populate sector information.")
        st.stop()

    # Summary metrics
    st.subheader("Overview")

    df_breakdown = pd.DataFrame(sector_breakdown)
    total_stocks = df_breakdown['Count'].sum() if 'Count' in df_breakdown.columns else 0
    num_sectors = len(df_breakdown)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Stocks", f"{total_stocks:,}")

    with col2:
        st.metric("Sectors", num_sectors)

    with col3:
        if 'Avg_Return_3M' in df_breakdown.columns:
            best_sector = df_breakdown.loc[df_breakdown['Avg_Return_3M'].idxmax(), 'Sector']
            st.metric("Best Performing", best_sector)
        else:
            st.metric("Best Performing", "N/A")

    st.divider()

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Sector Distribution")
        fig = create_sector_pie_chart(sector_breakdown)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Sector Performance")
        fig = create_sector_performance_chart(sector_breakdown)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Sector breakdown table
    st.subheader("Sector Details")

    df_display = df_breakdown.copy()

    column_mapping = {
        'Sector': 'Sector',
        'Count': 'Stock Count',
        'Avg_Return_1M': '1M Avg Return',
        'Avg_Return_3M': '3M Avg Return',
        'Avg_Return_6M': '6M Avg Return',
        'Avg_Return_1Y': '1Y Avg Return',
    }

    available_cols = [c for c in column_mapping.keys() if c in df_display.columns]
    df_display = df_display[available_cols]
    df_display.columns = [column_mapping[c] for c in available_cols]

    # Returns are stored as decimal fractions; scale to percent for display
    df_display = frac_cols_to_pct(
        df_display, ['1M Avg Return', '3M Avg Return', '6M Avg Return', '1Y Avg Return']
    )

    if '3M Avg Return' in df_display.columns:
        df_display = df_display.sort_values('3M Avg Return', ascending=False)

    st.dataframe(
        df_display,
        column_config={
            'Sector': 'Sector',
            'Stock Count': st.column_config.NumberColumn('Stocks', format="%d"),
            '1M Avg Return': st.column_config.NumberColumn('1M Avg', format="%.2f%%"),
            '3M Avg Return': st.column_config.NumberColumn('3M Avg', format="%.2f%%"),
            '6M Avg Return': st.column_config.NumberColumn('6M Avg', format="%.2f%%"),
            '1Y Avg Return': st.column_config.NumberColumn('1Y Avg', format="%.2f%%"),
        },
        hide_index=True,
        use_container_width=True,
    )

    render_top_ranked("sector", sorted(df_breakdown['Sector'].dropna().unique().tolist()), "Sector")

    # HQM Scores by Sector
    if sector_hqm:
        st.divider()
        st.subheader("HQM Scores by Sector")
        st.caption("Average HQM scores from recent scans")

        df_hqm = pd.DataFrame(sector_hqm)
        df_hqm = frac_cols_to_pct(df_hqm, ['avg_return_1m', 'avg_return_3m'])

        if 'avg_hqm' in df_hqm.columns:
            df_hqm = df_hqm.sort_values('avg_hqm', ascending=False)

        column_config = {
            'sector': 'Sector',
            'avg_hqm': st.column_config.NumberColumn('Avg HQM', format="%.1f"),
            'total_stocks': st.column_config.NumberColumn('Stocks', format="%d"),
            'avg_return_1m': st.column_config.NumberColumn('1M Avg', format="%.2f%%"),
            'avg_return_3m': st.column_config.NumberColumn('3M Avg', format="%.2f%%"),
        }

        available_cols = [c for c in column_config.keys() if c in df_hqm.columns]

        st.dataframe(
            df_hqm[available_cols],
            column_config={k: v for k, v in column_config.items() if k in available_cols},
            hide_index=True,
            use_container_width=True,
        )

    # Concentration warning
    if 'Count' in df_breakdown.columns:
        max_concentration = df_breakdown['Count'].max() / df_breakdown['Count'].sum() * 100
        if max_concentration > 30:
            top_sector = df_breakdown.loc[df_breakdown['Count'].idxmax(), 'Sector']
            st.warning(f"High concentration: {top_sector} represents {max_concentration:.1f}% of the universe. Consider diversification filters.")


# =============================================================================
# INDUSTRIES TAB
# =============================================================================
with tab_industries:
    industry_breakdown = get_industry_breakdown()
    industry_hqm = get_industry_hqm_scores()

    if not industry_breakdown:
        st.info("No industry data available. Run a scan to populate industry information.")
        st.stop()

    # Summary metrics
    st.subheader("Overview")

    df_ind_breakdown = pd.DataFrame(industry_breakdown)
    total_stocks_ind = df_ind_breakdown['Count'].sum() if 'Count' in df_ind_breakdown.columns else 0
    num_industries = len(df_ind_breakdown)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Stocks", f"{total_stocks_ind:,}")

    with col2:
        st.metric("Industries", num_industries)

    with col3:
        if 'Avg_Return_3M' in df_ind_breakdown.columns:
            best_industry = df_ind_breakdown.loc[df_ind_breakdown['Avg_Return_3M'].idxmax(), 'Industry']
            st.metric("Best Performing", best_industry)
        else:
            st.metric("Best Performing", "N/A")

    st.divider()

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Industry Distribution")
        fig = create_industry_pie_chart(industry_breakdown)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Industry Performance")
        fig = create_industry_performance_chart(industry_breakdown)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Industry breakdown table with sector column and search
    st.subheader("Industry Details")

    # Sector filter for drilling down
    sectors_in_data = sorted(df_ind_breakdown['Sector'].dropna().unique().tolist())
    selected_sector = st.selectbox(
        "Filter by Sector",
        options=["All Sectors"] + sectors_in_data,
        index=0,
    )

    df_ind_display = df_ind_breakdown.copy()
    if selected_sector != "All Sectors":
        df_ind_display = df_ind_display[df_ind_display['Sector'] == selected_sector]

    column_mapping = {
        'Industry': 'Industry',
        'Sector': 'Sector',
        'Count': 'Stock Count',
        'Avg_Return_1M': '1M Avg Return',
        'Avg_Return_3M': '3M Avg Return',
        'Avg_Return_6M': '6M Avg Return',
        'Avg_Return_1Y': '1Y Avg Return',
    }

    available_cols = [c for c in column_mapping.keys() if c in df_ind_display.columns]
    df_ind_display = df_ind_display[available_cols]
    df_ind_display.columns = [column_mapping[c] for c in available_cols]

    # Returns are stored as decimal fractions; scale to percent for display
    df_ind_display = frac_cols_to_pct(
        df_ind_display, ['1M Avg Return', '3M Avg Return', '6M Avg Return', '1Y Avg Return']
    )

    if '3M Avg Return' in df_ind_display.columns:
        df_ind_display = df_ind_display.sort_values('3M Avg Return', ascending=False)

    st.dataframe(
        df_ind_display,
        column_config={
            'Industry': 'Industry',
            'Sector': 'Sector',
            'Stock Count': st.column_config.NumberColumn('Stocks', format="%d"),
            '1M Avg Return': st.column_config.NumberColumn('1M Avg', format="%.2f%%"),
            '3M Avg Return': st.column_config.NumberColumn('3M Avg', format="%.2f%%"),
            '6M Avg Return': st.column_config.NumberColumn('6M Avg', format="%.2f%%"),
            '1Y Avg Return': st.column_config.NumberColumn('1Y Avg', format="%.2f%%"),
        },
        hide_index=True,
        use_container_width=True,
    )

    render_top_ranked("industry", sorted(df_ind_breakdown['Industry'].dropna().unique().tolist()), "Industry")

    # HQM Scores by Industry
    if industry_hqm:
        st.divider()
        st.subheader("HQM Scores by Industry")
        st.caption("Average HQM scores from recent scans (top 30)")

        df_ind_hqm = pd.DataFrame(industry_hqm)
        df_ind_hqm = frac_cols_to_pct(df_ind_hqm, ['avg_return_1m', 'avg_return_3m'])

        if 'avg_hqm' in df_ind_hqm.columns:
            df_ind_hqm = df_ind_hqm.sort_values('avg_hqm', ascending=False).head(30)

        column_config = {
            'industry': 'Industry',
            'avg_hqm': st.column_config.NumberColumn('Avg HQM', format="%.1f"),
            'total_stocks': st.column_config.NumberColumn('Stocks', format="%d"),
            'avg_return_1m': st.column_config.NumberColumn('1M Avg', format="%.2f%%"),
            'avg_return_3m': st.column_config.NumberColumn('3M Avg', format="%.2f%%"),
        }

        available_cols = [c for c in column_config.keys() if c in df_ind_hqm.columns]

        st.dataframe(
            df_ind_hqm[available_cols],
            column_config={k: v for k, v in column_config.items() if k in available_cols},
            hide_index=True,
            use_container_width=True,
        )

    # Concentration warning
    if 'Count' in df_ind_breakdown.columns:
        max_concentration = df_ind_breakdown['Count'].max() / df_ind_breakdown['Count'].sum() * 100
        if max_concentration > 15:
            top_industry = df_ind_breakdown.loc[df_ind_breakdown['Count'].idxmax(), 'Industry']
            st.warning(f"High concentration: {top_industry} represents {max_concentration:.1f}% of the universe.")


# =============================================================================
# SHARED INSIGHTS
# =============================================================================
st.divider()
st.subheader("Insights")

with st.expander("Sector & Industry Analysis Tips", expanded=False):
    st.markdown("""
    ### How to Use This Analysis

    **Momentum Rotation:**
    - Strong sectors/industries tend to stay strong (momentum persistence)
    - Consider overweighting sectors with high average HQM scores
    - Use sector diversification to manage concentration risk

    **Industry Drill-Down:**
    - Use the sector filter on the Industries tab to find the strongest industries within a sector
    - Industries are more specific than sectors -- e.g., "Semiconductor Equipment" vs "Technology"
    - Industry-level analysis helps identify targeted momentum themes

    **Warning Signs:**
    - Sudden sector/industry weakness after extended strength (potential mean reversion)
    - Very high concentration in a single industry
    - Large divergence between 1M and 3M returns (momentum shift)

    **Best Practices:**
    - Limit positions to 2-3 per sector for diversification
    - Monitor sector and industry rotation weekly
    - Consider both absolute and relative momentum
    """)


research_note()
