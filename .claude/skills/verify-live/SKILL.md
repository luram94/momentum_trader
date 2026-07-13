---
name: verify-live
description: Check the live Streamlit Cloud deployment (momentumtrader-main.streamlit.app) after a push to main, using headless Playwright
---

# Verifying the live deployment

## Facts
- Canonical URL: **https://momentumtrader-main.streamlit.app** (deploys `main`
  of luram94/momentum_trader, entry `streamlit_app.py`). The old
  `momentumtrader.streamlit.app` subdomain is stale — never reference it.
- Streamlit Cloud redeploys automatically on push to `main`; allow **2–5 min**
  (longer when `requirements.txt` changed — that forces a dependency reinstall,
  and touching that file is also the trick to force a full process restart
  when the previous process crashed).
- The cloud DB lives in `/tmp/hqm_data` (see `get_db_path()` in
  `hqm/database.py`) — **ephemeral**. "Data Status: No Data" right after a
  redeploy is NORMAL, not a failure; it just needs a Refresh Data.
- `curl` alone can't verify health: the shell HTML is served even when the app
  script crashes (the exception renders client-side), and there's a 303
  auth-cookie dance first. Use Playwright and read text from **all frames**
  (the app tree lives in a `/~/+/<Page>` frame).

## Playwright setup (WSL2, no sudo)
Chromium is installed at `~/.cache/ms-playwright/`; the conda env python has
`playwright`. Chromium needs libnspr4/libnss3/libasound2, which aren't
installed system-wide. Extracted copies may survive in a previous session's
scratchpad — find them with:
`find /tmp/claude-1000 -name "libnspr4.so" 2>/dev/null`
If gone, re-extract (no sudo needed):
```bash
cd <scratchpad>/libs && for p in libnspr4 libnss3 libasound2t64; do
  apt-get download "$p" 2>/dev/null || apt-get download "${p%t64}"; done
for f in *.deb; do dpkg -x "$f" .; done
```
Then run python with:
`LD_LIBRARY_PATH=<libs>/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH`

## Health-check script
Use `scripts/check_live.py` next to this skill (copy to scratchpad and run
with the conda python + LD_LIBRARY_PATH above; run in background, it polls up
to 7 min). Success criterion: sidebar text contains the five page names and
"HQM"; failure markers: "ModuleNotFoundError", "Oh no.", "Error running app";
booting markers: "oven", "Spinning up", "Waking up" (app asleep after
inactivity — a visit wakes it).

Exit codes: 0 healthy (screenshot saved), 1 broken (screenshot saved), 2 timeout.
