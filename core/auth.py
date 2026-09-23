"""Access gate for when the app is published beyond localhost.

Not a security system -- a shared access code that keeps a public tunnel URL from
being open to anyone who stumbles onto it. Disabled unless CI_APP_PASSWORD is set,
so local development is unaffected.
"""

from __future__ import annotations

import hmac

import streamlit as st

from .config import get_settings

_KEY = "_ci_authenticated"


def require_access() -> None:
    """Call at the top of every page. Halts rendering until the code is correct."""
    expected = get_settings().app_password.strip()
    if not expected or st.session_state.get(_KEY):
        return

    st.markdown("## Conference Intelligence Assistant")
    st.caption("This instance is published. Enter the access code to continue.")

    with st.form("access_gate"):
        entered = st.text_input("Access code", type="password")
        submitted = st.form_submit_button("Enter", type="primary")

    if submitted:
        if hmac.compare_digest(entered, expected):
            st.session_state[_KEY] = True
            st.rerun()
        else:
            st.error("Incorrect access code.")

    st.stop()
