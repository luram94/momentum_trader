"""
Nightly Data Snapshot
=====================
A GitHub Actions job (.github/workflows/snapshot.yml) runs the full Yahoo
refresh after the US close and publishes the stocks universe as a release
asset. Refresh Data downloads that file in about a second instead of spending
~4.5 minutes on per-ticker price downloads; when the snapshot is missing,
unreadable or older than the latest close, the app falls back to the live
refresh.

Build one locally: python -m hqm.snapshot stocks_snapshot.json.gz
"""

from __future__ import annotations

import gzip
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
import requests

from hqm.logger import get_logger

logger = get_logger('snapshot')

SNAPSHOT_VERSION = 1

STOCK_COLUMNS: List[str] = [
    'Ticker', 'Exchange', 'Sector', 'Industry', 'Market_Cap', 'Price',
    'Volume', 'Avg_Volume', 'Return_1M', 'Return_3M', 'Return_6M', 'Return_1Y',
]

# The US close is 21:00 UTC in winter (EST) and 20:00 UTC in summer (EDT);
# the snapshot job runs at 21:30 UTC on weekdays so it is after both.
_CLOSE_UTC_HOUR = 21

# GitHub delays scheduled runs under load, so a close only counts as
# "should be in the snapshot" this long after it happened. Until then the
# previous snapshot is still accepted.
_PUBLISH_GRACE = timedelta(hours=2)

_DOWNLOAD_TIMEOUT_SEC = 20


def latest_expected_close(now: datetime) -> datetime:
    """
    The most recent weekday close the snapshot should already include.

    Args:
        now: Timezone-aware current time.

    Returns:
        That close as a UTC datetime.
    """
    cutoff = now.astimezone(timezone.utc) - _PUBLISH_GRACE
    close = cutoff.replace(hour=_CLOSE_UTC_HOUR, minute=0, second=0, microsecond=0)
    if close > cutoff:
        close -= timedelta(days=1)
    while close.weekday() >= 5:  # Saturday/Sunday: no session
        close -= timedelta(days=1)
    return close


def is_fresh(generated_at: datetime, now: datetime) -> bool:
    """True when the snapshot was built after the latest expected close."""
    return generated_at >= latest_expected_close(now)


def write_snapshot(df: pd.DataFrame, path: Path, generated_at: datetime) -> None:
    """Write the stocks frame as gzipped JSON with its build time."""
    stocks = df[STOCK_COLUMNS].astype(object).where(df[STOCK_COLUMNS].notna(), None)
    payload = {
        'version': SNAPSHOT_VERSION,
        'generated_at': generated_at.astimezone(timezone.utc).isoformat(),
        'stocks': stocks.to_dict('records'),
    }
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'))


def read_snapshot(content: bytes) -> Tuple[pd.DataFrame, datetime]:
    """
    Parse a snapshot file.

    Returns:
        (stocks frame, UTC build time)

    Raises:
        ValueError: If the file is not a usable snapshot.
    """
    payload = json.loads(gzip.decompress(content))
    if payload.get('version') != SNAPSHOT_VERSION:
        raise ValueError(f"unsupported snapshot version {payload.get('version')!r}")
    df = pd.DataFrame(payload['stocks'], columns=STOCK_COLUMNS)
    if df.empty:
        raise ValueError('snapshot holds no stocks')
    generated_at = datetime.fromisoformat(payload['generated_at'])
    return df, generated_at


def load_fresh(
    url: str, now: Optional[datetime] = None
) -> Optional[Tuple[pd.DataFrame, datetime]]:
    """
    Download the published snapshot if it is current.

    Never raises: any problem is logged and returns None so the caller can
    fall back to the live refresh.

    Returns:
        (stocks frame, UTC build time), or None if unavailable or stale.
    """
    now = now or datetime.now(timezone.utc)
    try:
        response = requests.get(url, timeout=_DOWNLOAD_TIMEOUT_SEC)
        response.raise_for_status()
        df, generated_at = read_snapshot(response.content)
    except Exception as e:
        logger.warning(f"Snapshot unavailable, using live refresh: {e}")
        return None

    if not is_fresh(generated_at, now):
        logger.info(
            f"Snapshot from {generated_at:%Y-%m-%d %H:%M} UTC predates the "
            f"{latest_expected_close(now):%Y-%m-%d} close; using live refresh"
        )
        return None
    return df, generated_at


def main(argv: List[str]) -> int:
    """Run the live refresh and write its result as a snapshot file."""
    if len(argv) != 1:
        print('usage: python -m hqm.snapshot OUTPUT.json.gz', file=sys.stderr)
        return 2

    from hqm.database import fetch_live_stocks

    df = fetch_live_stocks()
    write_snapshot(df, Path(argv[0]), datetime.now(timezone.utc))
    logger.info(f"Wrote snapshot with {len(df)} stocks to {argv[0]}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
