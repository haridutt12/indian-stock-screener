"""Minimal auth test page — used to diagnose OAuth issues. Remove after fix confirmed."""
import streamlit as st

st.set_page_config(page_title="Login Test")

st.write("### Auth Test")
st.write("is_logged_in:", st.user.is_logged_in)

if st.user.is_logged_in:
    st.success(f"Logged in as: {st.user.email}")
    if st.button("Log out"):
        st.logout()
else:
    st.warning("Not logged in")
    if st.button("Login with Google"):
        st.login("google")
