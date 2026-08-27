import { useEffect, useState } from "react";
import { CommerceStorefrontManager } from "./CommerceStorefrontManager";

export function CommerceStorefrontLauncher() {
  const [open,setOpen]=useState(false);
  useEffect(()=>{if(!open)return;const close=(event:KeyboardEvent)=>{if(event.key==="Escape")setOpen(false);};window.addEventListener("keydown",close);return()=>window.removeEventListener("keydown",close);},[open]);
  return <>
    <button type="button" className="commerce-launcher" onClick={()=>setOpen(true)} aria-label="Open DoobieCommerce">Commerce</button>
    {open?<div className="commerce-launcher-backdrop" role="presentation" onMouseDown={event=>{if(event.target===event.currentTarget)setOpen(false);}}>
      <section className="commerce-launcher-window" role="dialog" aria-modal="true" aria-label="DoobieCommerce hosted storefront manager">
        <header><div><span>DOOBIECOMMERCE</span><strong>Wholesale storefront</strong></div><button type="button" onClick={()=>setOpen(false)} aria-label="Close DoobieCommerce">×</button></header>
        <div className="commerce-launcher-body"><CommerceStorefrontManager/></div>
      </section>
    </div>:null}
  </>;
}
