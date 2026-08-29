import { describe, expect, it } from "vitest";
import { COWBOY_STRAIN_TYPES, STRAIN_TYPES } from "./StorefrontPage.strain-types";

describe("Cowboy Kush strain classifications",()=>{
  it("uses only storefront-supported strain type labels",()=>{
    for(const value of Object.values(COWBOY_STRAIN_TYPES)) expect(STRAIN_TYPES.has(value)).toBe(true);
  });
});
