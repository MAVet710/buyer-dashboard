/* eslint-disable react-refresh/only-export-components -- standalone browser fixture entry */
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { WorkspaceWindow } from "../../src/components/WorkspaceWindow";
import { StreamlitDialog } from "../../src/components/StreamlitDialog";
import "../../src/styles.css";
import "../../src/table-filters.css";
import "../../src/parity.css";
import "../../src/parity-workspaces.css";
import "../../src/streamlit-exact.css";
import "../../src/streamlit-shell.css";
import "../../src/buyer-streamlit.css";
import "../../src/white-label-streamlit.css";
import "../../src/home-streamlit.css";
import "../../src/inventory-receiving.css";
import "../../src/auth-streamlit.css";
import "../../src/brand-image.css";
import "../../src/marketing-home.css";
import "../../src/beta-partner.css";
import "../../src/contact-channels.css";
import "../../src/commerce-storefront.css";
import "../../src/cowboy-storefront.css";
import "../../src/commerce-launcher.css";
import "../../src/offline.css";
import "../../src/popup-surfaces.css";

function Content() {
  return <><div className="view-tabs"><button className="active">Overview</button><button>History</button></div><label>Search<input aria-label="Search items" defaultValue="Synthetic inventory" /></label><div className="table-wrap"><table><thead><tr><th>Item</th><th>Quantity</th></tr></thead><tbody>{Array.from({length:20}, (_,i)=><tr key={i}><td>Sample {i+1}</td><td>{i+10}</td></tr>)}</tbody></table></div></>;
}
function Fixture() {
  const [open,setOpen]=useState(true), [dialog,setDialog]=useState(false), [nested,setNested]=useState(false);
  const mode=new URLSearchParams(location.search).get("mode");
  return <><div style={{position:"fixed",inset:0,overflow:"hidden"}}>{Array.from({length:80},(_,i)=><div key={i} style={{background:i%2?"#fff":"#000",color:i%2?"#000":"#fff",fontSize:18,whiteSpace:"nowrap"}}>BUSY BACKGROUND | Inventory 12345 | Quantity 987 | Review pending | Inventory 12345 | Quantity 987 | Review pending</div>)}<table style={{position:"absolute",top:0,left:"45%",width:"55%"}}><tbody>{Array.from({length:30},(_,i)=><tr key={i} style={{background:i%2?"#fff":"#000"}}><td><span style={{color:i%2?"#000":"#fff"}}>Background item {i+1}</span></td><td><span style={{color:i%2?"#000":"#fff"}}>987 units</span></td></tr>)}</tbody></table></div>
  {mode==="menus"?<div style={{position:"relative",margin:12,maxWidth:340}}><div className="global-search-shell"><input aria-label="Global search" defaultValue="Sample"/><div className="global-search-results"><button>Sample search result<small>Readable result description</small></button></div></div><details open className="multi-select-control" style={{marginTop:120,minWidth:0}}><summary>Select columns</summary><div className="multi-select-menu"><label><input type="checkbox" defaultChecked/>Inventory quantity</label><label><input type="checkbox"/>Product name</label></div></details></div>:
  mode==="commerce"?<div className="commerce-launcher-backdrop"><section className="commerce-launcher-window"><header><strong>Commerce preview</strong></header><div className="commerce-launcher-body"><Content/></div></section></div>:
  <WorkspaceWindow open={open} onClose={()=>setOpen(false)} title="Doobie workspace" subtitle="Synthetic popup readability review" windowKey="readability" footer={<button className="secondary">Save draft</button>}><button className="secondary" onClick={()=>setDialog(true)}>Open detail</button><button className="secondary" onClick={()=>setNested(true)}>Open nested window</button><Content/><StreamlitDialog open={dialog} onClose={()=>setDialog(false)} title="Detail dialog" subtitle="Synthetic detail" footer={<button className="secondary">Done</button>}><Content/></StreamlitDialog></WorkspaceWindow>}
  <WorkspaceWindow open={nested} onClose={()=>setNested(false)} windowKey="nested-readability" title="Nested window"><p>Nested content remains readable.</p></WorkspaceWindow>
  </>;
}
createRoot(document.getElementById("root")!).render(<Fixture/>);
