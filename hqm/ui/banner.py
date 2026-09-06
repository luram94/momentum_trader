"""Compact market-context panel shared by Overview and Scanner."""
from html import escape

import streamlit as st

from hqm.config_loader import get_config
from hqm.market_regime import get_market_regime, UPTREND, CAUTION, DOWNTREND
from hqm.ui.design import markup


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_regime(proxy: str) -> dict:
    return get_market_regime(proxy)


def render_regime_banner() -> None:
    cfg = get_config().market_regime
    if not cfg.enabled:
        return
    snap = _cached_regime(cfg.proxy)
    regime = snap.get('regime')
    if regime not in (UPTREND, CAUTION, DOWNTREND):
        _cached_regime.clear()
        st.info(f"Market context is unavailable for {cfg.proxy}. Try again later; no current regime classification is available.")
        return
    guidance = {
        UPTREND: 'Trend conditions support long exposure.',
        CAUTION: 'Mixed trend conditions. The model calls for reduced exposure.',
        DOWNTREND: 'Weak trend conditions. The model avoids new long entries.',
    }[regime]
    action = {UPTREND: 'FULL EXPOSURE ALLOWED', CAUTION: 'REDUCE EXPOSURE', DOWNTREND: 'AVOID NEW LONGS'}[regime]
    markup(f'<div class="mt-regime mt-regime-{regime}">'
           f'<div class="mt-regime-top"><span class="mt-badge {regime}">{escape(regime)}</span>'
           f'<span class="mt-regime-kicker">MARKET TREND ALERT · {escape(snap["proxy"])}</span></div>'
           f'<div class="mt-regime-main"><div><div class="mt-regime-title">{escape(action)}</div>'
           f'<div class="mt-regime-detail">{escape(guidance)}</div></div>'
           f'<div class="mt-regime-exposure"><small>MODEL EXPOSURE CAP</small><b>{snap["max_exposure"] * 100:.0f}%</b></div></div></div>')
    with st.expander(f'Market context details · As of {snap["as_of"]}'):
        st.caption("Rule-based trend classification, not an execution instruction. The scanner does not automatically apply this exposure cap.")
        st.dataframe([{
            'Proxy': snap['proxy'], 'Close ($)': snap['close'],
            'SMA20 ($)': snap['sma20'], 'SMA50 ($)': snap['sma50'], 'SMA200 ($)': snap['sma200'],
            'SMA10 direction': 'Rising' if snap['sma10_rising'] else 'Falling',
        }], hide_index=True, use_container_width=True,
            column_config={c: st.column_config.NumberColumn(format='$%.2f') for c in ['Close ($)', 'SMA20 ($)', 'SMA50 ($)', 'SMA200 ($)']})
        if cfg.secondary_proxy:
            secondary = _cached_regime(cfg.secondary_proxy)
            sec_regime = secondary.get('regime')
            if sec_regime not in (UPTREND, CAUTION, DOWNTREND):
                st.caption(f"Secondary proxy {cfg.secondary_proxy}: unavailable.")
            else:
                agreement = 'confirms' if sec_regime == regime else 'diverges from'
                st.caption(f"{cfg.secondary_proxy}: {sec_regime} · {agreement} the {cfg.proxy} classification. {cfg.proxy} remains the primary proxy.")
