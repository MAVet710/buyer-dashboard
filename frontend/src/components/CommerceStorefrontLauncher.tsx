export function CommerceStorefrontLauncher() {
  return <button
    type="button"
    className="commerce-launcher"
    onClick={() => window.location.assign("/wholesale")}
    aria-label="Open Wholesale Ops"
  >Wholesale Ops</button>;
}
