import {describe,it,expect} from "vitest";
import {inventoryHealth, operationsScore, parseInventoryCsv, safeFilename, scoreQuestions} from "./advisoryTools";

describe("transparent self assessment",()=>{
  it("excludes not applicable and rejects sparse results",()=>{
    const a=Object.fromEntries(scoreQuestions.map((q,i)=>[q.id,i<15?2:null]));
    expect(operationsScore(a)).toMatchObject({overall:50,answered:15});
    a[scoreQuestions[0].id]=null;expect(()=>operationsScore(a)).toThrow(/15/);
  });
  it("rejects missing, extra and out of range answers",()=>{
    expect(()=>operationsScore({})).toThrow();
    const a=Object.fromEntries(scoreQuestions.map(q=>[q.id,4]));
    expect(operationsScore(a).overall).toBe(100);
    expect(()=>operationsScore({...a,extra:1})).toThrow();
    expect(()=>operationsScore({...a,[scoreQuestions[0].id]:5})).toThrow();
  });
});
describe("bounded local CSV analysis",()=>{
  it("parses BOM, quoted commas, escaped quotes and multiline cells",()=>{
    const parsed=parseInventoryCsv('\uFEFFSKU,Product,Quantity\r\nA,"Flower, ""Alpha""",3\r\nB,"Multi\nline",0');
    expect(parsed.rows).toEqual([["A",'Flower, "Alpha"',"3"],["B","Multi\nline","0"]]);
  });
  it.each(['SKU,SKU\nA,1','SKU,Quantity\nA,1,2','SKU,Quantity\nA,"broken','SKU,Quantity\nA,\0','SKU,Quantity\nA,"x"evil'])('rejects malformed input %s',text=>expect(()=>parseInventoryCsv(text)).toThrow());
  it("bounds row, cell and column counts",()=>{
    expect(()=>parseInventoryCsv('SKU,Quantity\n'+Array(5001).fill('A,1').join('\n'))).toThrow(/5,000/);
    expect(()=>parseInventoryCsv('SKU,Quantity\n'+"a".repeat(2001)+',1')).toThrow(/2,000/);
    expect(()=>parseInventoryCsv(Array.from({length:65},(_,i)=>'c'+i).join(',')+'\n'+Array(65).fill('1').join(','))).toThrow(/64/);
  });
  it("leaves formula-like cells inert and sanitizes display filenames",()=>{
    expect(parseInventoryCsv('SKU,Quantity\n=HYPERLINK(123),2').formulaCells).toBe(1);
    expect(safeFilename('../../evil<script>.csv')).toBe('evil_script_.csv');
  });
  it("calculates only supplied metrics, with zero-sales denominator undefined",()=>{
    const csv=parseInventoryCsv('SKU,Quantity,Cost,Sales Quantity,Received Date,Last Sale Date,Category\nA,10,2,0,2026-01-01,2026-01-01,Flower\nB,5,4,30,2026-09-01,2026-09-18,Flower');
    const map=Object.fromEntries(csv.headers.map(h=>[h,h]));
    const r=inventoryHealth(csv.headers,csv.rows,map,30,'2026-09-19');
    expect(r.metrics.find(m=>m.label==='Inventory cost value')?.value).toBe('40');
    expect(r.metrics.find(m=>m.label==='Stock with zero period sales')?.value).toBe('1');
    expect(r.metrics.find(m=>m.label==='Stock cover under 7 days')?.value).toBe('1');
    expect(r.metrics.find(m=>m.label==='No sale in 90+ days')?.value).toBe('1');
    expect(JSON.stringify(r)).not.toContain('Infinity');
  });
  it("does not invent costs, sales velocity or age",()=>{
    const r=inventoryHealth(['SKU','Quantity'],[['A','12']],{SKU:'SKU',Quantity:'Quantity'},30);
    expect(r.metrics.map(m=>m.label)).toEqual(['Inventory rows']);
    expect(r.warnings.join(' ')).toMatch(/Cost.*Days on hand.*Last Sale/);
  });
  it("rejects duplicate mappings and invalid quantities, excludes invalid calendar dates",()=>{
    expect(()=>inventoryHealth(['SKU','Qty'],[['A','-1']],{SKU:'SKU',Quantity:'Qty'},30)).toThrow(/non-negative/);
    expect(()=>inventoryHealth(['SKU','Qty'],[['A','1']],{SKU:'SKU',Quantity:'Qty',Cost:'Qty'},30)).toThrow(/only once/);
    const r=inventoryHealth(['SKU','Qty','Date'],[['A','1','2026-02-30']],{SKU:'SKU',Quantity:'Qty','Received Date':'Date'},30,'2026-09-19');
    expect(r.metrics.some(m=>m.label==='Mean received age')).toBe(false);
  });
});
