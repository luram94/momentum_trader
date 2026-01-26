"""
Sectors Page
=============
Sector analysis and performance breakdown.
"""

import streamlit as st
import pandas as pd

from logger import get_logger
from database import (
    get_sector_breakdown,
    get_sector_hqm_scores,
    get_stock_count,
)
from components.state import init_session_state
from components.charts import (
    create_sector_pie_chart,
    create_sector_performance_chart,
)

logger = get_logger('sectors_page')

st.set_page_config(
    page_title="Sectors - HQM Momentum",
    page_icon="📊",
    layout="wide",
)

init_session_state()

st.title("Sector Analysis")
st.markdown("Analyze sector distribution and performance.")

# Check for data
stock_count = get_stock_count()

if stock_count == 0:
    st.warning("No market data available. Please refresh data from the Scanner page first.")
    st.stop()

# Get sector data
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

# Format the dataframe
df_display = df_breakdown.copy()

# Rename columns for display
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

# Sort by 3M return if available
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

# HQM Scores by Sector
if sector_hqm:
    st.divider()
    st.subheader("HQM Scores by Sector")
    st.caption("Average HQM scores from recent scans")

    df_hqm = pd.DataFrame(sector_hqm)

    # Sort by average HQM score
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

# Sector insights
st.divider()
st.subheader("Insights")

with st.expander("Sector Analysis Tips", expanded=False):
    st.markdown("""
    ### How to Use Sector Analysis

    **Momentum Rotation:**
    - Strong sectors tend to stay strong (momentum persistence)
    - Consider overweighting sectors with high average HQM scores
    - Use sector diversification to manage concentration risk

    **Warning Signs:**
    - Sudden sector weakness after extended strength (potential mean reversion)
    - Very high concentration in a single sector
    - Large divergence between 1M and 3M returns (momentum shift)

    **Best Practices:**
    - Limit positions to 2-3 per sector for diversification
    - Monitor sector rotation weekly
    - Consider both absolute and relative momentum
    """)

# Concentration warning
if 'Count' in df_breakdown.columns:
    max_concentration = df_breakdown['Count'].max() / df_breakdown['Count'].sum() * 100
    if max_concentration > 30:
        top_sector = df_breakdown.loc[df_breakdown['Count'].idxmax(), 'Sector']
        st.warning(f"High concentration: {top_sector} represents {max_concentration:.1f}% of the universe. Consider diversification filters.")
