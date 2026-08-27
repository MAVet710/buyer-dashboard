import { Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useInventory } from "../hooks/useInventory";
import type { InventoryPackage } from "../types/inventory";
import { ReceiveInventory } from "../components/ReceiveInventory";
import { ProductionReceiveInventory } from "../components/ProductionReceiveInventory";
import { ReceiveHistory } from "../components/ReceiveHistory";
import { AdjustInventory } from "../components/AdjustInventory";
import { PackageLineage } from "../components/PackageLineage";
import { Package360Window } from "../components/Package360Window";
import { PlantInventory } from "../components/PlantInventory";
import { StreamlitDialog } from "../components/StreamlitDialog";
import { Product360Drawer } from "../components/Product360Drawer";
import { PackageQrCode } from "../components/PackageQrCode";
import { PackageStudioPage } from "./PackageStudioPage";
import { apiGet } from "../lib/api";

const RETAIL_VIEWS = ["All Inventory", "Low Stock", "Under 14 DOH", "Slow Movers", "Expiring 90 Days", "Bulk Packages", "Quarantine / Hold"] as const;
const PRODUCTION_VIEWS = ["All Material", "Bulk Flower", "Biomass / Trim", "Extraction Input", "WIP", "Finished Bulk", "Production Ready", "Low Balance", "Quarantine / Hold"] as const;
const RETAIL_PRODUCT_DEFAULTS = ["SKU", "Product", "Material Type", "Room", "Available", "Reserved", "30d Sold", "DOH", "Cost", "Retail", "Margin", "Age", "Attention"];
const RETAIL_PACKAGE_DEFAULTS = ["SKU", "Product", "External Package ID", "Material Type", "Room", "Available", "Unit", "Reserved", "30d Sold", "DOH", "Status", "Attention"];
const PRODUCTION_DEFAULTS = ["SKU", "Product", "External Package ID", "Material Type", "Room", "Available", "Unit", "Status", "Attention"];
const ALL_COLUMNS = ["SKU", "Product", "External Package ID", "Material Type", "Source / Supplier", "Room", "Available", "Unit", "Reserved", "30d Sold", "DOH", "Cost", "Retail", "Margin", "Age", "Days to Expiry", "Status", "Attention"];
const RETAIL_CONTEXT_ROLES = ["dev","admin","buyer","supervisor","operator","qa","read_only","trial"];
const PRODUCTION_CONTEXT_ROLES = ["dev","admin","planner","supervisor","operator","qa"];

type Operation = "retail" | "production";
type Grain = "products" | "packages" | "plants";
type PackageAction = "studio" | "adjust";
type DisplayRow = InventoryPackage & { package_count?: number };

export function InventoryPage({ initialOperation="retail", onNavigate }: { initialOperation?:Operation; onNavigate?:(page:string)=>void } = {}) {
  const account = useQuery({ queryKey:["account-context"], queryFn:({signal})=>apiGet<{user:{role:string};capabilities:{retail:boolean;production:boolean;cultivation:boolean}}>("/api/v1/account/context",signal) });
  const operation:Operation=initialOperation;
  const [grain,setGrain]=useState<Grain>(initialOperation === "retail" ? "products" : "packages");
  const [receiving,setReceiving]=useState(false); const [history,setHistory]=useState(false); const [studio,setStudio]=useState(false); const [receiveFlash,setReceiveFlash]=useState("");
  const [adjusting,setAdjusting]=useState(false); const [lineage,setLineage]=useState(false); const [labels,setLabels]=useState(false); const [product360,setProduct360]=useState(false); const [package360,setPackage360]=useState("");
  const [packageChoice,setPackageChoice]=useState<PackageAction|null>(null); const [actionPackageId,setActionPackageId]=useState("");
  const [search,setSearch]=useState(""); const [view,setView]=useState(initialOperation === "retail" ? "All Inventory" : "All Material"); const [status,setStatus]=useState(""); const [materialType,setMaterialType]=useState(""); const [location,setLocation]=useState(""); const [source,setSource]=useState("");
  const [actionsOpen,setActionsOpen]=useState(false); const [selectedIds,setSelectedIds]=useState<string[]>([]); const [saveViewOpen,setSaveViewOpen]=useState(false); const [viewName,setViewName]=useState("");
  const [savedViews,setSavedViews]=useState<Record<string,{status:string;materialType:string;location:string;source:string}>>(()=>readJson("buyer-dash-inventory-views",{}));
  const defaultColumns = operation === "production" ? PRODUCTION_DEFAULTS : grain === "products" ? RETAIL_PRODUCT_DEFAULTS : RETAIL_PACKAGE_DEFAULTS;
  const [columns,setColumns]=useState<string[]>(defaultColumns);
  const retailEnabled=account.data?.capabilities.retail??true;
  const cultivationEnabled=account.data?.capabilities.cultivation??false;
  const productionEnabled=account.data ? Boolean(account.data.capabilities.production || account.data.capabilities.cultivation) : true;
  const role=account.data?.user.role??"";
  const retailContextAllowed=retailEnabled&&RETAIL_CONTEXT_ROLES.includes(role);
  const productionContextAllowed=productionEnabled&&PRODUCTION_CONTEXT_ROLES.includes(role);
  const receivingAllowed=["dev","admin","buyer","planner","supervisor","operator","qa","trial"].includes(role);
  const auditAllowed=["dev","admin","buyer","supervisor","operator","qa","trial"].includes(role);
  const packageStudioAllowed=["dev","admin","buyer","planner","supervisor","operator","qa"].includes(role);
  const purchasingAllowed=["dev","admin","supervisor","buyer"].includes(role);
  const adjustAllowed=["dev","admin","supervisor","operator","qa"].includes(role);
  const apiView = operation === "retail" && grain === "products" ? "all" : viewKey(view);
  const inventory=useInventory({operation,search,view:apiView,status,materialType,location,source});
  const packageRows=useMemo(()=>inventory.data?.items??[],[inventory.data?.items]);
  const rows=useMemo(()=>operation === "retail" && grain === "products" ? applyRetailView(aggregateProducts(packageRows),view) : packageRows,[grain,operation,packageRows,view]);
  const selected=rows.filter(row=>selectedIds.includes(row.id)); const first=selected[0]??null;
  const selectedPackages=grain==="packages"?selected:packageRows.filter(pkg=>selected.some(row=>row.product_id===pkg.product_id));
  const actionPackage=packageRows.find(pkg=>pkg.id===actionPackageId)??(grain==="packages"?first:null);
  const productPackages=selected.length===1?packageRows.filter(pkg=>pkg.product_id===selected[0].product_id):[];
  const facets=inventory.data?.facets; const views=operation === "production" ? PRODUCTION_VIEWS : RETAIL_VIEWS;

  useEffect(()=>{
    if(!account.data)return;
    if(operation==="production"&&!productionContextAllowed){if(retailContextAllowed)onNavigate?.("Inventory");return;}
    if(operation==="retail"&&!retailContextAllowed){if(productionContextAllowed)onNavigate?.("Production Inventory");return;}
    if(!cultivationEnabled&&grain==="plants")setGrain("packages");
  },[account.data,cultivationEnabled,grain,onNavigate,operation,productionContextAllowed,retailContextAllowed]);
  useEffect(()=>{
    setReceiveFlash("");
    setGrain(operation==="retail"?"products":"packages");
    setView(operation==="retail"?"All Inventory":"All Material");
    setColumns(operation==="retail"?RETAIL_PRODUCT_DEFAULTS:PRODUCTION_DEFAULTS);
    setSelectedIds([]);setActionPackageId("");setPackageChoice(null);setPackage360("");setProduct360(false);
  },[operation]);
  useEffect(()=>{setSelectedIds([]);setActionPackageId("");setPackageChoice(null);setPackage360("")},[grain,view,search,status,materialType,location,source]);
  useEffect(()=>{if(!receivingAllowed)setReceiving(false);if(!packageStudioAllowed){setStudio(false);setPackageChoice(choice=>choice==="studio"?null:choice)}if(!adjustAllowed){setAdjusting(false);setPackageChoice(choice=>choice==="adjust"?null:choice)}},[adjustAllowed,packageStudioAllowed,receivingAllowed]);
  function clearFilters(){setSearch("");setStatus("");setMaterialType("");setLocation("");setSource("");setView(operation==="retail"?"All Inventory":"All Material");}
  function saveCurrentView(){const name=viewName.trim();if(!name)return;const next={...savedViews,[name]:{status,materialType,location,source}};setSavedViews(next);localStorage.setItem("buyer-dash-inventory-views",JSON.stringify(next));setSaveViewOpen(false);setViewName("");}
  function applySaved(name:string){const saved=savedViews[name];if(!saved)return;setStatus(saved.status);setMaterialType(saved.materialType);setLocation(saved.location);setSource(saved.source);}
  function toggle(id:string){setSelectedIds(ids=>ids.includes(id)?ids.filter(value=>value!==id):[...ids,id]);}
  function stagePo(){if(!purchasingAllowed)return;sessionStorage.setItem("buyer-dash-po-inventory-selection",JSON.stringify(selected.map(row=>({product_id:row.product_id,sku:row.sku,description:row.product_name,quantity:Math.max(1,Math.ceil((row.daily_velocity||0)*21-row.available)),price:row.unit_cost}))));onNavigate?.("Purchase Orders");}
  function auditSelected(){if(!auditAllowed)return;sessionStorage.setItem("buyer-dash-audit-product-focus",JSON.stringify(selected.map(row=>({product_id:row.product_id,sku:row.sku,product_name:row.product_name,lot_id:grain==="packages"?row.id:""}))));onNavigate?.("Inventory Audits");}
  function openPackageAction(action:PackageAction){
    if(selected.length!==1)return;
    if(action==="studio"&&!packageStudioAllowed)return;
    if(action==="adjust"&&!adjustAllowed)return;
    const candidates=grain==="packages"&&first?[first]:productPackages;
    if(candidates.length===1){setActionPackageId(candidates[0].id);if(action==="studio")setStudio(true);else setAdjusting(true);return;}
    if(candidates.length>1)setPackageChoice(action);
  }
  function choosePackage(pkg:InventoryPackage){const action=packageChoice;setActionPackageId(pkg.id);setPackageChoice(null);if(action==="studio"&&packageStudioAllowed)setStudio(true);if(action==="adjust"&&adjustAllowed)setAdjusting(true);}
  function closeStudio(){setStudio(false);setActionPackageId("");}
  function closeAdjust(){setAdjusting(false);setActionPackageId("");}

  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">{operation === "retail" ? "RETAIL OPS" : "PRODUCTION OPS"}</div><h1>Inventory</h1><p>{operation === "retail" ? "Search, decide, receive, transform, and audit without leaving Inventory." : "Bulk cannabis materials, lots, rooms, receiving, transformations, and audits."}</p></div><span className="access-badge">{rows.length.toLocaleString()} loaded row(s)</span></div>
    {receiveFlash?<div className="success-banner">{receiveFlash}</div>:null}
    <section className="inventory-panel inventory-command-toolbar"><div className="grain-control" role="group" aria-label="View">{operation==="retail"?<><button className={grain==="products"?"active":""} onClick={()=>{setGrain("products");setColumns(RETAIL_PRODUCT_DEFAULTS)}}>Products</button><button className={grain==="packages"?"active":""} onClick={()=>{setGrain("packages");setColumns(RETAIL_PACKAGE_DEFAULTS)}}>Packages</button></>:<><button className={grain==="packages"?"active":""} onClick={()=>setGrain("packages")}>Packages</button>{cultivationEnabled?<button className={grain==="plants"?"active":""} onClick={()=>setGrain("plants")}>Plants</button>:null}</>}</div><button className="secondary" onClick={()=>setActionsOpen(open=>!open)}>Actions</button><button className="secondary" onClick={()=>setHistory(true)}>Receive history</button><button className="primary" disabled={!receivingAllowed} title={receivingAllowed?"Receive inventory into the active facility":"Receiving permission required"} onClick={()=>{if(!receivingAllowed)return;setReceiveFlash("");setReceiving(true)}}>Receive inventory</button></section>
    {grain==="plants"&&operation==="production"?<section className="inventory-panel plant-panel"><PlantInventory/></section>:<>
      <section className="inventory-panel filters"><label className="search"><Search size={17}/><input value={search} onChange={event=>setSearch(event.target.value)} placeholder={operation==="production"?"Material, package, lot, room…":"Product, SKU, package, strain, vendor…"}/></label><Filter label="Status" value={status} values={facets?.statuses} onChange={setStatus}/><Filter label={operation==="production"?"Source":"Vendor"} value={source} values={facets?.sources} onChange={setSource}/><select aria-label="View" value={view} onChange={event=>{const value=event.target.value;setView(value);applySaved(value)}}>{views.map(value=><option key={value}>{value}</option>)}{Object.keys(savedViews).map(value=><option key={value}>{value}</option>)}</select><Filter label="Room" value={location} values={facets?.locations} onChange={setLocation}/><Filter label={operation==="production"?"Material type":"Category"} value={materialType} values={facets?.material_types} onChange={setMaterialType}/><button className="secondary" onClick={clearFilters}>Clear filters</button></section>
      {actionsOpen?<section className="inventory-panel audit-actions"><button className="secondary" onClick={()=>onNavigate?.("Inventory Audits")}>Open audits</button><button className="secondary" disabled={!packageStudioAllowed} title={packageStudioAllowed?"Open Package Studio":"Package Studio permission required"} onClick={()=>{if(!packageStudioAllowed)return;setActionPackageId("");setStudio(true)}}>Package Studio</button><button className="secondary" onClick={clearFilters}>Reset filters</button><button className="secondary" onClick={()=>setSaveViewOpen(true)}>💾 Save current view</button></section>:null}
      <details className="streamlit-expander"><summary>📊 Columns</summary><div className="streamlit-expander-body"><div className="audit-actions"><button className="secondary" onClick={()=>setColumns(ALL_COLUMNS)}>Show all</button><button className="secondary" onClick={()=>setColumns(defaultColumns)}>Show defaults</button><button className="secondary" onClick={()=>setColumns(operation==="production"?["SKU","Product","Available","Room"]:["SKU","Product","Available","Source / Supplier"])}>Compact (essentials only)</button></div><div className="column-checks">{ALL_COLUMNS.map(column=><label className="toggle" key={column}><input type="checkbox" checked={columns.includes(column)} onChange={event=>setColumns(current=>event.target.checked?[...current,column]:current.filter(value=>value!==column))}/>{column}</label>)}</div></div></details>
      <div className="inventory-legend">{operation==="production"?<><span>Production ready</span><span>Low balance</span><span>Hold</span></>:<><span>Reorder now</span><span>Aging</span><span>Expiring</span><span>Hold</span></>}</div>
      {selected.length?<section className="inventory-panel selection-toolbar"><strong>{selected.length} selected</strong>{operation==="retail"&&selected.length===1?<button className="primary" onClick={()=>setProduct360(true)}>Product 360</button>:null}{grain==="packages"&&selected.length===1?<button className="primary" onClick={()=>setPackage360(first?.package_id||first?.id||"")}>Package 360</button>:null}<button className="secondary" disabled={!auditAllowed} title={auditAllowed?"Start or focus an inventory audit":"Audit change permission required"} onClick={auditSelected}>Audit</button>{operation==="retail"?<button className="secondary" disabled={!purchasingAllowed} title={purchasingAllowed?"Stage the selected item(s) for a purchase order":"Purchasing permission required"} onClick={stagePo}>Add to PO</button>:null}<button className="secondary" disabled={selected.length!==1||selectedPackages.length===0||!packageStudioAllowed} title={!packageStudioAllowed?"Package Studio permission required":grain==="products"?"Choose the underlying package to open":"Open the selected package"} onClick={()=>openPackageAction("studio")}>Work on package</button><button className="secondary" disabled={selectedPackages.length===0} title={grain==="products"?"Print labels for every package under the selected product(s)":"Print labels for the selected package(s)"} onClick={()=>setLabels(true)}>Print labels</button><button className="secondary" disabled={selected.length!==1||selectedPackages.length===0||!adjustAllowed} title={!adjustAllowed?"Adjustment permission required":grain==="products"?"Choose the underlying package to adjust":"Adjust the selected package"} onClick={()=>openPackageAction("adjust")}>Adjust</button><button className="secondary" onClick={()=>downloadCsv(selected,columns)}>Export selected</button>{grain==="packages"&&selected.length===1?<button className="secondary" onClick={()=>setLineage(true)}>View lineage</button>:null}</section>:null}
      {inventory.isError?<div className="state error">{inventory.error.message}</div>:null}{inventory.isLoading?<div className="state">Loading durable inventory…</div>:null}{!inventory.isLoading&&!inventory.isError?<InventoryTable rows={rows} columns={columns} selected={selectedIds} onToggle={toggle}/>:null}
      {!inventory.isLoading&&!inventory.isError?<p className="inventory-total">Displaying {rows.length.toLocaleString()} row(s) · {rows.reduce((sum,row)=>sum+row.available,0).toLocaleString(undefined,{maximumFractionDigits:1})} available</p>:null}
    </>}
    {receiving&&receivingAllowed?(operation==="production"?<ProductionReceiveInventory onClose={()=>setReceiving(false)} onReceived={setReceiveFlash}/>:<ReceiveInventory operation="retail" onClose={()=>setReceiving(false)}/>):null}{history?<ReceiveHistory operation={operation} onClose={()=>setHistory(false)}/>:null}{adjusting&&adjustAllowed&&actionPackage?<AdjustInventory operation={operation} item={actionPackage} onClose={closeAdjust}/>:null}{lineage&&first?<PackageLineage operation={operation} item={first} onClose={()=>setLineage(false)}/>:null}
    <StreamlitDialog open={Boolean(packageChoice)} onClose={()=>setPackageChoice(null)} eyebrow="Inventory" title={packageChoice==="adjust"?"Choose package to adjust":"Choose package to work on"} subtitle={first?`${first.product_name} has ${productPackages.length} package(s).`:"Select a package."}><div className="audit-actions package-choice-list">{productPackages.map(pkg=><button type="button" className="secondary" key={pkg.id} onClick={()=>choosePackage(pkg)}><strong>{pkg.package_id||pkg.id}</strong><span>{round(pkg.available)} {pkg.unit} · {pkg.location||"No room"}</span></button>)}</div></StreamlitDialog>
    <StreamlitDialog open={studio&&packageStudioAllowed} onClose={closeStudio} eyebrow="Inventory" title="Package Studio" subtitle={actionPackage?`${actionPackage.product_name} · ${actionPackage.package_id}`:"Break down, pack down, build, sample, correct, and trace packages."}><PackageStudioPage initialLotId={actionPackage?.id}/></StreamlitDialog>
    <StreamlitDialog open={labels} onClose={()=>setLabels(false)} eyebrow="Inventory control" title="Print inventory labels" subtitle={grain==="products"?`${selectedPackages.length} underlying package label(s) from ${selected.length} selected product(s).`:undefined} footer={<button className="primary" onClick={()=>window.print()}>Print labels</button>}><div className="label-sheet">{selectedPackages.map(row=><article className="inventory-label" key={row.id}><strong>{row.product_name}</strong><span>{row.package_id}</span><PackageQrCode value={row.package_id}/><b>{row.available.toLocaleString()} {row.unit}</b><small>{row.location} · {row.status}</small></article>)}</div></StreamlitDialog>
    <StreamlitDialog open={saveViewOpen} onClose={()=>setSaveViewOpen(false)} eyebrow="Inventory" title="Save this view for quick access" footer={<button className="primary" disabled={!viewName.trim()} onClick={saveCurrentView}>Save</button>}><label>View name<input value={viewName} onChange={event=>setViewName(event.target.value)} placeholder={operation==="production"?"My production-ready flower":"My low-stock flower"}/></label></StreamlitDialog>
    <Product360Drawer productId={first?.product_id??""} open={product360} onClose={()=>setProduct360(false)} onNavigate={page=>onNavigate?.(page)}/>
    <Package360Window code={package360} open={Boolean(package360)} onClose={()=>setPackage360("")} onNavigate={page=>onNavigate?.(page)}/>
  </div>;
}

function InventoryTable({rows,columns,selected,onToggle}:{rows:DisplayRow[];columns:string[];selected:string[];onToggle:(id:string)=>void}){return <section className="inventory-panel"><div className="table-wrap"><table><thead><tr><th aria-label="Select rows"></th>{columns.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.id} className={selected.includes(row.id)?"selected-row":""} onClick={()=>onToggle(row.id)}><td><input type="checkbox" aria-label={`Select ${row.product_name}`} checked={selected.includes(row.id)} onChange={()=>onToggle(row.id)} onClick={event=>event.stopPropagation()}/></td>{columns.map(column=><td key={column}>{cell(row,column)}</td>)}</tr>)}</tbody></table>{!rows.length?<div className="empty">No inventory matches the current view and filters.</div>:null}</div></section>}
function cell(row:DisplayRow,column:string){const values:Record<string,unknown>={"SKU":row.sku,"Product":row.product_name,"External Package ID":row.package_count?`${row.package_count} package(s)`:row.package_id,"Material Type":row.material_type,"Source / Supplier":row.source_name||"—","Room":row.location,"Available":round(row.available),"Unit":row.unit,"Reserved":round(row.reserved),"30d Sold":round(row.sold_30d),"DOH":row.days_on_hand==null?"—":round(row.days_on_hand),"Cost":money(row.unit_cost),"Retail":money(row.retail_price),"Margin":row.margin_pct==null?"—":`${round(row.margin_pct)}%`,"Age":row.age_days==null?"—":round(row.age_days),"Days to Expiry":row.days_to_expiry==null?"—":round(row.days_to_expiry),"Status":row.status,"Attention":row.attention};return String(values[column]??"—")}
function aggregateProducts(rows:InventoryPackage[]):DisplayRow[]{const groups=new Map<string,InventoryPackage[]>();for(const row of rows)groups.set(row.product_id,[...(groups.get(row.product_id)??[]),row]);return [...groups.values()].map(items=>{const first=items[0];const available=items.reduce((sum,row)=>sum+row.available,0);const reserved=items.reduce((sum,row)=>sum+row.reserved,0);const sold=Math.max(...items.map(row=>row.sold_30d),0);const velocity=sold/30;const held=items.some(row=>row.attention==="Hold");const age=Math.max(...items.map(row=>row.age_days??0));const expiries=items.map(row=>row.days_to_expiry).filter((value):value is number=>value!=null);const doh=velocity>0?available/velocity:null;const attention=held?"Hold":available<=0||doh!=null&&doh<=7?"Reorder now":expiries.some(value=>value>=0&&value<=90)?"Expiring":age>=60?"Aging":"Healthy";return {...first,id:`product:${first.product_id}`,package_id:"",available,reserved,usable:Math.max(0,available-reserved),sold_30d:sold,daily_velocity:velocity,days_on_hand:doh,age_days:age,days_to_expiry:expiries.length?Math.min(...expiries):null,attention,package_count:items.length}})}
function applyRetailView(rows:DisplayRow[],view:string){if(view==="Low Stock")return rows.filter(row=>(row.days_on_hand!=null&&row.days_on_hand<=7)||row.available<=0);if(view==="Under 14 DOH")return rows.filter(row=>row.days_on_hand!=null&&row.days_on_hand<=14);if(view==="Slow Movers")return rows.filter(row=>row.available>0&&(row.sold_30d<=2||(row.age_days??0)>=60||(row.days_on_hand??0)>=60));if(view==="Expiring 90 Days")return rows.filter(row=>row.days_to_expiry!=null&&row.days_to_expiry>=0&&row.days_to_expiry<=90);if(view==="Bulk Packages")return rows.filter(row=>["g","gram","grams","kg","oz","ounce","ounces","lb","pound","pounds"].includes(row.unit.toLowerCase())||/(bulk|flower|material)/i.test(row.material_type));if(view==="Quarantine / Hold")return rows.filter(row=>row.attention==="Hold");return rows}
function Filter({label,value,values=[],onChange}:{label:string;value:string;values?:string[];onChange:(value:string)=>void}){return <select aria-label={label} value={value} onChange={event=>onChange(event.target.value)}><option value="">All {label.toLowerCase()}</option>{values.map(item=><option key={item}>{item}</option>)}</select>}
function viewKey(value:string){return value.toLowerCase().replaceAll(" / ","-").replaceAll(" ","-")}
function round(value:number){return value.toLocaleString(undefined,{maximumFractionDigits:1})} function money(value:number){return value.toLocaleString(undefined,{style:"currency",currency:"USD",maximumFractionDigits:2})}
function readJson<T>(key:string,fallback:T):T{try{return JSON.parse(localStorage.getItem(key)||"") as T}catch{return fallback}}
function downloadCsv(rows:DisplayRow[],columns:string[]){const quote=(value:string)=>`"${value.replaceAll('"','""')}"`;const csv=[columns.map(quote).join(","),...rows.map(row=>columns.map(column=>quote(String(cell(row,column)))).join(","))].join("\n");const link=document.createElement("a");link.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));link.download="buyer_dash_inventory_selected.csv";link.click();URL.revokeObjectURL(link.href)}