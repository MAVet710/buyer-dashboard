import { describe, expect, it } from "vitest";
import { designIssues, initialDesign, resizeStock } from "./labelDesign";

describe("physical label geometry",()=>{
  it("supports arbitrary custom stock dimensions",()=>{
    const design=initialDesign(3.375,1.875);
    expect(designIssues(design)).toEqual([]);
    expect(design.width_in).toBe(3.375);
  });
  it("preserves relative positions on stock and orientation changes",()=>{
    const original=initialDesign(4,6);
    const resized=resizeStock(original,6,4);
    expect(designIssues(resized)).toEqual([]);
    original.blocks.forEach((block,i)=>{
      expect(resized.blocks[i].x/6).toBeCloseTo(block.x/4);
      expect(resized.blocks[i].height/4).toBeCloseTo(block.height/6);
      expect(resized.blocks[i].font_size).toBe(block.font_size);
    });
  });
  it("rejects overlap, clipping, and invalid sizes",()=>{
    const original=initialDesign(4,6);
    const outside=structuredClone(original);outside.blocks[0].x=4;
    expect(designIssues(outside).join(" ")).toContain("beyond");
    const overlap=structuredClone(original);overlap.blocks[1]={...overlap.blocks[0],id:"dates"};
    expect(designIssues(overlap).join(" ")).toContain("overlaps");
    expect(designIssues({...original,width_in:NaN})).not.toEqual([]);
  });
});
