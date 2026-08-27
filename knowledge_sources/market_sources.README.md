# DoobieLogic Public Market Intelligence Sources

DoobieLogic may index publicly accessible cannabis market information as secondary benchmark context for native Agents.

## Source tiers

- Official regulator/open-data feeds: state-published sales, price, license, plant, and testing data. These are preferred for state-level factual baselines but may still contain self-reported data limitations documented by the regulator.
- Commercial market-intelligence providers: public pages and reports from organizations such as Headset and BDSA. These provide category, brand, pricing, consumer, and market-trend context based on their disclosed samples/methodologies.
- Wholesale benchmarks: public wholesale index summaries and methodology from providers such as Cannabis Benchmarks.
- Transaction-derived industry research: public reports from cannabis POS/data providers such as Flowhub. These are useful directional context and carry lower authority than regulator data or dedicated market-intelligence providers.

## Usage rules

1. Facility operational data and deterministic DoobieLogic analytics remain the source of truth for the selected facility.
2. External market information is benchmark/context only. It cannot overwrite facility sales, inventory, production, cost, or margin facts.
3. External market sources cannot establish legal/regulatory compliance and cannot replace an approved facility SOP.
4. Agents should identify the relevant source, market/jurisdiction, and time period when using market data materially.
5. Retail, wholesale, unit, dollar, average-price, and market-share measures must not be conflated.
6. Sampling, retailer-coverage, self-reporting, classification, or other methodology limitations should be surfaced when material.
7. Only publicly accessible source material belongs in this repository catalog. Paid dashboards, licensed exports, private customer data, and paywalled datasets must not be copied into DoobieLogic without an appropriate data license/integration.
8. Source refresh cadence is controlled by each manifest entry's `review_every_days` field. Updated public pages are re-indexed by content hash.

## Why this exists

The goal is to let Agents answer questions such as:

- Is a category shift we see internally consistent with the broader Massachusetts market?
- Is retail price compression happening market-wide or only at this facility?
- How is a category such as vape, pre-roll, edible, beverage, or concentrate performing across tracked markets?
- Is wholesale flower pricing moving in a direction that may matter for future buying/manufacturing decisions?
- Which external trend is worth investigating in our own first-party data?

The correct pattern is always: external signal -> compare with authorized first-party data -> explain agreement/divergence -> recommend a human decision or further analysis.
