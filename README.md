# HQM Momentum Scanner

A web application implementing the **High Quality Momentum (HQM) investment strategy**, inspired by Qullamaggie's quantitative trading approach. It identifies stocks showing consistent "slow and steady" momentum across multiple timeframes, filtering out low-quality momentum caused by short-term news events.

## Strategy Overview

The HQM strategy differentiates between:

- **High-quality momentum**: Stocks showing strong performance across 1-month, 3-month, 6-month, and 1-year timeframes
- **Low-quality momentum**: Short-term spikes caused by news (e.g., FDA approvals) unlikely to sustain

By requiring consistency across all timeframes, the strategy filters out stocks with unreliable momentum patterns.

## Features

- **Multi-timeframe Momentum Analysis**: Prevents false signals from single-period spikes
- **Quality Filter**: Requires minimum 25th percentile in ALL timeframes
- **SMA10 Entry Filter**: Identifies optimal entry points based on 10-day moving average distance
- **SQLite Caching**: Fast scans without excessive API calls
- **Historical Tracking**: Enables backtesting and performance analysis
- **TradingView Integration**: Direct links to stock charts
- **CSV Export**: Download scan results for external analysis
- **Dark Theme UI**: Professional, low-eye-strain interface

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3, Flask |
| Database | SQLite |
| Frontend | HTML5, Bootstrap 5, Chart.js |
| Data APIs | FinViz, yfinance |
| Data Science | Pandas, NumPy, SciPy |

## Installation

### Prerequisites

- Python 3.8+
- pip or conda

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd momentum_trader

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Web Application

```bash
python app.py
```

Open your browser at `http://localhost:5000`

**Workflow:**
1. Click **"Refresh"** to fetch stock data from FinViz
2. Configure portfolio size and number of positions
3. Optionally enable SMA10 filter for better entry timing
4. Click **"Run Scan"** to calculate HQM scores
5. View results, charts, and export to CSV

### Command Line

```bash
python momentum.py
```

Follow the prompts to enter portfolio size and number of positions. Results are exported to `hqm_portfolio.xlsx`.

## Configuration

Default settings in `momentum.py`:

```python
PORTFOLIO_SIZE = 10000          # Portfolio size in USD
NUM_POSITIONS = 8               # Number of stocks to hold
MIN_MARKET_CAP = '+Mid (over $2bln)'  # Market cap filter
EXCHANGES = ['NYSE', 'NASDAQ']  # Exchanges to scan
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/data-status` | GET | Current data age & stock count |
| `/api/refresh` | POST | Fetch fresh data from FinViz |
| `/api/scan` | POST | Run HQM scan with parameters |
| `/api/status` | GET | Get operation progress |
| `/api/results` | GET | Fetch latest scan results |
| `/api/history` | GET | Get scan history |
| `/api/ticker-history/<ticker>` | GET | Get HQM history for specific ticker |

## Project Structure

```
momentum_trader/
├── app.py                 # Flask server & API endpoints
├── momentum.py            # Core HQM strategy algorithm
├── database.py            # SQLite database management
├── requirements.txt       # Python dependencies
├── templates/
│   └── index.html        # Web UI template
├── static/
│   ├── js/app.js         # Frontend logic
│   └── css/style.css     # Dark theme styling
└── hqm_data.db           # SQLite database (auto-generated)
```

## How HQM Scoring Works

1. **Percentile Calculation**: Each stock is ranked by return performance in each timeframe (0-100)
2. **Composite Score**: Average of percentiles across 4 timeframes
3. **Quality Filter**: Stocks below 25th percentile in ANY timeframe are removed
4. **Ranking**: Results sorted by HQM Score (highest first)
5. **Equal-weight Allocation**: Portfolio divided equally among selected positions

## SMA10 Distance Indicator

The optional SMA10 filter helps time entries:

- 🟢 **Green (≤5%)**: Good entry point
- 🟡 **Yellow (5-15%)**: Moderately extended
- 🔴 **Red (>15%)**: Overextended, consider waiting

## Dependencies

```
numpy
pandas
scipy
xlsxwriter
finvizfinance
flask
yfinance
```

## License

MIT License

## Acknowledgments

- Strategy inspired by [Qullamaggie](https://qullamaggie.com/) momentum trading approach
- Data provided by [FinViz](https://finviz.com/) and [Yahoo Finance](https://finance.yahoo.com/)
