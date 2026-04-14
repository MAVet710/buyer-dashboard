import streamlit as st
from doobie_panels import run_buyer_doobie


def render_buyer_view(by_product_df):
    st.header("🧠 Buyer Intelligence")

    if st.button("Generate AI Buyer Brief"):
        run_buyer_doobie(by_product_df)
