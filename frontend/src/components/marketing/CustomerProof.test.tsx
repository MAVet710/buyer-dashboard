import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CaseStudyPreview, CustomerLogoRow, QuantifiedResult, TestimonialCard, type CustomerProofRecord } from "./CustomerProof";

// Test fixture only; no fabricated record is exported to marketing content.
const fixture: CustomerProofRecord = {
  id: "test-only", company: "Test fixture company", source: "internal-test-evidence", verifiedOn: "2026-09-11",
  verification: "VERIFIED", approvalState: "approved", publicSafe: true, quote: "Test fixture quote.",
  logo: "/test-logo.png", result: "Test fixture result", caseStudyUrl: "/test-case-study",
};
function renderAll(proof: CustomerProofRecord) {
  return renderToStaticMarkup(<><TestimonialCard proof={proof} /><CustomerLogoRow proofs={[proof]} /><CaseStudyPreview proof={proof} /><QuantifiedResult proof={proof} /></>);
}

describe("public customer proof", () => {
  it("renders no logos by default", () => expect(renderToStaticMarkup(<CustomerLogoRow />)).toBe(""));
  it.each([
    { verification: "UNVERIFIED" as const }, { verification: "SUPPORTED_BUT_BETA" as const },
    { verification: "PLANNED" as const }, { approvalState: "pending" as const },
    { approvalState: "revoked" as const }, { publicSafe: false }, { source: "" }, { verifiedOn: "not-a-date" },
  ])("suppresses every component when evidence or permission is missing: %j", (override) => {
    expect(renderAll({ ...fixture, ...override })).toBe("");
  });
  it("renders approved verified public content", () => {
    const html = renderAll(fixture);
    expect(html).toContain("Test fixture quote.");
    expect(html).toContain("Test fixture result");
    expect(html).toContain('alt="Test fixture company"');
  });
  it("rejects unsafe or protocol-relative image and case study URLs", () => {
    const proof = { ...fixture, logo: "//third-party.example/logo.png", caseStudyUrl: "javascript:alert(1)" };
    expect(renderToStaticMarkup(<><CustomerLogoRow proofs={[proof]} /><CaseStudyPreview proof={proof} /></>)).toBe("");
  });
});
