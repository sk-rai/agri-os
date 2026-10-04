#!/usr/bin/env python3
from pathlib import Path
import sys
from uuid import UUID
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from sqlalchemy import text
from app.core.admin_auth import AdminPrincipal
from app.core.database import SessionLocal
from app.modules.master_data.api.project_local_villages import (
 ProjectLocalVillageAuthorization,ProjectLocalVillageRetirement,
 authorize_project_local_village,retire_project_local_village)
from app.modules.master_data.api.project_village_resolutions import nwdp_candidates,worklist
from scripts.admin_auth_test_utils import create_test_admin,delete_test_admin
PROJECT=UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
TENANT="android-dynamic-test"
TOKEN="single-admin-project-local-rollback"
def protected_counts(db):
 return dict(db.execute(text("""select
 (select count(*) from geography_villages) villages,
 (select count(*) from geography_village_pin_links) pin_links,
 (select count(*) from geography_boundary_crosswalk_candidates) candidates,
 (select count(*) from geography_boundary_runtime_crosswalks) runtime,
 (select count(*) from geography_boundary_project_matches) project_matches""")).mappings().one())
with SessionLocal() as db:
 actor,_headers=create_test_admin(db,role="ENTERPRISE_ADMIN",tenant_id=TENANT)
 principal=AdminPrincipal(user_id=actor.id,tenant_id=TENANT,role="ENTERPRISE_ADMIN",project_id=PROJECT)
 resolution_id=None
 try:
  before=protected_counts(db)
  scoped=worklist(PROJECT,None,200,0,db,TENANT,principal)
  candidate=None;anchor=None
  for row in scoped["items"]:
   search=nwdp_candidates(PROJECT,UUID(row["village_id"]),row["village_name"],50,db,TENANT,principal)
   candidate=next((item for item in search["items"] if item["eligible_for_project_local_addition"]),None)
   if candidate:
    anchor=row;break
  if not candidate or not anchor:raise AssertionError("No project-local NWDP candidate fixture is available")
  body=ProjectLocalVillageAuthorization(
   nwdp_source_feature_id=UUID(candidate["source_feature_id"]),
   display_name=candidate["source_village_name"] or anchor["village_name"],
   pin_codes=[],reason="Project administrator confirms this local village evidence.",
   rollback_token=TOKEN,confirmation_phrase="AUTHORIZE PROJECT LOCAL VILLAGE")
  try:
   authorize_project_local_village(PROJECT,body.copy(update={"confirmation_phrase":"WRONG"}),db,TENANT,principal)
   raise AssertionError("Wrong confirmation unexpectedly succeeded")
  except HTTPException as exc:assert exc.status_code==400
  result=authorize_project_local_village(PROJECT,body,db,TENANT,principal)
  resolution_id=UUID(result["resolution_id"])
  assert result["status"]=="ACTIVE"
  assert result["authorization_model"]=="SINGLE_PROJECT_ADMIN"
  assert any(result["parent_matches"].values())
  assert result["project_visible"] is True
  assert result["android_visible"] is False
  assert result["global_geography_changed"] is False
  stored=db.execute(text("""select resolution_mode,resolution_status,is_active,metadata
   from geography_project_village_resolutions where id=:id"""),{"id":str(resolution_id)}).mappings().one()
  assert stored["resolution_mode"]=="PROJECT_LOCAL_ADDITION"
  assert stored["resolution_status"]=="ACTIVE" and stored["is_active"] is True
  event=db.execute(text("""select action,actor_id::text,approver_id::text
   from geography_project_village_resolution_events where resolution_id=:id"""),
   {"id":str(resolution_id)}).mappings().one()
  assert event["action"]=="APPLIED" and event["actor_id"]==str(actor.id)
  assert event["approver_id"] is None
  try:
   authorize_project_local_village(PROJECT,body,db,TENANT,principal)
   raise AssertionError("Duplicate project-local village unexpectedly succeeded")
  except HTTPException as exc:assert exc.status_code==409
  retired=retire_project_local_village(
   PROJECT,resolution_id,
   ProjectLocalVillageRetirement(
    rollback_token=TOKEN,reason="Regression confirms immediate local retirement.",
    confirmation_phrase="RETIRE PROJECT LOCAL VILLAGE"),
   db,TENANT,principal)
  assert retired["status"]=="RETIRED"
  actions=list(db.execute(text("""select action
   from geography_project_village_resolution_events where resolution_id=:id
   order by created_at"""),{"id":str(resolution_id)}).scalars())
  assert actions==["APPLIED","ROLLED_BACK"]
  database_restored=protected_counts(db)==before
  assert database_restored
  print({"schema_version":"project_local_village_single_admin_test.v1",
   "authorization_model":"SINGLE_PROJECT_ADMIN",
   "parent_matches":result["parent_matches"],"audit_actions":actions,
   "database_restored":database_restored,"global_geography_changed":False,
   "android_visible":False})
 finally:
  if resolution_id:
   db.execute(text("delete from geography_project_village_resolution_events where resolution_id=:id"),{"id":str(resolution_id)})
   db.execute(text("delete from geography_project_village_resolutions where id=:id"),{"id":str(resolution_id)})
   db.commit()
  delete_test_admin(db,actor.id)
print("PROJECT LOCAL VILLAGE SINGLE-ADMIN WORKFLOW PASSED")
