# HQM Momentum Scanner

A comprehensive web application implementing the **High Quality Momentum (HQM) investment strategy**, inspired by Qullamaggie's quantitative trading approach. It identifies stocks showing consistent "slow and steady" momentum across multiple timeframes, with advanced features for backtesting, risk analysis, and portfolio management.

**Live Demo**: [momentumtrader-main.streamlit.app](https://momentumtrader-main.streamlit.app)

## Strategy Overview

The HQM strategy differentiates between:

- **High-quality momentum**: Stocks showing strong performance across 1-month, 3-month, 6-month, and 1-year timeframes
- **Low-quality momentum**: Short-term spikes caused by news (e.g., FDA approvals) unlikely to sustain

By requiring consistency across all timeframes, the strategy filters out stocks with unreliable momentum patterns.

## Features

### Core Scanning
- **Multi-timeframe Momentum Analysis**: Prevents false signals from single-period spikes
- **Quality Filter**: Requires minimum 25th percentile in ALL timeframes
- **HQM Score**: Composite ranking based on percentile averages

### Technical Indicators
- **RSI (Relative Strength Index)**: 14-period momentum oscillator
- **SMA10 Distance**: Entry timing based on 10-day moving average
- **ATR (Average True Range)**: Volatility measurement for position sizing

### Risk Analytics
- **Sharpe Ratio**: Risk-adjusted return measurement
- **Sortino Ratio**: Downside risk-adjusted returns
- **Maximum Drawdown**: Worst peak-to-trough decline
- **Value at Risk (VaR)**: 95% and 99% confidence levels
- **Beta**: Market correlation coefficient

### Backtesting Engine
- **Historical Simulation**: Test strategy on past data
- **Rebalancing Options**: Daily, weekly, or monthly
- **Slippage & Commissions**: Realistic cost modeling
- **Performance Metrics**: Comprehensive results analysis

### Portfolio Management
- **Watchlist**: Track stocks of interest
- **Portfolio Tracking**: Log positions and monitor P&L
- **Sector & Industry Analysis**: Performance breakdown by sector and industry, with drill-down by sector

> **Note**: The app has no user accounts. On the public demo deployment,
> Watchlist and Portfolio data is stored in a single shared, ephemeral
> database — it is visible to all visitors and resets on redeploy. Run the
> app locally for private, persistent tracking.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Streamlit, Plotly |
| Database | SQLite |
| Data APIs | FinViz, yfinance |
| Data Science | Pandas, NumPy, SciPy |
| Hosting | Streamlit Cloud |

## Installation

### Local Development

```bash
# Clone the repository
git clone <repository-url>
cd momentum_trader

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies (use requirements-dev.txt to also get test tools)
pip install -r requirements.txt

# Run the application
streamlit run streamlit_app.py
```

Access at `http://localhost:8501`

### Run with Docker

```bash
docker compose up --build
```

Access at `http://localhost:8501`. The SQLite database (`data/`) and logs
(`logs/`) are bind-mounted from the host, so they persist across container
rebuilds.

## Usage

### Web Application Workflow

1. **Refresh Data**: Click "Refresh" to fetch latest stock data from FinViz (~3-5 min)
2. **Configure Scan**: Set portfolio size, positions, and filters
3. **Run Scan**: Calculate HQM scores and generate recommendations
4. **Analyze Results**: Review stocks, sectors, and risk metrics
5. **Track Portfolio**: Add to watchlist or log positions

### Backtesting

1. Go to the **Backtest** page
2. Select date range and parameters
3. Click "Run Backtest"
4. Review performance metrics and equity curve

## Configuration

All settings are externalized in `config.yaml`:

```yaml
# Portfolio Settings
portfolio:
  default_size: 10000
  default_positions: 8

# Data Collection
data:
  exchanges: [NYSE, NASDAQ]
  min_market_cap: '+Mid (over $2bln)'
  cache_expiry_hours: 24

# Strategy Settings (shared by scanner and backtest)
strategy:
  min_percentile_threshold: 25

# Scanner Filter Defaults (initial UI values; filters are opt-in)
scanner_filters:
  max_sma10_distance: 15
  max_rsi: 70
  min_avg_volume: 500000
  max_atr_percent: 10
  max_per_sector: 3

# Backtesting
backtest:
  default_period_days: 90
  rebalance_frequency: weekly
  slippage_percent: 0.1
  commission_per_trade: 0
```

## Project Structure

```
momentum_trader/
├── streamlit_app.py       # Main entry point
├── pages/
│   ├── 1_Scanner.py       # HQM scanner with filters
│   ├── 2_Watchlist.py     # Watchlist management
│   ├── 3_Portfolio.py     # Portfolio tracking
│   ├── 4_Sectors.py       # Sector & industry analysis
│   └── 5_Backtest.py      # Backtesting
├── hqm/                   # Core package
│   ├── database.py        # SQLite database management + HQM scan logic
│   ├── backtest.py        # Backtesting engine
│   ├── risk_metrics.py    # Risk calculations (Sharpe, VaR, etc.)
│   ├── config_loader.py   # Type-safe configuration loader
│   ├── logger.py          # Centralized logging
│   ├── formatting.py      # Number/percentage formatting helpers
│   └── ui/
│       ├── charts.py      # Plotly chart helpers
│       └── state.py       # Session state management
├── tests/                 # Pytest test suite
├── config.yaml            # Externalized configuration
├── requirements.txt       # Runtime dependencies
├── requirements-dev.txt   # Dev/test dependencies (pytest, coverage)
├── .streamlit/
│   └── config.toml        # Streamlit theme configuration
├── data/
│   └── hqm_data.db        # SQLite database (auto-generated)
└── logs/                  # Log output (auto-generated)
```

## How HQM Scoring Works

1. **Data Collection**: Fetch stocks from NYSE/NASDAQ via FinViz
2. **Return Calculation**: Calculate 1M, 3M, 6M, 1Y returns
3. **Percentile Ranking**: Rank each stock (0-100) per timeframe
4. **Quality Filter**: Remove stocks below 25th percentile in ANY timeframe
5. **HQM Score**: Average of all four percentiles
6. **Technical Overlay**: Add RSI, SMA10 distance, ATR
7. **Position Sizing**: Equal-weight allocation across selected stocks

## Indicator Reference

### HQM Score (0-100)
- **90+**: Exceptional momentum across all timeframes
- **80-90**: Strong momentum
- **70-80**: Good momentum
- **<70**: Moderate momentum

### RSI (0-100)
- **>70**: Overbought - caution on new entries
- **30-70**: Neutral zone
- **<30**: Oversold - potential bounce

### SMA10 Distance
- **≤5%** (Green): Good entry point
- **5-15%** (Yellow): Moderately extended
- **>15%** (Red): Overextended, consider waiting

### ATR Percent
- Measures volatility as % of price
- Higher = more volatile, adjust position size accordingly

## Running Tests

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=hqm --cov-report=html

# Run specific test file
pytest tests/test_hqm.py -v
```

## License

MIT License

## Acknowledgments

- Strategy inspired by [Qullamaggie](https://qullamaggie.com/) momentum trading approach
- Data provided by [FinViz](https://finviz.com/) and [Yahoo Finance](https://finance.yahoo.com/)
