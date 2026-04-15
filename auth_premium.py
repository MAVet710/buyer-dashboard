import bcrypt
import streamlit as st

def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def premium_auth_gate():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.markdown("<div class='login-shell'><div class='login-card login-fade'>", unsafe_allow_html=True)
    st.markdown("<div class='login-title'>Platform</div>", unsafe_allow_html=True)
    st.markdown("<div class='login-sub'>Secure access portal</div>", unsafe_allow_html=True)

    username = st.text_input("Username", key="premium_login_user")
    password = st.text_input("Password", type="password", key="premium_login_pass")

    if st.button("Enter", use_container_width=True, key="premium_login_btn"):
        try:
            users = st.secrets.get("auth", {}).get("users", {})
        except Exception:
            users = {}

        stored_hash = users.get(username)
        if stored_hash and check_password(password, stored_hash):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid credentials")

    st.markdown("</div></div>", unsafe_allow_html=True)
    return False
