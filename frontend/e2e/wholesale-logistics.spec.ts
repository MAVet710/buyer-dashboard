import { expect, test } from "@playwright/test";

for (const width of [390, 1280]) {
  test(`dispatch partial delivery and return at ${width}px`, async ({page}) => {
    await page.setViewportSize({width,height:900});
    const account={user:{display_name:"Driver",email:"driver@example.test",role:"dev",must_change_password:false},organization:{id:"org",name:"Dispatch QA",slug:"dispatch-qa"},facility_id:"facility",capabilities:{commercial:true,production:true,retail:false,cultivation:false},facilities:[{id:"facility",name:"Main",code:"MAIN",capabilities:{commercial:true,production:true,retail:false,cultivation:false}}]};
    const run={id:"run",service_date:"2026-09-25",driver_name:"Test Driver",driver_license_number:"DL-123",vehicle_make:"Ford",vehicle_model:"Transit",vehicle_license_plate_number:"QA-10",status:"arrived",notes:"",version:1,stop_count:1};
    const stop={work_item_id:null as string|null,id:"stop",sequence:1,shipment_number:"SHIP-10",order_number:"ORDER-10",partner_name_snapshot:"QA Customer",manifest_reference:"MAN-10",status:"arrived",address_snapshot:"10 Main Street",contact_snapshot:"Receiver / 555-0100",planned_start:null,planned_end:null,notes:"Loading door",recipient_name:"",delivered_at:null as string|null,outcome_notes:"",acknowledgment_name:"",allowed_statuses:["delivered","partial","rejected"]};
    const work={id:"work-1",title:"Reconcile returned dispatch stop",description:"Review refused units",status:"open",priority:"medium",version:1,assignee_id:null,due_at:null,blocked_reason:"",notes:"",evidence:"",workspace:"Wholesale",entity_type:"wholesale_dispatch_stop",entity_id:"stop",route:"/wholesale?tab=fulfillment&dispatch=run&stop=stop"};
    const writes:Record<string,unknown>[]=[];
    await page.route("**/api/**",async route=>{
      const path=new URL(route.request().url()).pathname;
      let body:unknown={};
      if (path==="/api/v1/account/context") body=account;
      else if(path==="/api/v1/account/access-options") body={organizations:[{...account.organization,facilities:account.facilities}],organization_id:"org",facility_id:"facility"};
      else if(path==="/api/v1/wholesale-logistics/runs") body={runs:[run],has_more:false};
      else if(path==="/api/v1/wholesale-logistics/runs/run") body={...run,stops:[stop]};
      else if(path.endsWith("/create-reconciliation-work")) { stop.work_item_id=work.id;run.version++;body={work_item_id:work.id,message:"Reconciliation work created."}; }
      else if(path==="/api/v1/work/work-1") body=work;
      else if(path==="/api/v1/work" || path==="/api/v1/work/assignees") body={items:[],has_more:false};
      else if(path.endsWith("/stops/stop/status")) {
        const data=route.request().postDataJSON(); writes.push(data);
        expect(data.version).toBe(run.version);
        stop.status=data.status;run.status=data.status;run.version++;
        if(data.status==="partial") {stop.recipient_name=data.recipient_name;stop.delivered_at="2026-09-25T14:00:00Z";stop.allowed_statuses=["returned"];stop.outcome_notes=data.outcome_notes;}
        else {stop.allowed_statuses=[];stop.outcome_notes+="\n"+data.outcome_notes;}
        body={message:"Saved.",version:run.version};
      } else {await route.fulfill({status:503,json:{detail:"Not needed for isolated dispatch acceptance"}});return;}
      await route.fulfill({status:200,json:body});
    });
    await page.addInitScript(()=>{
      localStorage.setItem("buyer-dash-organization","org"); localStorage.setItem("buyer-dash-facility","facility");
      localStorage.setItem("buyer-dash-operation","Production Ops");
      if (location.pathname === "/") sessionStorage.setItem("buyer-dash-pending-page","Wholesale Ops");
    });
    await page.goto(process.env.DISPATCH_TEST_URL??"http://127.0.0.1:4173");
    await page.getByRole("tab",{name:"Logistics",exact:true}).click();
    await page.getByText("Create dispatch run",{exact:true}).click();
    for(const name of ["Driver license number (optional)","Vehicle make (optional)","Vehicle model (optional)"]) {
      await expect(page.getByLabel(name,{exact:true})).toBeVisible();
      await expect(page.getByLabel(name,{exact:true})).not.toHaveAttribute("required");
    }
    await page.getByRole("button",{name:/Test Driver/}).click();
    await expect(page.getByText("Driver license: DL-123 | Vehicle: Ford Transit",{exact:true})).toBeVisible();
    await expect(page.getByText("Manifest: MAN-10",{exact:false})).toBeVisible();
    await page.getByLabel("Next status").selectOption("partial");
    await page.getByLabel("Recipient name",{exact:true}).fill("Receiver");
    await page.getByLabel("Exception notes (required)").fill("Accepted 3, refused 2");
    await page.getByRole("button",{name:"Record partial",exact:true}).click();
    await expect(page.getByText("Received by Receiver",{exact:false})).toBeVisible();
    await page.getByLabel("Exception notes (required)").fill("Remainder returned for review");
    await page.getByRole("button",{name:"Record returned",exact:true}).click();
    await expect(page.getByLabel("Next status")).toHaveCount(0);
    expect(writes.map(row=>row.status)).toEqual(["partial","returned"]);
    await expect(page.getByText("Received by Receiver",{exact:false})).toBeVisible();
    await page.getByRole("button",{name:"Create reconciliation work",exact:true}).click();
    await expect(page.getByRole("button",{name:"Create reconciliation work",exact:true})).toHaveCount(0);
    await expect(page.getByRole("link",{name:"Open Work",exact:true})).toHaveAttribute("href","/work?item=work-1");
    await page.getByRole("link",{name:"Open Work",exact:true}).click();
    await expect(page.getByRole("heading",{name:"Work Queue",exact:true})).toBeVisible();
    await page.getByRole("button",{name:"Open linked workspace",exact:true}).click();
    await expect(page).toHaveURL(/wholesale\?tab=fulfillment&dispatch=run&stop=stop/);
    await expect(page.getByRole("tab",{name:"Logistics",exact:true})).toHaveAttribute("aria-selected","true");
    await expect(page.locator("#dispatch-stop-stop")).toHaveClass(/dispatch-stop-focused/);
    await page.reload();
    await expect(page.locator("#dispatch-stop-stop")).toHaveClass(/dispatch-stop-focused/);
    await expect(page.getByText("Received by Receiver",{exact:false})).toBeVisible();
    const dimensions=await page.locator(".dispatch-panel").evaluate(el=>({width:el.clientWidth,scroll:el.scrollWidth}));
    expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width+1);
  });
}
