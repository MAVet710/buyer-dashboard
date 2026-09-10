import { useEffect, useRef, useState } from "react";
import "./labelLayoutEditor.css";

import { BLOCK_NAMES, resizeStock, designIssues, type BlockId, type LabelBlock, type LabelDesign, type LabelContents } from "./labelDesign";

export function LabelDesignCanvas({design,contents,editable=false,selected,onSelect,onChange,onOverflow}:{design:LabelDesign;contents:LabelContents;editable?:boolean;selected?:BlockId;onSelect?:(id:BlockId)=>void;onChange?:(design:LabelDesign)=>void;onOverflow?:(names:string[])=>void}){
  const ref=useRef<HTMLDivElement>(null);
  const drag=useRef<{pointer:number;clientX:number;clientY:number;block:LabelBlock;resize:boolean}|null>(null);
  useEffect(()=>{
    if(!onOverflow||!ref.current)return;
    const root=ref.current;
    const measure=()=>onOverflow(Array.from(root.querySelectorAll<HTMLElement>(".label-design-content")).filter(el=>el.scrollHeight>el.clientHeight+1||el.scrollWidth>el.clientWidth+1).map(el=>el.dataset.name??"Content"));
    measure();
    const observer=new ResizeObserver(measure);observer.observe(root);
    root.querySelectorAll(".label-design-content").forEach(el=>observer.observe(el));
    return ()=>observer.disconnect();
  },[design,contents,onOverflow]);
  return <div ref={ref} className={`label-design-canvas ${editable?"is-editable":""}`} style={{width:`${design.width_in}in`,height:`${design.height_in}in`}}>
    {design.blocks.map(block=><div key={block.id} className={`label-design-block ${editable&&selected===block.id?"is-selected":""}`} style={{left:`${block.x}in`,top:`${block.y}in`,width:`${block.width}in`,height:`${block.height}in`,fontSize:`${block.font_size}pt`,fontWeight:block.bold?700:400,textAlign:block.align}}
      tabIndex={editable?0:undefined} role={editable?"button":undefined} aria-label={editable?`Move ${BLOCK_NAMES[block.id]}`:undefined}
      onKeyDown={event=>{if(!editable)return;const delta:Record<string,[number,number]>={ArrowLeft:[-.01,0],ArrowRight:[.01,0],ArrowUp:[0,-.01],ArrowDown:[0,.01]};if(!delta[event.key])return;event.preventDefault();const [dx,dy]=delta[event.key];onChange?.({...design,blocks:design.blocks.map(row=>row.id===block.id?{...row,x:Math.max(0,Math.min(design.width_in-row.width,row.x+dx)),y:Math.max(0,Math.min(design.height_in-row.height,row.y+dy))}:row)});}}
      onFocus={()=>editable&&onSelect?.(block.id)}
      onPointerDown={event=>{if(!editable)return;event.preventDefault();onSelect?.(block.id);event.currentTarget.setPointerCapture(event.pointerId);drag.current={pointer:event.pointerId,clientX:event.clientX,clientY:event.clientY,block,resize:(event.target as HTMLElement).dataset.resize==="true"};}}
      onPointerMove={event=>{const start=drag.current;if(!editable||!start||start.pointer!==event.pointerId)return;const scale=(ref.current?.getBoundingClientRect().width??design.width_in*96)/design.width_in;const dx=(event.clientX-start.clientX)/scale,dy=(event.clientY-start.clientY)/scale;const b=start.block;
        const next=start.resize?{...b,width:Math.max(.01,Math.min(design.width_in-b.x,b.width+dx)),height:Math.max(.01,Math.min(design.height_in-b.y,b.height+dy))}:{...b,x:Math.max(0,Math.min(design.width_in-b.width,b.x+dx)),y:Math.max(0,Math.min(design.height_in-b.height,b.y+dy))};
        onChange?.({...design,blocks:design.blocks.map(row=>row.id===b.id?next:row)});
      }} onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}}>
      <div className="label-design-content" data-name={BLOCK_NAMES[block.id]}>{contents[block.id]}</div>
      {editable&&selected===block.id?<span className="label-design-resize" data-resize="true" aria-hidden="true"/>:null}
    </div>)}
  </div>;
}

export function LabelLayoutEditor({design,contents,disabled,busy,onChange,onSave,onCancel,onOverflow}:{design:LabelDesign;contents:LabelContents;disabled:boolean;busy:boolean;onChange:(design:LabelDesign)=>void;onSave:()=>void;onCancel:()=>void;onOverflow:(names:string[])=>void}){
  const [selected,setSelected]=useState<BlockId>("header");
  const [units,setUnits]=useState("in");
  const [zoom,setZoom]=useState(1);
  const factor=units==="mm"?25.4:1;
  const block=design.blocks.find(row=>row.id===selected)!;
  const update=(patch:Partial<LabelBlock>)=>onChange({...design,blocks:design.blocks.map(row=>row.id===selected?{...row,...patch}:row)});
  const amount=(n:number)=>Number((n*factor).toFixed(3));
  return <section className="label-layout-editor" aria-label="Customize label layout">
    <h3>Customize label</h3><p>Drag blocks, pull a corner to resize, or use exact measurements. Arrow keys move a focused block. Source values stay linked to this run.</p>
    <fieldset disabled={disabled||busy}><div className="label-design-controls">
      <label>Units<select value={units} onChange={e=>setUnits(e.target.value)}><option value="in">Inches</option><option value="mm">Millimeters</option></select></label>
      <label>Stock preset<select defaultValue="" onChange={e=>{if(!e.target.value)return;const [w,h]=e.target.value.split("x").map(Number);onChange(resizeStock(design,w,h));e.target.value="";}}><option value="">Custom size</option>{["2x1","2x2","3x2","3.5x2.1","4x2","4x6","6x4"].map(size=><option key={size} value={size}>{size} in</option>)}</select></label>
      {(["width_in","height_in"] as const).map(key=><label key={key}>{key==="width_in"?"Stock width":"Stock height"}<input type="number" min={.1*factor} max={200*factor} step="any" value={amount(design[key])} onChange={e=>{const n=Number(e.target.value)/factor;if(Number.isFinite(n)&&n>=.1&&n<=200)onChange(resizeStock(design,key==="width_in"?n:design.width_in,key==="height_in"?n:design.height_in));}}/></label>)}
      <button type="button" className="secondary" onClick={()=>onChange(resizeStock(design,design.height_in,design.width_in))}>Swap orientation</button>
      <label>Selected block<select value={selected} onChange={e=>setSelected(e.target.value as BlockId)}>{Object.entries(BLOCK_NAMES).map(([id,name])=><option value={id} key={id}>{name}</option>)}</select></label>
      {(["x","y","width","height"] as const).map(key=><label key={key}>{key.toUpperCase()} ({units})<input type="number" step="any" value={amount(block[key])} onChange={e=>update({[key]:Number(e.target.value)/factor})}/></label>)}
      <label>Font size (pt)<input type="number" min="4" max="72" step=".5" value={block.font_size} onChange={e=>update({font_size:Number(e.target.value)})}/></label>
      <label>Alignment<select value={block.align} onChange={e=>update({align:e.target.value as LabelBlock["align"]})}><option>left</option><option>center</option><option>right</option></select></label>
      <label>Bold<input type="checkbox" checked={block.bold} onChange={e=>update({bold:e.target.checked})}/></label>
    </div></fieldset>
    <label>Preview zoom<select value={zoom} onChange={e=>setZoom(Number(e.target.value))}>{[.25,.5,.75,1,1.5,2].map(value=><option value={value} key={value}>{value*100}%</option>)}</select></label>
    <div className="label-design-scroll"><div style={{width:design.width_in*96*zoom,height:design.height_in*96*zoom}}><div style={{transform:`scale(${zoom})`,transformOrigin:"top left"}}><LabelDesignCanvas design={design} contents={contents} editable={!disabled&&!busy} selected={selected} onSelect={setSelected} onChange={onChange} onOverflow={onOverflow}/></div></div></div>
    <p>Print at 100% / actual size with matching printer stock and headers/footers off. Check spacing and scan a test label before a production print.</p>
    <div className="inline-form"><button type="button" className="primary" disabled={disabled||busy||designIssues(design).length>0} onClick={onSave}>{busy?"Saving design…":"Save layout to run"}</button><button type="button" className="secondary" disabled={busy} onClick={onCancel}>Close editor</button></div>
  </section>;
}
