"""
Tests for the nightly snapshot: freshness rule, file format, download, and
how Refresh Data chooses between the snapshot and the live refresh.
"""

import gzip
import json
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import pytest

import hqm.database as database
import hqm.snapshot as snapshot


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def _stocks(count=3):
    return pd.DataFrame({
        'Ticker': [f'T{i}' for i in range(count)],
        'Exchange': ['NYSE', 'NASDAQ', 'NASDAQ'][:count],
        'Sector': ['Technology'] * count,
        'Industry': ['Software - Infrastructure'] * count,
        'Market_Cap': [5e9] * count,
        'Price': [50.0] * count,
        'Volume': [400_000.0] * count,
        'Avg_Volume': [2_500_000.0, None, 1_000_000.0][:count],
        'Return_1M': [0.01] * count,
        'Return_3M': [0.03] * count,
        'Return_6M': [0.06] * count,
        'Return_1Y': [0.12] * count,
    })


def _snapshot_bytes(df, generated_at, tmp_path):
    path = tmp_path / 'snap.json.gz'
    snapshot.write_snapshot(df, path, generated_at)
    return path.read_bytes()


class TestFreshness:
    # 2026-10-26 is a Monday
    @pytest.mark.parametrize('now, expected', [
        (utc(2026, 10, 27, 10, 0), utc(2026, 10, 26, 21)),   # Tue morning -> Mon close
        (utc(2026, 10, 27, 22, 30), utc(2026, 10, 26, 21)),  # inside publish grace
        (utc(2026, 10, 27, 23, 30), utc(2026, 10, 27, 21)),  # after grace -> today
        (utc(2026, 10, 31, 12, 0), utc(2026, 10, 30, 21)),   # Saturday -> Friday
        (utc(2026, 11, 2, 10, 0), utc(2026, 10, 30, 21)),    # Monday morning -> Friday
    ])
    def test_latest_expected_close(self, now, expected):
        assert snapshot.latest_expected_close(now) == expected

    def test_weekend_keeps_fridays_snapshot_fresh(self):
        friday_build = utc(2026, 10, 30, 21, 40)
        assert snapshot.is_fresh(friday_build, utc(2026, 11, 1, 18, 0))
        assert snapshot.is_fresh(friday_build, utc(2026, 11, 2, 22, 0))
        assert not snapshot.is_fresh(friday_build, utc(2026, 11, 2, 23, 30))


class TestFileFormat:
    def test_round_trip_keeps_values_and_nulls(self, tmp_path):
        built = utc(2026, 10, 27, 21, 40)
        df, generated_at = snapshot.read_snapshot(_snapshot_bytes(_stocks(), built, tmp_path))

        assert generated_at == built
        pd.testing.assert_frame_equal(df, _stocks(), check_dtype=False)
        assert pd.isna(df.loc[1, 'Avg_Volume'])

    def test_rejects_unknown_version(self):
        content = gzip.compress(json.dumps({'version': 99, 'stocks': []}).encode())
        with pytest.raises(ValueError, match='version'):
            snapshot.read_snapshot(content)

    def test_rejects_empty_snapshot(self, tmp_path):
        with pytest.raises(ValueError, match='no stocks'):
            snapshot.read_snapshot(_snapshot_bytes(_stocks(0), utc(2026, 10, 27, 21, 40), tmp_path))


class _Response:
    def __init__(self, content=b'', status=200):
        self.content = content
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f'HTTP {self.status}')


class TestLoadFresh:
    NOW = utc(2026, 10, 28, 10, 0)

    def test_returns_current_snapshot(self, tmp_path, monkeypatch):
        content = _snapshot_bytes(_stocks(), utc(2026, 10, 27, 21, 40), tmp_path)
        monkeypatch.setattr(snapshot.requests, 'get', lambda url, timeout: _Response(content))

        df, generated_at = snapshot.load_fresh('https://example/snap', now=self.NOW)

        assert len(df) == 3

    def test_stale_snapshot_is_ignored(self, tmp_path, monkeypatch):
        content = _snapshot_bytes(_stocks(), utc(2026, 10, 26, 21, 40), tmp_path)
        monkeypatch.setattr(snapshot.requests, 'get', lambda url, timeout: _Response(content))

        assert snapshot.load_fresh('https://example/snap', now=self.NOW) is None

    @pytest.mark.parametrize('response', [_Response(status=404), _Response(b'not gzip')])
    def test_bad_download_never_raises(self, monkeypatch, response):
        monkeypatch.setattr(snapshot.requests, 'get', lambda url, timeout: response)
        assert snapshot.load_fresh('https://example/snap', now=self.NOW) is None

    def test_network_error_never_raises(self, monkeypatch):
        def offline(url, timeout):
            raise ConnectionError('offline')
        monkeypatch.setattr(snapshot.requests, 'get', offline)
        assert snapshot.load_fresh('https://example/snap', now=self.NOW) is None


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / 'snapshot.db'
    monkeypatch.setattr(database, 'DB_PATH', db_path)
    monkeypatch.setattr(database.config.data, 'snapshot_url', 'https://example/snap')
    database.init_database()
    return db_path


class TestRefreshUsesSnapshot:
    def test_fresh_snapshot_skips_the_live_refresh(self, temp_db, monkeypatch):
        built = datetime.now(timezone.utc)
        monkeypatch.setattr(database.snapshot, 'load_fresh', lambda url: (_stocks(), built))
        def unexpected(*args, **kwargs):
            pytest.fail('live refresh must not run when the snapshot is fresh')
        monkeypatch.setattr(database, 'fetch_live_stocks', unexpected)

        stats = database.fetch_and_store_data()

        assert stats['source'] == 'snapshot'
        assert stats['total_stored'] == 3
        assert stats['nyse_count'] == 1 and stats['nasdaq_count'] == 2
        conn = sqlite3.connect(temp_db)
        avg = dict(conn.execute('SELECT ticker, avg_volume FROM stocks').fetchall())
        conn.close()
        assert avg['T0'] == 2_500_000.0 and avg['T1'] is None
        # Data is dated by the snapshot build, not by the download
        assert database.get_last_refresh() == built.astimezone().replace(tzinfo=None)

    def test_missing_snapshot_falls_back_to_live(self, temp_db, monkeypatch):
        monkeypatch.setattr(database.snapshot, 'load_fresh', lambda url: None)
        monkeypatch.setattr(database, 'fetch_live_stocks', lambda progress: _stocks(2))

        stats = database.fetch_and_store_data()

        assert stats['source'] == 'live'
        assert database.get_stock_count() == 2

    def test_disabled_snapshot_is_not_downloaded(self, temp_db, monkeypatch):
        monkeypatch.setattr(database.config.data, 'snapshot_url', '')
        def unexpected(url):
            pytest.fail('snapshot must not be fetched when disabled')
        monkeypatch.setattr(database.snapshot, 'load_fresh', unexpected)
        monkeypatch.setattr(database, 'fetch_live_stocks', lambda progress: _stocks(1))

        assert database.fetch_and_store_data()['source'] == 'live'
