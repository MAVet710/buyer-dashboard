import { approvedCustomerProof, isApprovedProof, type CustomerProofRecord } from "./customerProofData";
export type { CustomerProofRecord } from "./customerProofData";

function publicUrl(value: string | undefined): string | undefined {
  if (!value) return undefined;
  if (/^\/(?!\/)/.test(value)) return value;
  try {
    return new URL(value).protocol === "https:" ? value : undefined;
  } catch { return undefined; }
}

export function TestimonialCard({ proof }: { proof: CustomerProofRecord }) {
  if (!isApprovedProof(proof) || !proof.quote?.trim()) return null;
  return <figure className="mk-customer-quote">
    <blockquote><p>{proof.quote}</p></blockquote>
    <figcaption>{[proof.person, proof.role, proof.company].filter(Boolean).join(" · ")}</figcaption>
  </figure>;
}

export function CustomerLogoRow({ proofs = approvedCustomerProof }: { proofs?: readonly CustomerProofRecord[] }) {
  const approved = proofs.filter((proof) => isApprovedProof(proof) && publicUrl(proof.logo));
  if (!approved.length) return null;
  return <ul className="mk-customer-logos" aria-label="Customers who approved public logo use">
    {approved.map((proof) => <li key={proof.id}><img src={publicUrl(proof.logo)} alt={proof.company} width="144" height="64" loading="lazy" /></li>)}
  </ul>;
}

export function CaseStudyPreview({ proof }: { proof: CustomerProofRecord }) {
  const href = publicUrl(proof.caseStudyUrl);
  if (!isApprovedProof(proof) || !href) return null;
  return <article className="mk-case-study">
    <h3>{proof.company}</h3>
    {(proof.state || proof.licenseType) && <p>{[proof.state, proof.licenseType].filter(Boolean).join(" · ")}</p>}
    {proof.result && <p>{proof.result}</p>}
    <a href={href}>Read {proof.company}’s case study</a>
  </article>;
}

export function QuantifiedResult({ proof }: { proof: CustomerProofRecord }) {
  if (!isApprovedProof(proof) || !proof.result?.trim()) return null;
  return <figure className="mk-customer-result"><p>{proof.result}</p><figcaption>{proof.company}</figcaption></figure>;
}
