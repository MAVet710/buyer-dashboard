import re
import pandas as pd

INV_NAME_ALIASES = ["product", "productname", "item", "itemname", "name", "skuname", "skuid", "product name", "product_name", "product title", "title"]
INV_CAT_ALIASES = ["category", "subcategory", "productcategory", "department", "mastercategory", "product category", "cannabis", "product_category", "ecomm category", "ecommcategory"]
INV_QTY_ALIASES = ["available", "onhand", "onhandunits", "quantity", "qty", "quantityonhand", "instock", "currentquantity", "current quantity", "inventoryavailable", "inventory available", "available quantity", "med total", "medtotal", "med sellable", "medsellable"]
INV_SKU_ALIASES = ["sku", "skuid", "productid", "product_id", "itemid", "item_id"]
INV_COST_ALIASES = ["cost", "unitcost", "unit cost", "cogs", "costprice", "cost price", "wholesale", "wholesaleprice", "wholesale price", "currentprice", "current price"]
INV_RETAIL_ALIASES = ["medprice", "med price", "retail", "retailprice", "retail price", "msrp"]
INV_BRAND_ALIASES = ["brand", "brandname", "brand name", "vendor", "vendorname", "vendor name", "manufacturer", "producer", "supplier"]
INV_ROOM_ALIASES = ["room", "location", "storage location", "inventory room"]

SALES_NAME_ALIASES = ["product", "productname", "product title", "producttitle", "productid", "name", "item", "itemname", "skuname", "sku", "description", "product name", "product_name"]
SALES_QTY_ALIASES = ["quantitysold", "quantity sold", "qtysold", "qty sold", "itemsold", "item sold", "items sold", "unitssold", "units sold", "unit sold", "unitsold", "units", "totalunits", "total units", "totalinventorysold", "total inventory sold", "quantity", "qty"]
SALES_CAT_ALIASES = ["mastercategory", "category", "master_category", "productcategory", "product category", "department", "dept", "subcategory", "productcategoryname", "product category name"]
SALES_REV_ALIASES = ["netsales", "net sales", "sales", "totalsales", "total sales", "revenue", "grosssales", "gross sales"]
SALES_DATE_ALIASES = ["ordertime", "order time", "orderdate", "order date", "datetime", "date", "business date", "day"]
SALES_ORDER_ALIASES = ["orderid", "order id", "ordernumber", "order number", "order"]


def normalize_col(col: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(col).lower())


def detect_column(columns, aliases):
    norm_map = {normalize_col(c): c for c in columns}
    for alias in aliases:
        n = normalize_col(alias)
        if n in norm_map:
            return norm_map[n]
    return None


def _detect_header_row(df: pd.DataFrame, kind: str) -> int:
    max_scan = min(20, len(df))
    for i in range(max_scan):
        row_text = " ".join(str(v) for v in df.iloc[i].tolist()).lower()
        if kind == "inventory":
            if any(tok in row_text for tok in ["product", "item", "sku", "name"]) and any(tok in row_text for tok in ["available", "on hand", "quantity", "qty"]):
                return i
        else:
            if any(tok in row_text for tok in ["product", "item", "name"]) and any(tok in row_text for tok in ["category", "master category", "department"]) and any(tok in row_text for tok in ["quantity", "qty", "sold", "units"]):
                return i
    return 0


def read_tabular_auto(uploaded_file, kind: str):
    name = str(getattr(uploaded_file, "name", "")).lower()
    uploaded_file.seek(0)
    if name.endswith(".csv"):
        tmp = pd.read_csv(uploaded_file, header=None)
    else:
        tmp = pd.read_excel(uploaded_file, header=None)
    header_row = _detect_header_row(tmp, kind)
    uploaded_file.seek(0)
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file, header=header_row)
    return pd.read_excel(uploaded_file, header=header_row)


def detect_pos_source(df: pd.DataFrame) -> str:
    cols = [normalize_col(c) for c in df.columns]
    if any(c in cols for c in ["mastercategory", "totalinventorysold", "netsales"]):
        return "Dutchie"
    if any(c in cols for c in ["medsellable", "medtotal", "ecommcategory"]):
        return "BLAZE"
    return "Generic"


def automap_inventory(df: pd.DataFrame):
    cols = list(df.columns)
    mapped = {
        "product_name": detect_column(cols, INV_NAME_ALIASES),
        "category": detect_column(cols, INV_CAT_ALIASES),
        "on_hand": detect_column(cols, INV_QTY_ALIASES),
        "sku": detect_column(cols, INV_SKU_ALIASES),
        "unit_cost": detect_column(cols, INV_COST_ALIASES),
        "retail_price": detect_column(cols, INV_RETAIL_ALIASES),
        "brand": detect_column(cols, INV_BRAND_ALIASES),
        "room": detect_column(cols, INV_ROOM_ALIASES),
    }
    ok = all([mapped["product_name"], mapped["category"], mapped["on_hand"]])
    return mapped, ok


def automap_sales(df: pd.DataFrame):
    cols = list(df.columns)
    mapped = {
        "product_name": detect_column(cols, SALES_NAME_ALIASES),
        "category": detect_column(cols, SALES_CAT_ALIASES),
        "units_sold": detect_column(cols, SALES_QTY_ALIASES),
        "revenue": detect_column(cols, SALES_REV_ALIASES),
        "sale_date": detect_column(cols, SALES_DATE_ALIASES),
        "order_id": detect_column(cols, SALES_ORDER_ALIASES),
    }
    ok = all([mapped["product_name"], mapped["category"], mapped["units_sold"]])
    return mapped, ok


def normalize_inventory_for_session(df: pd.DataFrame, mapping: dict):
    out = df.copy()
    rename_map = {}
    if mapping.get("product_name"): rename_map[mapping["product_name"]] = "product_name"
    if mapping.get("category"): rename_map[mapping["category"]] = "category"
    if mapping.get("on_hand"): rename_map[mapping["on_hand"]] = "on_hand"
    if mapping.get("sku"): rename_map[mapping["sku"]] = "sku"
    if mapping.get("unit_cost"): rename_map[mapping["unit_cost"]] = "unit_cost"
    if mapping.get("retail_price"): rename_map[mapping["retail_price"]] = "retail_price"
    if mapping.get("brand"): rename_map[mapping["brand"]] = "brand"
    if mapping.get("room"): rename_map[mapping["room"]] = "room"
    out = out.rename(columns=rename_map)
    return out


def normalize_sales_for_session(df: pd.DataFrame, mapping: dict):
    out = df.copy()
    rename_map = {}
    if mapping.get("product_name"): rename_map[mapping["product_name"]] = "product_name"
    if mapping.get("category"): rename_map[mapping["category"]] = "category"
    if mapping.get("units_sold"): rename_map[mapping["units_sold"]] = "units_sold"
    if mapping.get("revenue"): rename_map[mapping["revenue"]] = "revenue"
    if mapping.get("sale_date"): rename_map[mapping["sale_date"]] = "sale_date"
    if mapping.get("order_id"): rename_map[mapping["order_id"]] = "order_id"
    out = out.rename(columns=rename_map)
    return out
