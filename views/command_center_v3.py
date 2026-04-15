import streamlit as st
from doobie_panels_v2 import render_exec_ai


def render_command_center_v3():
    st.title("Command Center")

    st.subheader("Executive AI Brief")
    render_exec_ai()

    st.markdown("---")
    st.subheader("System Status")
    st.write("All systems connected")
