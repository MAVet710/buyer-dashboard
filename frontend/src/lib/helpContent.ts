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
const screenNameForPath = (path: string, fallback: string) => {
  const slug = path.replace(/^\/help\/?/, "").replaceAll("/", "-").trim();
  return slug || fallback;
};

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
  path, category, title, summary, navPath,
  screenshot: screen(screenNameForPath(path, screenshot)),
  screenshotAlt: `Real DoobieLogic ${title} workspace captured in the DEV Sandbox`,
  thingsToKnow, sections, related,
});

export const helpArticles: HelpArticle[] = [
  article("/help/getting-started","getting-started","Getting started with DoobieLogic","Get your bearings, make sure you're in the right facility, and set up the view you actually need.","Log in → confirm Access Context","home",[
    "DoobieLogic keeps organization, facility, and operation context visible while you work.",
    "The workspaces available to you depend on your role and the capabilities enabled for the selected facility.",
    "Screenshots in this Help Center are captured from the live DoobieLogic DEV Sandbox with demonstration data."
  ],[
    {title:"Sign in and confirm context",steps:["Sign in at the operator application.","Make sure you're in the right organization and facility in the top bar.","Choose Retail Ops, Cultivation Ops, or Production Ops when more than one mode is available.","Start from Home to review what needs attention."]},
    {title:"Choose the right data source",body:"Retail work can use published uploads or an enabled connected source. Production and cultivation work use saved DoobieLogic records plus whatever traceability connection is configured.",notes:["Do not change a facility or organization just to make a record appear. Confirm access with an administrator instead."]},
    {title:"Find a workspace",steps:["Use the left navigation to choose a work area.","Use Current Area to open the specific tool.","Use global search when you already know the product, package, plant, order, partner, or tool you need."]}
  ],["/help/home","/help/settings/location","/help/settings/integrations"]),

  article("/help/home","home","Operations Home","This is your starting point. See what needs attention and jump straight into the work.","Home → Needs Attention / Today","home",[
    "Home changes with your role and current operation mode.",
    "The cards don't create another copy of anything. They just take you to the same underlying workspace."
  ],[
    {title:"See what needs attention",steps:["Open Home.","Check Needs attention, Low stock, Open POs, and source readiness.","Open the highest-priority task card or the Operations Control Tower for cross-workspace review."]},
    {title:"Start a task",body:"Use the task cards to jump into inventory review, audits, traceability, wholesale, or Doobie Agent without rebuilding context."}
  ],["/help/home/control-towers","/help/doobie-agent"]),


  article("/help/home/control-towers","home","Operations and Enterprise Control Towers","Get the bigger picture when a problem stretches across more than one workspace or facility.","Home → Operations Control Tower","home",[
    "Operations Control Tower is designed for active facility work.",
    "Enterprise Control Tower is restricted to authorized administrative roles."
  ],[
    {title:"Work the problem",steps:["Open Operations Control Tower.","Check exceptions by domain.","Open the source workspace from the issue instead of correcting data from a summary card.","Return to the tower to confirm the exception clears."]},
    {title:"Look across facilities",body:"Authorized enterprise users can compare facilities without moving or changing where the underlying records actually live."}
  ],["/help/home","/help/reports/executive"]),

  article("/help/buying","buying","Buying overview","Everything you need to decide what to buy, what to hold off on, and what's already on the way.","Buying → What Should I Order?","buying",[
    "Buying decisions use the active retail facility and selected data source.",
    "Recommendations are a starting point, not an order. Check vendor timing, shelf space, what's already committed, and anything else you know before you buy."
  ],[
    {title:"Daily buying flow",steps:["Open What Should I Order? and review the current demand and stock picture.","Open Buying Recommendations for proposed actions.","Convert approved needs into Purchase Orders.","Check Buying Budget before committing spend.","Use Delivery Performance to review how prior deliveries affected the business."]},
    {title:"Tune planning",body:"Planning Settings controls replenishment assumptions such as target cover and related policy inputs. Change policies deliberately because they affect downstream recommendations."}
  ],["/help/buying/recommendations","/help/buying/purchase-orders","/help/buying/budget"]),

  article("/help/buying/recommendations","buying","Buying Recommendations","See what DoobieLogic thinks you should buy, then check the numbers before turning anything into a PO.","Buying → Buying Recommendations","buying",[
    "A recommendation is not a purchase order until an operator approves and creates one.",
    "Investigate unusual demand spikes, stale inventory, and pending receipts before accepting a recommendation."
  ],[
    {title:"Check the recommendation",steps:["Open Buying Recommendations.","Sort or filter the list to the categories or products you own.","Compare recommended quantity with on-hand, available, recent sales, and days on hand.","Adjust the proposed buy when business context requires it.","Send approved lines into the purchase-order workflow."]},
    {title:"If a number looks off",notes:["Make sure the active data source is current.","Check that product naming and catalog mapping are correct.","Check pending POs and commitments before assuming available stock is overstated."]}
  ],["/help/buying","/help/buying/purchase-orders","/help/inventory/slow-movers"]),

  article("/help/buying/purchase-orders","buying","Purchase Orders","Build the order, keep tabs on what's coming in, and clean up anything that changes along the way.","Buying → Purchase Orders","buying",[
    "Keep vendor, facility, expected date, and line quantities accurate because receiving and delivery analysis depend on them."
  ],[
    {title:"Create a PO",steps:["Open Purchase Orders.","Create a new order or start from approved recommendations.","Choose the vendor and confirm the receiving facility.","Check product, quantity, cost, and expected delivery details.","Save the order and move it through your internal approval process."]},
    {title:"Keep the order current",steps:["Update expected dates when a vendor changes timing.","Use receiving history to compare expected and actual delivery.","Close or resolve lines that will not arrive so planning does not keep counting them as pending."]}
  ],["/help/buying/recommendations","/help/inventory/receiving","/help/buying/delivery-performance"]),

  article("/help/buying/budget","buying","Buying Budget","See how much room you have to buy before you start stacking POs.","Buying → Buying Budget","buying",[
    "Budget context is only useful when open purchase orders and expected receipts are maintained."
  ],[
    {title:"See where the budget stands",steps:["Open Buying Budget.","Check available spend, committed spend, and upcoming purchase needs.","Compare high-priority recommendations against the remaining budget.","Adjust order timing or assortment when required."]},
    {title:"Use budget with recommendations",body:"Treat budget as a constraint alongside stock health and demand. A product can deserve replenishment while still needing a smaller or later order."}
  ],["/help/buying/recommendations","/help/buying/purchase-orders"]),

  article("/help/buying/delivery-performance","buying","Delivery Performance","See what happened after inventory landed so you know what worked and what didn't.","Buying → Delivery Performance","buying",[
    "Delivery analysis is directional. Product availability, promotions, seasonality, and assortment changes can affect the same period."
  ],[
    {title:"See what the delivery actually did",steps:["Open Delivery Performance.","Choose the delivery or comparison period.","Compare pre-delivery and post-delivery sales for delivered products.","Look for products that accelerated, stalled, or remained overstocked.","Carry the result into the next vendor and purchasing review."]}
  ],["/help/buying","/help/buying/planning-settings"]),

  article("/help/buying/planning-settings","buying","Planning Settings","Tune the rules behind your buying recommendations without guessing.","Buying → Planning Settings","buying",[
    "Policy changes can alter recommendations across many products at once.",
    "Document intentional changes so buyers understand why recommendations moved."
  ],[
    {title:"Adjust a policy",steps:["Open Planning Settings.","Look at the targets and thresholds you're using now.","Change only the policy you intend to tune.","Save the setting.","Go back to Buying Recommendations and make sure the change did what you expected before touching anything else."]}
  ],["/help/buying/recommendations","/help/buying"]),

  article("/help/inventory","inventory","Inventory overview","See what you have, where it is, what's tied up, and what needs attention.","Inventory → Inventory","inventory",[
    "On hand isn't always the same as available. Reservations and commitments can tie up inventory that's still physically sitting there.",
    "Use Product 360 when you're asking about the product as a whole. Use Package 360 when you care about one specific lot or package."
  ],[
    {title:"Configure",steps:["Keep clean products and categories in Catalog Administration.","Make sure rooms or locations are available for the facility.","Keep package and product naming aligned with connected traceability data."]},
    {title:"Receive",steps:["Open Receive inventory.","Check the source, vendor, quantities, package identifiers, and destination.","Complete receiving only after physical and source records agree."]},
    {title:"Manage",steps:["Use Transfers for movement between valid locations or facilities.","Use Product 360 and Package 360 for history and context.","Use Slow Movers to surface age and cover risk."]},
    {title:"Audit",steps:["Start an Inventory Audit for the intended scope.","Count or scan physical inventory.","Pause and resume when the floor workflow requires it.","Recount discrepancies, reconcile approved differences, and complete the audit."]}
  ],["/help/inventory/receiving","/help/inventory/transfers","/help/inventory/audits"]),

  article("/help/inventory/receiving","inventory","Receive inventory","Receive what actually showed up, not what the paperwork hoped would show up.","Inventory → Inventory → Receive inventory","inventory",[
    "Receiving changes your inventory right away, so make sure you're in the right facility and sending it to the right location first.",
    "For regulated inventory, double-check the traceability transfer or package details before you finish."
  ],[
    {title:"Receive an incoming shipment",steps:["Open Inventory and select Receive inventory.","Choose the incoming source or receiving workflow available to the facility.","Double-check vendor or source, product, package identifiers, and expected quantity.","Enter the physically received quantity and destination.","Check discrepancies before completing the receipt.","Make sure the new inventory appears in Inventory or Package 360."]},
    {title:"If the shipment doesn't match",notes:["Don't make the count fit the paperwork. Record what actually showed up.","Record or resolve the discrepancy through the approved workflow.","Check Traceability Actions separately if the discrepancy also needs a state-system update."]}
  ],["/help/inventory","/help/inventory/package-360","/help/compliance/state-actions"]),

  article("/help/inventory/transfers","inventory","Inventory Transfers","Move inventory without losing track of where it came from or where it went.","Inventory → Transfers","inventory",[
    "If inventory moved, use a transfer. Don't fake a move with a quantity adjustment.",
    "Facility-to-facility movement may require a separate regulated transfer workflow."
  ],[
    {title:"Create a transfer",steps:["Open Inventory → Transfers.","Choose the source location and destination.","Select the package or inventory lines to move.","Enter quantities and review availability.","Submit the transfer.","Check the destination inventory and transfer history after the move."]},
    {title:"Before a regulated transfer",body:"Before it leaves, double-check the manifest, destination license, package status, and any state-system requirements in Traceability."}
  ],["/help/inventory","/help/compliance/traceability"]),

  article("/help/inventory/product-360","inventory","Product 360","Everything you need to know about one product, in one place.","Inventory → Product 360","inventory",[
    "Product 360 gives you the big picture. If one specific package or lot is the issue, jump into Package 360 instead."
  ],[
    {title:"Open a product",steps:["Open Product 360.","Search for the product or open it from another workspace.","Check current stock, related packages, sales or movement context, and any actions surfaced by the workspace.","Follow linked package or buying records when deeper detail is required."]}
  ],["/help/inventory/package-360","/help/buying/recommendations"]),

  article("/help/inventory/package-360","inventory","Package 360","Follow one package from where it came from to what happened next.","Inventory → Package 360","inventory",[
    "If you're chasing one package, one source lot, a hold, or a transformation, this is the screen you want."
  ],[
    {title:"Look at a package",steps:["Open Package 360.","Scan, search, or open the package from another workspace.","Check the current quantity, status, room or location, and product identity.","Check movement, production, quality, and traceability context as available.","Open the owning workflow before making a regulated change."]}
  ],["/help/inventory/product-360","/help/compliance/traceability"]),

  article("/help/inventory/audits","inventory","Inventory Audits","Count the floor, pause when you need to, and come back without losing your place.","Inventory → Inventory Audits","inventory",[
    "Set the count scope before you start scanning so you don't accidentally count the same stock twice.",
    "Pausing saves your place. Come back to the same audit instead of starting another one."
  ],[
    {title:"Run an audit",steps:["Open Inventory Audits and create the intended count scope.","Scan a barcode or QR code, or search the item manually.","Enter the physical quantity.","Continue through the scope and pause when needed.","Resume the same audit session.","Check discrepancies and recount exceptions.","Complete the audit only after approved reconciliation."]},
    {title:"Scanner options",body:"Phone and tablet cameras, Bluetooth scanners, USB scanners, and typed codes can all be used where supported by the device and browser."}
  ],["/help/inventory","/help/compliance/traceability"]),

  article("/help/inventory/slow-movers","inventory","Slow Movers","Find product that's sitting too long before it turns into dead weight.","Inventory → Slow Movers","inventory",[
    "Slow doesn't automatically mean discount it. It's a signal to look closer before you decide what to do."
  ],[
    {title:"Find what's getting stale",steps:["Open Slow Movers.","Sort by age, days on hand, value, or the available risk signals.","Check sales velocity and incoming inventory.","Choose an operational response such as purchasing pause, transfer review, promotion review, or assortment action.","Track the result in the owning workflow."]}
  ],["/help/inventory","/help/buying/recommendations"]),

  article("/help/inventory/catalog-admin","inventory","Catalog Administration","Keep product names and identities clean so the rest of the app doesn't turn into a mess.","Inventory → Catalog Administration","inventory",[
    "Clean product names matter more than they look like they do. Bad naming turns into duplicate inventory, messy reports, and broken mappings later."
  ],[
    {title:"Keep the catalog clean",steps:["Open Catalog Administration.","Find the product to review or add.","Check the product name, category, vendor or brand, and any other required identity fields.","Save the record.","Validate the result in Product 360 and connected workflows."]}
  ],["/help/inventory/product-360","/help/compliance/product-name-mapper"]),

  article("/help/cultivation","cultivation","Cultivation overview","Run the grow without bouncing between rooms, spreadsheets, and side notes.","Cultivation → Grow Operations","cultivation",[
    "Cultivation follows the grow facility you're working in.",
    "Post-Harvest lives in its own workspace so dry, trim, cure, testing, and release don't get mixed into the living-plant side of the grow."
  ],[
    {title:"Run the grow",steps:["Open Grow Operations.","Check rooms, plant or group status, and items needing attention.","Open the specific plant or group before recording work.","Use the appropriate harvest or regulatory action instead of altering historical data manually."]},
    {title:"Hand off to post-harvest",steps:["Complete the harvest workflow with the required source context.","Open Post-Harvest.","Track drying, trim, cure, testing hold, release, and downstream material handoff."]}
  ],["/help/cultivation/post-harvest","/help/compliance/traceability"]),

  article("/help/cultivation/post-harvest","cultivation","Post-Harvest","Keep the harvest moving from dry to trim to cure to testing without losing the thread.","Cultivation → Post-Harvest","cultivation",[
    "Keep harvested material tied back to where it came from. That trail matters later.",
    "Don't let material move downstream while testing or release status is still unclear."
  ],[
    {title:"Move a batch through post-harvest",steps:["Open Post-Harvest.","Select the batch or harvest handoff.","Record the current stage and measured weight events as work occurs.","Check loss or variance instead of overwriting earlier measurements.","Record testing or hold context.","Release material through the approved workflow when requirements are satisfied."]}
  ],["/help/cultivation","/help/production","/help/compliance/traceability"]),

  article("/help/production","production","Production overview","Plan what's getting made, what it needs, and what's blocking it.","Production → Today / Production","production",[
    "Each production run belongs to a facility, and its saved run record should stay the place you work from.",
    "Use Run 360 for the complete history and deep detail of one production run."
  ],[
    {title:"Plan and execute",steps:["Open Today / Production to review active and upcoming work.","Use Calendar to understand timing and capacity.","Open the production run before consuming material or recording output.","Record actual quantities, stage changes, losses, and completion as work occurs.","Check the finished output and downstream package or inventory handoff."]}
  ],["/help/production/calendar","/help/production/run-360","/help/extraction"]),

  article("/help/production/calendar","production","Production Calendar","See what's scheduled and where production is about to collide.","Production → Calendar","production",[
    "The calendar is a planning surface. Actual execution remains in the run."
  ],[
    {title:"Use the calendar",steps:["Open Production → Calendar.","Check scheduled runs and capacity by date.","Open a run when you need its materials, stages, or execution details.","Reschedule through the supported planning controls rather than duplicating the run."]}
  ],["/help/production","/help/production/run-360"]),

  article("/help/production/run-360","production","Production Run 360","Open one run and see the whole story: inputs, outputs, variance, QA, and status.","Production → Production Run 360","production",[
    "Run 360 is the one place to trust when you want the full story on a production run.",
    "Measured actuals should not be replaced with planned values when they differ."
  ],[
    {title:"Check a run",steps:["Open Production Run 360.","Select or search for the run.","Check the status, planned and actual inputs, current stage, outputs, loss, and QA context.","Record the next approved execution event.","Use linked package, inventory, or compliance views for downstream review."]}
  ],["/help/production","/help/extraction","/help/package-studio"]),

  article("/help/extraction","production","Extraction","Track an extraction run from source material to yield, QA, and finished output.","Production → Extraction","extraction",[
    "Extraction runs retain source-to-output context so operators can review yield and variance without rebuilding the history from spreadsheets.",
    "Deep run detail remains available in Advanced Run 360."
  ],[
    {title:"Start a run",steps:["Open Production → Extraction.","Choose New run.","Select compatible, released source material.","Check the planned input and extraction process before you create the run.","Create the run and begin work only when the source and facility are correct."]},
    {title:"Work the current process",steps:["Open the active run.","Record stage progress and measured quantities as work occurs.","Record output and loss instead of forcing yield to a planned target.","Check QA or hold requirements before releasing downstream output."]},
    {title:"Check performance",steps:["Open Runs or Analytics.","Compare input, output, recovery, variance, and run history.","Open Advanced Run 360 when you need complete source, cost, QA, or traceability context."]}
  ],["/help/production/run-360","/help/package-studio","/help/compliance/traceability"]),

  article("/help/white-label-repack","production","White Label / Repack","Plan and run repack or white-label work without losing the source, labor, packaging, or customer context.","Production → White Label / Repack","white-label-repack",[
    "Repack work should preserve the source package or lot relationship.",
    "Cost and margin models are planning tools until actual production quantities are recorded."
  ],[
    {title:"Plan a repack job",steps:["Open White Label / Repack.","Choose the source bulk material and customer or brand context.","Define finished package formats and target quantities.","Check packaging, labor, yield, pricing, and margin assumptions.","Save the job before execution."]},
    {title:"Execute and close",steps:["Record actual material used and finished output.","Capture loss or variance.","Create or link downstream packages through the approved workflow.","Complete the job after the final inventory and traceability handoff."]}
  ],["/help/package-studio","/help/production/run-360"]),

  article("/help/package-studio","production","Package Studio","Break down, pack down, build, sample, or correct packages with the source trail intact.","Production → Package Studio","package-studio",[
    "Package creation is a material transformation. Source quantities and resulting output should reconcile.",
    "Use Traceability Actions when a corresponding state-system action is required."
  ],[
    {title:"Create output packages",steps:["Open Package Studio.","Choose the source material or package.","Define the output product, package format, quantity, and destination.","Check source availability and expected remaining quantity.","Create the transformation.","Open the new package in Package 360, then check Traceability if the action created any follow-up work."]}
  ],["/help/inventory/package-360","/help/compliance/state-actions"]),

  article("/help/wholesale","wholesale","Wholesale Ops overview","Run wholesale from sellable inventory to paid invoice without hopping between separate systems.","Wholesale → Wholesale Ops","wholesale",[
    "Wholesale availability is based on sellable inventory after active reservations and commitments.",
    "The public storefront and internal order engine feed the same commercial workflow."
  ],[
    {title:"Order-to-cash flow",steps:["Check sellable inventory.","Create or approve an order.","Reserve or allocate inventory.","Pick and pack the order.","Complete required manifest and fulfillment readiness.","Move invoicing and receivable status through Accounting."]},
    {title:"Use the storefront",body:"Published storefront inventory creates customer-facing availability while incoming requests remain subject to operator review before becoming committed internal orders."}
  ],["/help/wholesale/orders","/help/wholesale/warehouse-pick-pack","/help/compliance/traceability"]),

  article("/help/wholesale/orders","wholesale","Orders & Fulfillment","Take an order from approval to allocation to fulfillment without losing the customer or inventory context.","Wholesale → Orders & Fulfillment","wholesale",[
    "An order request is not the same as an approved sales order.",
    "Allocation should use sellable inventory and respect existing commitments."
  ],[
    {title:"Work an order",steps:["Open Orders & Fulfillment.","Open an existing order or create one for the customer.","Check requested items, quantities, pricing, delivery timing, and inventory availability.","Approve or revise the order through the allowed workflow.","Allocate inventory.","Send ready work to pick and pack."]}
  ],["/help/wholesale","/help/wholesale/warehouse-pick-pack"]),

  article("/help/wholesale/warehouse-pick-pack","wholesale","Warehouse Pick / Pack","Pick the right package, pack it, and make sure what leaves the building matches the order.","Wholesale → Warehouse Pick / Pack","wholesale",[
    "Pick against the approved order and allocated inventory.",
    "Resolve package or quantity discrepancies before marking fulfillment complete."
  ],[
    {title:"Pick and pack",steps:["Open Warehouse Pick / Pack.","Choose the order ready for fulfillment.","Scan or select the allocated packages.","Check the picked quantity against the order.","Resolve substitutions or shortages through the approved order workflow.","Pack and complete the warehouse step.","Before the order leaves, make sure the manifest or delivery setup is ready when required."]}
  ],["/help/wholesale/orders","/help/compliance/state-actions"]),

  article("/help/compliance","compliance","Compliance overview","Keep traceability, state actions, labels, and compliance tools close to the work they affect.","Compliance → Compliance Q&A or Traceability","compliance",[
    "Compliance tools support the operator and compliance team. They do not replace current regulations, state-system requirements, or legal review.",
    "State-system changes still need a deliberate operator action. Doobie does not quietly send them for you."
  ],[
    {title:"Choose the right tool",steps:["Use Compliance Q&A for reviewed source-backed answers.","Use Traceability for synchronized regulatory context and reconciliation.","Use State Actions for pending, rejected, or approved external actions.","Use Label Studio for compliant label creation and reprinting history.","Use Product Name Mapper for catalog alignment.","Use MA Flower Equivalency for Massachusetts adult-use equivalency calculations."]}
  ],["/help/compliance/traceability","/help/compliance/state-actions","/help/compliance/label-studio"]),

  article("/help/compliance/qa","compliance","Compliance Q&A","Ask a compliance question and see the source behind the answer.","Compliance → Compliance Q&A","compliance",[
    "Before you rely on an answer, check the jurisdiction, adult-use or medical scope, source, and review status.",
    "If an exact rule cannot be verified, DoobieLogic should show the limitation instead of inventing certainty."
  ],[
    {title:"Ask a compliance question",steps:["Open Compliance Q&A.","Write a specific operational question and include the relevant jurisdiction or program when needed.","Check the answer and source references.","Make sure the cited source is current for the situation.","Escalate ambiguous or high-risk interpretations to your compliance or legal team."]}
  ],["/help/compliance","/help/doobie-agent"]),

  article("/help/compliance/traceability","compliance","Traceability","See the regulated history without leaving the operational side of the app.","Compliance → Traceability","compliance",[
    "DoobieLogic treats external traceability systems as regulated adapters, not the only operational database.",
    "Reconciliation should preserve what DoobieLogic observed, what the provider returned, and what action was approved."
  ],[
    {title:"Check traceability",steps:["Open Traceability.","Check the facility and integration status first.","Check the relevant package, plant, harvest, transfer, or reconciliation context.","Open any pending exception.","Use State Actions for an approved provider mutation when required.","Read back or reconcile the result after submission."]}
  ],["/help/compliance/state-actions","/help/settings/integrations"]),

  article("/help/compliance/state-actions","compliance","State Actions","Handle state-system actions on purpose, with a human making the final call.","Compliance → State Actions","compliance",[
    "Pending does not mean submitted.",
    "Rejected actions should retain the provider error and the requested payload context for investigation."
  ],[
    {title:"Work the queue",steps:["Open State Actions.","Filter for pending, rejected, or reconciliation-required items.","Open the action and verify facility, entity, requested change, and evidence.","Approve and submit only when the action is correct and authorized.","Check the provider response.","Use reconciliation or readback to make sure the state system ended up where you expected."]}
  ],["/help/compliance/traceability","/help/settings/integrations"]),

  article("/help/compliance/label-studio","compliance","Label Studio","Build, save, print, and reprint labels without starting over every time.","Compliance → Label Studio","compliance",[
    "Use the saved label history when an identical compliant label needs to be reprinted.",
    "Before printing, check the regulatory fields required for that product and jurisdiction."
  ],[
    {title:"Create a label",steps:["Open Label Studio.","Choose the product, package, or source context.","Select the intended label size.","Place and format the supported fields.","Preview the label.","Save the label record and print."]},
    {title:"Reprint a historical label",steps:["Open the saved label history.","Find the original label by product, package, date, or available identifiers.","Check the stored content before reprinting.","Print from the historical record instead of rebuilding it from memory."]}
  ],["/help/compliance","/help/inventory/package-360"]),

  article("/help/compliance/product-name-mapper","compliance","Product Name Mapper","Clean up messy incoming product names so they map to the catalog you actually use.","Compliance → Product Name Mapper","compliance",[
    "The facility catalog is the naming standard.",
    "Check newly generated mappings before publishing them into downstream operations."
  ],[
    {title:"Map product names",steps:["Open Product Name Mapper.","Load or choose the facility catalog that represents the naming standard.","Load the incoming source items.","Check exact matches and proposed mappings.","Correct exceptions.","Export or publish the corrected names through the supported workflow."]}
  ],["/help/inventory/catalog-admin","/help/compliance/traceability"]),

  article("/help/compliance/ma-flower-equivalency","compliance","MA Flower Equivalency","Run Massachusetts flower-equivalency math without doing it on a calculator every time.","Compliance → MA Flower Equivalency","compliance",[
    "Double-check current Massachusetts requirements with your compliance team before operational use.",
    "Input accuracy matters. Product form, quantity, potency, and package configuration can affect the calculation."
  ],[
    {title:"Calculate equivalency",steps:["Open MA Flower Equivalency.","Choose the applicable product form.","Enter the required package and potency values.","Check the calculated equivalency.","Check the result against your current compliance procedure before you use it operationally."]}
  ],["/help/compliance","/help/compliance/qa"]),


  article("/help/production/inventory","production","Production Inventory","See which materials are actually available for production and what's already committed.","Production Ops → Inventory → Materials","production",[
    "Production Inventory is the same saved inventory that runs and Package Studio use downstream.",
    "Available quantity accounts for active reservations and commitments."
  ],[
    {title:"Check materials",steps:["Switch to Production Ops.","Open Inventory → Materials.","Filter by room, material type, status, or product.","Check on-hand, available, reserved, and hold context before assigning material to a run."]},
    {title:"Take action",body:"Use package-level actions for moves, holds, releases, adjustments, transfers, labels, audits, and Package Studio when your permissions allow them."}
  ],["/help/production/inventory/transfers","/help/production/products","/help/production/run-360"]),

  article("/help/production/inventory/transfers","production","Production Inventory Transfers","Move production packages between facilities without losing package or manifest context.","Production Ops → Inventory → Transfers","production",[
    "Transfers operate on physical packages, not product summary rows.",
    "Held, quarantined, failed, or unavailable packages must be resolved before transfer."
  ],[
    {title:"Start a transfer",steps:["Open Production Ops → Inventory → Transfers.","Select the source packages.","Choose the destination facility and review quantities.","Enter required manifest or transport context.","Check eligibility before posting or dispatching the transfer."]},
    {title:"Receive and reconcile",steps:["Open the transfer at the destination.","Double-check package identity and quantity against the physical shipment.","Receive through the supported workflow.","Resolve discrepancies before closing the transfer."]}
  ],["/help/production/inventory","/help/inventory/transfers","/help/compliance/traceability"]),

  article("/help/production/package-360","production","Production Package 360","Open one production package and see balance, location, reservations, history, and lineage.","Production Ops → Inventory → Package 360","production",[
    "Open Package 360 when the question is about one physical package or lot.",
    "Use Product 360 or Product Master when the question is about a reusable product identity."
  ],[
    {title:"Open a package",steps:["Open Production Ops → Inventory → Package 360.","Search or scan the package identifier.","Check quantity, location, status, commitments, and source context.","Follow lineage or related run links when investigating where the material came from or went."]}
  ],["/help/production/inventory","/help/package-studio","/help/inventory/package-360"]),

  article("/help/production/products","production","Production Products","Keep the product master clean so runs, packages, and reports all speak the same language.","Production Ops → Inventory → Products","production",[
    "Product records describe what the material is. Package records describe a specific physical quantity of it.",
    "Naming and units should stay consistent because planning and package workflows reuse these identities."
  ],[
    {title:"Check the product master",steps:["Open Production Ops → Inventory → Products.","Find the product by name or SKU.","Check type, unit, active status, and other production fields.","Update only supported master-data fields and verify downstream workflows after the change."]}
  ],["/help/production/inventory","/help/package-studio","/help/production/run-360"]),

  article("/help/production/inventory-audits","production","Production Inventory Audits","Count production inventory without losing your place or your recount trail.","Production Ops → Inventory → Inventory Audits","production",[
    "Audit sessions can pause, resume, recount, and reconcile.",
    "Define the facility and count scope before scanning so the expected population is clear."
  ],[
    {title:"Run the count",steps:["Open Production Ops → Inventory → Inventory Audits.","Start or resume the audit for the intended scope.","Scan or select each package and record the physical count.","Pause safely when the floor work stops.","Recount discrepancies, review evidence, and complete only after reconciliation."]}
  ],["/help/inventory/audits","/help/production/inventory","/help/compliance/traceability"]),

  article("/help/wholesale/inventory","wholesale","Wholesale Inventory","See what you can actually sell and why anything else is blocked.","Wholesale → Inventory","wholesale",[
    "Wholesale eligibility requires released inventory, passed COA context, and positive uncommitted quantity.",
    "Blocked lots stay visible for investigation without silently becoming sellable."
  ],[
    {title:"Check sellable inventory",steps:["Open Wholesale → Inventory.","Check available and reserved quantity by lot.","Look at COA/release state and blocked reasons.","Open the source package or production context when a lot needs investigation."]}
  ],["/help/wholesale","/help/wholesale/orders","/help/compliance/traceability"]),

  article("/help/wholesale/customers","wholesale","Wholesale Customers","Keep the account, contacts, license info, and payment terms together.","Wholesale → Customers","wholesale",[
    "Customer records should represent the licensed account, not just an individual contact.",
    "Keep license and payment context current before relying on it for order-to-cash decisions."
  ],[
    {title:"Work a customer account",steps:["Open Wholesale → Customers.","Search for the account.","Check license, contacts, terms, activity, and linked commercial history.","Update supported customer fields or open related opportunities/orders from the account context."]}
  ],["/help/wholesale/orders","/help/wholesale/accounting"]),


  article("/help/wholesale/accounting","wholesale","Wholesale Accounting","See invoices, open balances, aging, and payments without leaving wholesale.","Wholesale → Accounting","wholesale",[
    "Accounting follows the main sales order and fulfillment records, so the numbers stay tied to the actual order.",
    "A saved accounting connection is not treated as healthy until provider validation succeeds."
  ],[
    {title:"Check finance handoffs",steps:["Open Wholesale → Accounting.","Check invoices and open balances.","Prioritize overdue or exception accounts.","Record or synchronize payment information through the supported workflow.","Return to the order-to-cash view to verify the exception clears."]}
  ],["/help/wholesale/orders","/help/wholesale/customers","/help/settings/integrations"]),

  article("/help/wholesale/storefront","wholesale","Wholesale Storefront","Control what customers can order and review what they send in before it becomes a real order.","Wholesale → Storefront","wholesale",[
    "Only eligible inventory should be published to the storefront.",
    "A storefront request is not a real sales order yet. Someone still needs to review it before it can reserve inventory."
  ],[
    {title:"Manage the catalog",steps:["Open Wholesale → Storefront.","Check storefront identity and publication status.","Choose eligible products or sales units for the catalog.","Preview the customer-facing storefront before publishing changes."]},
    {title:"Check incoming requests",steps:["Open pending storefront orders.","Double-check customer and license context.","Check requested items and availability.","Approve valid requests into the commercial order workflow or resolve the request without creating duplicate demand."]}
  ],["/help/wholesale","/help/wholesale/orders","/help/wholesale/inventory"]),

  article("/help/reports/sales-category-trends","reports","Sales & Category Trends","See what's moving, what's slowing down, and where demand is changing.","Reports → Sales & Category Trends","buying",[
    "Trend views depend on the freshness and completeness of the active retail source."
  ],[
    {title:"Check trends",steps:["Open Sales & Category Trends.","Choose the date or comparison context.","Check category mix, package-size mix, velocity, and fast or slow movement.","Open the related buying or inventory workspace when a trend requires action."]}
  ],["/help/buying","/help/inventory/slow-movers","/help/reports/executive"]),

  article("/help/reports/executive","reports","Executive Reports","Get a clean leadership view without mixing retail and production together.","Reports → Executive Reports","production",[
    "Retail and Production reports stay separate on purpose. Mixing them usually makes the picture worse, not better.",
    "Before you send a report around, make sure you're looking at the right facility and date range."
  ],[
    {title:"Generate a report",steps:["Open Executive Reports.","Choose the appropriate Retail or Production report context.","Set the period and available filters.","Check the on-screen metrics and action tables.","Generate or export the report only after confirming the scope."]}
  ],["/help/reports/sales-category-trends","/help/home/control-towers"]),

  article("/help/settings/location","settings","Location Settings","Make sure you're looking at the right facility and the right setup before changing anything.","Settings & Administration → Location","home",[
    "The facility selector matters. It controls which records and settings you're actually working with."
  ],[
    {title:"Check location context",steps:["Open Settings & Administration → Location.","Make sure you're in the right facility, then look over the settings available there.","Update only fields your role is authorized to manage.","Save changes and re-open the affected workspace to verify the result."]}
  ],["/help/getting-started","/help/settings/admin"]),

  article("/help/settings/imports-data","settings","Imports & Data","Bring in a file, check it, publish it, and know exactly what data the app is using.","Settings & Administration → Imports & Data","home",[
    "Uploading a file doesn't change the app by itself. You still get a chance to check it before publishing.",
    "Published data goes to the organization and facility you have selected, so check that first."
  ],[
    {title:"Publish a dataset",steps:["Open Imports & Data.","Choose the dataset type.","Upload CSV, XLSX, or XLS when supported.","Check detected rows, columns, required-field mapping, and preview.","Make sure the source file is the one you actually meant to publish.","Publish the version.","Open the downstream workspace and validate the result."]},
    {title:"Use history",body:"The Data Import Center retains version context so an operator can see which source is active and inspect prior published versions according to the platform retention rules."}
  ],["/help/getting-started","/help/buying","/help/inventory"]),

  article("/help/settings/admin","settings","Admin Tools","Manage users and access without touching Supabase by hand.","Settings & Administration → Admin Tools","home",[
    "Create users here, not directly in Supabase. DoobieLogic keeps the login, role, facility access, password rules, and audit trail lined up for you.",
    "Don't manually insert app users into Supabase Auth. You'll skip part of the normal setup and create a mess to untangle later."
  ],[
    {title:"Create a user",steps:["Open Admin Tools → User Management.","Choose Create User.","Enter username, display name, optional email, and role.","Choose the organization and facility access for non-DEV accounts.","Set a temporary password and password-change requirement.","Create the user.","Double-check the new account appears in User Management."]},
    {title:"Manage access",steps:["Open Manage Existing.","Choose the account.","Check role, organization, facility assignments, active status, and password policy.","Save the supported account changes.","Use facility-specific permission overrides only for documented exceptions."]}
  ],["/help/settings/location","/help/settings/integrations","/help/getting-started"]),

  article("/help/settings/integrations","settings","Integrations","Connect Metrc, accounting, and other providers, then make sure the connection actually works.","Settings & Administration → AI, Traceability & Accounting Integrations","integrations",[
    "Saving credentials isn't the finish line. The connection isn't ready until validation passes.",
    "Never paste a server secret or service-role key into a browser field.",
    "Metrc can be optional in supported sandbox or alpha operating modes."
  ],[
    {title:"Choose operating mode",steps:["Open Integrations.","Make sure you're in the right facility before changing the connection.","Choose the supported operating mode for that facility.","Check the effect before saving."]},
    {title:"Connect a provider",steps:["Open the provider section.","Enter the provider-specific credentials or configuration.","Save the connection.","Run validation.","Check the status and any returned error.","Open the downstream workspace only after validation succeeds."]},
    {title:"Troubleshoot",notes:["Make sure you selected the correct facility and environment.","Check provider permissions and license scope.","Use the displayed validation error rather than regenerating credentials blindly.","Do not expose keys in screenshots, chat, or public documentation."]}
  ],["/help/compliance/traceability","/help/settings/admin"]),

  article("/help/doobie-agent","intelligence","Doobie Agent","Ask Doobie what's going on, see the evidence, and jump straight to the place where you can act.","Doobie Agent → available from the app shell","home",[
    "Doobie can help you figure out what's going on and where to look next. It doesn't quietly make admin decisions for you.",
    "Doobie can explain what is happening and recommend a next move. Changes still go through the normal operator-controlled workflow."
  ],[
    {title:"Ask a useful question",steps:["Open Doobie Agent from the sidebar.","Ask a specific operational question such as what needs attention, what inventory is aging, or which runs need review.","Read the evidence and confidence or limitations provided.","Open the recommended workspace to inspect the source record.","Approve or perform any regulated action through the normal workflow."]}
  ],["/help/home","/help/compliance/qa","/help/settings/integrations"]),
];

export const helpCategories: HelpCategory[] = [
  {id:"getting-started",title:"Getting Started",description:"Sign in, choose the right operating context, and learn how DoobieLogic is organized.",articles:["/help/getting-started"]},
  {id:"home",title:"Home & Operations",description:"What's happening today, what's waiting on the team, and where the bigger problems are.",articles:["/help/home","/help/home/control-towers"]},
  {id:"buying",title:"Buying",description:"Figure out what to buy, build the PO, watch the budget, and learn from what actually sold.",articles:["/help/buying","/help/buying/recommendations","/help/buying/purchase-orders","/help/buying/budget","/help/buying/delivery-performance","/help/buying/planning-settings"]},
  {id:"inventory",title:"Inventory",description:"Receive it, move it, count it, trace it, and catch inventory that's starting to sit.",articles:["/help/inventory","/help/inventory/receiving","/help/inventory/transfers","/help/inventory/product-360","/help/inventory/package-360","/help/inventory/audits","/help/inventory/slow-movers","/help/inventory/catalog-admin"]},
  {id:"cultivation",title:"Cultivation",description:"Run the grow and keep the handoff into post-harvest clean.",articles:["/help/cultivation","/help/cultivation/post-harvest"]},
  {id:"production",title:"Production & Extraction",description:"Plan production, run extraction and repack work, and keep the materials and outputs connected.",articles:["/help/production","/help/production/inventory","/help/production/inventory/transfers","/help/production/package-360","/help/production/products","/help/production/inventory-audits","/help/production/calendar","/help/production/run-360","/help/extraction","/help/white-label-repack","/help/package-studio"]},
  {id:"wholesale",title:"Wholesale & Warehouse",description:"From what's sellable to who bought it, what needs picking, and whether you've been paid.",articles:["/help/wholesale","/help/wholesale/inventory","/help/wholesale/orders","/help/wholesale/warehouse-pick-pack","/help/wholesale/customers","/help/wholesale/accounting","/help/wholesale/storefront"]},
  {id:"compliance",title:"Compliance",description:"The compliance tools you actually need while the work is happening.",articles:["/help/compliance","/help/compliance/qa","/help/compliance/traceability","/help/compliance/state-actions","/help/compliance/label-studio","/help/compliance/product-name-mapper","/help/compliance/ma-flower-equivalency"]},
  {id:"reports",title:"Reports",description:"See what's moving and turn it into something leadership can actually use.",articles:["/help/reports/sales-category-trends","/help/reports/executive"]},
  {id:"settings",title:"Settings & Integrations",description:"The setup side of DoobieLogic: facilities, users, data, Metrc, accounting, and connections.",articles:["/help/settings/location","/help/settings/imports-data","/help/settings/admin","/help/settings/integrations"]},
  {id:"intelligence",title:"Doobie Agent",description:"Ask what's going on, see why Doobie thinks that, and go straight to the work.",articles:["/help/doobie-agent"]},
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
