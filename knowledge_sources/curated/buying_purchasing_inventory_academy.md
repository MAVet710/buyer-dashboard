# DoobieLogic Buying, Purchasing, and Inventory Academy

## Audience

Primary agents: Buyer Agent, Purchasing Agent, Inventory Agent.
Secondary use: Operations, Commercial, Wholesale, Finance, Data Hub.

## Source posture

This is an independently written synthesis of inventory management, procurement, supplier management, demand planning, assortment, and working-capital principles. It uses NIST Manufacturing Extension Partnership supply-chain guidance as a primary public government foundation and durable operations/economics concepts.

Primary reference:
- NIST MEP Supply Chain Management: https://www.nist.gov/mep/supply-chain

NIST MEP specifically emphasizes supplier segmentation, supplier evaluation/selection, total cost of ownership, strategic supplier relationships, supplier metrics/scorecards, forecasting, demand and sales planning, operations planning, inventory management, lead-time reduction, bottleneck improvement, and quality systems.

## 1. Inventory is a risk buffer, not just a quantity

Inventory exists because timing, demand, supply, production, and information are imperfect.

For each item, distinguish:
- on-hand physical quantity;
- available/usable quantity;
- reserved/committed quantity;
- quarantined/held quantity;
- incoming/open-PO quantity;
- expected production quantity;
- sellable quantity;
- obsolete/expired/nonconforming quantity.

Never recommend buying against a quantity field without understanding which class it represents.

## 2. Demand rate and time window

Demand is a flow over time. A weekly velocity cannot be mixed directly with daily lead time without conversion.

When calculating demand:
- identify the time window;
- distinguish units sold from orders, revenue, or customers;
- account for stockouts that may suppress observed sales;
- account for one-time promotions or launch effects;
- separate returns/cancellations when relevant;
- compare recent and longer-run demand when seasonality or trend matters.

## 3. Days of supply and coverage

Coverage is an interpretation of inventory relative to demand.

A simple concept is usable inventory divided by average daily demand. The result is only as reliable as the demand window and inventory definition.

Do not treat days-of-supply as a universal target. Appropriate coverage depends on:
- lead time;
- lead-time variability;
- demand variability;
- order frequency;
- MOQ/case-pack constraints;
- product shelf life and age risk;
- supplier reliability;
- substitute availability;
- service-level expectations;
- cash constraints;
- future production or harvest.

## 4. Reorder point concepts

A reorder point represents expected demand during replenishment lead time plus a buffer for uncertainty when a buffer is justified.

Before using a reorder formula, verify:
- the demand rate unit;
- actual or policy lead time;
- variability data;
- on-order quantity;
- reserved commitments;
- MOQ/case pack;
- review cadence;
- inventory already expected from production or cultivation.

Do not invent a safety-stock formula or service-level target when policy or required statistical inputs are absent.

## 5. Safety stock

Safety stock protects against uncertainty, not known demand.

Potential uncertainty sources:
- demand variability;
- supplier lead-time variability;
- fill-rate variation;
- receiving delays;
- testing/QA delays;
- production yield variability;
- harvest timing variability;
- transfer delays.

Too little buffer increases stockout risk. Too much buffer ties up cash and increases aging/expiry risk.

## 6. Overstock and slow-moving inventory

Overstock is not simply a large on-hand number. It is excess inventory relative to realistic future demand and replenishment conditions.

When ranking overstock or slow movers, consider:
- days of supply;
- recent velocity trend;
- age and expiration risk;
- margin and cost basis;
- inbound orders;
- substitute products;
- planned promotions;
- customer/channel demand;
- product lifecycle status;
- legal or quality restrictions.

A high-potency or high-margin item can still be bad inventory if it cannot move before value deteriorates.

## 7. Stockouts and lost-demand interpretation

A zero on-hand period can distort forecasting because observed sales fall when the customer cannot buy the item.

When possible, distinguish:
- true low demand;
- demand constrained by stockout;
- substitution into another SKU;
- discontinued/unavailable status;
- temporary listing or merchandising issue.

Do not conclude that an item has weak demand solely because sales were low during prolonged unavailability.

## 8. Forecasting discipline

Forecasting should be reproducible and modest about uncertainty.

Useful starting methods include:
- recent average;
- weighted recent average;
- moving average;
- seasonal comparison;
- trend-adjusted demand;
- scenario ranges.

Before using a more complex model, establish whether it materially outperforms a simple baseline.

A forecast should include:
- horizon;
- method;
- data window;
- known future events;
- uncertainty/range when possible;
- exceptions such as stockouts or promotions.

Do not hide forecast assumptions behind an LLM narrative.

## 9. Assortment and category thinking

Buyer decisions are portfolio decisions.

Consider:
- category role;
- brand/cultivar/product-type coverage;
- price tiers;
- format/size coverage;
- sales velocity;
- gross-margin contribution;
- inventory productivity;
- customer demand;
- duplicate/substitute SKUs;
- shelf/menu space;
- vendor concentration;
- strategic house-brand goals;
- compliance and testing status.

Do not optimize assortment solely for unit velocity or potency.

## 10. Vendor evaluation

NIST MEP highlights supplier evaluation and supplier scorecards as important supply-chain practices.

Useful dimensions include:
- on-time delivery;
- fill rate;
- lead-time consistency;
- quality/COA issues;
- receiving discrepancies;
- invoice accuracy;
- response time;
- pricing consistency;
- MOQ/flexibility;
- order cancellation rate;
- defect/return rate;
- concentration risk.

A supplier score should not hide missing data. Show the underlying evidence.

## 11. Supplier segmentation

Not every vendor or item deserves the same management approach.

Segment by factors such as:
- spend;
- revenue dependency;
- supply criticality;
- substitution difficulty;
- lead time;
- quality risk;
- vendor concentration;
- legal/licensing dependency;
- operational disruption if unavailable.

A strategic sole-source material requires different risk management from an easily substituted commodity.

## 12. Total cost of ownership

Purchase price is only one component of economic cost.

Consider when measurable:
- unit purchase cost;
- freight/delivery cost;
- payment terms;
- receiving labor;
- quality failures;
- short shipments;
- returns;
- storage/aging exposure;
- minimum-order effects;
- cash tied up in inventory;
- production downtime caused by late supply.

Do not call one supplier cheaper if hidden costs reverse the result.

## 13. Purchase timing

The decision is not merely whether to buy, but when and how much.

Balance:
- demand timing;
- lead time;
- open POs;
- current usable inventory;
- future production/harvest;
- budget/cash;
- vendor order cadence;
- MOQ/case pack;
- aging risk;
- expected price changes only when supported by evidence.

## 14. Purchase-order lifecycle

Separate:
- planned recommendation;
- approved PO;
- sent PO;
- vendor confirmation;
- shipped/in transit;
- partial receipt;
- complete receipt;
- invoice reconciliation;
- closed/cancelled.

Do not count the same expected quantity twice across PO and receipt records.

## 15. Receiving as a control point

Receiving should verify what physically arrived against what was expected and what the source system says.

Potential exceptions:
- wrong item;
- wrong quantity;
- wrong lot/package;
- damaged product;
- missing COA/testing status;
- manifest mismatch;
- unit-of-measure mismatch;
- cost mismatch;
- unexpected substitution;
- partial delivery.

A receiving exception may affect Inventory, Purchasing, Audit, Compliance, and Finance simultaneously.

## 16. Inventory aging and FEFO/FIFO concepts

FIFO and FEFO are control concepts, not universal legal rules.

Where shelf life or expiration applies, inventory with the earliest relevant expiry may deserve priority if quality, allocation, and compliance permit it. Where harvest/production age affects commercial value, age should be considered separately from formal expiration.

Never invent an expiration date or assume a state rule from general warehouse practice.

## 17. Cannabis-specific purchasing constraints

Commercial cannabis adds constraints such as:
- licensed vendors and facilities;
- state-specific transfer rules;
- seed-to-sale package identity;
- testing/COA status;
- category and potency/serving limits;
- regulated samples/returns;
- cultivar and form-factor differences;
- production/cultivation internal supply;
- batch/lot variability.

Operational education cannot substitute for current jurisdiction-specific regulation.

## 18. Budget allocation

When purchasing budget is constrained, prioritize expected business value rather than distributing money evenly.

Potential factors:
- stockout risk;
- expected contribution margin;
- demand confidence;
- category importance;
- supplier risk;
- inventory age elsewhere in the assortment;
- cash conversion time;
- internal production alternative;
- existing open commitments.

Show tradeoffs and do not imply a budget is available unless authorized data says so.

## 19. Working capital

Inventory ties up cash before it becomes revenue.

Useful questions:
- How much cash is tied up in low-velocity stock?
- How much inventory is committed but not yet revenue-generating?
- Which purchases have the longest cash-conversion exposure?
- Which shortages would cause outsized lost-margin risk?

Do not confuse inventory value with cash on hand.

## 20. Recommended answer pattern

For a buying or purchasing decision:
1. State current usable inventory and demand evidence.
2. Include open/incoming supply and internal future supply when available.
3. Calculate coverage/reorder logic deterministically.
4. Identify uncertainty in demand and lead time.
5. Explain vendor, aging, budget, margin, and service-level tradeoffs.
6. Recommend order timing/quantity only within available policy and data.
7. Identify required Compliance, Inventory, Production, Cultivation, or Finance handoffs.
8. State assumptions, source boundary, and confidence.