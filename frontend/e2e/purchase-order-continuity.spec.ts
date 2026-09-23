import { expect, test } from "@playwright/test";

test("inventory handoff creates one saved PO that reopens and exports from its record",async({page})=>{
  const account={user:{id:"buyer",display_name:"Buyer",email:"buyer@example.test",role:"buyer",must_change_password:false},organization:{id:"po-org",name:"PO organization",slug:"po-org"},facility_id:"po-facility",capabilities:{retail:true,production:false,cultivation:false,commercial:false},facilities:[{id:"po-facility",name:"Retail facility",code:"RETAIL",capabilities:{retail:true,production:false,cultivation:false,commercial:false}}]};
  const writes:Array<Record<string,unknown>>=[];
  const pdfPaths:string[]=[];
  let saved:Record<string,unknown>|null=null;
  let savedLines:Array<Record<string,unknown>>=[];
  await page.addInitScript(()=>{
    localStorage.setItem("buyer-dash-organization","po-org");localStorage.setItem("buyer-dash-facility","po-facility");localStorage.setItem("buyer-dash-operation","Retail Ops");localStorage.setItem("buyer-dash-data-mode","Uploads");
    sessionStorage.setItem("buyer-dash-po-inventory-selection",JSON.stringify([{product_id:"product-one",sku:"WRONG",description:"Old uploaded description",quantity:3,price:999}]));
  });
  await page.route("**/api/v1/**",async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    let body:unknown={};
    if(path==="/api/v1/account/context")body=account;
    else if(path==="/api/v1/account/access-options")body={organizations:[{...account.organization,facilities:account.facilities}],organization_id:"po-org",facility_id:"po-facility"};
    else if(path==="/api/v1/purchasing/workspace")body={recommendations:[{product_id:"product-one",sku:"ONE",product_name:"Canonical product",unit:"unit",unit_cost:12.5,suggested_quantity:3}],vendors:[{id:"vendor-one",name:"Canonical vendor",license_or_registration:"VENDOR-TEST",payment_terms:"Net 30"}],open_purchase_orders:[]};
    else if(path==="/api/v1/purchasing/purchase-orders"&&request.method()==="POST"){
      const payload=request.postDataJSON() as Record<string,unknown>;writes.push(payload);
      saved={id:"saved-po",order_number:payload.order_number,status:"draft",order_type:"purchase",order_date:payload.order_date,due_at:null,currency:"USD",notes:payload.notes,partner_name:"Canonical vendor"};
      savedLines=(payload.lines as Array<Record<string,unknown>>).map((line,index)=>({...line,id:`line-${index}`,sku_snapshot:"ONE",fulfilled_quantity:0}));
      body={id:"saved-po",order_number:payload.order_number,status:"draft"};
    }else if(path==="/api/v1/purchasing/purchase-orders")body={items:saved?[saved]:[],total:saved?1:0,has_more:false};
    else if(path==="/api/v1/purchasing/purchase-orders/saved-po")body={order:saved,lines:savedLines,vendor_name:"Canonical vendor",facility_name:"Retail facility",total:"37.50"};
    else if(path==="/api/v1/purchasing/purchase-orders/saved-po/pdf"){
      expect(request.method()).toBe("GET");expect(request.postData()).toBe(null);pdfPaths.push(path);
      await route.fulfill({status:200,contentType:"application/pdf",body:"%PDF-1.4\n% Synthetic browser download fixture; the real renderer is covered by backend tests.\n%%EOF"});return;
    }else if(path==="/api/v1/search")body={results:[]};
    else if(request.method()!=="GET"){
      await route.fulfill({status:500,contentType:"application/json",body:JSON.stringify({detail:"Unexpected mutation"})});return;
    }
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(body)});
  });
  await page.goto("/buying/purchase-orders");
  await expect(page.getByRole("heading",{name:"Draft purchase order",exact:true})).toBeVisible();
  await expect(page.getByLabel("Quantity for ONE")).toHaveValue("3");
  await expect(page.getByLabel("Price for ONE")).toHaveValue("12.5");
  await page.getByLabel("Vendor",{exact:true}).selectOption("vendor-one");
  await page.getByLabel("PO number",{exact:true}).fill("PO-TEST-ONE");
  await page.getByLabel("Notes",{exact:true}).fill("Preserve delivery instructions");
  await page.getByRole("checkbox",{name:/I reviewed the facility/}).check();
  await page.getByRole("button",{name:"Save draft purchase order",exact:true}).click();
  await expect(page).toHaveURL(/po=saved-po/);
  expect(writes).toHaveLength(1);
  expect(writes[0].lines).toEqual([{product_id:"product-one",description:"Canonical product",quantity:3,unit:"unit",unit_price:12.5}]);
  expect(await page.evaluate(()=>sessionStorage.getItem("buyer-dash-po-inventory-selection"))).toBe(null);
  await page.reload();
  await expect(page.getByRole("heading",{name:"PO-TEST-ONE · draft"})).toBeVisible();
  await expect(page.getByText("Preserve delivery instructions",{exact:true})).toBeVisible();
  await expect(page.getByText("37.50",{exact:true})).toBeVisible();
  const download=page.waitForEvent("download");
  await page.getByRole("button",{name:"Download saved PO PDF"}).click();
  expect((await download).suggestedFilename()).toBe("PO_PO-TEST-ONE.pdf");
  expect(pdfPaths).toEqual(["/api/v1/purchasing/purchase-orders/saved-po/pdf"]);
  expect(writes).toHaveLength(1);
});
