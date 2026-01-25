# HQM Momentum Scanner

A comprehensive web application implementing the **High Quality Momentum (HQM) investment strategy**, inspired by Qullamaggie's quantitative trading approach. It identifies stocks showing consistent "slow and steady" momentum across multiple timeframes, with advanced features for backtesting, risk analysis, and portfolio management.

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
- **Sector Analysis**: Performance breakdown by sector

### User Interface
- **5 Navigation Tabs**: Scanner, Watchlist, Portfolio, Sectors, Backtest
- **Light/Dark Theme**: Toggle with persistent preference
- **Sortable Tables**: Click headers to sort any column
- **TradingView Integration**: Direct links to stock charts
- **CSV/Excel Export**: Download scan results

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, Flask, Gunicorn |
| Database | SQLite |
| Frontend | HTML5, Bootstrap 5, Chart.js |
| Data APIs | FinViz, yfinance |
| Data Science | Pandas, NumPy, SciPy |
| Technical Analysis | TA-Lib |
| Containerization | Docker, Docker Compose |
| Testing | pytest, pytest-cov |
| Type Checking | mypy |

## Installation

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd momentum_trader

# Start with Docker Compose
docker compose up -d

# View logs
docker logs -f hqm-momentum-scanner
```

Access at `http://localhost:5000`

### Option 2: Local Installation

```bash
# Clone the repository
git clone <repository-url>
cd momentum_trader

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

## Usage

### Web Application Workflow

1. **Refresh Data**: Click "Refresh" to fetch latest stock data from FinViz (~3-5 min)
2. **Configure Scan**: Set portfolio size, positions, and filters
3. **Run Scan**: Calculate HQM scores and generate recommendations
4. **Analyze Results**: Review stocks, sectors, and risk metrics
5. **Track Portfolio**: Add to watchlist or log positions

### Backtesting

1. Go to the **Backtest** tab
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

# Strategy Settings
strategy:
  min_percentile_threshold: 25

# Technical Indicators
indicators:
  rsi:
    period: 14
    overbought: 70
    oversold: 30
  sma:
    period: 10
    good_threshold: 5

# Backtesting
backtest:
  default_period_days: 365
  rebalance_frequency: weekly
  slippage_percent: 0.1
  commission_per_trade: 0
```

## API Endpoints

### Data Management
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/data-status` | GET | Current data age & stock count |
| `/api/refresh` | POST | Fetch fresh data from FinViz |
| `/api/config` | GET | Get current configuration |

### Scanning
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/scan` | POST | Run HQM scan with parameters |
| `/api/status` | GET | Get operation progress |
| `/api/results` | GET | Fetch latest scan results |
| `/api/history` | GET | Get scan history |

### Watchlist
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/watchlist` | GET | Get all watchlist items |
| `/api/watchlist` | POST | Add ticker to watchlist |
| `/api/watchlist/<ticker>` | DELETE | Remove from watchlist |

### Portfolio
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/portfolio` | GET | Get all positions |
| `/api/portfolio` | POST | Add new position |
| `/api/portfolio/<id>/close` | POST | Close a position |

### Analytics
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sectors` | GET | Sector performance breakdown |
| `/api/risk-metrics` | POST | Calculate portfolio risk metrics |
| `/api/stock-metrics/<ticker>` | GET | Individual stock metrics |

### Backtesting
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/backtest` | POST | Run backtest simulation |
| `/api/backtest/results` | GET | Get latest backtest results |
| `/api/backtest/history` | GET | Get backtest history |

## Project Structure

```
momentum_trader/
├── app.py                 # Flask server & API endpoints
├── momentum.py            # Core HQM strategy algorithm
├── database.py            # SQLite database management
├── backtest.py            # Backtesting engine
├── risk_metrics.py        # Risk calculations (Sharpe, VaR, etc.)
├── config_loader.py       # Type-safe configuration loader
├── logger.py              # Centralized logging
├── config.yaml            # Externalized configuration
├── requirements.txt       # Python dependencies
├── Dockerfile             # Multi-stage Docker build
├── docker-compose.yml     # Container orchestration
├── pytest.ini             # Test configuration
├── templates/
│   └── index.html         # Web UI template (5 tabs)
├── static/
│   ├── js/app.js          # Frontend logic
│   └── css/style.css      # Light/Dark theme styling
├── tests/
│   ├── __init__.py
│   └── test_hqm.py        # Unit tests
└── data/
    └── hqm_data.db        # SQLite database (auto-generated)
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
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_hqm.py -v
```

## Docker Commands

```bash
# Start in background
docker compose up -d

# View logs
docker logs -f hqm-momentum-scanner

# Stop
docker compose down

# Rebuild after code changes
docker compose up -d --build

# Development mode (with hot reload)
docker compose --profile dev up hqm-scanner-dev
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | production | Flask environment |
| `FLASK_DEBUG` | 0 | Enable debug mode |
| `PYTHONUNBUFFERED` | 1 | Unbuffered output |

## Performance Tips

1. **Initial Data Load**: First refresh takes 3-5 minutes (fetching ~2000 stocks)
2. **Subsequent Scans**: Use cached data if <24 hours old
3. **Backtesting**: Large universes may take several minutes
4. **Docker**: Uses multi-stage build for smaller image size

## License

MIT License

## Acknowledgments

- Strategy inspired by [Qullamaggie](https://qullamaggie.com/) momentum trading approach
- Data provided by [FinViz](https://finviz.com/) and [Yahoo Finance](https://finance.yahoo.com/)
- Technical analysis powered by [TA-Lib](https://github.com/bukosabino/ta)
