"""
Chart Components
=================
Plotly chart helpers for the HQM Scanner Streamlit app.
"""

from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# Theme colors matching the Streamlit config
COLORS = {
    'primary': '#198754',
    'success': '#20c997',
    'warning': '#ffc107',
    'danger': '#dc3545',
    'background': '#0d1117',
    'paper': '#161b22',
    'text': '#c9d1d9',
    'grid': '#30363d',
}


def _apply_dark_theme(fig: go.Figure) -> go.Figure:
    """Apply consistent dark theme to a Plotly figure."""
    fig.update_layout(
        paper_bgcolor=COLORS['paper'],
        plot_bgcolor=COLORS['background'],
        font=dict(color=COLORS['text']),
        xaxis=dict(
            gridcolor=COLORS['grid'],
            zerolinecolor=COLORS['grid'],
        ),
        yaxis=dict(
            gridcolor=COLORS['grid'],
            zerolinecolor=COLORS['grid'],
        ),
        margin=dict(l=40, r=40, t=40, b=40),
    )
    return fig


def create_allocation_chart(results: List[Dict[str, Any]]) -> go.Figure:
    """
    Create a horizontal bar chart showing portfolio allocation.

    Args:
        results: List of scan result dictionaries with 'Ticker' and 'Value' keys

    Returns:
        Plotly figure
    """
    df = pd.DataFrame(results)

    fig = go.Figure(go.Bar(
        x=df['Value'],
        y=df['Ticker'],
        orientation='h',
        marker_color=COLORS['primary'],
        text=df['Value'].apply(lambda x: f'${x:,.0f}'),
        textposition='auto',
    ))

    fig.update_layout(
        title='Portfolio Allocation',
        xaxis_title='Value ($)',
        yaxis_title='Ticker',
        yaxis=dict(categoryorder='total ascending'),
        height=max(400, len(df) * 35),
    )

    return _apply_dark_theme(fig)


def create_hqm_score_chart(results: List[Dict[str, Any]]) -> go.Figure:
    """
    Create a horizontal bar chart showing HQM scores.

    Args:
        results: List of scan result dictionaries with 'Ticker' and 'HQM_Score' keys

    Returns:
        Plotly figure
    """
    df = pd.DataFrame(results)

    # Color based on score
    colors = df['HQM_Score'].apply(
        lambda x: COLORS['success'] if x >= 80 else COLORS['warning'] if x >= 60 else COLORS['danger']
    )

    fig = go.Figure(go.Bar(
        x=df['HQM_Score'],
        y=df['Ticker'],
        orientation='h',
        marker_color=colors,
        text=df['HQM_Score'].apply(lambda x: f'{x:.1f}'),
        textposition='auto',
    ))

    fig.update_layout(
        title='HQM Scores',
        xaxis_title='HQM Score',
        yaxis_title='Ticker',
        yaxis=dict(categoryorder='total ascending'),
        xaxis=dict(range=[0, 100]),
        height=max(400, len(df) * 35),
    )

    return _apply_dark_theme(fig)


def create_sector_pie_chart(
    sector_data: List[Dict[str, Any]],
    value_column: str = 'Count'
) -> go.Figure:
    """
    Create a pie chart showing sector distribution.

    Args:
        sector_data: List of dictionaries with 'Sector' and value column
        value_column: Column name for values

    Returns:
        Plotly figure
    """
    df = pd.DataFrame(sector_data)

    fig = px.pie(
        df,
        values=value_column,
        names='Sector',
        color_discrete_sequence=px.colors.qualitative.Set2,
    )

    fig.update_traces(
        textposition='inside',
        textinfo='percent+label',
    )

    fig.update_layout(
        title='Sector Distribution',
        showlegend=True,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=-0.2,
            xanchor='center',
            x=0.5
        ),
        height=450,
    )

    return _apply_dark_theme(fig)


def create_equity_curve(portfolio_history: List[Dict[str, Any]]) -> go.Figure:
    """
    Create an equity curve chart from backtest results.

    Args:
        portfolio_history: List of portfolio history records

    Returns:
        Plotly figure
    """
    df = pd.DataFrame(portfolio_history)
    df['date'] = pd.to_datetime(df['date'])

    fig = go.Figure()

    # Equity curve
    fig.add_trace(go.Scatter(
        x=df['date'],
        y=df['total_value'],
        mode='lines',
        name='Portfolio Value',
        line=dict(color=COLORS['primary'], width=2),
        fill='tozeroy',
        fillcolor=f"rgba(25, 135, 84, 0.2)",
    ))

    fig.update_layout(
        title='Equity Curve',
        xaxis_title='Date',
        yaxis_title='Portfolio Value ($)',
        hovermode='x unified',
        height=400,
    )

    return _apply_dark_theme(fig)


def create_drawdown_chart(portfolio_history: List[Dict[str, Any]]) -> go.Figure:
    """
    Create a drawdown chart from backtest results.

    Args:
        portfolio_history: List of portfolio history records

    Returns:
        Plotly figure
    """
    df = pd.DataFrame(portfolio_history)
    df['date'] = pd.to_datetime(df['date'])

    # Calculate drawdown
    df['cummax'] = df['total_value'].cummax()
    df['drawdown'] = (df['total_value'] - df['cummax']) / df['cummax'] * 100

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df['date'],
        y=df['drawdown'],
        mode='lines',
        name='Drawdown',
        line=dict(color=COLORS['danger'], width=2),
        fill='tozeroy',
        fillcolor=f"rgba(220, 53, 69, 0.2)",
    ))

    fig.update_layout(
        title='Drawdown',
        xaxis_title='Date',
        yaxis_title='Drawdown (%)',
        hovermode='x unified',
        height=300,
    )

    return _apply_dark_theme(fig)


def create_returns_comparison_chart(
    results: List[Dict[str, Any]]
) -> go.Figure:
    """
    Create a grouped bar chart comparing returns across timeframes.

    Args:
        results: List of scan result dictionaries

    Returns:
        Plotly figure
    """
    df = pd.DataFrame(results)

    # Only show top 10 for readability
    df = df.head(10)

    fig = go.Figure()

    timeframes = [
        ('Return_1M', '1 Month', COLORS['primary']),
        ('Return_3M', '3 Month', COLORS['success']),
        ('Return_6M', '6 Month', COLORS['warning']),
        ('Return_1Y', '1 Year', '#6f42c1'),
    ]

    for col, name, color in timeframes:
        if col in df.columns:
            fig.add_trace(go.Bar(
                name=name,
                x=df['Ticker'],
                y=df[col] * 100,  # Convert to percentage
                marker_color=color,
            ))

    fig.update_layout(
        title='Returns by Timeframe (Top 10)',
        xaxis_title='Ticker',
        yaxis_title='Return (%)',
        barmode='group',
        height=400,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='center',
            x=0.5
        ),
    )

    return _apply_dark_theme(fig)


def create_sector_performance_chart(
    sector_data: List[Dict[str, Any]]
) -> go.Figure:
    """
    Create a bar chart showing sector performance.

    Args:
        sector_data: List of sector performance dictionaries

    Returns:
        Plotly figure
    """
    df = pd.DataFrame(sector_data)

    if 'Avg_Return_3M' in df.columns:
        df = df.sort_values('Avg_Return_3M', ascending=True)
        colors = df['Avg_Return_3M'].apply(
            lambda x: COLORS['success'] if x > 0 else COLORS['danger']
        )

        fig = go.Figure(go.Bar(
            x=df['Avg_Return_3M'] * 100,
            y=df['Sector'],
            orientation='h',
            marker_color=colors,
            text=df['Avg_Return_3M'].apply(lambda x: f'{x*100:.1f}%'),
            textposition='auto',
        ))

        fig.update_layout(
            title='Sector Performance (3-Month Avg Return)',
            xaxis_title='Return (%)',
            yaxis_title='Sector',
            height=max(400, len(df) * 35),
        )
    else:
        # Fallback to count-based chart
        fig = go.Figure(go.Bar(
            x=df.get('Count', df.get('stock_count', [])),
            y=df['Sector'],
            orientation='h',
            marker_color=COLORS['primary'],
        ))

        fig.update_layout(
            title='Stocks by Sector',
            xaxis_title='Count',
            yaxis_title='Sector',
            height=max(400, len(df) * 35),
        )

    return _apply_dark_theme(fig)


def create_industry_pie_chart(
    industry_data: List[Dict[str, Any]],
    value_column: str = 'Count',
    top_n: int = 15
) -> go.Figure:
    """
    Create a pie chart showing industry distribution (top N).

    Args:
        industry_data: List of dictionaries with 'Industry' and value column
        value_column: Column name for values
        top_n: Number of top industries to show individually

    Returns:
        Plotly figure
    """
    df = pd.DataFrame(industry_data)

    # Group smaller industries into "Other"
    if len(df) > top_n:
        df = df.sort_values(value_column, ascending=False)
        top = df.head(top_n).copy()
        other_sum = df.iloc[top_n:][value_column].sum()
        other_row = pd.DataFrame([{'Industry': 'Other', value_column: other_sum}])
        df = pd.concat([top, other_row], ignore_index=True)

    fig = px.pie(
        df,
        values=value_column,
        names='Industry',
        color_discrete_sequence=px.colors.qualitative.Set3,
    )

    fig.update_traces(
        textposition='inside',
        textinfo='percent+label',
    )

    fig.update_layout(
        title=f'Industry Distribution (Top {top_n})',
        showlegend=True,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=-0.3,
            xanchor='center',
            x=0.5
        ),
        height=500,
    )

    return _apply_dark_theme(fig)


def create_industry_performance_chart(
    industry_data: List[Dict[str, Any]],
    top_n: int = 20
) -> go.Figure:
    """
    Create a bar chart showing industry performance (top and bottom).

    Args:
        industry_data: List of industry performance dictionaries
        top_n: Number of industries to show

    Returns:
        Plotly figure
    """
    df = pd.DataFrame(industry_data)

    if 'Avg_Return_3M' in df.columns:
        df = df.sort_values('Avg_Return_3M', ascending=False)
        # Show top and bottom performers
        if len(df) > top_n:
            half = top_n // 2
            df = pd.concat([df.head(half), df.tail(half)])
        df = df.sort_values('Avg_Return_3M', ascending=True)

        colors = df['Avg_Return_3M'].apply(
            lambda x: COLORS['success'] if x > 0 else COLORS['danger']
        )

        fig = go.Figure(go.Bar(
            x=df['Avg_Return_3M'] * 100,
            y=df['Industry'],
            orientation='h',
            marker_color=colors,
            text=df['Avg_Return_3M'].apply(lambda x: f'{x*100:.1f}%'),
            textposition='auto',
        ))

        fig.update_layout(
            title='Industry Performance (3-Month Avg Return)',
            xaxis_title='Return (%)',
            yaxis_title='Industry',
            height=max(500, len(df) * 28),
        )
    else:
        fig = go.Figure(go.Bar(
            x=df.get('Count', df.get('stock_count', [])),
            y=df['Industry'],
            orientation='h',
            marker_color=COLORS['primary'],
        ))

        fig.update_layout(
            title='Stocks by Industry',
            xaxis_title='Count',
            yaxis_title='Industry',
            height=max(500, len(df) * 28),
        )

    return _apply_dark_theme(fig)
