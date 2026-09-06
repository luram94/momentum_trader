"""Offline UI regressions using actual Streamlit page execution."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import hqm.database as database
import hqm.ui.banner as banner
from tests.test_integration import _seed_stocks

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    database.init_database()
    monkeypatch.setattr(banner, '_cached_regime', lambda proxy: {
        'regime': 'caution', 'proxy': proxy, 'close': 100, 'sma20': 101,
        'sma50': 99, 'sma200': 90, 'sma10_rising': False,
        'max_exposure': .5, 'as_of': '2026-09-01',
    })
    return database.DB_PATH


def app():
    return AppTest.from_file(str(ROOT / 'streamlit_app.py'), default_timeout=20).run()


@pytest.mark.parametrize('page', ['streamlit_app.py', 'pages/1_Scanner.py',
    'pages/2_Watchlist.py', 'pages/3_Portfolio.py', 'pages/4_Sectors.py', 'pages/5_Backtest.py'])
@pytest.mark.parametrize('seeded', [False, True])
def test_pages_render(app_db, page, seeded):
    if seeded:
        _seed_stocks(app_db)
        database.set_last_refresh()
    at = app()
    if page != 'streamlit_app.py':
        at.switch_page(page).run()
    assert not at.exception


def test_scan_preserves_results_when_risk_provider_fails(app_db, monkeypatch):
    import hqm.risk_metrics as risk
    _seed_stocks(app_db)
    database.set_last_refresh()
    def unavailable(**kwargs):
        raise RuntimeError('provider offline')
    monkeypatch.setattr(risk, 'calculate_all_risk_metrics', unavailable)
    at = app().switch_page('pages/1_Scanner.py').run()
    next(b for b in at.button if b.label == 'Run Scan').click().run()
    assert not at.exception
    assert at.session_state['scan_results']
    assert not at.session_state['scan_summary']['risk_metrics']['data_available']
    assert len(at.get('download_button')) == 1
    at.number_input(key='portfolio_size').set_value(20000).run()
    assert any('Settings have changed' in w.value for w in at.warning)


def test_failed_refresh_feedback_survives(app_db, monkeypatch):
    def unavailable(callback):
        raise RuntimeError('provider offline')
    monkeypatch.setattr(database, 'fetch_and_store_data', unavailable)
    at = app().switch_page('pages/1_Scanner.py').run()
    next(b for b in at.button if b.label == 'Refresh Data').click().run()
    assert not at.exception
    assert any('Refresh failed' in e.value for e in at.error)


def test_invalid_rsi_does_not_scan(app_db, monkeypatch):
    _seed_stocks(app_db)
    def unexpected(**kwargs):
        pytest.fail('Invalid RSI must be rejected before scanning')
    monkeypatch.setattr(database, 'run_hqm_scan_from_db', unexpected)
    at = app().switch_page('pages/1_Scanner.py').run()
    at.checkbox(key='rsi_filter_enabled').check().run()
    at.number_input(key='rsi_min').set_value(90)
    at.number_input(key='rsi_max').set_value(20)
    next(b for b in at.button if b.label == 'Run Scan').click().run()
    assert not at.exception
    assert any('Minimum RSI' in e.value for e in at.error)


def test_failed_rescan_clears_previous_selection(app_db, monkeypatch):
    import hqm.risk_metrics as risk
    _seed_stocks(app_db)
    monkeypatch.setattr(risk, 'calculate_all_risk_metrics', lambda **kwargs: {'data_available': False})
    at = app().switch_page('pages/1_Scanner.py').run()
    next(b for b in at.button if b.label == 'Run Scan').click().run()
    assert at.session_state['scan_results']
    monkeypatch.setattr(database, 'run_hqm_scan_from_db', lambda **kwargs: {
        'success': False, 'error': 'No stocks meet these filters.'})
    next(b for b in at.button if b.label == 'Run Scan').click().run()
    assert not at.exception
    assert at.session_state['scan_results'] is None
    assert any('No stocks meet' in e.value for e in at.error)


def test_refresh_marks_existing_scan_outdated(app_db, monkeypatch):
    from datetime import datetime, timedelta
    import hqm.risk_metrics as risk
    _seed_stocks(app_db)
    database.set_last_refresh(datetime.now() - timedelta(hours=1))
    monkeypatch.setattr(risk, 'calculate_all_risk_metrics', lambda **kwargs: {'data_available': False})
    at = app().switch_page('pages/1_Scanner.py').run()
    next(b for b in at.button if b.label == 'Run Scan').click().run()
    database.set_last_refresh()
    at.run()
    assert not at.exception
    assert any('Market data has changed' in w.value for w in at.warning)


def test_group_leaders_use_full_universe_percentile_ranking(app_db):
    _seed_stocks(app_db, count=12)
    leaders = database.get_top_stocks_by_group('sector', 'Tech', limit=5)
    assert len(leaders) == 5
    assert all(row['Sector'] == 'Tech' for row in leaders)
    assert all(leaders[i]['HQM_Score'] >= leaders[i + 1]['HQM_Score'] for i in range(4))
    assert leaders[0]['Ticker'] == 'T10'
