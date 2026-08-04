import streamlit as st

st.set_page_config(
    page_title="Admin Panel · NiftyEdge",
    page_icon="🛡️",
    layout="centered",
)

from ui.styles import inject_global_css, auth_guard, user_sidebar, page_header, _get_admin_email

inject_global_css()
auth_guard()

with st.sidebar:
    user_sidebar()

_current_email = (getattr(st.user, "email", "") or "").strip().lower()
_admin_email   = _get_admin_email()

if not _admin_email or _current_email != _admin_email:
    st.markdown(
        '<div style="text-align:center;padding:60px 20px;">'
        '<div style="font-size:2.5rem;margin-bottom:12px;">🔒</div>'
        '<div style="font-size:1.2rem;font-weight:700;color:#e2e8f0;margin-bottom:8px;">'
        'Administrator Only</div>'
        '<div style="color:#4b5a72;font-size:0.85rem;">'
        'This page is restricted to the app administrator.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()

page_header("Admin Panel", subtitle="NiftyEdge", badge="ADMIN", badge_color="#ef4444")

from signals.signal_logger import get_signal_logger
_log = get_signal_logger()

# ── Add user ──────────────────────────────────────────────────────────────────
st.subheader("Add Allowed User")
with st.form("add_user_form", clear_on_submit=True):
    _col1, _col2 = st.columns([2, 1])
    with _col1:
        _new_email = st.text_input("Gmail address", placeholder="user@gmail.com")
    with _col2:
        _new_name  = st.text_input("Name (optional)")
    _submitted = st.form_submit_button("Add User", type="primary", use_container_width=True)

if _submitted:
    _new_email = _new_email.strip().lower()
    if not _new_email or "@" not in _new_email:
        st.error("Enter a valid email address.")
    else:
        ok = _log.add_allowed_user(_new_email, _new_name)
        if ok:
            st.success(f"✅ **{_new_email}** added to the access list.")
            st.rerun()
        else:
            st.error("Failed to add user — check logs.")

st.divider()

# ── Allowed users list ────────────────────────────────────────────────────────
st.subheader("Access List")

_users = _log.list_allowed_users()

if not _users:
    st.info(
        "No users on the access list yet. When the list is empty, **all** signed-in "
        "Google accounts can access the app. Add at least one user to enforce restrictions.",
        icon="ℹ️",
    )
else:
    st.caption(f"{len(_users)} user{'s' if len(_users) != 1 else ''} on the access list")
    for _u in _users:
        _c1, _c2, _c3 = st.columns([3, 2, 1])
        with _c1:
            _display = _u["name"] if _u["name"] else _u["email"]
            st.markdown(
                f'<div style="font-size:0.85rem;font-weight:600;color:#e2e8f0;">'
                f'{_display}</div>'
                f'<div style="font-size:0.7rem;color:#4b5a72;">{_u["email"]}</div>',
                unsafe_allow_html=True,
            )
        with _c2:
            _added = _u.get("added_at", "")
            if _added:
                st.caption(_added[:10])
        with _c3:
            if st.button("Remove", key=f"rm_{_u['email']}", type="secondary"):
                _log.remove_allowed_user(_u["email"])
                st.success(f"Removed **{_u['email']}**")
                st.rerun()
        st.divider()

# ── Admin info ────────────────────────────────────────────────────────────────
with st.expander("Admin account"):
    st.markdown(
        f'<div style="font-size:0.8rem;color:#94a3b8;">'
        f'Signed in as <strong style="color:#e2e8f0;">{_current_email}</strong> (admin).<br>'
        f'The admin account always has access regardless of the list above.</div>',
        unsafe_allow_html=True,
    )
