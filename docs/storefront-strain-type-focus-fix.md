# Storefront strain type and mobile focus fix

This change updates the Cowboy Kush wholesale product card star line to display a strain classification (`Indica`, `Sativa`, `Hybrid`, `Indica Hybrid`, or `Sativa Hybrid`) instead of the product category.

It also fixes the mobile keyboard dismissal bug caused by locally declared render helpers being mounted as fresh React component types on every parent state update. The helpers are now invoked as render functions, preserving the underlying input nodes and focus while typing in search, quantity, and buyer/order fields.
