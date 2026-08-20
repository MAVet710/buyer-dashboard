# Product Master Foundation

Buyer Dash keeps `coman_products.id` as the canonical product identifier so existing inventory, production, Package Studio, and commercial relationships remain stable.

Migration `0020_product_master` adds durable extensions for:

- cannabis/product identity: brand, category, subcategory, strain, manufacturer, product format, description
- vendor relationships: vendor SKU, primary vendor, lead time, MOQ, case pack
- external mappings: Metrc, Dutchie, BioTrack, or other external product identifiers
- normalized aliases for matching inconsistent import names to one canonical product
- append-only unit cost, landed cost, retail price, and wholesale price history

Current `coman_products.unit_cost` and `coman_products.retail_price` remain mirrored for backward compatibility while `product_value_events` preserves the historical values and source references.

The Product Master repository validates organization ownership, prevents external-ID and alias collisions inside a tenant, enforces vendor-only relationships, and writes audit events for master-data changes.
