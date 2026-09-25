import "../wholesale-website.css";

type PartnerProps = {
  displayName: string;
  description?: string;
  heading?: string;
  body?: string;
  listedCount: number;
  orderableCount: number;
  coaBackedCount: number;
  volumePricedCount: number;
  cowboy?: boolean;
};

export function WholesalePartnerSection({
  displayName,
  description,
  heading,
  body,
  listedCount,
  orderableCount,
  coaBackedCount,
  volumePricedCount,
  cowboy = false,
}: PartnerProps) {
  const defaultSummary = description?.trim() ||
    `A direct wholesale relationship with live availability, batch transparency, and a clear path from request to fulfillment.`;
  const resolvedHeading = heading?.trim() || `Built for buyers who want a dependable ${displayName} relationship.`;
  const resolvedBody = body?.trim() || defaultSummary;
  return <section id="wholesale-partners" className={`wholesale-partner-section${cowboy ? " cowboy-partner-section" : ""}`}>
    <div className="wholesale-site-heading">
      <span>WHOLESALE PARTNERSHIP</span>
      <h2>{resolvedHeading}</h2>
      <p>{resolvedBody}</p>
    </div>
    <div className="wholesale-proof-grid">
      <article>
        <strong>{orderableCount}</strong>
        <span>orderable now</span>
        <p>Live sellable inventory, not a static line sheet.</p>
      </article>
      <article>
        <strong>{coaBackedCount}</strong>
        <span>COA-backed listings</span>
        <p>Passed batch data stays attached to the products buyers review.</p>
      </article>
      <article>
        <strong>{volumePricedCount}</strong>
        <span>volume-priced products</span>
        <p>Quantity breaks stay connected to the same catalog and order request.</p>
      </article>
      <article>
        <strong>{listedCount}</strong>
        <span>products listed</span>
        <p>Availability, batch status, and buyer ordering stay in one experience.</p>
      </article>
    </div>
    <div className="wholesale-partner-actions">
      <a className="storefront-cta" href="#catalog">Browse live availability</a>
      <a className="wholesale-secondary-link" href="#order-request">Start an order request</a>
    </div>
  </section>;
}

export function WholesaleProcessSection({displayName}:{displayName:string}) {
  const steps = [
    ["01", "Browse live inventory", "Review current products, batch availability, volume pricing, and passed-COA information."],
    ["02", "Build the request", "Choose quantities and provide buyer, license, PO, and delivery details in one place."],
    ["03", "Sales review", `${displayName} reviews the request before inventory is committed and can approve adjusted quantities or pricing.`],
    ["04", "Fulfillment & status", "Approved demand becomes an operational sales order that can move through allocation, pick/pack, shipment, invoicing, and payment tracking."],
  ];
  return <section id="wholesale-process" className="wholesale-process-section">
    <div className="wholesale-site-heading">
      <span>HOW WHOLESALE WORKS</span>
      <h2>From live catalog to fulfillment without duplicate entry.</h2>
      <p>The website is the buyer-facing door into the same DoobieLogic wholesale operation your team fulfills.</p>
    </div>
    <div className="wholesale-process-grid">
      {steps.map(([number,title,copy]) => <article key={number}>
        <b>{number}</b>
        <h3>{title}</h3>
        <p>{copy}</p>
      </article>)}
    </div>
    <div className="wholesale-process-note">
      <strong>Approval-gated by design.</strong>
      <span>Submitting a web request does not deduct inventory. Inventory is committed only after seller review and approval.</span>
    </div>
  </section>;
}
