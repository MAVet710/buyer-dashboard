import streamlit as st


def simple_auth_gate():
    """Minimal login gate for commercial UX (uses Streamlit secrets)."""

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.markdown("<div class='login-card'>", unsafe_allow_html=True)
    st.markdown("<div class='login-title'>Secure Login</div>", unsafe_allow_html=True)

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        try:
            users = st.secrets.get("auth", {}).get("users", {})
        except Exception:
            users = {}

        if username in users and password == users[username]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid credentials")

    st.markdown("</div>", unsafe_allow_html=True)

    return False
