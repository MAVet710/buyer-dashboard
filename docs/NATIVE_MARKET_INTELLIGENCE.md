# Native Market Intelligence

DoobieLogic Buyer Intelligence can layer public market context over a facility's own sales and inventory evidence without requiring buyers to leave the application.

## Provider contract

`services.market_data.MassachusettsCCCProvider` is the first provider. It reads the Massachusetts Cannabis Control Commission public sales and price JSON datasets. Provider failures are fail-soft: store-level Buyer Intelligence must continue to return normally.

## Decision hierarchy

1. Facility sales and inventory remain the primary evidence.
2. Public market data is directional context only.
3. Deterministic code produces signals; the Doobie Agent may explain the evidence but does not invent the signal.
4. Source and as-of metadata must be visible to the user.

## Expansion

Future states should implement the same provider boundary and normalize state-specific product labels into DoobieLogic categories before comparison.
