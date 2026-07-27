"""
Tests for the FinViz ticker parsing patch, the scrape sanity guard, and the
repair that heals data written while the scrape was broken.

FinViz's screener renders a logo-placeholder initial inside the Ticker cell,
which finvizfinance's ``col.text`` parse concatenates onto the symbol
(ABNB -> AABNB). These tests drive the patched parser with the real markup.
"""

import sqlite3

from bs4 import BeautifulSoup
from finvizfinance.screener.base import Base
import pandas as pd
import pytest

import hqm.database as database
from hqm.finviz_patch import apply_ticker_parsing_fix

apply_ticker_parsing_fix()


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point database.py at a fresh temporary SQLite file."""
    db_path = tmp_path / 'test_hqm.db'
    monkeypatch.setattr(database, 'DB_PATH', db_path)
    return db_path


HEADERS = ['Ticker', 'Sector', 'Price']


def _row(ticker: str, sector: str, price: str, *, logo: bool = True,
         boxover: bool = True, index_cell: bool = True) -> str:
    """Build a screener row matching FinViz's live markup."""
    attr = f' data-boxover-ticker="{ticker}"' if boxover else ''
    placeholder = (
        f'<a class="company-ticker"><img src="{ticker}.svg"/>'
        f'<span>{ticker[0]}</span></a>'
        if logo else ''
    )
    leading = '<td>1</td>' if index_cell else ''
    return (
        f'<tr>{leading}'
        f'<td{attr}><span>{placeholder}'
        f'<a class="tab-link">{ticker}</a></span></td>'
        f'<td>{sector}</td><td>{price}</td></tr>'
    )


def _parse(rows_html: str) -> pd.DataFrame:
    """Run the patched parser over a screener table."""
    header = '<tr><th>No.</th><th>Ticker</th><th>Sector</th><th>Price</th></tr>'
    soup = BeautifulSoup(
        f'<table class="screener_table">{header}{rows_html}</table>',
        'html.parser',
    )
    rows = soup.find('table').find_all('tr')
    df = pd.DataFrame([], columns=HEADERS)
    return Base._get_table(
        Base.__new__(Base), rows, df, [HEADERS.index('Price')], HEADERS, -1
    )


class TestTickerParsing:
    """The placeholder initial must never reach the parsed symbol."""

    def test_strips_logo_placeholder_initial(self):
        df = _parse(_row('ABNB', 'Consumer Cyclical', '146.01'))
        assert df['Ticker'].tolist() == ['ABNB']

    def test_handles_symbols_that_legitimately_repeat_a_letter(self):
        # AA and AAPL are real symbols; a "strip the first char" fix would be
        # indistinguishable from corruption here, an attribute read is not.
        html = ''.join([
            _row('AA', 'Basic Materials', '38.64'),
            _row('AAPL', 'Technology', '336.26'),
            _row('SLS', 'Healthcare', '13.05'),
        ])
        df = _parse(html)
        assert df['Ticker'].tolist() == ['AA', 'AAPL', 'SLS']

    def test_correct_without_the_placeholder(self):
        # If FinViz reverts the markup the patch must be a no-op, not a
        # second source of corruption.
        df = _parse(_row('SLS', 'Healthcare', '13.05', logo=False))
        assert df['Ticker'].tolist() == ['SLS']

    def test_falls_back_to_tab_link_without_boxover_attribute(self):
        df = _parse(_row('MSFT', 'Technology', '410.00', boxover=False))
        assert df['Ticker'].tolist() == ['MSFT']

    def test_other_columns_are_untouched(self):
        df = _parse(_row('ABNB', 'Consumer Cyclical', '146.01'))
        assert df['Sector'].tolist() == ['Consumer Cyclical']
        assert df['Price'].tolist() == [146.01]

    def test_appends_to_an_existing_frame_across_pages(self):
        # screener_view accumulates page by page; the repair must land on the
        # rows just parsed, not on the whole frame.
        first = _parse(_row('SLS', 'Healthcare', '13.05'))
        rows = BeautifulSoup(
            '<table class="screener_table">'
            '<tr><th>No.</th><th>Ticker</th><th>Sector</th><th>Price</th></tr>'
            + _row('EE', 'Energy', '38.64')
            + '</table>',
            'html.parser',
        ).find('table').find_all('tr')
        combined = Base._get_table(
            Base.__new__(Base), rows, first,
            [HEADERS.index('Price')], HEADERS, -1
        )
        assert combined['Ticker'].tolist() == ['SLS', 'EE']

    def test_survives_a_cell_without_either_marker(self):
        html = (
            '<tr><td>1</td><td>ZZZ</td>'
            '<td>Technology</td><td>1.00</td></tr>'
        )
        df = _parse(html)
        assert df['Ticker'].tolist() == ['ZZZ']


class TestScrapeSanityGuard:
    """A systematically doubled scrape must not overwrite good data."""

    def test_rejects_a_fully_doubled_scrape(self):
        bad = pd.Series(['AAAPL', 'AABNB', 'SSLS', 'TTSLA'])
        with pytest.raises(RuntimeError, match='doubled letter'):
            database._assert_tickers_look_sane(bad)

    def test_accepts_a_real_universe(self):
        # Real screens carry a few percent of genuine doubles
        real = pd.Series(['AAPL', 'AA', 'TTWO', 'SLS', 'MSFT', 'EE', 'NVDA',
                          'AMZN', 'GOOG', 'META'])
        database._assert_tickers_look_sane(real)

    def test_ignores_an_empty_column(self):
        database._assert_tickers_look_sane(pd.Series([], dtype=object))


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
