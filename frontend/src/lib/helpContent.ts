export type HelpSection = {
  title: string;
  body?: string;
  steps?: string[];
  notes?: string[];
};

export type HelpArticle = {
  path: string;
  category: string;
  title: string;
  summary: string;
  navPath?: string;
  screenshot?: string;
  screenshotAlt?: string;
  thingsToKnow?: string[];
  sections: HelpSection[];
  related?: string[];
};

export type HelpCategory = {
  id: string;
  title: string;
  description: string;
  articles: string[];
};

const screen = (name: string) => `/help/screens/${name}-guide.webp`;

const article = (
  path: string,
  category: string,
  title: string,
  summary: string,
  navPath: string,
  screenshot: string,
  thingsToKnow: string[],
  sections: HelpSection[],
  related: string[] = [],
): HelpArticle => ({
  path, category, title, summary, navPath, screenshot: screen(screenshot),
  screenshotAlt: `Real DoobieLogic ${title} workspace captured in the DEV Sandbox`,
  thingsToKnow, sections, related,
});

export const helpArticles: HelpArticle[] = [
  article("/help/getting-started","getting-started","Getting started with DoobieLogic","Set your organization, facility, operation mode, and data source before beginning daily work.","Log in → confirm Access Context","home",[
    "DoobieLogic keeps organization, facility, and operation context visible while you work.",
    "The workspaces available to you depend on your role and the capabilities enabled for the selected facility.",
    "Screenshots in this Help Center are captured from the live DoobieLogic DEV Sandbox with demonstration data."
  ],[
    {title:"Sign in and confirm context",steps:["Sign in at the operator application.","Confirm the organization and facility in the top bar.","Choose Retail Ops, Cultivation Ops, or Production Ops when more than one mode is available.","Start from Home to review what needs attention."]},
    {title:"Choose the right data source",body:"Retail work can use published uploads or an enabled connected source. Production and cultivation work use durable DoobieLogic records plus configured traceability connections.",notes:["Do not change a facility or organization just to make a record appear. Confirm access with an administrator instead."]},
    {title:"Find a workspace",steps:["Use the left navigation to choose a work area.","Use Current Area to open the specific tool.","Use global search when you already know the product, package, plant, order, partner, or tool you need."]}
  ],["/help/home","/help/settings/location","/help/settings/integrations"]),

  article("/help/home","home","Operations Home","Use the home workspace to see immediate priorities, source readiness, and shortcuts into active work.","Home → Needs Attention / Today","home",[
    "Home changes with your role and current operation mode.",
    "Cards are shortcuts into the same durable workspaces, not separate copies of the data."
  ],[
    {title:"Review the day",steps:["Open Home.","Review Needs attention, Low stock, Open POs, and source readiness.","Open the highest-priority task card or the Operations Control Tower for cross-workspace review."]},
    {title:"Start a task",body:"Use the task cards to jump into inventory review, audits, traceability, wholesale, or Doobie Agent without rebuilding context."}
  ],["/help/home/work-queue","/help/home/control-towers","/help/doobie-agent"]),

  article("/help/home/work-queue","home","Work Queue","Review assigned and system-generated work in one place and move from exception to the source workspace.","Home → Work Queue","home",[
    "Work items link back to the workspace that owns the underlying record.",
    "Completion should happen in the owning workflow when the work item represents a regulated or operational change."
  ],[
    {title:"Review work",steps:["Open Home → Work Queue.","Filter or scan for overdue, high-priority, or assigned items.","Open an item to inspect its source context.","Complete the underlying action in the linked workspace."]},
    {title:"Use the queue as a handoff",body:"The queue is most useful when teams treat it as the shared list of unresolved work instead of keeping a second list in chat or spreadsheets."}
  ],["/help/home","/help/home/control-towers"]),

  article("/help/home/control-towers","home","Operations and Enterprise Control Towers","Use control towers for cross-workspace exceptions, readiness, risk, and multi-facility oversight.","Home → Operations Control Tower","home",[
    "Operations Control Tower is designed for active facility work.",
    "Enterprise Control Tower is restricted to authorized administrative roles."
  ],[
    {title:"Operations review",steps:["Open Operations Control Tower.","Review exceptions by domain.","Open the source workspace from the issue instead of correcting data from a summary card.","Return to the tower to confirm the exception clears."]},
    {title:"Enterprise review",body:"Authorized enterprise users can compare organization and facility conditions without changing the operating boundary of the underlying records."}
  ],["/help/home","/help/reports/executive"]),

  article("/help/buying","buying","Buying overview","Move from sales and stock context to recommendations, purchase orders, budget, delivery performance, and replenishment policies.","Buying → What Should I Order?","buying",[
    "Buying decisions use the active retail facility and selected data source.",
    "Recommendations are decision support. Review vendor, lead time, shelf capacity, commitments, and operational context before ordering."
  ],[
    {title:"Daily buying flow",steps:["Open What Should I Order? and review the current demand and stock picture.","Open Buying Recommendations for proposed actions.","Convert approved needs into Purchase Orders.","Check Buying Budget before committing spend.","Use Delivery Performance to review how prior deliveries affected the business."]},
    {title:"Tune planning",body:"Planning Settings controls replenishment assumptions such as target cover and related policy inputs. Change policies deliberately because they affect downstream recommendations."}
  ],["/help/buying/recommendations","/help/buying/purchase-orders","/help/buying/budget"]),

  article("/help/buying/recommendations","buying","Buying Recommendations","Review suggested purchase actions with the sales, inventory, cover, and vendor context behind them.","Buying → Buying Recommendations","buying",[
    "A recommendation is not a purchase order until an operator approves and creates one.",
    "Investigate unusual demand spikes, stale inventory, and pending receipts before accepting a recommendation."
  ],[
    {title:"Review recommendations",steps:["Open Buying Recommendations.","Sort or filter the list to the categories or products you own.","Compare recommended quantity with on-hand, available, recent sales, and days on hand.","Adjust the proposed buy when business context requires it.","Send approved lines into the purchase-order workflow."]},
    {title:"When a number looks wrong",notes:["Confirm the active data source is current.","Check that product naming and catalog mapping are correct.","Review pending POs and commitments before assuming available stock is overstated."]}
  ],["/help/buying","/help/buying/purchase-orders","/help/inventory/slow-movers"]),

  article("/help/buying/purchase-orders","buying","Purchase Orders","Build, review, and track purchase orders from recommendation through expected receipt.","Buying → Purchase Orders","buying",[
    "Keep vendor, facility, expected date, and line quantities accurate because receiving and delivery analysis depend on them."
  ],[
    {title:"Create a PO",steps:["Open Purchase Orders.","Create a new order or start from approved recommendations.","Choose the vendor and confirm the receiving facility.","Review product, quantity, cost, and expected delivery details.","Save the order and move it through your internal approval process."]},
    {title:"Maintain the order",steps:["Update expected dates when a vendor changes timing.","Use receiving history to compare expected and actual delivery.","Close or resolve lines that will not arrive so planning does not keep counting them as pending."]}
  ],["/help/buying/recommendations","/help/inventory/receiving","/help/buying/delivery-performance"]),

  article("/help/buying/budget","buying","Buying Budget","Compare planned purchasing against the budget available to the active retail operation.","Buying → Buying Budget","buying",[
    "Budget context is only useful when open purchase orders and expected receipts are maintained."
  ],[
    {title:"Review budget position",steps:["Open Buying Budget.","Review available spend, committed spend, and upcoming purchase needs.","Compare high-priority recommendations against the remaining budget.","Adjust order timing or assortment when required."]},
    {title:"Use budget with recommendations",body:"Treat budget as a constraint alongside stock health and demand. A product can deserve replenishment while still needing a smaller or later order."}
  ],["/help/buying/recommendations","/help/buying/purchase-orders"]),

  article("/help/buying/delivery-performance","buying","Delivery Performance","Review how vendor deliveries affected sales and operating performance after they landed.","Buying → Delivery Performance","buying",[
    "Delivery analysis is directional. Product availability, promotions, seasonality, and assortment changes can affect the same period."
  ],[
    {title:"Review a delivery",steps:["Open Delivery Performance.","Choose the delivery or comparison period.","Compare pre-delivery and post-delivery sales for delivered products.","Look for products that accelerated, stalled, or remained overstocked.","Carry the result into the next vendor and purchasing review."]}
  ],["/help/buying","/help/buying/planning-settings"]),

  article("/help/buying/planning-settings","buying","Planning Settings","Control replenishment assumptions used by buying tools.","Buying → Planning Settings","buying",[
    "Policy changes can alter recommendations across many products at once.",
    "Document intentional changes so buyers understand why recommendations moved."
  ],[
    {title:"Adjust a policy",steps:["Open Planning Settings.","Review the current targets and thresholds.","Change only the policy you intend to tune.","Save the setting.","Return to Buying Recommendations and validate the effect before making additional changes."]}
  ],["/help/buying/recommendations","/help/buying"]),

  article("/help/inventory","inventory","Inventory overview","Receive, inspect, move, audit, and understand physical inventory with commitments and traceability context close by.","Inventory → Inventory","inventory",[
    "Available inventory can differ from on-hand inventory because active commitments and reservations reduce what is truly available.",
    "Use Product 360 for product-level context and Package 360 for package or lot-level context."
  ],[
    {title:"Configure",steps:["Maintain clean products and categories in Catalog Administration.","Confirm rooms or locations are available for the facility.","Keep package and product naming aligned with connected traceability data."]},
    {title:"Receive",steps:["Open Receive inventory.","Review the source, vendor, quantities, package identifiers, and destination.","Complete receiving only after physical and source records agree."]},
    {title:"Manage",steps:["Use Transfers for movement between valid locations or facilities.","Use Product 360 and Package 360 for history and context.","Use Slow Movers to surface age and cover risk."]},
    {title:"Audit",steps:["Start an Inventory Audit for the intended scope.","Count or scan physical inventory.","Pause and resume when the floor workflow requires it.","Recount discrepancies, reconcile approved differences, and complete the audit."]}
  ],["/help/inventory/receiving","/help/inventory/transfers","/help/inventory/audits"]),

  article("/help/inventory/receiving","inventory","Receive inventory","Bring incoming inventory into DoobieLogic with the physical count, source record, and destination aligned.","Inventory → Inventory → Receive inventory","inventory",[
    "Receiving changes inventory availability, so confirm the facility and destination before submitting.",
    "For regulated inventory, validate the corresponding traceability transfer or package information before completion."
  ],[
    {title:"Receive an incoming shipment",steps:["Open Inventory and select Receive inventory.","Choose the incoming source or receiving workflow available to the facility.","Verify vendor or source, product, package identifiers, and expected quantity.","Enter the physically received quantity and destination.","Review discrepancies before completing the receipt.","Confirm the new inventory appears in Inventory or Package 360."]},
    {title:"If received quantity differs",notes:["Do not force the expected number to match the paperwork.","Record or resolve the discrepancy through the approved workflow.","Confirm any required state-system action separately in Traceability Actions."]}
  ],["/help/inventory","/help/inventory/package-360","/help/compliance/state-actions"]),

  article("/help/inventory/transfers","inventory","Inventory Transfers","Move inventory while preserving source, destination, quantity, and transfer history.","Inventory → Transfers","inventory",[
    "Use transfers for movement. Do not use quantity adjustments as a substitute for movement.",
    "Facility-to-facility movement may require a separate regulated transfer workflow."
  ],[
    {title:"Create a transfer",steps:["Open Inventory → Transfers.","Choose the source location and destination.","Select the package or inventory lines to move.","Enter quantities and review availability.","Submit the transfer.","Confirm the destination inventory and transfer history."]},
    {title:"Before a regulated transfer",body:"Confirm manifest, destination license, package status, and state-system requirements in the applicable Traceability workflow."}
  ],["/help/inventory","/help/compliance/traceability"]),

  article("/help/inventory/product-360","inventory","Product 360","Inspect product-level stock, sales, movement, and purchasing context without losing the product identity.","Inventory → Product 360","inventory",[
    "Product 360 rolls up product context. Use Package 360 when the package or lot identity matters."
  ],[
    {title:"Open a product",steps:["Open Product 360.","Search for the product or open it from another workspace.","Review current stock, related packages, sales or movement context, and any actions surfaced by the workspace.","Follow linked package or buying records when deeper detail is required."]}
  ],["/help/inventory/package-360","/help/buying/recommendations"]),

  article("/help/inventory/package-360","inventory","Package 360","Inspect one package or lot across inventory, status, source, movement, and downstream use.","Inventory → Package 360","inventory",[
    "Package-level review is the right place to investigate a specific regulated package, source lot, hold, or transformation history."
  ],[
    {title:"Inspect a package",steps:["Open Package 360.","Scan, search, or open the package from another workspace.","Confirm current quantity, status, room or location, and product identity.","Review movement, production, quality, and traceability context as available.","Open the owning workflow before making a regulated change."]}
  ],["/help/inventory/product-360","/help/compliance/traceability"]),

  article("/help/inventory/audits","inventory","Inventory Audits","Count physical inventory in a durable session that can pause, resume, recount, and reconcile.","Inventory → Inventory Audits","inventory",[
    "Define the count scope before scanning so the same physical stock is not counted twice.",
    "A paused audit retains progress. Use resume instead of creating a duplicate session."
  ],[
    {title:"Run an audit",steps:["Open Inventory Audits and create the intended count scope.","Scan a barcode or QR code, or search the item manually.","Enter the physical quantity.","Continue through the scope and pause when needed.","Resume the same audit session.","Review discrepancies and recount exceptions.","Complete the audit only after approved reconciliation."]},
    {title:"Scanner options",body:"Phone and tablet cameras, Bluetooth scanners, USB scanners, and typed codes can all be used where supported by the device and browser."}
  ],["/help/inventory","/help/compliance/traceability"]),

  article("/help/inventory/slow-movers","inventory","Slow Movers","Find inventory with aging or excess cover before it becomes a margin or storage problem.","Inventory → Slow Movers","inventory",[
    "Slow movement is context, not an automatic markdown decision."
  ],[
    {title:"Review aging risk",steps:["Open Slow Movers.","Sort by age, days on hand, value, or the available risk signals.","Review sales velocity and incoming inventory.","Choose an operational response such as purchasing pause, transfer review, promotion review, or assortment action.","Track the result in the owning workflow."]}
  ],["/help/inventory","/help/buying/recommendations"]),

  article("/help/inventory/catalog-admin","inventory","Catalog Administration","Maintain the retail product identities that buying, inventory, reporting, and mapping depend on.","Inventory → Catalog Administration","inventory",[
    "Clean product identity is foundational. Naming problems can appear later as duplicate inventory, weak reports, or failed mappings."
  ],[
    {title:"Maintain the catalog",steps:["Open Catalog Administration.","Find the product to review or add.","Confirm product name, category, vendor or brand, and other required identity fields.","Save the record.","Validate the result in Product 360 and connected workflows."]}
  ],["/help/inventory/product-360","/help/compliance/product-name-mapper"]),

  article("/help/cultivation","cultivation","Cultivation overview","Work rooms, plants, groups, harvest handoffs, lineage, cost, and regulatory context from the living grow workspace.","Cultivation → Grow Operations","cultivation",[
    "Cultivation uses the active cultivation-capable facility.",
    "Post-Harvest has its own operator workspace so drying, trim, cure, testing, and release do not crowd living plant work."
  ],[
    {title:"Work the grow",steps:["Open Grow Operations.","Review rooms, plant or group status, and items needing attention.","Open the specific plant or group before recording work.","Use the appropriate harvest or regulatory action instead of altering historical data manually."]},
    {title:"Hand off to post-harvest",steps:["Complete the harvest workflow with the required source context.","Open Post-Harvest.","Track drying, trim, cure, testing hold, release, and downstream material handoff."]}
  ],["/help/cultivation/post-harvest","/help/compliance/traceability"]),

  article("/help/cultivation/post-harvest","cultivation","Post-Harvest","Track harvested material through drying, trimming, cure, testing, hold, and release.","Cultivation → Post-Harvest","cultivation",[
    "Keep harvested material tied to its source harvest and facility context.",
    "Testing and release status should be explicit before downstream use."
  ],[
    {title:"Move a batch through post-harvest",steps:["Open Post-Harvest.","Select the batch or harvest handoff.","Record the current stage and measured weight events as work occurs.","Review loss or variance instead of overwriting earlier measurements.","Record testing or hold context.","Release material through the approved workflow when requirements are satisfied."]}
  ],["/help/cultivation","/help/production","/help/compliance/traceability"]),

  article("/help/production","production","Production overview","Plan work, schedule runs, manage materials, and move completed output into downstream inventory.","Production → Today / Production","production",[
    "Production work is facility-scoped and should use durable run records.",
    "Use Run 360 for the complete history and deep detail of one production run."
  ],[
    {title:"Plan and execute",steps:["Open Today / Production to review active and upcoming work.","Use Calendar to understand timing and capacity.","Open the production run before consuming material or recording output.","Record actual quantities, stage changes, losses, and completion as work occurs.","Review the finished output and downstream package or inventory handoff."]}
  ],["/help/production/calendar","/help/production/run-360","/help/extraction"]),

  article("/help/production/calendar","production","Production Calendar","Review scheduled production work across time and open the run that owns the work.","Production → Calendar","production",[
    "The calendar is a planning surface. Actual execution remains in the run."
  ],[
    {title:"Use the calendar",steps:["Open Production → Calendar.","Review scheduled runs and capacity by date.","Open a run when you need its materials, stages, or execution details.","Reschedule through the supported planning controls rather than duplicating the run."]}
  ],["/help/production","/help/production/run-360"]),

  article("/help/production/run-360","production","Production Run 360","Inspect and work one run from planned inputs through actual output, variance, quality, and completion.","Production → Production Run 360","production",[
    "Run 360 is the durable source of truth for one production run.",
    "Measured actuals should not be replaced with planned values when they differ."
  ],[
    {title:"Review a run",steps:["Open Production Run 360.","Select or search for the run.","Confirm status, planned inputs, actual inputs, current stage, outputs, loss, and QA context.","Record the next approved execution event.","Use linked package, inventory, or compliance views for downstream review."]}
  ],["/help/production","/help/extraction","/help/package-studio"]),

  article("/help/extraction","production","Extraction","Plan and track extraction work from source material through process stages, yield, output, QA, and downstream inventory.","Production → Extraction","extraction",[
    "Extraction runs retain source-to-output context so operators can review yield and variance without rebuilding the history from spreadsheets.",
    "Deep run detail remains available in Advanced Run 360."
  ],[
    {title:"Start a run",steps:["Open Production → Extraction.","Choose New run.","Select compatible, released source material.","Confirm planned input and the extraction process context.","Create the run and begin work only when the source and facility are correct."]},
    {title:"Work the current process",steps:["Open the active run.","Record stage progress and measured quantities as work occurs.","Record output and loss instead of forcing yield to a planned target.","Review QA or hold requirements before releasing downstream output."]},
    {title:"Review performance",steps:["Open Runs or Analytics.","Compare input, output, recovery, variance, and run history.","Open Advanced Run 360 when you need complete source, cost, QA, or traceability context."]}
  ],["/help/production/run-360","/help/package-studio","/help/compliance/traceability"]),

  article("/help/white-label-repack","production","White Label / Repack","Model and execute repack or private-label work while keeping bulk source, packaging, labor, yield, and customer context together.","Production → White Label / Repack","white-label-repack",[
    "Repack work should preserve the source package or lot relationship.",
    "Cost and margin models are planning tools until actual production quantities are recorded."
  ],[
    {title:"Plan a repack job",steps:["Open White Label / Repack.","Choose the source bulk material and customer or brand context.","Define finished package formats and target quantities.","Review packaging, labor, yield, pricing, and margin assumptions.","Save the job before execution."]},
    {title:"Execute and close",steps:["Record actual material used and finished output.","Capture loss or variance.","Create or link downstream packages through the approved workflow.","Complete the job after the final inventory and traceability handoff."]}
  ],["/help/package-studio","/help/production/run-360"]),

  article("/help/package-studio","production","Package Studio","Create and transform packages with source, output, quantity, and compliance context preserved.","Production → Package Studio","package-studio",[
    "Package creation is a material transformation. Source quantities and resulting output should reconcile.",
    "Use Traceability Actions when a corresponding state-system action is required."
  ],[
    {title:"Create output packages",steps:["Open Package Studio.","Choose the source material or package.","Define the output product, package format, quantity, and destination.","Review source availability and expected remaining quantity.","Create the transformation.","Confirm the new package in Package 360 and any required traceability queue."]}
  ],["/help/inventory/package-360","/help/compliance/state-actions"]),

  article("/help/wholesale","wholesale","Wholesale Ops overview","Move sellable inventory through customer demand, orders, fulfillment, storefront, accounting, and collection context.","Wholesale → Wholesale Ops","wholesale",[
    "Wholesale availability is based on sellable inventory after active reservations and commitments.",
    "The public storefront and internal order engine feed the same commercial workflow."
  ],[
    {title:"Order-to-cash flow",steps:["Review sellable inventory.","Create or approve an order.","Reserve or allocate inventory.","Pick and pack the order.","Complete required manifest and fulfillment readiness.","Move invoicing and receivable status through Accounting."]},
    {title:"Use the storefront",body:"Published storefront inventory creates customer-facing availability while incoming requests remain subject to operator review before becoming committed internal orders."}
  ],["/help/wholesale/orders","/help/wholesale/warehouse-pick-pack","/help/compliance/traceability"]),

  article("/help/wholesale/orders","wholesale","Orders & Fulfillment","Create, approve, allocate, and progress wholesale orders with customer and inventory context together.","Wholesale → Orders & Fulfillment","wholesale",[
    "An order request is not the same as an approved sales order.",
    "Allocation should use sellable inventory and respect existing commitments."
  ],[
    {title:"Work an order",steps:["Open Orders & Fulfillment.","Open an existing order or create one for the customer.","Review requested items, quantities, pricing, delivery timing, and inventory availability.","Approve or revise the order through the allowed workflow.","Allocate inventory.","Send ready work to pick and pack."]}
  ],["/help/wholesale","/help/wholesale/warehouse-pick-pack"]),

  article("/help/wholesale/warehouse-pick-pack","wholesale","Warehouse Pick / Pack","Turn an approved order into physically verified fulfillment without losing package identity.","Wholesale → Warehouse Pick / Pack","wholesale",[
    "Pick against the approved order and allocated inventory.",
    "Resolve package or quantity discrepancies before marking fulfillment complete."
  ],[
    {title:"Pick and pack",steps:["Open Warehouse Pick / Pack.","Choose the order ready for fulfillment.","Scan or select the allocated packages.","Confirm picked quantity against the order.","Resolve substitutions or shortages through the approved order workflow.","Pack and complete the warehouse step.","Confirm manifest or delivery readiness when required."]}
  ],["/help/wholesale/orders","/help/compliance/state-actions"]),

  article("/help/compliance","compliance","Compliance overview","Keep traceability, state actions, labels, regulatory Q&A, naming, and Massachusetts flower equivalency close to operational work.","Compliance → Compliance Q&A or Traceability","compliance",[
    "Compliance tools support the operator and compliance team. They do not replace current regulations, state-system requirements, or legal review.",
    "Regulated mutations remain governed actions rather than automatic AI changes."
  ],[
    {title:"Choose the right tool",steps:["Use Compliance Q&A for reviewed source-backed answers.","Use Traceability for synchronized regulatory context and reconciliation.","Use State Actions for pending, rejected, or approved external actions.","Use Label Studio for compliant label creation and reprinting history.","Use Product Name Mapper for catalog alignment.","Use MA Flower Equivalency for Massachusetts adult-use equivalency calculations."]}
  ],["/help/compliance/traceability","/help/compliance/state-actions","/help/compliance/label-studio"]),

  article("/help/compliance/qa","compliance","Compliance Q&A","Ask operational compliance questions against reviewed sources and inspect the source context behind the answer.","Compliance → Compliance Q&A","compliance",[
    "Confirm jurisdiction, adult-use or medical scope, source, and review status before relying on an answer.",
    "If an exact rule cannot be verified, DoobieLogic should show the limitation instead of inventing certainty."
  ],[
    {title:"Ask a compliance question",steps:["Open Compliance Q&A.","Write a specific operational question and include the relevant jurisdiction or program when needed.","Review the answer and source references.","Confirm the cited source is current for the situation.","Escalate ambiguous or high-risk interpretations to your compliance or legal team."]}
  ],["/help/compliance","/help/doobie-agent"]),

  article("/help/compliance/traceability","compliance","Traceability","Review package, plant, harvest, transfer, and other regulated context alongside DoobieLogic operations.","Compliance → Traceability","compliance",[
    "DoobieLogic treats external traceability systems as regulated adapters, not the only operational database.",
    "Reconciliation should preserve what DoobieLogic observed, what the provider returned, and what action was approved."
  ],[
    {title:"Review traceability",steps:["Open Traceability.","Confirm the facility and integration status.","Review the relevant package, plant, harvest, transfer, or reconciliation context.","Open any pending exception.","Use State Actions for an approved provider mutation when required.","Read back or reconcile the result after submission."]}
  ],["/help/compliance/state-actions","/help/settings/integrations"]),

  article("/help/compliance/state-actions","compliance","State Actions","Review and execute governed external traceability actions with explicit operator approval.","Compliance → State Actions","compliance",[
    "Pending does not mean submitted.",
    "Rejected actions should retain the provider error and the requested payload context for investigation."
  ],[
    {title:"Work the queue",steps:["Open State Actions.","Filter for pending, rejected, or reconciliation-required items.","Open the action and verify facility, entity, requested change, and evidence.","Approve and submit only when the action is correct and authorized.","Review the provider response.","Confirm the resulting state through reconciliation or readback."]}
  ],["/help/compliance/traceability","/help/settings/integrations"]),

  article("/help/compliance/label-studio","compliance","Label Studio","Create, save, customize, print, and reprint labels while retaining label history.","Compliance → Label Studio","compliance",[
    "Use the saved label history when an identical compliant label needs to be reprinted.",
    "Confirm required regulatory fields for the product and jurisdiction before printing."
  ],[
    {title:"Create a label",steps:["Open Label Studio.","Choose the product, package, or source context.","Select the intended label size.","Place and format the supported fields.","Preview the label.","Save the label record and print."]},
    {title:"Reprint a historical label",steps:["Open the saved label history.","Find the original label by product, package, date, or available identifiers.","Review the stored content before reprinting.","Print from the historical record instead of rebuilding it from memory."]}
  ],["/help/compliance","/help/inventory/package-360"]),

  article("/help/compliance/product-name-mapper","compliance","Product Name Mapper","Align incoming Metrc or manifest item names with the facility's canonical product catalog.","Compliance → Product Name Mapper","compliance",[
    "The facility catalog is the naming standard.",
    "Review newly generated mappings before publishing them into downstream operations."
  ],[
    {title:"Map product names",steps:["Open Product Name Mapper.","Load or choose the facility catalog that represents the naming standard.","Load the incoming source items.","Review exact matches and proposed mappings.","Correct exceptions.","Export or publish the corrected names through the supported workflow."]}
  ],["/help/inventory/catalog-admin","/help/compliance/traceability"]),

  article("/help/compliance/ma-flower-equivalency","compliance","MA Flower Equivalency","Calculate Massachusetts adult-use flower-equivalency values for supported cannabis product forms.","Compliance → MA Flower Equivalency","compliance",[
    "Verify current Massachusetts requirements with your compliance team before operational use.",
    "Input accuracy matters. Product form, quantity, potency, and package configuration can affect the calculation."
  ],[
    {title:"Calculate equivalency",steps:["Open MA Flower Equivalency.","Choose the applicable product form.","Enter the required package and potency values.","Review the calculated equivalency.","Confirm the result against your current compliance procedure before using it operationally."]}
  ],["/help/compliance","/help/compliance/qa"]),


  article("/help/production/inventory","production","Production Inventory","Review materials and packages available to production, including commitments, rooms, holds, and usable quantity.","Production Ops → Inventory → Materials","production",[
    "Production inventory is the same durable inventory system used by downstream runs and Package Studio.",
    "Available quantity accounts for active reservations and commitments."
  ],[
    {title:"Review materials",steps:["Switch to Production Ops.","Open Inventory → Materials.","Filter by room, material type, status, or product.","Review on-hand, available, reserved, and hold context before assigning material to a run."]},
    {title:"Take action",body:"Use package-level actions for moves, holds, releases, adjustments, transfers, labels, audits, and Package Studio when your permissions allow them."}
  ],["/help/production/inventory/transfers","/help/production/products","/help/production/run-360"]),

  article("/help/production/inventory/transfers","production","Production Inventory Transfers","Move production packages between licensed facilities while preserving package identity, quantities, manifest context, and receiving history.","Production Ops → Inventory → Transfers","production",[
    "Transfers operate on physical packages, not product summary rows.",
    "Held, quarantined, failed, or unavailable packages must be resolved before transfer."
  ],[
    {title:"Start a transfer",steps:["Open Production Ops → Inventory → Transfers.","Select the source packages.","Choose the destination facility and review quantities.","Enter required manifest or transport context.","Review eligibility before posting or dispatching the transfer."]},
    {title:"Receive and reconcile",steps:["Open the transfer at the destination.","Verify package identity and quantity against the physical shipment.","Receive through the supported workflow.","Resolve discrepancies before closing the transfer."]}
  ],["/help/production/inventory","/help/inventory/transfers","/help/compliance/traceability"]),

  article("/help/production/package-360","production","Production Package 360","Inspect a production package across balance, location, reservations, source history, status, and downstream use.","Production Ops → Inventory → Package 360","production",[
    "Open Package 360 when the question is about one physical package or lot.",
    "Use Product 360 or Product Master when the question is about a reusable product identity."
  ],[
    {title:"Open a package",steps:["Open Production Ops → Inventory → Package 360.","Search or scan the package identifier.","Review quantity, location, status, commitments, and source context.","Follow lineage or related run links when investigating where the material came from or went."]}
  ],["/help/production/inventory","/help/package-studio","/help/inventory/package-360"]),

  article("/help/production/products","production","Production Products","Maintain the product master used by production planning, package outputs, BOM context, reporting, and downstream inventory.","Production Ops → Inventory → Products","production",[
    "Product records describe what the material is. Package records describe a specific physical quantity of it.",
    "Naming and units should stay consistent because planning and package workflows reuse these identities."
  ],[
    {title:"Review the product master",steps:["Open Production Ops → Inventory → Products.","Find the product by name or SKU.","Review type, unit, active status, and other production fields.","Update only supported master-data fields and verify downstream workflows after the change."]}
  ],["/help/production/inventory","/help/package-studio","/help/production/run-360"]),

  article("/help/production/inventory-audits","production","Production Inventory Audits","Count production materials and packages in resumable audit sessions without losing the expected-versus-counted trail.","Production Ops → Inventory → Inventory Audits","production",[
    "Audit sessions can pause, resume, recount, and reconcile.",
    "Define the facility and count scope before scanning so the expected population is clear."
  ],[
    {title:"Run the count",steps:["Open Production Ops → Inventory → Inventory Audits.","Start or resume the audit for the intended scope.","Scan or select each package and record the physical count.","Pause safely when the floor work stops.","Recount discrepancies, review evidence, and complete only after reconciliation."]}
  ],["/help/inventory/audits","/help/production/inventory","/help/compliance/traceability"]),

  article("/help/wholesale/inventory","wholesale","Wholesale Inventory","Review released, sellable lots and understand why inventory is available, reserved, or blocked from the commercial catalog.","Wholesale → Inventory","wholesale",[
    "Wholesale eligibility requires released inventory, passed COA context, and positive uncommitted quantity.",
    "Blocked lots stay visible for investigation without silently becoming sellable."
  ],[
    {title:"Review sellable inventory",steps:["Open Wholesale → Inventory.","Review available and reserved quantity by lot.","Inspect COA/release state and blocked reasons.","Open the source package or production context when a lot needs investigation."]}
  ],["/help/wholesale","/help/wholesale/orders","/help/compliance/traceability"]),

  article("/help/wholesale/customers","wholesale","Wholesale Customers","Maintain retailer and partner account context, licensing, contacts, payment terms, and the relationship behind commercial orders.","Wholesale → Customers","wholesale",[
    "Customer records should represent the licensed account, not just an individual contact.",
    "Keep license and payment context current before relying on it for order-to-cash decisions."
  ],[
    {title:"Work a customer account",steps:["Open Wholesale → Customers.","Search for the account.","Review license, contacts, terms, activity, and linked commercial history.","Update supported customer fields or open related opportunities/orders from the account context."]}
  ],["/help/wholesale/pipeline","/help/wholesale/orders","/help/wholesale/accounting"]),

  article("/help/wholesale/pipeline","wholesale","Wholesale Pipeline","Track opportunities and commercial follow-up before an opportunity becomes a confirmed sales order.","Wholesale → Pipeline","wholesale",[
    "Pipeline work belongs before order confirmation; confirmed demand moves into the canonical sales-order workflow.",
    "Keep expected value, stage, owner, and next action current so the pipeline remains useful."
  ],[
    {title:"Review the pipeline",steps:["Open Wholesale → Pipeline.","Review opportunities by stage and next action.","Open the customer context before changing an opportunity.","Advance or close the opportunity based on actual commercial progress.","Convert approved demand through the supported quote/order workflow rather than duplicating it manually."]}
  ],["/help/wholesale/customers","/help/wholesale/orders"]),

  article("/help/wholesale/accounting","wholesale","Wholesale Accounting","Review invoices, open balances, A/R aging, payment status, and accounting synchronization from the wholesale workflow.","Wholesale → Accounting","wholesale",[
    "Accounting follows the canonical sales order and fulfillment records.",
    "A saved accounting connection is not treated as healthy until provider validation succeeds."
  ],[
    {title:"Review finance handoffs",steps:["Open Wholesale → Accounting.","Review invoices and open balances.","Prioritize overdue or exception accounts.","Record or synchronize payment information through the supported workflow.","Return to the order-to-cash view to verify the exception clears."]}
  ],["/help/wholesale/orders","/help/wholesale/customers","/help/settings/integrations"]),

  article("/help/wholesale/storefront","wholesale","Wholesale Storefront","Publish a branded wholesale catalog, control eligible listings, and review customer order requests before they become commercial sales orders.","Wholesale → Storefront","wholesale",[
    "Only eligible inventory should be published to the storefront.",
    "Customer submissions require review before they become canonical sales orders or reserve inventory."
  ],[
    {title:"Manage the catalog",steps:["Open Wholesale → Storefront.","Review storefront identity and publication status.","Choose eligible products or sales units for the catalog.","Preview the customer-facing storefront before publishing changes."]},
    {title:"Review incoming requests",steps:["Open pending storefront orders.","Verify customer and license context.","Review requested items and availability.","Approve valid requests into the commercial order workflow or resolve the request without creating duplicate demand."]}
  ],["/help/wholesale","/help/wholesale/orders","/help/wholesale/inventory"]),

  article("/help/reports/sales-category-trends","reports","Sales & Category Trends","Review retail sales mix, velocity, category performance, and changing demand from the active data source.","Reports → Sales & Category Trends","buying",[
    "Trend views depend on the freshness and completeness of the active retail source."
  ],[
    {title:"Review trends",steps:["Open Sales & Category Trends.","Choose the date or comparison context.","Review category mix, package-size mix, velocity, and fast or slow movement.","Open the related buying or inventory workspace when a trend requires action."]}
  ],["/help/buying","/help/inventory/slow-movers","/help/reports/executive"]),

  article("/help/reports/executive","reports","Executive Reports","Create leadership-ready views of retail or production performance without mixing incompatible operating contexts.","Reports → Executive Reports","production",[
    "Retail and Production report packs are intentionally separated.",
    "Verify the facility and reporting period before sharing a report."
  ],[
    {title:"Generate a report",steps:["Open Executive Reports.","Choose the appropriate Retail or Production report context.","Set the period and available filters.","Review the on-screen metrics and action tables.","Generate or export the report only after confirming the scope."]}
  ],["/help/reports/sales-category-trends","/help/home/control-towers"]),

  article("/help/settings/location","settings","Location Settings","Maintain the location and facility-specific context used by operational workflows.","Settings & Administration → Location","home",[
    "Facility context is an access and operating boundary, not just a label."
  ],[
    {title:"Review location context",steps:["Open Settings & Administration → Location.","Confirm facility identity and the available configuration.","Update only fields your role is authorized to manage.","Save changes and re-open the affected workspace to verify the result."]}
  ],["/help/getting-started","/help/settings/admin"]),

  article("/help/settings/imports-data","settings","Imports & Data","Use the Data Import Center to upload, inspect, review, and publish operational datasets.","Settings & Administration → Imports & Data","home",[
    "Uploading a file does not make it operational until it is reviewed and published.",
    "Published data is scoped to the selected organization and facility."
  ],[
    {title:"Publish a dataset",steps:["Open Imports & Data.","Choose the dataset type.","Upload CSV, XLSX, or XLS when supported.","Review detected rows, columns, required-field mapping, and preview.","Confirm the source.","Publish the version.","Open the downstream workspace and validate the result."]},
    {title:"Use history",body:"The Data Import Center retains version context so an operator can see which source is active and inspect prior published versions according to the platform retention rules."}
  ],["/help/getting-started","/help/buying","/help/inventory"]),

  article("/help/settings/admin","settings","Admin Tools","Manage users, organizations, facilities, permissions, security readiness, and platform-level configuration through the supported admin workflows.","Settings & Administration → Admin Tools","home",[
    "Create users through DoobieLogic so Supabase Auth, app users, organization/facility access, metadata, password policy, and audit history stay aligned.",
    "Do not create application users by manually inserting records into Supabase Auth tables."
  ],[
    {title:"Create a user",steps:["Open Admin Tools → User Management.","Choose Create User.","Enter username, display name, optional email, and role.","Choose the organization and facility access for non-DEV accounts.","Set a temporary password and password-change requirement.","Create the user.","Verify the new account appears in User Management."]},
    {title:"Manage access",steps:["Open Manage Existing.","Choose the account.","Review role, organization, facility assignments, active status, and password policy.","Save the supported account changes.","Use facility-specific permission overrides only for documented exceptions."]}
  ],["/help/settings/location","/help/settings/integrations","/help/getting-started"]),

  article("/help/settings/integrations","settings","Integrations","Configure facility operating mode, Metrc, accounting, and other supported connections with validation and explicit scope.","Settings & Administration → AI, Traceability & Accounting Integrations","integrations",[
    "A saved credential is not treated as live until provider-specific validation succeeds.",
    "Never place server secret or service-role credentials in a browser-facing field.",
    "Metrc can be optional in supported sandbox or alpha operating modes."
  ],[
    {title:"Choose operating mode",steps:["Open Integrations.","Confirm the current facility.","Choose the supported operating mode for that facility.","Review the effect before saving."]},
    {title:"Connect a provider",steps:["Open the provider section.","Enter the provider-specific credentials or configuration.","Save the connection.","Run validation.","Review the status and any returned error.","Open the downstream workspace only after validation succeeds."]},
    {title:"Troubleshoot",notes:["Confirm you selected the correct facility and environment.","Check provider permissions and license scope.","Use the displayed validation error rather than regenerating credentials blindly.","Do not expose keys in screenshots, chat, or public documentation."]}
  ],["/help/compliance/traceability","/help/settings/admin"]),

  article("/help/doobie-agent","intelligence","Doobie Agent","Ask contextual operational questions, review evidence, and move into the workspace that owns the next action.","Doobie Agent → available from the app shell","home",[
    "Doobie Agent is an operational intelligence layer, not an autonomous administrator.",
    "Read-oriented analysis and recommendations remain separate from governed mutations."
  ],[
    {title:"Ask a useful question",steps:["Open Doobie Agent from the sidebar.","Ask a specific operational question such as what needs attention, what inventory is aging, or which runs need review.","Read the evidence and confidence or limitations provided.","Open the recommended workspace to inspect the source record.","Approve or perform any regulated action through the normal workflow."]}
  ],["/help/home","/help/compliance/qa","/help/settings/integrations"]),
];

export const helpCategories: HelpCategory[] = [
  {id:"getting-started",title:"Getting Started",description:"Sign in, choose the right operating context, and learn how DoobieLogic is organized.",articles:["/help/getting-started"]},
  {id:"home",title:"Home & Operations",description:"Daily priorities, shared work, and cross-workspace control towers.",articles:["/help/home","/help/home/work-queue","/help/home/control-towers"]},
  {id:"buying",title:"Buying",description:"Recommendations, purchase orders, budget, delivery performance, and planning policy.",articles:["/help/buying","/help/buying/recommendations","/help/buying/purchase-orders","/help/buying/budget","/help/buying/delivery-performance","/help/buying/planning-settings"]},
  {id:"inventory",title:"Inventory",description:"Receiving, transfers, Product 360, Package 360, audits, aging, and catalog administration.",articles:["/help/inventory","/help/inventory/receiving","/help/inventory/transfers","/help/inventory/product-360","/help/inventory/package-360","/help/inventory/audits","/help/inventory/slow-movers","/help/inventory/catalog-admin"]},
  {id:"cultivation",title:"Cultivation",description:"Grow operations and the harvest-to-post-harvest handoff.",articles:["/help/cultivation","/help/cultivation/post-harvest"]},
  {id:"production",title:"Production & Extraction",description:"Production inventory, planning, Run 360, extraction, repack, and package creation.",articles:["/help/production","/help/production/inventory","/help/production/inventory/transfers","/help/production/package-360","/help/production/products","/help/production/inventory-audits","/help/production/calendar","/help/production/run-360","/help/extraction","/help/white-label-repack","/help/package-studio"]},
  {id:"wholesale",title:"Wholesale & Warehouse",description:"Sellable inventory, customers, pipeline, orders, fulfillment, accounting, storefront operations, and pick/pack.",articles:["/help/wholesale","/help/wholesale/inventory","/help/wholesale/orders","/help/wholesale/warehouse-pick-pack","/help/wholesale/customers","/help/wholesale/pipeline","/help/wholesale/accounting","/help/wholesale/storefront"]},
  {id:"compliance",title:"Compliance",description:"Traceability, governed state actions, labels, Q&A, naming, and Massachusetts equivalency.",articles:["/help/compliance","/help/compliance/qa","/help/compliance/traceability","/help/compliance/state-actions","/help/compliance/label-studio","/help/compliance/product-name-mapper","/help/compliance/ma-flower-equivalency"]},
  {id:"reports",title:"Reports",description:"Sales and category trends plus executive reporting.",articles:["/help/reports/sales-category-trends","/help/reports/executive"]},
  {id:"settings",title:"Settings & Integrations",description:"Locations, data imports, users, permissions, Metrc, accounting, and provider connections.",articles:["/help/settings/location","/help/settings/imports-data","/help/settings/admin","/help/settings/integrations"]},
  {id:"intelligence",title:"Doobie Agent",description:"Contextual operational intelligence and evidence-backed next-step guidance.",articles:["/help/doobie-agent"]},
];

export const helpArticleByPath = new Map(helpArticles.map(item => [item.path, item]));
export const helpCategoryById = new Map(helpCategories.map(item => [item.id, item]));

export function helpSearch(query: string): HelpArticle[] {
  const term = query.trim().toLocaleLowerCase();
  if (!term) return helpArticles;
  return helpArticles.filter(item => [
    item.title,
    item.summary,
    item.category,
    item.navPath ?? "",
    ...item.thingsToKnow ?? [],
    ...item.sections.flatMap(section => [section.title, section.body ?? "", ...(section.steps ?? []), ...(section.notes ?? [])]),
  ].join(" ").toLocaleLowerCase().includes(term));
}
