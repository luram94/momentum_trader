"""
FinViz Screener Patch
=====================
Work around FinViz's logo placeholder leaking into scraped ticker symbols.

FinViz now renders the screener's Ticker cell as::

    <td data-boxover-ticker="ABNB">
      <span>
        <a class="company-ticker" style="--logo-url: url(...ABNB.svg)">
          <img src=".../ABNB.svg"/><span>A</span>
        </a>
        <a class="tab-link">ABNB</a>
      </span>
    </td>

The inner ``<span>A</span>`` is the initial shown behind the company logo while
it loads. finvizfinance (through 1.3.0) reads every cell with ``col.text``,
which concatenates that initial onto the front of the symbol, so the whole
screen comes back with the first letter doubled: ABNB -> AABNB, SLS -> SSLS.

Rather than stripping the leading character -- which silently corrupts symbols
once FinViz changes the markup back -- this reads the symbol straight from the
cell's ``data-boxover-ticker`` attribute, falling back to the ``tab-link``
anchor that holds the ticker on its own. Both are correct whether or not the
placeholder is present, so the patch is safe to leave in place.
"""

from __future__ import annotations

from typing import Any, List, Optional

from finvizfinance.screener.base import Base

from hqm.logger import get_logger

logger = get_logger('finviz_patch')

_TICKER_HEADER = 'Ticker'

# finvizfinance drops the leading "No." cell before zipping cells to headers.
_LEADING_INDEX_COLUMNS = 1

_applied = False


def _extract_ticker(cell: Any) -> Optional[str]:
    """
    Read the true symbol out of a screener Ticker cell.

    Args:
        cell: BeautifulSoup ``<td>`` for the Ticker column.

    Returns:
        The ticker symbol, or None if the cell has neither marker (in which
        case the caller keeps finvizfinance's own parse).
    """
    boxover = cell.get('data-boxover-ticker')
    if boxover and boxover.strip():
        return boxover.strip()

    link = cell.find('a', class_='tab-link')
    if link is not None and link.text.strip():
        return link.text.strip()

    return None


def apply_ticker_parsing_fix() -> None:
    """
    Patch ``Base._get_table`` so Ticker columns are read from the DOM.

    Idempotent: repeated calls (Streamlit reruns, test imports) are no-ops.
    """
    global _applied
    if _applied:
        return

    original_get_table = Base._get_table

    def _get_table(
        self: Base,
        rows: List[Any],
        df: Any,
        num_col_index: List[int],
        table_header: List[str],
        limit: int = -1,
    ) -> Any:
        result = original_get_table(
            self, rows, df, num_col_index, table_header, limit
        )

        if _TICKER_HEADER not in table_header:
            return result

        # Mirror the upstream row selection so cells line up with the rows
        # just appended to the tail of the frame.
        data_rows = rows[1:]
        if limit != -1:
            data_rows = data_rows[0:limit]

        col_index = table_header.index(_TICKER_HEADER) + _LEADING_INDEX_COLUMNS

        tickers: List[Optional[str]] = []
        for row in data_rows:
            cells = row.find_all('td')
            if col_index >= len(cells):
                tickers.append(None)
                continue
            tickers.append(_extract_ticker(cells[col_index]))

        if len(tickers) != len(data_rows):
            return result

        # Newly parsed rows are always the tail of the accumulated frame.
        start = len(result) - len(tickers)
        if start < 0:
            logger.warning(
                'Skipping ticker repair: parsed %d rows but frame has %d',
                len(tickers), len(result)
            )
            return result

        position = result.columns.get_loc(_TICKER_HEADER)
        for offset, ticker in enumerate(tickers):
            if ticker is not None:
                result.iat[start + offset, position] = ticker

        return result

    Base._get_table = _get_table
    _applied = True
    logger.debug('Applied FinViz ticker parsing patch')
