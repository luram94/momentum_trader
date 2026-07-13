"""
Market Regime Banner
=====================
Shared banner for Home and Scanner showing the current market regime and
the exposure guidance that goes with it. Regime data is cached for an hour
so page reruns don't refetch the proxy.
"""

import streamlit as st

from hqm.config_loader import get_config
from hqm.market_regime import get_market_regime, UPTREND, CAUTION, DOWNTREND


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_regime(proxy: str) -> dict:
    return get_market_regime(proxy)


def _exposure_pct(fraction: float) -> str:
    return f"{fraction * 100:.0f}%"


def render_regime_banner() -> None:
    """Render the market regime banner (no-op if disabled in config)."""
    cfg = get_config().market_regime
    if not cfg.enabled:
        return

    snap = _cached_regime(cfg.proxy)
    regime = snap.get('regime')

    if regime not in (UPTREND, CAUTION, DOWNTREND):
        st.info(
            f"**Market regime unavailable** — could not evaluate {cfg.proxy} "
            f"({snap.get('error', 'unknown error')}). Trade as if in Caution."
        )
        return

    slope = "rising" if snap['sma10_rising'] else "falling"
    detail = (
        f"{snap['proxy']} ${snap['close']:,.2f} · "
        f"SMA20 ${snap['sma20']:,.2f} · SMA50 ${snap['sma50']:,.2f} · "
        f"SMA200 ${snap['sma200']:,.2f} · SMA10 {slope}"
    )
    exposure = _exposure_pct(snap['max_exposure'])

    header = f"Market Regime: {regime.capitalize()} — primary proxy {snap['proxy']}"

    if regime == UPTREND:
        st.success(
            f"🟢 **{header}** — long exposure allowed up to "
            f"{exposure}.\n\n{detail} · as of {snap['as_of']}"
        )
    elif regime == CAUTION:
        st.warning(
            f"🟡 **{header}** — reduce position size, max long "
            f"exposure {exposure}.\n\n{detail} · as of {snap['as_of']}"
        )
    else:
        st.error(
            f"🔴 **{header}** — avoid new long entries, max "
            f"long exposure {exposure}.\n\n{detail} · as of {snap['as_of']}"
        )

    # Secondary proxy as a confirmation read, never the decision driver
    if cfg.secondary_proxy:
        secondary = _cached_regime(cfg.secondary_proxy)
        sec_regime = secondary.get('regime', 'unknown')
        agreement = "confirms" if sec_regime == regime else "diverges from"
        st.caption(
            f"Secondary confirmation — {cfg.secondary_proxy}: **{sec_regime}** "
            f"({agreement} the {cfg.proxy} regime; {cfg.proxy} is the "
            f"decision driver)."
        )
