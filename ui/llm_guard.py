"""
Per-session LLM cost guard.

Tracks estimated token spend across all AI features in a Streamlit session
and blocks further calls once the configured limit is reached.

Usage:
    from ui.llm_guard import llm_guard, record_llm_tokens

    # Before making an LLM call:
    if not llm_guard(estimated_tokens=600, label="Quant Critic"):
        st.stop()

    # After the call completes, record actual usage:
    record_llm_tokens(used=response.usage.input_tokens + response.usage.output_tokens)

Configuration (Streamlit secrets or env vars):
    SESSION_LLM_TOKEN_LIMIT  — hard cap per session (default 50_000 input+output)
    SESSION_LLM_WARN_TOKENS  — show warning banner at this level (default 30_000)
"""
from __future__ import annotations

import os

import streamlit as st

# ── Defaults ─────────────────────────────────────────────────────────────────
_DEFAULT_LIMIT = 50_000    # tokens per session before LLM calls are blocked
_DEFAULT_WARN  = 30_000    # tokens before warning banner appears

_SESSION_KEY_USED    = "_llm_tokens_used"
_SESSION_KEY_BLOCKED = "_llm_blocked"


def _limit() -> int:
    try:
        return int(st.secrets.get("SESSION_LLM_TOKEN_LIMIT", _DEFAULT_LIMIT))
    except Exception:
        return int(os.environ.get("SESSION_LLM_TOKEN_LIMIT", _DEFAULT_LIMIT))


def _warn_at() -> int:
    try:
        return int(st.secrets.get("SESSION_LLM_WARN_TOKENS", _DEFAULT_WARN))
    except Exception:
        return int(os.environ.get("SESSION_LLM_WARN_TOKENS", _DEFAULT_WARN))


def tokens_used() -> int:
    """Return total tokens consumed by LLM calls in this session."""
    return int(st.session_state.get(_SESSION_KEY_USED, 0))


def record_llm_tokens(used: int) -> None:
    """Add `used` tokens to the session counter. Call after each LLM response."""
    current = int(st.session_state.get(_SESSION_KEY_USED, 0))
    st.session_state[_SESSION_KEY_USED] = current + max(0, used)


def llm_guard(estimated_tokens: int = 500, label: str = "AI feature") -> bool:
    """
    Check whether this session has budget left for an LLM call.

    Args:
        estimated_tokens: conservative estimate of tokens this call will use.
        label: human-readable name shown in the blocked message.

    Returns True if the call is allowed; False if the session limit is reached.
    Renders a visible warning / blocked banner — caller should st.stop() on False.
    """
    used  = tokens_used()
    limit = _limit()
    warn  = _warn_at()

    if used >= limit:
        st.session_state[_SESSION_KEY_BLOCKED] = True
        st.error(
            f"**Session AI limit reached** ({used:,} / {limit:,} tokens used). "
            f"Refresh the page to start a new session with a fresh allowance. "
            f"*{label}* is disabled until then.",
            icon="🚫",
        )
        return False

    if used + estimated_tokens > limit:
        st.warning(
            f"**AI budget nearly exhausted** ({used:,} tokens used · limit {limit:,}). "
            f"This may be the last AI call this session.",
            icon="⚠️",
        )

    elif used >= warn:
        st.warning(
            f"**AI usage notice:** {used:,} / {limit:,} tokens used this session.",
            icon="⚠️",
        )

    return True


def llm_usage_badge() -> None:
    """Render a compact token-usage badge (intended for sidebars)."""
    used  = tokens_used()
    limit = _limit()
    pct   = min(used / limit * 100, 100) if limit > 0 else 0

    if pct >= 90:
        color, label = "#ff4d6d", "Critical"
    elif pct >= 60:
        color, label = "#f0b429", "Moderate"
    else:
        color, label = "#00c896", "OK"

    st.markdown(
        f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
        f'border-radius:8px;padding:8px 12px;margin-top:6px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'margin-bottom:6px;">'
        f'<span style="color:#64748b;font-size:0.68rem;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.07em;">AI Usage</span>'
        f'<span style="color:{color};font-size:0.68rem;font-weight:700;">{label}</span>'
        f'</div>'
        f'<div style="background:rgba(255,255,255,0.06);border-radius:99px;height:4px;">'
        f'<div style="width:{pct:.0f}%;height:100%;background:{color};border-radius:99px;'
        f'transition:width 0.3s;"></div></div>'
        f'<div style="color:#475569;font-size:0.65rem;margin-top:4px;">'
        f'{used:,} / {limit:,} tokens</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
