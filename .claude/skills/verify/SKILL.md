---
name: verify
description: How to run and verify the HQM Momentum Scanner Streamlit app end-to-end in this repo (unit tests, AppTest harness, Docker)
---

# Verifying momentum_trader

## Environment
Use the conda env python directly (never create a venv):
`~/miniforge3/envs/quanttrader/bin/python`
It has all requirements deps incl. streamlit/plotly/pytest/playwright (added 2026-07-09).

## Project layout (since 2026-07-10, PR #6)
Core code lives in the `hqm/` package (`hqm/database.py`, `hqm/backtest.py`,
`hqm/risk_metrics.py`, `hqm/config_loader.py`, `hqm/logger.py`,
`hqm/formatting.py`, UI helpers in `hqm/ui/`). Entry `streamlit_app.py` and
`pages/` stay at repo root. Paths resolve via `PROJECT_ROOT` in
`hqm/config_loader.py`; logs go to `logs/hqm_scanner.log`.

## Unit tests
`~/miniforge3/envs/quanttrader/bin/python -m pytest`
(pytest.ini has `pythonpath = .`; no sys.path hacks needed.)

## Driving the app (no browser available)
Use Streamlit's official AppTest harness — it executes the real page scripts
end-to-end (real SQLite DB, real yfinance/FinViz network calls):

```python
import os, sys
ROOT = '/home/luram94/workspace/quantTrader/momentum_trader'
# `streamlit run` puts the entry dir on sys.path (bootstrap._fix_sys_path)
# and runs from repo root; AppTest does NEITHER — without these two lines
# every page fails with "No module named 'hqm'".
sys.path.insert(0, ROOT); os.chdir(ROOT)

from streamlit.testing.v1 import AppTest
at = AppTest.from_file('pages/1_Scanner.py', default_timeout=900)
at.run()
buttons = {b.label: b for b in at.button}
buttons['Run Scan'].click()   # or 'Refresh Data' first (real FinViz, ~70s)
at.run()
# inspect: at.metric (label/value), at.warning, at.error, at.dataframe[0].value,
# at.exception
```

Filter driver stderr noise: `grep -v "SettingWithCopy\|missing ScriptRunContext"`.

## Docker (since PR #8)
```bash
docker compose up -d --build          # serves on localhost:8501
curl -sf http://localhost:8501/_stcore/health   # -> "ok"
docker compose exec app python -c "import hqm.database as db; print(db.DB_PATH)"
docker compose down
```
`./data` and `./logs` are bind-mounted (uid 1000 in image matches host user).
Image has runtime deps only — no pytest inside the container.

## Gotchas
- `data/hqm_data.db` schema does NOT migrate for user tables; scan/data tables
  are dropped+rebuilt by `_migrate_schema`. If a page crashes with "no such
  column", back up the file, let `init_database()` rebuild, then Refresh Data.
- Data refresh (since PR #9) uses ONE FinViz Custom screen per exchange
  (`_CUSTOM_SCREENER_COLUMNS` in `hqm/database.py`). `limit=100000` is
  REQUIRED — Custom's default limit=-1 stops pagination after one 20-row page;
  a full-universe refresh stores ~2,000 stocks, so if you see ~40, that broke.
  Page sleep is `rate_limits.finviz_sleep_sec` in config.yaml (0.3s; raise it
  if FinViz starts rate-limiting). Full refresh ≈ 70s.
- A refresh that would store 0 stocks raises RuntimeError and keeps existing
  rows — intentional guard against FinViz layout changes, don't "fix" it.
- Scan filters (RSI/SMA/ATR) default OFF in session state; a plain Run Scan
  exercises HQM scoring + indicators + risk metrics.
- Degraded-path probe: monkeypatch `hqm.risk_metrics.get_historical_prices` to
  return `pd.DataFrame()` before AppTest run — the Scanner must show
  Est. Sharpe "N/A" plus a warning, never zeros.
- yfinance in this env: no 'Adj Close' column (auto_adjust default True).
  `get_technical_indicators` uses `threads=False` (threaded downloads segfault
  Streamlit Cloud) — don't optimize it back without making it conditional.
