from pathlib import Path
import streamlit as st

SVG_PATH = Path(__file__).with_name("loader.svg")

def show_loader():
    svg = SVG_PATH.read_text(encoding="utf-8")
    st.markdown(
        f'''
        <div class="loader-stage">
            <div class="loader-shell">{svg}</div>
            <div class="loader-copy">Preparing your workspace...</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )
