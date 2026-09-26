import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { RunDetail, StopOutcome } from "./WholesaleLogisticsPanel";

vi.mock("../lib/api", () => ({apiGet:vi.fn(), apiPost:vi.fn()}));
const stop = {work_item_id:null as string|null,id:"stop", sequence:1, shipment_number:"S-10", order_number:"O-10", partner_name_snapshot:"Customer", manifest_reference:"MAN-10", status:"arrived", address_snapshot:"10 Main Street", contact_snapshot:"Receiver / 555-0100", planned_start:null, planned_end:null, notes:"Use loading door", recipient_name:"", delivered_at:null as string|null, outcome_notes:"", acknowledgment_name:"", allowed_statuses:["delivered","partial","rejected"]};
function renderRun(overrides:Partial<typeof stop> = {}) {
  const client=new QueryClient({defaultOptions:{queries:{retry:false,staleTime:Infinity}}});
  client.setQueryData(["dispatch","run","run"], {id:"run",service_date:"2026-09-25",driver_name:"Driver",driver_license_number:"DL-123",vehicle_make:"Ford",vehicle_model:"Transit",vehicle_license_plate_number:"PLATE",status:"arrived",notes:"",version:2,stops:[{...stop,...overrides}]});
  return renderToStaticMarkup(<QueryClientProvider client={client}><RunDetail id="run"/></QueryClientProvider>);
}
describe("dispatch driver workflow",()=>{
  it("explicitly creates reconciliation Work or opens its canonical detail",()=>{
    expect(renderRun()).not.toContain("Create reconciliation work");
    expect(renderRun({status:"rejected"})).toContain("Create reconciliation work");
    const linked=renderRun({status:"returned",work_item_id:"work-1"});
    expect(linked).toContain('href="/work?item=work-1"');
    expect(linked).not.toContain("Create reconciliation work");
  });
  it("shows operational snapshots and keeps the new edit fields optional",()=>{
    const html=renderRun({status:"planned",allowed_statuses:["loaded"]});
    for(const value of ["DL-123","Ford","Transit"]) expect(html).toContain(value);
    for(const name of ["driver_name","vehicle_license_plate_number","driver_license_number","vehicle_make","vehicle_model"]) {
      expect(html).toContain(`name="${name}"`);
      expect(html).not.toMatch(new RegExp(`<input(?=[^>]*name="${name}")(?=[^>]*required="")[^>]*>`));
    }
  });
  it("renders canonical references and contact snapshots with delivery controls",()=>{
    const html=renderRun();
    for (const expected of ["S-10","O-10","MAN-10","10 Main Street","Receiver / 555-0100","Recipient name","Record delivered"]) expect(html).toContain(expected);
    expect(html).not.toContain("Move up");
    expect(html).not.toContain("Add shipment stop");
  });
  it("requires recipient evidence for accepted outcomes and notes for exceptions",()=>{
    const delivered=renderToStaticMarkup(<StopOutcome stop={stop} onSave={()=>{}}/>);
    expect(delivered).toMatch(/<input(?=[^>]*name="recipient_name")(?=[^>]*required="")[^>]*>/);
    const rejected=renderToStaticMarkup(<StopOutcome stop={{...stop,allowed_statuses:["rejected"]}} onSave={()=>{}}/>);
    expect(rejected).toMatch(/<textarea(?=[^>]*name="outcome_notes")(?=[^>]*required="")[^>]*>/);
    expect(rejected).not.toContain('name="recipient_name"');
    expect(rejected).not.toContain('type="file"');
  });
  it("retains POD and exception notes when a partial delivery is returned",()=>{
    const html=renderRun({status:"returned",recipient_name:"Receiver",delivered_at:"2026-09-25T14:00:00Z",acknowledgment_name:"Receiver",outcome_notes:"partial: Two refused\nreturned: Remainder received",allowed_statuses:[]});
    expect(html).toContain("Received by Receiver");
    expect(html).toContain("Two refused");
    expect(html).toContain("Remainder received");
    expect(html).not.toContain("Next status");
  });
});
