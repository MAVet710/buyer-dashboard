export type CannabisProgramStatus = "adult-use-and-medical" | "medical" | "adult-use" | "other";

export type CannabisJurisdiction = {
  code: string;
  name: string;
  program: CannabisProgramStatus;
  territory?: boolean;
};

// Regulated U.S. cannabis jurisdictions reviewed against the NCSL state medical
// cannabis program table and adult-use indicators on 2026-08-25. Keeping this
// catalog centralized prevents individual workflows from drifting into partial,
// hard-coded state lists.
export const REGULATED_CANNABIS_JURISDICTIONS: CannabisJurisdiction[] = [
  { code: "AL", name: "Alabama", program: "medical" },
  { code: "AK", name: "Alaska", program: "adult-use-and-medical" },
  { code: "AZ", name: "Arizona", program: "adult-use-and-medical" },
  { code: "AR", name: "Arkansas", program: "medical" },
  { code: "CA", name: "California", program: "adult-use-and-medical" },
  { code: "CO", name: "Colorado", program: "adult-use-and-medical" },
  { code: "CT", name: "Connecticut", program: "adult-use-and-medical" },
  { code: "DE", name: "Delaware", program: "adult-use-and-medical" },
  { code: "DC", name: "District of Columbia", program: "adult-use-and-medical" },
  { code: "FL", name: "Florida", program: "medical" },
  { code: "GA", name: "Georgia", program: "medical" },
  { code: "GU", name: "Guam", program: "adult-use-and-medical", territory: true },
  { code: "HI", name: "Hawaii", program: "medical" },
  { code: "IL", name: "Illinois", program: "adult-use-and-medical" },
  { code: "KY", name: "Kentucky", program: "medical" },
  { code: "LA", name: "Louisiana", program: "medical" },
  { code: "ME", name: "Maine", program: "adult-use-and-medical" },
  { code: "MD", name: "Maryland", program: "adult-use-and-medical" },
  { code: "MA", name: "Massachusetts", program: "adult-use-and-medical" },
  { code: "MI", name: "Michigan", program: "adult-use-and-medical" },
  { code: "MN", name: "Minnesota", program: "adult-use-and-medical" },
  { code: "MS", name: "Mississippi", program: "medical" },
  { code: "MO", name: "Missouri", program: "adult-use-and-medical" },
  { code: "MT", name: "Montana", program: "adult-use-and-medical" },
  { code: "NE", name: "Nebraska", program: "medical" },
  { code: "NV", name: "Nevada", program: "adult-use-and-medical" },
  { code: "NH", name: "New Hampshire", program: "medical" },
  { code: "NJ", name: "New Jersey", program: "adult-use-and-medical" },
  { code: "NM", name: "New Mexico", program: "adult-use-and-medical" },
  { code: "NY", name: "New York", program: "adult-use-and-medical" },
  { code: "ND", name: "North Dakota", program: "medical" },
  { code: "MP", name: "Northern Mariana Islands", program: "adult-use", territory: true },
  { code: "OH", name: "Ohio", program: "adult-use-and-medical" },
  { code: "OK", name: "Oklahoma", program: "medical" },
  { code: "OR", name: "Oregon", program: "adult-use-and-medical" },
  { code: "PA", name: "Pennsylvania", program: "medical" },
  { code: "PR", name: "Puerto Rico", program: "medical", territory: true },
  { code: "RI", name: "Rhode Island", program: "adult-use-and-medical" },
  { code: "SD", name: "South Dakota", program: "medical" },
  { code: "TX", name: "Texas", program: "medical" },
  { code: "VI", name: "U.S. Virgin Islands", program: "adult-use-and-medical", territory: true },
  { code: "UT", name: "Utah", program: "medical" },
  { code: "VT", name: "Vermont", program: "adult-use-and-medical" },
  { code: "VA", name: "Virginia", program: "adult-use-and-medical" },
  { code: "WA", name: "Washington", program: "adult-use-and-medical" },
  { code: "WV", name: "West Virginia", program: "medical" },
];

export const CANNABIS_JURISDICTION_OPTIONS = [
  ...REGULATED_CANNABIS_JURISDICTIONS,
  { code: "Other", name: "Other / Tribal / International", program: "other" as const },
];

export function cannabisJurisdictionLabel(jurisdiction: CannabisJurisdiction) {
  return `${jurisdiction.code} · ${jurisdiction.name}`;
}
