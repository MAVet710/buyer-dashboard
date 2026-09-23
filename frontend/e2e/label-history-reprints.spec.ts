import { expect, test, type Page } from "@playwright/test";

const tag = "1A4000000000000000007999";
const sourceTag = "1A4000000000000000007001";
const account = {
  user: { id: "label-operator", display_name: "Operator", email: "operator@example.test", role: "operator", must_change_password: false },
  organization: { id: "history-org", name: "History Test", slug: "history-test" }, facility_id: "history-facility",
  capabilities: { retail: true, production: true, cultivation: false, commercial: true },
  facilities: [{ id: "history-facility", name: "History Facility", code: "HISTORY", capabilities: { retail: true, production: true, cultivation: false, commercial: true } }],
};
function savedRun(status = "printed") {
  const source = { lot_id: "old-lot", package_id: sourceTag, lot_code: "BATCH-ORIGINAL", product_id: "source-product", product_name: "Original source", inventory_unit: "g", label: { batch_number: "BATCH-ORIGINAL", harvest_date: "2026-08-01", test_date: "2026-08-30", expiration_date: "2027-08-30", cultivated_by: "Original grower", cultivator_license: "MC-TEST" }, coa: { available: true, needs_confirmation: false, document_id: "old-coa", filename: "original.pdf", lab_name: "Original laboratory", lab_license_number: "LAB-TEST", date_tested: "2026-08-30", overall_status: "pass", total_thc: 20, total_cbd: 0, total_cannabinoids: 22, total_terpenes: 2, results: [{analysis:"cannabinoids",name:"THCA",value:20,value_text:"20",units:"%"}] }, source_summary: {} };
  const graphic = { value: tag, svg: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect x="2" y="2" width="16" height="16"/></svg>' };
  return { id: "saved-run", product_id: "finished-product", quantity: 24, expected_material_quantity: 0, expected_material_unit: "", status, metrc_package_tag: tag, created_by: "original-operator", printed_by: "original-operator", created_at: "2026-09-03T17:00:00Z", printed_at: "2026-09-03T17:01:00Z", snapshot: { source, sources: [source], product: { name: "Original product", sku: "OLD-SKU" }, label: { product_name: "Original product", total_thc: "20%", net_contents: "3.5 g", manufacturer: "Original manufacturer", license_number: "MFG-TEST" }, quantity: 24, print_layout: { layout: "compact_single", width_in: 3.5, height_in: 2.1, source_count: 1 } }, traceability: { value: tag, qr: graphic, barcode: { ...graphic, format: "Code128" } }, events: [{id:"first-print",event_type:"printed",from_status:"tagged",to_status:"printed",actor:"original-operator",details:{copies:24,reason:""},occurred_at:"2026-09-03T17:01:00Z"}] };
}
async function install(page: Page, status = "printed", unavailable = false) {
  let saved = savedRun(status);
  const requests: Array<{ path: string; method: string; payload: Record<string,unknown> | null }> = [];
  await page.addInitScript(() => {
    localStorage.setItem("buyer-dash-organization","history-org"); localStorage.setItem("buyer-dash-facility","history-facility"); localStorage.setItem("buyer-dash-operation","Production Ops"); localStorage.setItem("buyer-dash-data-mode","Uploads");
    const target = window as unknown as { __printRequests: number };
    target.__printRequests = 0;
    window.print = () => { target.__printRequests++; };
  });
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    const method = request.method();
    if (path.startsWith("/api/v1/label-printing") || path.startsWith("/api/v1/product-master")) requests.push({path,method,payload:method==="POST"?request.postDataJSON() as Record<string,unknown>:null});
    let body: unknown = {};
    if(path==="/api/v1/account/context") body=account;
    else if(path==="/api/v1/account/access-options") body={organizations:[{...account.organization,facilities:account.facilities}],organization_id:account.organization.id,facility_id:account.facility_id};
    else if(path==="/api/v1/label-printing/history") body={items:[{id:saved.id,product_name:"Original product",sku:"OLD-SKU",package_tag:tag,source_packages:[sourceTag],quantity:24,status:saved.status,created_by:"original-operator",created_at:saved.created_at,printed_at:saved.printed_at,print_requests:saved.events.length,last_print_request_at:saved.events.at(-1)?.occurred_at,width_in:3.5,height_in:2.1,design_revision:0,sandbox_test_pass:false}],total:1,offset:0,limit:50,has_more:false};
    else if(path==="/api/v1/label-printing/production-runs/saved-run") {
      if(unavailable){await route.fulfill({status:404,contentType:"application/json",body:JSON.stringify({detail:"Label production run was not found in this facility."})});return;}
      body=saved;
    } else if(path==="/api/v1/label-printing/production-runs/saved-run/print") {
      const payload=request.postDataJSON() as {copies:number;reason:string};
      saved={...saved,events:[...saved.events,{id:"replacement-print",event_type:"reprinted",from_status:saved.status,to_status:saved.status,actor:"replacement-operator",details:payload,occurred_at:"2026-09-23T10:00:00Z"}]};
      body=saved;
    } else if(path.startsWith("/api/v1/label-printing") || path.startsWith("/api/v1/product-master")) {
      await route.fulfill({status:500,contentType:"application/json",body:JSON.stringify({detail:"Historical labels must not depend on current source data or create new runs/tags."})});return;
    } else if(path==="/api/v1/search") body={results:[]};
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(body)});
  });
  return {requests, getSaved:()=>saved};
}

test("history reopens after refresh and prints only the original replacement range", async ({page}) => {
  const fixture=await install(page);
  await page.goto("/compliance/labels?labelMode=history");
  await page.getByLabel("Search label history").fill(tag);
  await page.getByRole("button",{name:"Search saved labels"}).click();
  await page.getByRole("button",{name:`Open saved label ${tag}`}).click();
  await expect(page).toHaveURL(/labelRun=saved-run/);
  await page.reload();
  await expect(page.getByRole("heading",{name:"Saved label & reprints"})).toBeVisible();
  await expect(page.locator(".production-label-copy").first()).toHaveAttribute("data-label-width","3.5");
  await page.getByLabel("Replacement copies").fill("2");
  await page.getByLabel("First original label number").fill("7");
  await page.getByLabel("Reprint reason").fill("Two damaged labels");
  await page.getByRole("button",{name:"Reprint 2 replacements"}).click();
  await expect.poll(()=>page.evaluate(()=>(window as unknown as {__printRequests:number}).__printRequests)).toBe(1);
  await expect(page.locator(".production-label-copy")).toHaveCount(2);
  await expect(page.locator(".production-label-copy").nth(0).locator(".printed-unit-id")).toHaveText("#7 / 24");
  await expect(page.locator(".production-label-copy").nth(1).locator(".printed-unit-id")).toHaveText("#8 / 24");
  const writes=fixture.requests.filter(row=>row.method==="POST");
  expect(writes).toHaveLength(1);
  expect(writes[0].path).toBe("/api/v1/label-printing/production-runs/saved-run/print");
  expect(writes[0].payload?.copies).toBe(2);
  expect(writes[0].payload?.reason).toContain("Two damaged labels");
  expect(fixture.requests.some(row=>row.path.includes("inventory-sources")||row.path.includes("product-master")||row.path.endsWith("/tag"))).toBe(false);
  expect(fixture.getSaved().quantity).toBe(24);
  expect(fixture.getSaved().metrc_package_tag).toBe(tag);
  expect(fixture.getSaved().snapshot.label.total_thc).toBe("20%");
  await expect(page.locator(".label-audit-row").last()).toContainText("2 requested copies");
  await page.reload();
  await expect(page.locator(".label-audit-row").last()).toContainText("Two damaged labels");
});

test("archived labels remain discoverable without offering a new-tag or reprint action", async ({page})=>{
  const fixture=await install(page,"archived");
  await page.goto("/compliance/labels?labelMode=history&labelRun=saved-run");
  await expect(page.getByText("Its saved label and history remain available",{exact:false})).toBeVisible();
  await expect(page.getByRole("button",{name:/^Reprint \d/})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Assign tag",exact:true})).toHaveCount(0);
  expect(fixture.requests.filter(row=>row.method==="POST")).toEqual([]);
});

test("a missing or unauthorized historical run does not fall back to another label",async({page})=>{
  await install(page,"printed",true);
  await page.goto("/compliance/labels?labelMode=history&labelRun=saved-run");
  await expect(page.getByText("This saved label could not be opened",{exact:false})).toBeVisible();
  await expect(page.getByRole("button",{name:/^Reprint \d/})).toHaveCount(0);
  await expect(page.locator(".production-label-print-batch")).toHaveCount(0);
});
