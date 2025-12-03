import streamlit as st
import pandas as pd
import numpy as np
import re

# Title
st.title("Cannabis Inventory Forecast Dashboard")

# Custom background image and dark overlay CSS
bg_url = "https://raw.githubusercontent.com/yourusername/yourrepo/main/background.jpg"  # Replace with your GitHub image URL
st.markdown(f"""
    <style>
    .stApp {{
        background: linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5)), url("{bg_url}");
        background-size: cover;
    }}
    </style>
    """, unsafe_allow_html=True)

# File uploads
sales_file = st.file_uploader("Upload Product Sales Report (Excel)", type=['xlsx'])
detailed_file = st.file_uploader("Upload Detailed Sales Breakdown by Product (Excel)", type=['xlsx'])
inventory_file = st.file_uploader("Upload Inventory Snapshot (CSV)", type=['csv'])

if sales_file and detailed_file and inventory_file:
    try:
        # Read and normalize product sales report
        df_ps = pd.read_excel(sales_file)
        df_ps.columns = df_ps.columns.str.strip().str.lower().str.replace(' ', '_')
        # If mastercategory missing, use category
        if 'master_category' in df_ps.columns:
            df_ps = df_ps.rename(columns={'master_category': 'mastercategory'})
        if 'mastercategory' not in df_ps.columns and 'category' in df_ps.columns:
            df_ps['mastercategory'] = df_ps['category']
        # Map Quantity Sold to units_sold
        if 'quantity_sold' in df_ps.columns:
            df_ps = df_ps.rename(columns={'quantity_sold': 'units_sold'})
        units_col = 'units_sold'
        if units_col not in df_ps.columns:
            st.error("Could not find 'Units Sold' column in Product Sales Report.")
            st.stop()
        df_ps['units_sold'] = pd.to_numeric(df_ps['units_sold'], errors='coerce').fillna(0)
        total_units_sold = int(df_ps['units_sold'].sum())
        # Active categories from product sales
        if 'mastercategory' in df_ps.columns:
            active_categories_count = int(df_ps['mastercategory'].nunique())
        elif 'category' in df_ps.columns:
            active_categories_count = int(df_ps['category'].nunique())
        else:
            active_categories_count = 0

        # Read and normalize detailed sales breakdown
        df_det = pd.read_excel(detailed_file)
        df_det.columns = df_det.columns.str.strip().str.lower().str.replace(' ', '_')
        product_col = None
        quantity_col = None
        date_col = None
        for col in df_det.columns:
            if 'product' in col or 'item' in col:
                product_col = col
                break
        for col in df_det.columns:
            if 'quantity' in col or 'qty' in col:
                quantity_col = col
                break
        for col in df_det.columns:
            if 'date' in col:
                date_col = col
                break
        if product_col is None or quantity_col is None:
            st.error("Could not identify product or quantity column in Detailed Sales data.")
            st.stop()
        df_det = df_det.rename(columns={product_col: 'product', quantity_col: 'quantity'})
        # Compute days in period
        if date_col:
            df_det['date'] = pd.to_datetime(df_det[date_col])
            days = (df_det['date'].max() - df_det['date'].min()).days + 1
        else:
            days = 64  # Fallback for Oct1-Dec3
        if days <= 0:
            days = 1
        # Aggregate total units per product
        df_units = df_det.groupby('product')['quantity'].sum().reset_index().rename(columns={'quantity': 'total_sold'})
        df_units['total_sold'] = pd.to_numeric(df_units['total_sold'], errors='coerce').fillna(0)

        # Read and normalize inventory
        df_inv = pd.read_csv(inventory_file)
        df_inv.columns = df_inv.columns.str.strip().str.lower().str.replace(' ', '_')
        if 'master_category' in df_inv.columns:
            df_inv = df_inv.rename(columns={'master_category': 'mastercategory'})
        if 'mastercategory' not in df_inv.columns and 'category' in df_inv.columns:
            df_inv['mastercategory'] = df_inv['category']
        if 'available' not in df_inv.columns:
            st.error("Could not find 'Available' column in Inventory data.")
            st.stop()
        df_inv['available'] = pd.to_numeric(df_inv['available'], errors='coerce').fillna(0)
        # Extract subcategory (package size) from product name
        def extract_subcategory(name):
            match = re.search(r'(\d+(?:\.\d+)?\s*(?:mg|g))', str(name), re.IGNORECASE)
            if match:
                return match.group(1).strip()
            else:
                return "N/A"
        df_inv['subcategory'] = df_inv['product'].apply(extract_subcategory)
        # Trim product names for consistency
        df_inv['product'] = df_inv['product'].astype(str).str.strip()
        df_units['product'] = df_units['product'].astype(str).str.strip()
        # Merge inventory with sales units
        df = pd.merge(df_inv, df_units, on='product', how='left')
        df['total_sold'] = df['total_sold'].fillna(0)
        # Compute average units sold per day per product
        df['avg_per_day'] = df['total_sold'] / days
        df.loc[df['total_sold'] == 0, 'avg_per_day'] = 0
        # Aggregate by master category and subcategory
        df_group = df.groupby(['mastercategory', 'subcategory']).agg(
            total_sold=('total_sold', 'sum'),
            available=('available', 'sum')
        ).reset_index()
        # Compute avg per day and days on hand for group
        df_group['avg_per_day'] = df_group['total_sold'] / days
        df_group['days_on_hand'] = np.where(df_group['avg_per_day'] > 0,
                                           df_group['available'] / df_group['avg_per_day'],
                                           np.nan)
        # Compute reorder quantity based on threshold
        threshold = st.number_input("DaysOnHand Threshold (days)", min_value=0, max_value=30, value=14)
        df_group['reorder_qty'] = np.maximum(0, threshold * df_group['avg_per_day'] - df_group['available'])
        # Classify reorder priority
        conditions = [
            df_group['total_sold'] == 0,
            df_group['days_on_hand'] < 7,
            df_group['days_on_hand'] < 21
        ]
        choices = [4, 1, 2]
        df_group['priority'] = np.select(conditions, choices, default=3)
        # Round numeric values for display
        df_group['avg_per_day'] = df_group['avg_per_day'].round(2)
        df_group['days_on_hand'] = df_group['days_on_hand'].round(1)
        df_group['reorder_qty'] = df_group['reorder_qty'].round(0).astype(int)
        df_group['total_sold'] = df_group['total_sold'].astype(int)
        df_group = df_group.sort_values(['mastercategory', 'priority'])

        # Compute metrics
        watchlist_count = int((df_group['priority'] == 2).sum())
        asap_count = int((df_group['priority'] == 1).sum())

        # Top metrics clickable to filter
        col1, col2, col3, col4 = st.columns(4)
        if 'filter' not in st.session_state:
            st.session_state.filter = 'all'
        with col1:
            if st.button(f"Total Units Sold\n{total_units_sold}"):
                st.session_state.filter = 'all'
        with col2:
            if st.button(f"Active Categories\n{active_categories_count}"):
                st.session_state.filter = 'all'
        with col3:
            if st.button(f"Watchlist Items\n{watchlist_count}"):
                st.session_state.filter = 'watchlist'
        with col4:
            if st.button(f"Reorder ASAP Items\n{asap_count}"):
                st.session_state.filter = 'asap'

        # Filter dataframe based on selection
        if st.session_state.filter == 'watchlist':
            df_display = df_group[df_group['priority'] == 2]
        elif st.session_state.filter == 'asap':
            df_display = df_group[df_group['priority'] == 1]
        else:
            df_display = df_group.copy()

        # Display inventory forecast in collapsible master-category blocks
        for category in sorted(df_display['mastercategory'].unique()):
            cat_df = df_display[df_display['mastercategory'] == category]
            if cat_df.empty:
                continue
            with st.expander(f"{category}"):
                display_df = cat_df[['subcategory', 'total_sold', 'avg_per_day', 'available', 'days_on_hand', 'reorder_qty', 'priority']].copy()
                display_df.columns = ['Subcategory', 'Total Sold', 'Avg/Day', 'Available', 'Days On Hand', 'Reorder Qty', 'Priority']
                display_df = display_df.sort_values(['Priority', 'Subcategory'])
                # Style Days On Hand < 100 as bold red
                def highlight_days(val):
                    try:
                        return 'color: red; font-weight: bold' if val < 100 else ''
                    except:
                        return ''
                styled = display_df.style.applymap(highlight_days, subset=['Days On Hand'])
                st.dataframe(styled)

        # Download CSV of forecast table
        df_download = df_group[['mastercategory', 'subcategory', 'total_sold', 'avg_per_day', 'available', 'days_on_hand', 'reorder_qty', 'priority']].copy()
        df_download.columns = ['Category', 'Subcategory', 'Total Units Sold', 'Avg Units/Day', 'On Hand', 'Days On Hand', 'Reorder Quantity', 'Priority']
        csv = df_download.to_csv(index=False)
        st.download_button("Download Forecast CSV", data=csv, file_name="inventory_forecast.csv", mime='text/csv')
    except Exception as e:
        st.error(f"An error occurred: {e}")
        st.stop()
else:
    st.info("Please upload all three files to display the dashboard.")
