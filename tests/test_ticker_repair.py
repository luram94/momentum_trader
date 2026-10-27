"""
Tests for the repair that heals history written while the old FinViz scrape
was doubling the first letter of every ticker (ABNB -> AABNB).
"""

import sqlite3

import pytest

import hqm.database as database


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point database.py at a fresh temporary SQLite file."""
    db_path = tmp_path / 'test_hqm.db'
    monkeypatch.setattr(database, 'DB_PATH', db_path)
    return db_path


class TestTickerRepair:
    """History written during the outage is healed by the next clean refresh."""

    def _seed_universe(self, conn, tickers=('SLS', 'AAPL', 'AA')):
        for t in tickers:
            conn.execute('INSERT INTO stocks (ticker) VALUES (?)', (t,))

    def test_repairs_history_and_scan_rows(self, temp_db):
        database.init_database()
        conn = sqlite3.connect(temp_db)
        self._seed_universe(conn)
        conn.execute(
            "INSERT INTO hqm_history (ticker, date, hqm_score) "
            "VALUES ('SSLS', '2026-07-20', 91.0)"
        )
        conn.execute(
            "INSERT INTO scan_positions (scan_id, ticker, hqm_score) "
            "VALUES (1, 'AAAPL', 88.0)"
        )
        conn.execute("INSERT INTO watchlist (ticker) VALUES ('SSLS')")

        assert database._repair_doubled_tickers(conn) == 3
        conn.commit()

        assert conn.execute(
            'SELECT ticker FROM hqm_history'
        ).fetchall() == [('SLS',)]
        assert conn.execute(
            'SELECT ticker FROM scan_positions'
        ).fetchall() == [('AAPL',)]
        assert conn.execute(
            'SELECT ticker FROM watchlist'
        ).fetchall() == [('SLS',)]
        conn.close()

    def test_leaves_legitimate_doubles_alone(self, temp_db):
        # AA and AAPL are in the universe, so they are never candidates
        database.init_database()
        conn = sqlite3.connect(temp_db)
        self._seed_universe(conn)
        conn.execute(
            "INSERT INTO hqm_history (ticker, date, hqm_score) "
            "VALUES ('AA', '2026-07-20', 70.0)"
        )
        conn.execute(
            "INSERT INTO hqm_history (ticker, date, hqm_score) "
            "VALUES ('AAPL', '2026-07-20', 80.0)"
        )

        assert database._repair_doubled_tickers(conn) == 0
        assert sorted(
            r[0] for r in conn.execute('SELECT ticker FROM hqm_history')
        ) == ['AA', 'AAPL']
        conn.close()

    def test_leaves_unknown_symbols_alone(self, temp_db):
        # 'DDOG' looks doubled but 'DOG' is not in the universe -- a delisted
        # or filtered-out symbol must never be silently rewritten.
        database.init_database()
        conn = sqlite3.connect(temp_db)
        self._seed_universe(conn)
        conn.execute(
            "INSERT INTO hqm_history (ticker, date, hqm_score) "
            "VALUES ('DDOG', '2026-07-20', 70.0)"
        )

        assert database._repair_doubled_tickers(conn) == 0
        conn.close()

    def test_drops_a_corrupted_row_colliding_with_the_clean_one(self, temp_db):
        # UNIQUE(ticker, date): repairing SSLS onto an existing SLS row would
        # violate the constraint, so the corrupted duplicate goes.
        database.init_database()
        conn = sqlite3.connect(temp_db)
        self._seed_universe(conn)
        conn.execute(
            "INSERT INTO hqm_history (ticker, date, hqm_score) "
            "VALUES ('SLS', '2026-07-20', 91.0)"
        )
        conn.execute(
            "INSERT INTO hqm_history (ticker, date, hqm_score) "
            "VALUES ('SSLS', '2026-07-20', 91.0)"
        )

        assert database._repair_doubled_tickers(conn) == 1
        conn.commit()
        assert conn.execute(
            'SELECT ticker, hqm_score FROM hqm_history'
        ).fetchall() == [('SLS', 91.0)]
        conn.close()

    def test_keeps_a_corrupted_row_on_a_different_date(self, temp_db):
        # Same symbol, different date -> no collision, so it is repaired
        database.init_database()
        conn = sqlite3.connect(temp_db)
        self._seed_universe(conn)
        conn.execute(
            "INSERT INTO hqm_history (ticker, date, hqm_score) "
            "VALUES ('SLS', '2026-07-19', 90.0)"
        )
        conn.execute(
            "INSERT INTO hqm_history (ticker, date, hqm_score) "
            "VALUES ('SSLS', '2026-07-20', 91.0)"
        )

        assert database._repair_doubled_tickers(conn) == 1
        conn.commit()
        assert sorted(
            conn.execute('SELECT ticker, date FROM hqm_history')
        ) == [('SLS', '2026-07-19'), ('SLS', '2026-07-20')]
        conn.close()

    def test_is_idempotent(self, temp_db):
        database.init_database()
        conn = sqlite3.connect(temp_db)
        self._seed_universe(conn)
        conn.execute(
            "INSERT INTO hqm_history (ticker, date, hqm_score) "
            "VALUES ('SSLS', '2026-07-20', 91.0)"
        )
        assert database._repair_doubled_tickers(conn) == 1
        assert database._repair_doubled_tickers(conn) == 0
        conn.close()

    def test_no_op_when_the_universe_is_empty(self, temp_db):
        database.init_database()
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO hqm_history (ticker, date, hqm_score) "
            "VALUES ('SSLS', '2026-07-20', 91.0)"
        )
        assert database._repair_doubled_tickers(conn) == 0
        conn.close()
