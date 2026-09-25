import { expect, test } from "@playwright/test";
import type { DurablePlan } from "../src/pages/WhiteLabelRepackPage";

test.use({baseURL:"http://127.0.0.1:4187"});

for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
  test(`durable save, reload, approval and package handoff at ${viewport.width}px`,async({page})=>{
    await page.setViewportSize(viewport);
    let saved:DurablePlan|null=null;
    const writes:string[]=[];
    const account={user:{id:"planner",display_name:"Planner",email:"planner@example.test",role:"planner",must_change_password:false},organization:{id:"org",name:"Repack test",slug:"org"},facility_id:"facility",capabilities:{retail:true,production:true,cultivation:false,commercial:false},facilities:[{id:"facility",name:"Production",code:"P",capabilities:{retail:true,production:true,cultivation:false,commercial:false}}]};
    await page.addInitScript(()=>{localStorage.setItem("buyer-dash-organization","org");localStorage.setItem("buyer-dash-facility","facility");localStorage.setItem("buyer-dash-operation","Production Ops")});
    await page.route("**/api/v1/**",async route=>{
      const request=route.request(),path=new URL(request.url()).pathname;
      let body:unknown={};
      if(request.method()!=="GET")writes.push(path);
      if(path==="/api/v1/account/context")body=account;
      else if(path==="/api/v1/account/access-options")body={organizations:[{...account.organization,facilities:account.facilities}],organization_id:"org",facility_id:"facility"};
      else if(path==="/api/v1/white-label/sources")body=[{id:"source",lot_code:"BULK-1",package_id:"EXISTING-TAG",product_name:"Bulk flower",status:"available"}];
      else if(path==="/api/v1/white-label/plans"&&request.method()==="POST"){
        const input=request.postDataJSON();
        saved={...input,id:"saved-plan",revision:1,status:"draft",production_order_id:null,execution_status:null,source:{lot_code:"BULK-1",quantity:100,unit:"g"},economics:{outputs:[{package_size_g:3.5,units:14,packaged_g:49}]}};
        body=saved;
      }else if(path==="/api/v1/white-label/plans")body=saved?[saved]:[];
      else if(path==="/api/v1/white-label/plans/saved-plan/approve"&&saved){saved={...saved,status:"approved",revision:2,production_order_id:"canonical-run",execution_status:"draft"};body=saved}
      else if(path==="/api/v1/white-label/plans/saved-plan")body=saved;
      else if(path==="/api/v1/package-studio/workspace")body={lots:[{lot_id:"source",lot_code:"BULK-1",compliance_package_id:"EXISTING-TAG",product_id:"bulk",product_name:"Bulk flower",sku:"BULK",balance:1000,unit:"g",location_code:"VAULT"}],products:[],runs:[],can_commit:true};
      else if(path==="/api/v1/search")body={results:[]};
      await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(body)});
    });
    await page.goto("/production/repack");
    await page.getByLabel("Scenario Name",{exact:true}).fill("Durable repack");
    await page.getByRole("combobox",{name:"Existing source inventory",exact:true}).selectOption("source");
    await page.getByLabel("Bulk Weight *",{exact:true}).fill("100");
    await page.getByRole("button",{name:"Save durable plan",exact:true}).click();
    await expect(page.getByText("Saved durable plan: Durable repack",{exact:true})).toBeVisible();
    await page.getByLabel("Bulk Weight *",{exact:true}).fill("101");
    await expect(page.getByRole("button",{name:"Approve plan",exact:true})).toBeDisabled();
    await page.reload();
    await expect(page.getByLabel("Bulk Weight *",{exact:true})).toHaveValue("100");
    await page.getByRole("button",{name:"Approve plan",exact:true}).click();
    await expect(page.getByRole("link",{name:"Production Run 360",exact:true})).toHaveAttribute("href","/production/runs/canonical-run");
    await page.reload();
    await expect(page.getByRole("button",{name:"Approve plan",exact:true})).toBeDisabled();
    await page.getByRole("link",{name:"Package Studio",exact:true}).click();
    await expect(page.getByRole("heading",{name:"White Label execution handoff: Durable repack",exact:true})).toBeVisible();
    await expect(page.getByText("BULK-1: 100 g. Status: approved.",{exact:true})).toBeVisible();
    expect(writes).toEqual(["/api/v1/white-label/plans","/api/v1/white-label/plans/saved-plan/approve"]);
  });
}
