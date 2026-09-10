import type { ReactNode } from "react";

export const BLOCK_NAMES = {header:"Product and net contents",dates:"Dates",sources:"Source testing",parties:"Cultivator and manufacturer",warning:"Warning",qr:"METRC QR",barcode:"METRC barcode",tag:"METRC tag",unit:"Copy number"};
export type BlockId = keyof typeof BLOCK_NAMES;
export type LabelBlock = {id:BlockId;x:number;y:number;width:number;height:number;font_size:number;bold:boolean;align:"left"|"center"|"right"};
export type LabelDesign = {version:1;width_in:number;height_in:number;blocks:LabelBlock[]};
export type LabelContents = Record<BlockId,ReactNode>;

export function initialDesign(width:number,height:number):LabelDesign {
  const rows:[BlockId,number,number,number,number][] = [
    ["header",.03,.02,.94,.12],["dates",.03,.15,.94,.09],
    ["sources",.03,.25,.64,.40],["qr",.70,.25,.27,.20],
    ["barcode",.70,.47,.27,.13],["tag",.70,.61,.27,.08],
    ["parties",.03,.70,.94,.09],["warning",.03,.80,.94,.14],["unit",.70,.95,.27,.04],
  ];
  return {version:1,width_in:width,height_in:height,blocks:rows.map(([id,x,y,w,h])=>({id,x:x*width,y:y*height,width:w*width,height:h*height,font_size:id==="header"?10:6,bold:id==="header",align:id==="header"?"center":"left"}))};
}

export function resizeStock(design:LabelDesign,width:number,height:number):LabelDesign {
  return {...design,width_in:width,height_in:height,blocks:design.blocks.map(block=>({...block,x:block.x*width/design.width_in,y:block.y*height/design.height_in,width:block.width*width/design.width_in,height:block.height*height/design.height_in}))};
}

export function designIssues(design:LabelDesign):string[] {
  const issues:string[]=[];
  if (![design.width_in,design.height_in].every(n=>Number.isFinite(n)&&n>=.1&&n<=200)) issues.push("Enter stock dimensions between 0.1 and 200 inches.");
  for(const block of design.blocks){
    if(![block.x,block.y,block.width,block.height,block.font_size].every(Number.isFinite)||block.x<0||block.y<0||block.width<.01||block.height<.01||block.x+block.width>design.width_in+.00001||block.y+block.height>design.height_in+.00001) issues.push(`${BLOCK_NAMES[block.id]} extends beyond the label.`);
    if(block.font_size<4||block.font_size>72) issues.push(`${BLOCK_NAMES[block.id]} needs a font size between 4 and 72 pt.`);
  }
  design.blocks.forEach((left,index)=>design.blocks.slice(index+1).forEach(right=>{
    if(Math.min(left.x+left.width,right.x+right.width)-Math.max(left.x,right.x)>.00001&&Math.min(left.y+left.height,right.y+right.height)-Math.max(left.y,right.y)>.00001) issues.push(`${BLOCK_NAMES[left.id]} overlaps ${BLOCK_NAMES[right.id]}.`);
  }));
  return issues;
}

