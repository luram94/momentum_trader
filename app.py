"""
HQM Momentum Scanner - Flask Web Application
=============================================
Interactive web interface for the High Quality Momentum strategy.
Now with advanced features: backtesting, watchlist, portfolio tracking, and risk metrics.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional

from flask import Flask, render_template, jsonify, request

from logger import get_logger
from config_loader import get_config
from database import (
    fetch_and_store_data,
    run_hqm_scan_from_db,
    get_data_age_hours,
    get_last_refresh,
    get_stock_count,
    get_scan_history,
    get_hqm_history,
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
    add_portfolio_position,
    close_portfolio_position,
    get_portfolio_positions,
    get_portfolio_summary,
    get_sector_breakdown,
    get_sector_hqm_scores
)
from risk_metrics import calculate_all_risk_metrics, get_individual_stock_metrics
from backtest import run_backtest, get_backtest_history

# Initialize logger and config
logger = get_logger('app')
config = get_config()

app = Flask(__name__)
app.secret_key = config.web.secret_key

# Global state for operations
app_state: Dict[str, Any] = {
    'status': 'idle',  # idle, refreshing, scanning, backtesting, completed, error
    'progress': 0,
    'message': '',
    'results': None,
    'summary': None,
    'backtest_results': None
}
state_lock = threading.Lock()


def update_state(
    status: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    results: Optional[List[Dict]] = None,
    summary: Optional[Dict] = None,
    backtest_results: Optional[Dict] = None
) -> None:
    """Thread-safe state update."""
    with state_lock:
        if status is not None:
            app_state['status'] = status
        if progress is not None:
            app_state['progress'] = progress
        if message is not None:
            app_state['message'] = message
        if results is not None:
            app_state['results'] = results
        if summary is not None:
            app_state['summary'] = summary
        if backtest_results is not None:
            app_state['backtest_results'] = backtest_results


# =============================================================================
# FLASK ROUTES - PAGES
# =============================================================================

@app.route('/')
def index():
    """Render main page."""
    return render_template('index.html')


# =============================================================================
# FLASK ROUTES - DATA API
# =============================================================================

@app.route('/api/data-status')
def data_status():
    """Get current data status (age, count, etc.)."""
    last_refresh = get_last_refresh()
    return jsonify({
        'stock_count': get_stock_count(),
        'data_age_hours': round(get_data_age_hours(), 1),
        'last_refresh': last_refresh.isoformat() if last_refresh else None,
        'has_data': get_stock_count() > 0
    })


@app.route('/api/refresh', methods=['POST'])
def start_refresh():
    """Start data refresh from FinViz API."""
    with state_lock:
        if app_state['status'] in ['refreshing', 'scanning', 'backtesting']:
            return jsonify({'success': False, 'error': 'Operation already in progress'})

    update_state(status='refreshing', progress=0, message='Starting data refresh...')
    logger.info("Starting data refresh")

    def refresh_thread():
        try:
            def progress_callback(pct: int, msg: str) -> None:
                update_state(progress=pct, message=msg)

            stats = fetch_and_store_data(progress_callback)

            update_state(
                status='completed',
                progress=100,
                message=f"Refreshed {stats['total_stored']} stocks in {stats['duration_seconds']:.1f}s"
            )
            logger.info(f"Data refresh completed: {stats['total_stored']} stocks")

        except Exception as e:
            logger.error(f"Refresh failed: {e}")
            update_state(status='error', message=str(e))

    thread = threading.Thread(target=refresh_thread)
    thread.start()

    return jsonify({'success': True, 'message': 'Refresh started'})


# =============================================================================
# FLASK ROUTES - SCAN API
# =============================================================================

@app.route('/api/scan', methods=['POST'])
def start_scan():
    """Run HQM scan using cached database data with advanced filters."""
    # Check if we have data
    if get_stock_count() == 0:
        return jsonify({
            'success': False,
            'error': 'No data available. Please refresh data first.'
        })

    with state_lock:
        if app_state['status'] in ['refreshing', 'scanning', 'backtesting']:
            return jsonify({'success': False, 'error': 'Operation already in progress'})

    # Get parameters
    data = request.get_json()
    portfolio_size = float(data.get('portfolio_size', 10000))
    num_positions = int(data.get('num_positions', 8))

    # Optional filters
    max_sma10_distance = data.get('max_sma10_distance')
    if max_sma10_distance is not None and max_sma10_distance != '':
        try:
            max_sma10_distance = float(max_sma10_distance)
        except (ValueError, TypeError):
            max_sma10_distance = None

    # RSI filter
    rsi_filter = None
    if data.get('rsi_enabled'):
        rsi_min = float(data.get('rsi_min', 0))
        rsi_max = float(data.get('rsi_max', 70))
        rsi_filter = (rsi_min, rsi_max)

    # Volume filter
    min_volume = None
    if data.get('volume_enabled'):
        min_volume = int(data.get('min_volume', 500000))

    # ATR filter
    max_atr_percent = None
    if data.get('atr_enabled'):
        max_atr_percent = float(data.get('max_atr_percent', 10))

    # Sector filter
    sector_filter = data.get('sector_filter')  # List of sectors or None

    # Sector diversification
    max_per_sector = None
    if data.get('diversification_enabled'):
        max_per_sector = int(data.get('max_per_sector', 3))

    # Validate
    if portfolio_size < config.portfolio.min_size:
        return jsonify({'success': False, 'error': f'Portfolio size must be at least ${config.portfolio.min_size:,}'})
    if num_positions < 1 or num_positions > config.portfolio.max_positions:
        return jsonify({'success': False, 'error': f'Number of positions must be between 1 and {config.portfolio.max_positions}'})

    update_state(status='scanning', progress=0, message='Running HQM scan...')
    logger.info(f"Starting scan: ${portfolio_size:,.0f}, {num_positions} positions")

    def scan_thread():
        try:
            update_state(progress=30, message='Calculating HQM scores...')

            result = run_hqm_scan_from_db(
                portfolio_size=portfolio_size,
                num_positions=num_positions,
                max_sma10_distance=max_sma10_distance,
                rsi_filter=rsi_filter,
                min_volume=min_volume,
                max_atr_percent=max_atr_percent,
                sector_filter=sector_filter,
                max_per_sector=max_per_sector
            )

            if result['success']:
                # Calculate risk metrics for the portfolio
                tickers = [r['Ticker'] for r in result['results']]
                weights = [r['Weight'] / 100 for r in result['results']]

                update_state(progress=80, message='Calculating risk metrics...')

                risk_metrics = calculate_all_risk_metrics(
                    tickers=tickers,
                    weights=weights,
                    portfolio_value=portfolio_size
                )

                result['summary']['risk_metrics'] = risk_metrics

                update_state(
                    status='completed',
                    progress=100,
                    message='Scan complete!',
                    results=result['results'],
                    summary=result['summary']
                )
                logger.info(f"Scan completed: {len(result['results'])} stocks selected")
            else:
                update_state(status='error', message=result.get('error', 'Scan failed'))

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            update_state(status='error', message=str(e))

    thread = threading.Thread(target=scan_thread)
    thread.start()

    return jsonify({'success': True, 'message': 'Scan started'})


@app.route('/api/status')
def get_status():
    """Get current operation status."""
    with state_lock:
        return jsonify(app_state)


@app.route('/api/results')
def get_results():
    """Get scan results."""
    with state_lock:
        if app_state['results'] is None:
            return jsonify({'success': False, 'error': 'No results available'})
        return jsonify({
            'success': True,
            'results': app_state['results'],
            'summary': app_state['summary']
        })


@app.route('/api/history')
def get_history():
    """Get scan history."""
    limit = request.args.get('limit', 10, type=int)
    scans = get_scan_history(limit)
    return jsonify({'success': True, 'scans': scans})


@app.route('/api/ticker-history/<ticker>')
def get_ticker_history(ticker: str):
    """Get HQM history for a specific ticker."""
    days = request.args.get('days', 30, type=int)
    history = get_hqm_history(ticker.upper(), days)
    return jsonify({'success': True, 'history': history})


# =============================================================================
# FLASK ROUTES - WATCHLIST API
# =============================================================================

@app.route('/api/watchlist', methods=['GET'])
def watchlist_get():
    """Get all watchlist items."""
    items = get_watchlist()
    return jsonify({'success': True, 'watchlist': items})


@app.route('/api/watchlist', methods=['POST'])
def watchlist_add():
    """Add ticker to watchlist."""
    data = request.get_json()
    ticker = data.get('ticker', '').upper()

    if not ticker:
        return jsonify({'success': False, 'error': 'Ticker is required'})

    target_price = data.get('target_price')
    notes = data.get('notes')
    alert_enabled = data.get('alert_enabled', False)
    alert_threshold = data.get('alert_threshold')

    success = add_to_watchlist(
        ticker=ticker,
        target_price=float(target_price) if target_price else None,
        notes=notes,
        alert_enabled=alert_enabled,
        alert_threshold=float(alert_threshold) if alert_threshold else None
    )

    if success:
        return jsonify({'success': True, 'message': f'{ticker} added to watchlist'})
    else:
        return jsonify({'success': False, 'error': f'{ticker} already in watchlist'})


@app.route('/api/watchlist/<ticker>', methods=['DELETE'])
def watchlist_remove(ticker: str):
    """Remove ticker from watchlist."""
    success = remove_from_watchlist(ticker.upper())

    if success:
        return jsonify({'success': True, 'message': f'{ticker} removed from watchlist'})
    else:
        return jsonify({'success': False, 'error': f'{ticker} not found in watchlist'})


# =============================================================================
# FLASK ROUTES - PORTFOLIO TRACKING API
# =============================================================================

@app.route('/api/portfolio', methods=['GET'])
def portfolio_get():
    """Get portfolio positions and summary."""
    include_closed = request.args.get('include_closed', 'false').lower() == 'true'
    positions = get_portfolio_positions(include_closed=include_closed)
    summary = get_portfolio_summary()

    return jsonify({
        'success': True,
        'positions': positions,
        'summary': summary
    })


@app.route('/api/portfolio', methods=['POST'])
def portfolio_add():
    """Add position to portfolio."""
    data = request.get_json()

    required = ['ticker', 'shares', 'entry_price']
    for field in required:
        if field not in data:
            return jsonify({'success': False, 'error': f'{field} is required'})

    position_id = add_portfolio_position(
        ticker=data['ticker'].upper(),
        shares=int(data['shares']),
        entry_price=float(data['entry_price']),
        entry_date=data.get('entry_date'),
        hqm_score=float(data['hqm_score']) if data.get('hqm_score') else None,
        notes=data.get('notes')
    )

    return jsonify({'success': True, 'position_id': position_id})


@app.route('/api/portfolio/<int:position_id>/close', methods=['POST'])
def portfolio_close(position_id: int):
    """Close a portfolio position."""
    data = request.get_json()

    if 'exit_price' not in data:
        return jsonify({'success': False, 'error': 'exit_price is required'})

    success = close_portfolio_position(
        position_id=position_id,
        exit_price=float(data['exit_price']),
        exit_date=data.get('exit_date')
    )

    if success:
        return jsonify({'success': True, 'message': 'Position closed'})
    else:
        return jsonify({'success': False, 'error': 'Position not found'})


# =============================================================================
# FLASK ROUTES - SECTOR ANALYSIS API
# =============================================================================

@app.route('/api/sectors')
def sectors_get():
    """Get sector breakdown and performance."""
    breakdown = get_sector_breakdown()
    hqm_scores = get_sector_hqm_scores()

    return jsonify({
        'success': True,
        'breakdown': breakdown,
        'hqm_scores': hqm_scores
    })


# =============================================================================
# FLASK ROUTES - RISK METRICS API
# =============================================================================

@app.route('/api/risk-metrics', methods=['POST'])
def risk_metrics():
    """Calculate risk metrics for a portfolio."""
    data = request.get_json()

    tickers = data.get('tickers', [])
    weights = data.get('weights', [])
    portfolio_value = float(data.get('portfolio_value', 10000))
    period = data.get('period', '1y')

    if not tickers:
        return jsonify({'success': False, 'error': 'No tickers provided'})

    if not weights:
        # Equal weight if not provided
        weights = [1.0 / len(tickers)] * len(tickers)

    metrics = calculate_all_risk_metrics(
        tickers=tickers,
        weights=weights,
        portfolio_value=portfolio_value,
        period=period
    )

    return jsonify({'success': True, 'metrics': metrics})


@app.route('/api/stock-metrics/<ticker>')
def stock_metrics(ticker: str):
    """Get risk metrics for individual stock."""
    period = request.args.get('period', '1y')
    metrics = get_individual_stock_metrics(ticker.upper(), period)
    return jsonify({'success': True, 'metrics': metrics})


# =============================================================================
# FLASK ROUTES - BACKTESTING API
# =============================================================================

@app.route('/api/backtest', methods=['POST'])
def start_backtest():
    """Start a backtest."""
    with state_lock:
        if app_state['status'] in ['refreshing', 'scanning', 'backtesting']:
            return jsonify({'success': False, 'error': 'Operation already in progress'})

    data = request.get_json()

    start_date = data.get('start_date')
    end_date = data.get('end_date')
    initial_capital = float(data.get('initial_capital', config.backtest.initial_capital))
    num_positions = int(data.get('num_positions', config.portfolio.default_positions))
    rebalance_frequency = data.get('rebalance_frequency', config.backtest.rebalance_frequency)

    update_state(status='backtesting', progress=0, message='Starting backtest...', backtest_results=None)
    logger.info(f"Starting backtest: {start_date} to {end_date}")

    def backtest_thread():
        try:
            def progress_callback(pct: int, msg: str) -> None:
                update_state(progress=pct, message=msg)

            results = run_backtest(
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                num_positions=num_positions,
                rebalance_frequency=rebalance_frequency,
                progress_callback=progress_callback
            )

            if results['success']:
                update_state(
                    status='completed',
                    progress=100,
                    message='Backtest complete!',
                    backtest_results=results
                )
                logger.info(f"Backtest completed: {results['total_return']:.2f}% return")
            else:
                update_state(status='error', message=results.get('error', 'Backtest failed'))

        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            update_state(status='error', message=str(e))

    thread = threading.Thread(target=backtest_thread)
    thread.start()

    return jsonify({'success': True, 'message': 'Backtest started'})


@app.route('/api/backtest/results')
def backtest_results():
    """Get backtest results."""
    with state_lock:
        if app_state['backtest_results'] is None:
            return jsonify({'success': False, 'error': 'No backtest results available'})
        return jsonify({'success': True, 'results': app_state['backtest_results']})


@app.route('/api/backtest/history')
def backtest_history():
    """Get backtest history."""
    limit = request.args.get('limit', 10, type=int)
    history = get_backtest_history(limit)
    return jsonify({'success': True, 'history': history})


# =============================================================================
# FLASK ROUTES - SETTINGS API
# =============================================================================

@app.route('/api/config')
def get_config_api():
    """Get current configuration (safe subset for frontend)."""
    return jsonify({
        'success': True,
        'config': {
            'portfolio': {
                'default_size': config.portfolio.default_size,
                'default_positions': config.portfolio.default_positions,
                'min_size': config.portfolio.min_size,
                'max_positions': config.portfolio.max_positions
            },
            'indicators': {
                'sma': {
                    'period': config.indicators.sma.period,
                    'good_threshold': config.indicators.sma.good_threshold,
                    'moderate_threshold': config.indicators.sma.moderate_threshold
                },
                'rsi': {
                    'enabled': config.indicators.rsi.enabled,
                    'overbought': config.indicators.rsi.overbought,
                    'oversold': config.indicators.rsi.oversold
                },
                'volume': {
                    'enabled': config.indicators.volume.enabled,
                    'min_avg_volume': config.indicators.volume.min_avg_volume
                },
                'volatility': {
                    'enabled': config.indicators.volatility.enabled,
                    'max_atr_percent': config.indicators.volatility.max_atr_percent
                }
            },
            'sectors': {
                'diversification_enabled': config.sectors.diversification.enabled,
                'max_per_sector': config.sectors.diversification.max_per_sector
            },
            'theme': {
                'default': config.theme.default,
                'colors': {
                    'primary': config.theme.colors.primary,
                    'success': config.theme.colors.success,
                    'warning': config.theme.colors.warning,
                    'danger': config.theme.colors.danger
                }
            }
        }
    })


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    logger.info(f"Starting HQM Momentum Scanner on {config.web.host}:{config.web.port}")
    app.run(
        host=config.web.host,
        port=config.web.port,
        debug=config.web.debug
    )
