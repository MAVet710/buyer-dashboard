export type CustomerProofRecord = {
  id: string;
  company: string;
  person?: string;
  role?: string;
  quote?: string;
  logo?: string;
  state?: string;
  licenseType?: string;
  result?: string;
  source: string;
  verifiedOn: string;
  verification: "VERIFIED" | "SUPPORTED_BUT_BETA" | "PLANNED" | "UNVERIFIED";
  approvalState: "pending" | "approved" | "revoked";
  publicSafe: boolean;
  caseStudyUrl?: string;
};

/** Intentionally empty until evidence and public usage permission are recorded. */
export const approvedCustomerProof: readonly CustomerProofRecord[] = [];

export function isApprovedProof(proof: CustomerProofRecord): boolean {
  return proof.verification === "VERIFIED" && proof.approvalState === "approved" &&
    proof.publicSafe && Boolean(proof.source.trim()) && Boolean(proof.company.trim()) &&
    /^\d{4}-\d{2}-\d{2}$/.test(proof.verifiedOn) && Number.isFinite(Date.parse(proof.verifiedOn));
}
