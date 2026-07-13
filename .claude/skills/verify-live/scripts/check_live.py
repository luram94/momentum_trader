"""Poll the live Streamlit Cloud app until it is healthy (or broken/timeout).

Run with the quanttrader conda python and LD_LIBRARY_PATH pointing at the
extracted chromium libs (see SKILL.md). Polls up to 7 minutes.
Exit codes: 0 healthy, 1 broken, 2 timeout. Saves live_app.png / live_app_fail.png
into the current working directory.
"""
import sys
import time
from playwright.sync_api import sync_playwright

URL = 'https://momentumtrader-main.streamlit.app'
DEADLINE = time.time() + 420

BAD = ['ModuleNotFoundError', 'ImportError', 'Oh no.', 'Error running app',
       'No module named']
BOOTING = ['oven', 'Spinning up', 'Waking up', 'Zzz', 'back up and running']


def check(page):
    page.goto(URL, wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(12000)
    texts = []
    for fr in page.frames:  # app tree lives in a /~/+/<Page> frame
        try:
            texts.append(fr.inner_text('body', timeout=3000))
        except Exception:
            pass
    blob = '\n'.join(texts)
    for marker in BAD:
        if marker in blob:
            return 'FAIL', marker
    for marker in BOOTING:
        if marker in blob:
            return 'BOOTING', marker
    if 'HQM' in blob or 'Momentum' in blob:
        return 'OK', blob[:600]
    return 'UNKNOWN', blob[:600]


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    while True:
        status, detail = check(page)
        print(f"[{time.strftime('%H:%M:%S')}] {status}: {detail[:200]!r}", flush=True)
        if status == 'OK':
            print('LIVE APP HEALTHY')
            page.screenshot(path='live_app.png')
            sys.exit(0)
        if status == 'FAIL':
            print('LIVE APP BROKEN')
            page.screenshot(path='live_app_fail.png')
            sys.exit(1)
        if time.time() > DEADLINE:
            print('TIMEOUT waiting for healthy app')
            sys.exit(2)
        time.sleep(20)
