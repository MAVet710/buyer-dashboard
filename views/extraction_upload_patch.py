import pandas as pd
import streamlit as st


def read_extraction_file(uploaded_file):
    name = str(getattr(uploaded_file, "name", "")).lower()
    try:
        if name.endswith(".xlsx") or name.endswith(".xls"):
            return pd.read_excel(uploaded_file)
        return pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        return None
