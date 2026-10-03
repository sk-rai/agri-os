#!/usr/bin/env python3
from pathlib import Path
import sys
from uuid import UUID
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from sqlalchemy import text
from app.core.admin_auth import AdminPrincipal
from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.master_data.api.project_village_resolutions import ProjectVillageResolutionApply,ProjectVillageResolutionRollback,apply_canonical_resolution,nwdp_candidates,rollback_canonical_resolution,worklist
from scripts.admin_auth_test_utils import create_test_admin,delete_test_admin
PROJECT=UUID('0f7e0a6b-8472-5d6d-8a14-a9d000000001');TENANT='android-dynamic-test';TOKEN='guarded-resolution-rollback-token'
def snapshot(db):return dict(db.execute(text("select (select count(*) from geography_villages) villages,(select count(*) from geography_village_pin_links) pins,(select count(*) from geography_boundary_crosswalk_candidates) candidates,(select count(*) from geography_boundary_runtime_crosswalks) runtime,(select count(*) from geography_boundary_project_matches) project_matches")).mappings().one())
with SessionLocal() as db:
 actor,actor_headers=create_test_admin(db,role='ENTERPRISE_ADMIN',tenant_id=TENANT);approver,approver_headers=create_test_admin(db,role='ENTERPRISE_ADMIN',tenant_id=TENANT)
 principal=AdminPrincipal(user_id=actor.id,tenant_id=TENANT,role='ENTERPRISE_ADMIN',project_id=PROJECT)
 resolution_id=None
 original=settings.PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED
 try:
  before=snapshot(db);payload=worklist(PROJECT,'FULLY_RESOLVED',1,0,db,TENANT,principal);row=payload['items'][0]
  search=nwdp_candidates(PROJECT,UUID(row['village_id']),row['village_name'],20,db,TENANT,principal);candidate=next(item for item in search['items'] if item['eligible_for_canonical_enrichment'])
  body=ProjectVillageResolutionApply(resolution_mode='CANONICAL_ENRICHMENT',canonical_village_id=UUID(row['village_id']),nwdp_source_feature_id=UUID(candidate['source_feature_id']),display_name=row['village_name'],pin_codes=list(row['pin_codes']),hierarchy_labels={'state':row['state_name'],'district':row['district_name'],'block':row['block_name']},evidence_basis='DUAL_ADMIN_LOCAL_CANARY',review_notes='Guarded canonical enrichment regression',rollback_token=TOKEN,dry_run=False,confirm_apply=True,approver_token=approver_headers['Authorization'].replace('Bearer ',''),confirmation_phrase='APPLY PROJECT CANONICAL ENRICHMENT')
  settings.PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED=False
  try:apply_canonical_resolution(PROJECT,body,db,TENANT,principal);raise AssertionError('Disabled apply unexpectedly succeeded')
  except HTTPException as exc:assert exc.status_code==503 and exc.detail['code']=='PROJECT_VILLAGE_RESOLUTION_APPLY_DISABLED'
  settings.PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED=True
  applied=apply_canonical_resolution(PROJECT,body,db,TENANT,principal);resolution_id=UUID(applied['resolution_id'])
  assert applied['status']=='ACTIVE' and applied['android_visible'] is False and applied['global_geography_changed'] is False
  stored=db.execute(text("select resolution_status,is_active,reviewer,metadata from geography_project_village_resolutions where id=:id"),{'id':str(resolution_id)}).mappings().one();assert stored['resolution_status']=='ACTIVE' and stored['is_active'] is True and stored['metadata']['android_visible'] is False
  event=db.execute(text("select action,actor_id::text,approver_id::text from geography_project_village_resolution_events where resolution_id=:id"),{'id':str(resolution_id)}).mappings().one();assert event['action']=='APPLIED' and event['actor_id']==str(actor.id) and event['approver_id']==str(approver.id)
  try:apply_canonical_resolution(PROJECT,body,db,TENANT,principal);raise AssertionError('Duplicate active resolution unexpectedly succeeded')
  except HTTPException as exc:assert exc.status_code==409 and exc.detail['code']=='ACTIVE_PROJECT_CANONICAL_RESOLUTION_EXISTS'
  try:rollback_canonical_resolution(PROJECT,resolution_id,ProjectVillageResolutionRollback(rollback_token='wrong-token-value',reason='Regression wrong token check'),db,TENANT,principal);raise AssertionError('Wrong rollback token unexpectedly succeeded')
  except HTTPException as exc:assert exc.status_code==409
  rolled=rollback_canonical_resolution(PROJECT,resolution_id,ProjectVillageResolutionRollback(rollback_token=TOKEN,reason='Regression confirms immediate project-only rollback'),db,TENANT,principal);assert rolled['status']=='RETIRED' and rolled['android_visible'] is False
  actions=list(db.execute(text("select action from geography_project_village_resolution_events where resolution_id=:id order by created_at"),{'id':str(resolution_id)}).scalars());assert actions==['APPLIED','ROLLED_BACK']
  retired=db.execute(text("select resolution_status,is_active from geography_project_village_resolutions where id=:id"),{'id':str(resolution_id)}).mappings().one();assert retired['resolution_status']=='RETIRED' and retired['is_active'] is False
  assert snapshot(db)==before
  print({'schema_version':'project_village_resolution_guarded_apply_test.v1','apply_status':'ACTIVE','rollback_status':'RETIRED','audit_actions':actions,'global_geography_unchanged':True,'android_visible':False})
 finally:
  settings.PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED=original
  if resolution_id:
   db.execute(text('delete from geography_project_village_resolution_events where resolution_id=:id'),{'id':str(resolution_id)});db.execute(text('delete from geography_project_village_resolutions where id=:id'),{'id':str(resolution_id)});db.commit()
  delete_test_admin(db,actor.id);delete_test_admin(db,approver.id)
print('PROJECT VILLAGE RESOLUTION GUARDED APPLY PASSED')