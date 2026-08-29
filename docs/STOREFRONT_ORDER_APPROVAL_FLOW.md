# Storefront order approval flow

Hosted storefront submissions are demand requests, not direct inventory mutations.

1. The public storefront renders customer-facing quantities and prices in the configured display unit.
2. Inventory, listing source quantities, and Metrc-facing operational truth remain in the product base unit.
3. A successful customer submission writes a durable `CommerceStorefrontOrderRequest` with `status="submitted"` for the storefront organization and facility.
4. Wholesale Ops reads those durable requests into the Pending Storefront Orders approval queue.
5. Approval creates the commercial sales order, normalizes display-unit order lines back to the product base unit, confirms the order, and creates the operational inventory commitment.
6. Rejection closes the request without creating a commercial sales order or inventory commitment.

A storefront submit must never report success unless the durable approval request was written. A failed submission must return an error to the storefront rather than leaving the UI in a permanent pending state.
