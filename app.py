"""
HQM Momentum Scanner - Flask Web Application
=============================================
Interactive web interface for the High Quality Momentum strategy.
Now with SQLite caching for fast scans!
"""

from flask import Flask, render_template, jsonify, request
import threading
from database import (
    fetch_and_store_data,
    run_hqm_scan_from_db,
    get_data_age_hours,
    get_last_refresh,
    get_stock_count,
    get_scan_history,
    get_hqm_history
)

app = Flask(__name__)

# Global state for operations
app_state = {
    'status': 'idle',  # idle, refreshing, scanning, completed, error
    'progress': 0,
    'message': '',
    'results': None,
    'summary': None
}
state_lock = threading.Lock()


def update_state(status=None, progress=None, message=None, results=None, summary=None):
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


# =============================================================================
# FLASK ROUTES
# =============================================================================

@app.route('/')
def index():
    """Render main page."""
    return render_template('index.html')


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
        if app_state['status'] in ['refreshing', 'scanning']:
            return jsonify({'success': False, 'error': 'Operation already in progress'})

    update_state(status='refreshing', progress=0, message='Starting data refresh...')

    def refresh_thread():
        try:
            def progress_callback(pct, msg):
                update_state(progress=pct, message=msg)

            stats = fetch_and_store_data(progress_callback)

            update_state(
                status='completed',
                progress=100,
                message=f"Refreshed {stats['total_stored']} stocks in {stats['duration_seconds']:.1f}s"
            )
        except Exception as e:
            update_state(status='error', message=str(e))

    thread = threading.Thread(target=refresh_thread)
    thread.start()

    return jsonify({'success': True, 'message': 'Refresh started'})


@app.route('/api/scan', methods=['POST'])
def start_scan():
    """Run HQM scan using cached database data."""
    # Check if we have data
    if get_stock_count() == 0:
        return jsonify({
            'success': False,
            'error': 'No data available. Please refresh data first.'
        })

    with state_lock:
        if app_state['status'] in ['refreshing', 'scanning']:
            return jsonify({'success': False, 'error': 'Operation already in progress'})

    # Get parameters
    data = request.get_json()
    portfolio_size = float(data.get('portfolio_size', 10000))
    num_positions = int(data.get('num_positions', 8))
    max_sma10_distance = data.get('max_sma10_distance')

    # Convert max_sma10_distance to float if provided
    if max_sma10_distance is not None and max_sma10_distance != '':
        try:
            max_sma10_distance = float(max_sma10_distance)
        except (ValueError, TypeError):
            max_sma10_distance = None

    # Validate
    if portfolio_size < 1000:
        return jsonify({'success': False, 'error': 'Portfolio size must be at least $1,000'})
    if num_positions < 1 or num_positions > 50:
        return jsonify({'success': False, 'error': 'Number of positions must be between 1 and 50'})

    update_state(status='scanning', progress=0, message='Running HQM scan...')

    def scan_thread():
        try:
            update_state(progress=30, message='Calculating HQM scores...')

            result = run_hqm_scan_from_db(portfolio_size, num_positions, max_sma10_distance=max_sma10_distance)

            if result['success']:
                update_state(
                    status='completed',
                    progress=100,
                    message='Scan complete!',
                    results=result['results'],
                    summary=result['summary']
                )
            else:
                update_state(status='error', message=result.get('error', 'Scan failed'))

        except Exception as e:
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
def get_ticker_history(ticker):
    """Get HQM history for a specific ticker."""
    days = request.args.get('days', 30, type=int)
    history = get_hqm_history(ticker.upper(), days)
    return jsonify({'success': True, 'history': history})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
