import streamlit as st
import bcrypt

st.title("Bcrypt Hash Generator")

password = st.text_input("Enter password", type="password")

if st.button("Generate Hash"):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    st.code(hashed)
    st.write("Check works:", bcrypt.checkpw(password.encode(), hashed.encode()))
