import os

INV_NAME_ALIASES = [
    "product", "productname", "item", "itemname", "name", "skuname",
    "skuid", "product name", "product_name", "product title", "title"
]
INV_CAT_ALIASES = [
    "category", "subcategory", "productcategory", "department",
    "mastercategory", "product category", "cannabis", "product_category",
    "ecomm category", "ecommcategory",
]
INV_QTY_ALIASES = [
    "available", "onhand", "onhandunits", "quantity", "qty",
    "quantityonhand", "instock", "currentquantity", "current quantity",
    "inventoryavailable", "inventory available", "available quantity",
    "med total", "medtotal",
    "med sellable", "medsellable",
]
INV_SKU_ALIASES = ["sku", "skuid", "productid", "product_id", "itemid", "item_id"]
INV_BATCH_ALIASES = [
    "batch", "batchnumber", "batch number", "lot", "lotnumber", "lot number",
    "batchid", "batch id", "lotid", "lot id", "inventorybatch", "inventory batch",
    "packageid", "package id",
]
SALES_NAME_ALIASES = [
    "product", "productname", "product title", "producttitle",
    "productid", "name", "item", "itemname", "skuname",
    "sku", "description", "product name", "product_name"
]
SALES_QTY_ALIASES = [
    "quantitysold", "quantity sold", "qtysold", "qty sold", "itemsold", "item sold", "items sold",
    "unitssold", "units sold", "unit sold", "unitsold", "units", "totalunits", "total units",
    "totalinventorysold", "total inventory sold", "quantity", "qty",
]
SALES_CAT_ALIASES = [
    "mastercategory", "category", "master_category", "productcategory", "product category",
    "department", "dept", "subcategory", "productcategoryname", "product category name"
]
SALES_SKU_ALIASES = ["sku", "skuid", "productid", "product_id"]
SALES_REV_ALIASES = ["netsales", "net sales", "sales", "totalsales", "total sales", "revenue", "grosssales", "gross sales"]
SALES_BATCH_ALIASES = ["batchid", "batch id", "batch", "batchnumber", "batch number", "lotid", "lot id", "lot", "lotnumber", "lot number"]
SALES_PACKAGE_ALIASES = ["packageid", "package id", "packagenumber", "package number"]
SALES_ORDER_ID_ALIASES = ["orderid", "order id", "ordernumber", "order number", "order"]
SALES_ORDER_TIME_ALIASES = ["ordertime", "order time", "orderdate", "order date", "datetime"]
UNKNOWN_DAYS_OF_SUPPLY = 999
DEFAULT_SALES_PERIOD_DAYS = 30
SLOW_MOVER_VELOCITY_WINDOWS = [28, 56, 84]
SLOW_MOVER_DEFAULT_DOH_THRESHOLD = 60
SLOW_MOVER_TOP_N_OPTIONS = [25, 50, 100, 0]
SLOW_MOVER_SORT_OPTIONS = ["Days of Supply ↓", "Weeks of Supply ↓", "$ On-Hand ↓", "Days Since Last Sale ↓"]
INV_COST_ALIASES = ["cost", "unitcost", "unit cost", "cogs", "costprice", "cost price", "wholesale", "wholesaleprice", "wholesale price", "currentprice", "current price"]
INV_RETAIL_PRICE_ALIASES = ["medprice", "med price", "retail", "retailprice", "retail price", "msrp"]
INV_STRAIN_TYPE_ALIASES = ["straintype", "strain type", "strain", "ecommstraintype", "ecomm strain type", "producttype", "product type"]
INV_BRAND_ALIASES = ["brand", "brandname", "brand name", "vendor", "vendorname", "vendor name", "manufacturer", "producer", "supplier"]
INV_SKU_COL_ALIASES = INV_SKU_ALIASES
INV_EXPIRY_ALIASES = ["expirationdate", "expiration date", "expiry", "expirydate", "expiry date", "bestby", "best by", "bestbydate", "best by date", "usebydate", "use by date", "expires", "exp", "expdate", "exp date"]
INV_COST_RETAIL_RATIO = 0.5
VALID_STRAIN_TYPES = frozenset(["indica", "sativa", "hybrid", "cbd", "indica dominant hybrid", "sativa dominant hybrid"])
INVENTORY_SORT_OPTIONS = ["$ on hand ↓", "DOH (high→low) ↓", "DOH (low→high) ↑", "Expiring soonest", "Avg weekly sales ↓"]
INVENTORY_REORDER_DOH_THRESHOLD = 21
INVENTORY_OVERSTOCK_DOH_THRESHOLD = 90
INVENTORY_EXPIRING_SOON_DAYS = 60
MAX_SKU_LENGTH_PDF = 10
MAX_DESCRIPTION_LENGTH_PDF = 20
MAX_STRAIN_LENGTH_PDF = 10
MAX_SIZE_LENGTH_PDF = 8
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
PRODUCT_TABLE_DISPLAY_LIMIT = 2000
PO_REVIEW_THRESHOLD = 15
BUYER_MARKET_REFERENCES = [{"name": "Headset Brand Marketplace", "url": "https://www.headset.io/brands", "notes": "Live, frequently updated brand-level market visibility across U.S. cannabis markets."}]
LOCAL_APP_URL = os.environ.get("LOCAL_APP_URL", "http://localhost:8501")
