import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ... [Existing app code that loads data, sets up user preferences, and field mappings goes here] ...
# For example, assume the user has uploaded their Dutchie sales and inventory files and we've read them into DataFrames:
# df_sales = pd.read_csv(sales_file)
# df_inventory = pd.read_csv(inventory_file) 
# (The code below will use df_sales and df_inventory for the new features.)

st.title("Cannabis Buyer Dashboard – Advanced Purchasing Analytics")

# Sidebar toggles for optional advanced features
st.sidebar.markdown("## Advanced Features")
enable_predictive = st.sidebar.checkbox("Predictive Ordering Forecasts")
enable_budget    = st.sidebar.checkbox("Budget Tracking & Purchase Planning")
enable_vendor    = st.sidebar.checkbox("Vendor Performance Analysis")
enable_pricing   = st.sidebar.checkbox("Pricing Trends")
enable_alerts    = st.sidebar.checkbox("Dead Stock & Low-Margin Alerts")

# --- Predictive Ordering Logic ---
if enable_predictive:
    st.subheader("Predictive Reorder Suggestions")
    # Input for lead time (days) and safety stock (days)
    lead_time = st.sidebar.number_input("Lead Time (days)", min_value=1, max_value=60, value=7)
    safety_stock = st.sidebar.number_input("Safety Buffer (days)", min_value=0, max_value=60, value=7)
    review_period = lead_time + safety_stock

    # Prepare sales data: calculate average daily sales for each product
    # Assume df_sales has a 'Item' column for product identifier and 'Quantity Sold' column for amount sold in that transaction.
    # Also assume df_sales covers a recent period (e.g., last 30 days of sales).
    if 'Sales Date/Time' in df_sales.columns:
        # Ensure date is datetime
        df_sales['Sales Date/Time'] = pd.to_datetime(df_sales['Sales Date/Time'])
    # Calculate total quantity sold per item in the period and derive daily rate
    sales_period_days = 30  # (Could also compute from min/max dates if available)
    sales_by_item = df_sales.groupby('Item')['Quantity Sold'].sum()
    daily_sales_rate = sales_by_item / sales_period_days

    # Prepare current inventory levels for each product.
    # If df_inventory (or a mapping file) provides current stock per product:
    current_stock = {}
    if 'Product' in df_inventory.columns and 'Available' in df_inventory.columns:
        # df_inventory might have one row per product with available quantity
        inv_data = df_inventory.set_index('Product')['Available'].to_dict()
        current_stock.update(inv_data)
    elif 'Name' in df_inventory.columns:
        # If inventory is provided at package level (multiple entries per item), sum quantities by product Name
        # (Assume 'Name' in df_inventory corresponds to product identifier similar to df_sales 'Item')
        if 'Quantity' in df_inventory.columns:
            current_stock = df_inventory.groupby('Name')['Quantity'].sum().to_dict()
        elif 'Available' in df_inventory.columns:
            current_stock = df_inventory.groupby('Name')['Available'].sum().to_dict()
    else:
        st.write("Inventory data not found or not loaded.")
        current_stock = {}

    # Compute reorder suggestions
    suggestions = []
    for item, daily_rate in daily_sales_rate.iteritems():
        if daily_rate <= 0:
            continue  # no sales, skip (these might be handled as dead stock separately)
        stock = current_stock.get(item, 0)
        # Calculate how many days current stock will last
        cover_days = stock / daily_rate if daily_rate > 0 else float('inf')
        # Determine if we need to reorder: stock covers less than lead time + safety buffer
        if cover_days < review_period:
            # Recommend reorder qty to have an additional 30 days of stock beyond the review period (for example)
            target_cover = review_period + 30  # we aim for an extra month of stock
            recommended_qty = max(0, daily_rate * target_cover - stock)
            suggestions.append({
                "Item": item,
                "Daily Sales": round(daily_rate, 2),
                "Current Stock": round(stock, 1),
                "Cover Days": round(cover_days, 1),
                "Recommended Reorder Qty": round(recommended_qty, 1)
            })
    if suggestions:
        sugg_df = pd.DataFrame(suggestions)
        # Sort suggestions by how soon stock will run out (Cover Days ascending)
        sugg_df.sort_values("Cover Days", inplace=True)
        st.write("Based on the past sales and a lead time of **{} days** (plus {} days safety), the following items may need reordering:".format(lead_time, safety_stock))
        st.dataframe(sugg_df, height=300)
    else:
        st.write("No immediate reorders suggested – current stock is sufficient for the next {} days for all top-selling items.".format(review_period))

# --- Budget Tracking & Purchase Planning ---
if enable_budget:
    st.subheader("Budget Planning")
    # Input budget (e.g., monthly budget for purchases)
    budget = st.sidebar.number_input("Purchase Budget ($)", min_value=0.0, value=0.0, step=1000.0)
    if budget and enable_predictive:
        # Ensure we have suggestions from predictive section
        if 'suggestions' in locals() and suggestions:
            # Estimate cost of suggested orders.
            # Assume we have a cost for each item (either via mapping or as a percentage of selling price).
            # Here, we use a simplistic approach: if inventory data has cost or if df_sales has price, derive cost.
            cost_mapping = {}
            if 'Cost' in df_sales.columns:
                # If sales data includes a Cost column for each item (not typical), use average cost
                avg_cost = df_sales.groupby('Item')['Cost'].mean().to_dict()
                cost_mapping.update(avg_cost)
            # If no explicit cost, assume a default cost as a percentage of price (e.g., 60% of retail price)
            avg_price = df_sales.groupby('Item')['Price'].mean().to_dict() if 'Price' in df_sales.columns else {}
            for item in sales_by_item.index:
                if item not in cost_mapping:
                    price = avg_price.get(item, 0)
                    if price:
                        cost_mapping[item] = 0.6 * price  # assume 60% of retail as cost if not provided
            # Calculate total cost of all recommended reorders
            total_cost = 0.0
            for sugg in suggestions:
                item = sugg["Item"]
                rec_qty = sugg["Recommended Reorder Qty"]
                item_cost = cost_mapping.get(item, 0)
                total_cost += item_cost * rec_qty
            total_cost = round(total_cost, 2)
            # Display suggested purchase plan vs budget
            st.write(f"**Total Cost of Recommended Orders:** ${total_cost:,.2f} out of a budget of ${budget:,.2f}")
            if total_cost > budget:
                st.error("⚠️ The suggested orders exceed your budget by ${:,.2f}. Consider prioritizing items or increasing the budget.".format(total_cost - budget))
            else:
                st.success("The suggested orders are within your budget.")
        else:
            st.write("No purchase suggestions available to apply against the budget.")
    else:
        st.write("Enter a budget and enable Predictive Ordering to plan purchases within your budget.")

# --- Vendor Performance Analysis ---
if enable_vendor:
    st.subheader("Vendor Performance")
    # Analyze sales and inventory by vendor/brand. We need a vendor name for each item.
    # Use field mapping if provided, otherwise attempt to parse from item name.
    vendor_map = {}
    if 'Vendor' in df_sales.columns:
        # If sales data or an uploaded mapping provides a Vendor for each item
        vendor_map = df_sales.set_index('Item')['Vendor'].to_dict()
    else:
        # Fallback: parse vendor/brand from item name (heuristic based on naming conventions)
        for item_name in df_sales['Item'].unique():
            name_without_code = item_name.split(": ", 1)[-1]  # remove any leading code if present
            # Assume brand/vendor is the first segment before the first "-" (dash) in the name
            brand = name_without_code.split('-')[0].strip()
            vendor_map[item_name] = brand

    # Aggregate key metrics by vendor
    df_sales['Vendor'] = df_sales['Item'].map(vendor_map)
    vendor_groups = df_sales.groupby('Vendor')
    vendor_stats = []
    for vendor, group in vendor_groups:
        total_units = group['Quantity Sold'].sum()
        total_sales = group['Price'].sum() if 'Price' in group.columns else group['Total Price'].sum()
        # Compute average margin if cost data is available or has been estimated
        avg_margin = None
        if 'Cost' in group.columns:
            # If cost per line is present, compute margin per sale
            margins = (group['Price'] - group['Cost']) / group['Price']
            avg_margin = margins.replace([np.inf, -np.inf], np.nan).mean()  # average margin ratio
        vendor_stats.append({
            "Vendor": vendor,
            "Products Sold": group['Item'].nunique(),
            "Total Units Sold": total_units,
            "Total Sales ($)": round(total_sales, 2),
            "Avg Profit Margin": f"{avg_margin*100:.1f}%" if avg_margin is not None else "N/A"
        })
    vendor_df = pd.DataFrame(vendor_stats).sort_values("Total Sales ($)", ascending=False)
    st.write("Below is a summary of sales performance by vendor/supplier:")
    st.dataframe(vendor_df.reset_index(drop=True), height=300)

    # (Optional) We could also integrate vendor order history analysis if purchase order data were available, 
    # e.g., fill rate or on-time delivery metrics. For now, we focus on sales performance as a proxy.

# --- Pricing Trends ---
if enable_pricing:
    st.subheader("Pricing Trends")
    # This section would visualize wholesale or cost trends over time.
    # If multiple time-period data is available (e.g., monthly reports), we merge and plot cost trends.
    # For demonstration, check if there's a monthly sales or cost history in df_inventory or another dataset.
    if 'Inventory date' in df_inventory.columns:
        # Example: show how old some inventory is as a proxy for price stability (not actual price trend).
        df_inventory['Inventory date'] = pd.to_datetime(df_inventory['Inventory date'], errors='coerce')
        inv_by_date = df_inventory.groupby(df_inventory['Inventory date'].dt.to_period('M'))['Product'].count()
        inv_by_date.index = inv_by_date.index.to_timestamp()
        st.line_chart(inv_by_date, width=0, height=0)  # plot count of active products by last inventory date per month
        st.write("*(Example chart above: Inventory count by last updated month. In a real scenario, this would plot actual cost or price data over time.)*")
    else:
        st.write("Upload historical pricing data to see trends over time (e.g., cost per unit by month).")
    # Note: In practice, you would replace the above with actual price trend data if available, 
    # such as plotting average cost per gram for a product across multiple months.

# --- Dead Stock & Low-Margin Alerts ---
if enable_alerts:
    st.subheader("Alerts: Dead Stock & Low Margins")

    # Dead Stock Alert: identify items with no recent sales
    # If inventory file has "Inventory date" (last movement date) and "Available" quantity:
    dead_stock_list = []
    if 'Inventory date' in df_inventory.columns and 'Available' in df_inventory.columns:
        df_inventory['Inventory date'] = pd.to_datetime(df_inventory['Inventory date'], errors='coerce')
        cutoff_date = datetime.now() - timedelta(days=90)  # e.g., 90 days without sales
        mask = (df_inventory['Available'] > 0) & (df_inventory['Inventory date'] < cutoff_date)
        dead_items = df_inventory[mask]
        for _, row in dead_items.iterrows():
            dead_stock_list.append({
                "Product": row['Product'] if 'Product' in row else row.get('Name', 'Unknown'),
                "Category": row.get('Category', 'N/A'),
                "Last Sale/Update": row['Inventory date'].date().isoformat() if pd.notna(row['Inventory date']) else "Unknown",
                "Qty in Stock": row['Available']
            })
    else:
        # Fallback: use sales data to find items with zero sales in period but present in inventory
        sold_items = set(df_sales['Item'])
        for prod in current_stock:  # current_stock from predictive section or recalc here
            if prod not in sold_items and current_stock.get(prod, 0) > 0:
                dead_stock_list.append({
                    "Product": prod,
                    "Category": df_inventory[df_inventory['Name']==prod]['Category'].iloc[0] if 'Category' in df_inventory.columns else "N/A",
                    "Last Sale/Update": "No sales in period",
                    "Qty in Stock": current_stock.get(prod, 0)
                })
    if dead_stock_list:
        dead_df = pd.DataFrame(dead_stock_list)
        dead_df.sort_values("Last Sale/Update", inplace=True)  # oldest first
        st.write(f"**Dead Stock Items:** (No sales in last 90 days, still in inventory)")
        st.table(dead_df.head(10))  # show top 10 for brevity
        if len(dead_stock_list) > 10:
            st.write(f"...and {len(dead_stock_list)-10} more items.")
    else:
        st.write("✅ **Dead Stock Check:** No items without recent sales (within last 90 days).")

    # Low Margin Warning: find items selling below a margin threshold
    # We need cost vs price. If cost data is available (from mapping or assumption), use it.
    low_margin_items = []
    margin_threshold = 0.20  # 20% minimum margin
    # Ensure we have a 'Cost' column in sales data; if not, estimate as before
    if 'Cost' not in df_sales.columns:
        # Estimate cost for each item if not provided
        df_sales['Cost'] = df_sales.apply(
            lambda row: row['Price'] * 0.9 if isinstance(row['Item'], str) and "High Supply" in row['Item'] else row['Price'] * 0.6, 
            axis=1
        )
    df_sales['Margin_pct'] = (df_sales['Price'] - df_sales['Cost']) / df_sales['Price']
    margin_by_item = df_sales.groupby('Item')['Margin_pct'].mean().dropna()
    low_margin = margin_by_item[margin_by_item < margin_threshold]
    for item, margin in low_margin.iteritems():
        low_margin_items.append({
            "Product": item,
            "Margin %": f"{margin*100:.1f}%"
        })
    if low_margin_items:
        lm_df = pd.DataFrame(low_margin_items)
        st.write(f"**Low Margin Products:** (Below {int(margin_threshold*100)}% profit margin)")
        st.table(lm_df)
    else:
        st.write(f"✅ **Margin Check:** No products are below the {int(margin_threshold*100)}% margin threshold.")
