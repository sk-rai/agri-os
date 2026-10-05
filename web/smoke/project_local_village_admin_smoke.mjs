import {execFileSync} from "node:child_process";
import fs from "node:fs/promises";
import {chromium} from "playwright";
const webBaseUrl=process.env.WEB_BASE_URL||"http://localhost:3000";
const apiBaseUrl=process.env.API_BASE_URL||"http://127.0.0.1:8000";
const tenantId="android-dynamic-test";
const projectId="0f7e0a6b-8472-5d6d-8a14-a9d000000001";
const screenshot="smoke/screenshots/project-local-village-admin.png";
function pythonJson(code){return JSON.parse(execFileSync("../venv/bin/python",["-c",code],{cwd:process.cwd(),encoding:"utf-8"}))}
const admin=pythonJson([
 "import json,sys","from pathlib import Path","sys.path.insert(0,str(Path.cwd().parent/'backend'))",
 "from app.core.database import SessionLocal","from scripts.admin_auth_test_utils import create_test_admin",
 "db=SessionLocal()","user,headers=create_test_admin(db,role='ENTERPRISE_ADMIN',tenant_id='"+tenantId+"')",
 "user_id=str(user.id)","print(json.dumps({'user_id':user_id,'headers':headers}))","db.close()"].join("\n"));
const protectedCode=[
 "import json,sys","from pathlib import Path","sys.path.insert(0,str(Path.cwd().parent/'backend'))",
 "from sqlalchemy import text","from app.core.database import SessionLocal","db=SessionLocal()",
 "row=db.execute(text(\"select (select count(*) from geography_villages) villages,(select count(*) from geography_village_pin_links) pins,(select count(*) from geography_boundary_crosswalk_candidates) candidates,(select count(*) from geography_boundary_runtime_crosswalks) runtime,(select count(*) from geography_boundary_project_matches) project_matches\")).mappings().one()",
 "db.close()","print(json.dumps(dict(row),sort_keys=True))"].join("\n");
const before=pythonJson(protectedCode);
const headers={Authorization:admin.headers.Authorization,"X-Tenant-ID":tenantId,"X-Actor-ID":admin.user_id};
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1600,height:1200}});
await context.addInitScript(({token,tenant,actor})=>{localStorage.setItem("agrios_token",token);localStorage.setItem("agrios_tenant_id",tenant);localStorage.setItem("agrios_user_id",actor);localStorage.setItem("agrios_role","ENTERPRISE_ADMIN")},{token:admin.headers.Authorization.replace("Bearer ",""),tenant:tenantId,actor:admin.user_id});
await context.route("**/api/v1/projects*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify([{id:projectId,name:"Android Dynamic Profile Test Project",tenant_id:tenantId,status:"ACTIVE",is_active:true}])}));
let resolutionId=null;
let sourceId=null;
let displayName=null;
const errors=[];
try{
 const page=await context.newPage();
 page.on("pageerror",error=>errors.push(error.message));
 page.on("console",message=>{if(message.type()==="error")errors.push(message.text())});
 await page.goto(webBaseUrl+"/geography-layer-readiness",{waitUntil:"domcontentloaded",timeout:60000});
 const panel=page.getByTestId("project-village-resolution-panel");
 await panel.waitFor({timeout:60000});
 await page.waitForFunction(wanted=>Array.from(document.querySelectorAll('select[aria-label="Resolution project"] option')).some(row=>row.value===wanted),projectId,{timeout:60000});
 await panel.getByLabel("Resolution project").selectOption(projectId);
 const worklistPromise=page.waitForResponse(response=>response.url().includes("/projects/"+projectId+"/worklist?")&&response.status()===200,{timeout:180000});
 await panel.getByRole("button",{name:"Load project worklist"}).click();
 const worklist=await(await worklistPromise).json();
 let anchor=null,candidate=null;
 for(const row of worklist.items){
  const response=await context.request.get(apiBaseUrl+"/api/v1/master-data/geography/project-village-resolutions/projects/"+projectId+"/nwdp-candidates?canonical_village_id="+row.village_id+"&q="+encodeURIComponent(row.village_name)+"&limit=50",{headers,timeout:180000});
  if(response.status()!==200)continue;
  const payload=await response.json();
  candidate=payload.items.find(item=>item.eligible_for_project_local_addition);
  if(candidate){anchor=row;break}
 }
 if(!anchor||!candidate)throw new Error("No eligible project-local candidate in the loaded worklist");
 sourceId=candidate.source_feature_id;
 displayName=candidate.source_village_name||anchor.village_name;
 await panel.getByLabel("Review "+anchor.village_name).check();
 await panel.getByLabel("NWDP candidate search").fill(displayName);
 const candidatePromise=page.waitForResponse(response=>response.url().includes("/nwdp-candidates?")&&response.status()===200,{timeout:120000});
 await panel.getByRole("button",{name:"Search NWDP"}).click();
 await candidatePromise;
 await panel.getByLabel("NWDP candidate",{exact:true}).selectOption(sourceId);
 const authorization=panel.getByTestId("project-local-village-authorization");
 await authorization.waitFor({timeout:30000});
 await authorization.getByLabel("Project-local village confirmation").fill("AUTHORIZE PROJECT LOCAL VILLAGE");
 const authorizePromise=page.waitForResponse(response=>response.url().endsWith("/projects/"+projectId+"/local-additions")&&response.request().method()==="POST",{timeout:60000});
 await authorization.getByRole("button",{name:"Authorize for this project only"}).click();
 const authorizeResponse=await authorizePromise;
 const authorize=await authorizeResponse.json();
 if(authorizeResponse.status()!==200||authorize.status!=="ACTIVE"||authorize.android_visible!==false||authorize.global_geography_changed!==false)throw new Error("Authorization contract failed: "+JSON.stringify(authorize));
 resolutionId=authorize.resolution_id;
 const catalog=panel.getByTestId("project-local-village-catalog");
 const catalogItem=catalog.getByTestId("project-local-village-"+resolutionId);
 await catalogItem.waitFor({timeout:180000});
 const wrongTenant=await context.request.get(apiBaseUrl+"/api/v1/master-data/geography/project-village-resolutions/projects/"+projectId+"/available-villages?q="+encodeURIComponent(displayName),{headers:{...headers,"X-Tenant-ID":"wrong-tenant"}});
 if(![403,404].includes(wrongTenant.status()))throw new Error("Cross-tenant catalog isolation failed: "+wrongTenant.status());
 if(JSON.stringify(pythonJson(protectedCode))!==JSON.stringify(before))throw new Error("Protected geography changed after authorization");
 await catalogItem.getByLabel("Rollback token for "+displayName).fill("project-local-"+sourceId.slice(0,12));
 await catalogItem.getByLabel("Retirement confirmation for "+displayName).fill("RETIRE PROJECT LOCAL VILLAGE");
 const retirePromise=page.waitForResponse(response=>response.url().endsWith("/local-additions/"+resolutionId+"/retire")&&response.request().method()==="POST",{timeout:60000});
 await catalogItem.getByRole("button",{name:"Retire from this project"}).click();
 const retireResponse=await retirePromise;
 const retired=await retireResponse.json();
 if(retireResponse.status()!==200||retired.status!=="RETIRED"||retired.android_visible!==false||retired.global_geography_changed!==false)throw new Error("Retirement contract failed: "+JSON.stringify(retired));
 await catalog.getByText("No active project-local villages match this search.").waitFor({timeout:180000});
 const queueResponse=await context.request.get(apiBaseUrl+"/api/v1/master-data/geography/project-village-resolutions/projects/"+projectId+"/resolutions",{headers,timeout:180000});
 const queue=await queueResponse.json();
 const row=queue.items.find(item=>item.resolution_id===resolutionId);
 const actions=row?.events.map(event=>event.action)||[];
 if(row?.resolution_status!=="RETIRED"||actions.join(",")!=="APPLIED,ROLLED_BACK")throw new Error("Audit history failed: "+JSON.stringify(row));
 if(JSON.stringify(pythonJson(protectedCode))!==JSON.stringify(before))throw new Error("Protected geography changed after retirement");
 await fs.mkdir("smoke/screenshots",{recursive:true});
 await catalog.screenshot({path:screenshot,timeout:30000});
 if(errors.length)throw new Error("Browser errors: "+errors.join(" | "));
 console.log(JSON.stringify({schema_version:"project_local_village_admin_web_smoke.v1",status:"PASSED",project_id:projectId,resolution_id:resolutionId,authorization_model:"SINGLE_PROJECT_ADMIN",catalog_visible_before_retirement:true,catalog_hidden_after_retirement:true,cross_tenant_hidden:true,audit_actions:actions,protected_global_geography_unchanged:true,android_visible:false,screenshot:"web/"+screenshot},null,2));
}finally{
 await browser.close();
 const cleanup=["import sys","from pathlib import Path","sys.path.insert(0,str(Path.cwd().parent/'backend'))","from sqlalchemy import text","from app.core.database import SessionLocal","from scripts.admin_auth_test_utils import delete_test_admin","db=SessionLocal()","resolution_id='"+(resolutionId||"")+"'","if resolution_id:"," db.execute(text('delete from geography_project_village_resolution_events where resolution_id=:id'),{'id':resolution_id})"," db.execute(text('delete from geography_project_village_resolutions where id=:id'),{'id':resolution_id})"," db.commit()","delete_test_admin(db,'"+admin.user_id+"')","db.close()"].join("\n");
 execFileSync("../venv/bin/python",["-c",cleanup],{cwd:process.cwd(),stdio:"inherit"});
}
