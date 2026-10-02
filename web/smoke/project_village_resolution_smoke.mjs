import { execFileSync } from "node:child_process";
import fs from "node:fs/promises";
import { chromium } from "playwright";
const webBaseUrl=process.env.WEB_BASE_URL||"http://localhost:3000",apiBaseUrl=process.env.API_BASE_URL||"http://127.0.0.1:8000",tenantId="android-dynamic-test",projectId="0f7e0a6b-8472-5d6d-8a14-a9d000000001",screenshot="smoke/screenshots/project-village-resolution.png";
function pythonJson(code){return JSON.parse(execFileSync("../venv/bin/python",["-c",code],{cwd:process.cwd(),encoding:"utf-8"}))}
const snapshotCode=["import json,sys","from pathlib import Path","sys.path.insert(0,str(Path.cwd().parent/'backend'))","from sqlalchemy import text","from app.core.database import SessionLocal","db=SessionLocal()","row=db.execute(text(\"select (select count(*) from geography_villages) villages,(select count(*) from geography_village_pin_links) pins,(select count(*) from geography_boundary_crosswalk_candidates) candidates,(select count(*) from geography_boundary_runtime_crosswalks) runtime,(select count(*) from geography_boundary_project_matches) project_matches,(select count(*) from geography_project_village_resolutions) project_resolutions\")).mappings().one()","db.close()","print(json.dumps(dict(row)))"].join("\n");
const before=pythonJson(snapshotCode);
const createCode=["import json,sys","from pathlib import Path","sys.path.insert(0,str(Path.cwd().parent/'backend'))","from app.core.database import SessionLocal","from scripts.admin_auth_test_utils import create_test_admin","db=SessionLocal()","admin,headers=create_test_admin(db,role='ENTERPRISE_ADMIN',tenant_id='"+tenantId+"')","db.close()","print(json.dumps({'user_id':str(admin.id),'headers':headers}))"].join("\n");
const admin=pythonJson(createCode),token=admin.headers.Authorization.replace("Bearer ","");
const browser=await chromium.launch({headless:true}),context=await browser.newContext({viewport:{width:1600,height:1100}});
await context.addInitScript(({authToken,tenant,actor})=>{localStorage.setItem("agrios_token",authToken);localStorage.setItem("agrios_tenant_id",tenant);localStorage.setItem("agrios_user_id",actor)},{authToken:token,tenant:tenantId,actor:admin.user_id});
const page=await context.newPage(),browserErrors=[];
page.on("pageerror",error=>browserErrors.push(error.message));page.on("console",message=>{if(message.type()==="error")browserErrors.push(message.text())});
try{
 const liveWorklistResponse=await context.request.get(apiBaseUrl+"/api/v1/master-data/geography/project-village-resolutions/projects/"+projectId+"/worklist?limit=50&offset=0",{headers:{Authorization:"Bearer "+token,"X-Tenant-ID":tenantId,"X-Actor-ID":admin.user_id},timeout:180000});
 const liveWorklist=await liveWorklistResponse.json();if(liveWorklistResponse.status()!==200)throw new Error("Live worklist HTTP "+liveWorklistResponse.status()+": "+JSON.stringify(liveWorklist));
 await page.route("**/api/v1/master-data/geography/project-village-resolutions/projects/"+projectId+"/worklist?*",async route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(liveWorklist)}));
 await page.route("**/api/v1/projects",async route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify([{id:projectId,name:"Android Dynamic Profile Test Project",tenant_id:tenantId,status:"ACTIVE",is_active:true}])}));
 await page.goto(webBaseUrl+"/geography-layer-readiness",{waitUntil:"domcontentloaded",timeout:60000});
 const panel=page.getByTestId("project-village-resolution-panel");await panel.waitFor({timeout:60000});
 await page.waitForFunction(wanted=>Array.from(document.querySelectorAll('select[aria-label="Resolution project"] option')).some(row=>row.value===wanted),projectId,{timeout:60000});
 await panel.getByLabel("Resolution project").selectOption(projectId);
 const worklistResponse=page.waitForResponse(response=>response.url().includes("/projects/"+projectId+"/worklist?"),{timeout:180000});
 await panel.getByRole("button",{name:"Load project worklist"}).click();const worklistHttp=await worklistResponse; const worklist=await worklistHttp.json(); if(worklistHttp.status()!==200)throw new Error("Worklist HTTP "+worklistHttp.status()+": "+JSON.stringify(worklist));
 if(worklist.schema_version!=="project_village_resolution_worklist_api.v1"||!worklist.items.length)throw new Error("Invalid or empty worklist");
 if(worklist.guardrails.apply_enabled!==false)throw new Error("Apply guardrail is not disabled");
 if(await panel.locator("tbody tr").count()!==worklist.items.length)throw new Error("Rendered row count mismatch");
 const first=worklist.items[0];await panel.getByLabel("Review "+first.village_name).check();
 const dryRunResponse=page.waitForResponse(response=>response.url().includes("/projects/"+projectId+"/dry-run"),{timeout:60000});
 await panel.getByRole("button",{name:"Validate dry run"}).click();const dryRunHttp=await dryRunResponse;const dryRun=await dryRunHttp.json();if(dryRunHttp.status()!==200)throw new Error("Dry run HTTP "+dryRunHttp.status()+": "+JSON.stringify(dryRun));
 if(dryRun.status!=="VALID"||dryRun.preview.would_write!==false||dryRun.preview.would_be_android_visible!==false)throw new Error("Dry-run safety contract failed");
 await panel.getByText(/Dry run valid\. Would write: false.*Android visible: false/).waitFor();
 const applyResponse=await context.request.post(apiBaseUrl+"/api/v1/master-data/geography/project-village-resolutions/projects/"+projectId+"/dry-run",{headers:{Authorization:"Bearer "+token,"X-Tenant-ID":tenantId,"X-Actor-ID":admin.user_id},data:{resolution_mode:"CANONICAL_ENRICHMENT",canonical_village_id:first.village_id,display_name:first.village_name,pin_codes:first.pin_codes,hierarchy_labels:{},evidence_basis:"ADMIN_PROJECT_REVIEW",rollback_token:"project-village-smoke",dry_run:false,confirm_apply:true}});
 const applyPayload=await applyResponse.json();if(applyResponse.status()!==503||applyPayload.detail?.code!=="PROJECT_VILLAGE_RESOLUTION_APPLY_DISABLED")throw new Error("Apply boundary contract failed");
 await fs.mkdir("smoke/screenshots",{recursive:true});await panel.screenshot({path:screenshot});
 if(browserErrors.length)throw new Error("Browser errors: "+browserErrors.join(" | "));
 const after=pythonJson(snapshotCode);if(JSON.stringify(before)!==JSON.stringify(after))throw new Error("Database state changed");
 console.log(JSON.stringify({schema_version:"project_village_resolution_web_smoke.v1",status:"PASSED",project_id:projectId,summary:worklist.summary,selected_status:first.resolution_status,dry_run:{would_write:false,android_visible:false},apply:{http_status:503,code:applyPayload.detail.code},database_unchanged:true,screenshot:"web/"+screenshot},null,2));
}finally{
 await browser.close();
 const deleteCode=["import sys","from pathlib import Path","sys.path.insert(0,str(Path.cwd().parent/'backend'))","from app.core.database import SessionLocal","from scripts.admin_auth_test_utils import delete_test_admin","db=SessionLocal()","delete_test_admin(db,'"+admin.user_id+"')","db.close()"].join("\n");
 execFileSync("../venv/bin/python",["-c",deleteCode],{cwd:process.cwd()});
}
