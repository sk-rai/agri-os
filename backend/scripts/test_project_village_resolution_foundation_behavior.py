#!/usr/bin/env python3
from uuid import UUID
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from sqlalchemy import text
from app.core.database import SessionLocal
from app.modules.master_data.api.project_village_resolutions import ProjectVillageResolutionDryRun,dry_run,nwdp_candidates,worklist
PROJECT=UUID('0f7e0a6b-8472-5d6d-8a14-a9d000000001');TENANT='android-dynamic-test'
def snapshot(db):return dict(db.execute(text("select (select count(*) from geography_villages) villages,(select count(*) from geography_village_pin_links) pins,(select count(*) from geography_boundary_crosswalk_candidates) candidates,(select count(*) from geography_boundary_runtime_crosswalks) runtime,(select count(*) from geography_boundary_project_matches) project_matches")).mappings().one())
with SessionLocal() as db:
 before=snapshot(db);payload=worklist(PROJECT,None,30,0,db,TENANT,None)
 assert payload['schema_version']=='project_village_resolution_worklist_api.v1' and payload['items']
 row=next(item for item in payload['items'] if item['resolution_status']=='FULLY_RESOLVED')
 search=nwdp_candidates(PROJECT,UUID(row['village_id']),row['village_name'],20,db,TENANT,None)
 assert search['schema_version']=='project_village_resolution_nwdp_candidates.v1' and search['mode']=='READ_ONLY' and search['guardrails']['db_writes_attempted'] is False and search['items']
 assert any(candidate['eligible_for_canonical_enrichment'] for candidate in search['items'])
 for candidate in search['items']:
  assert isinstance(candidate['eligible_for_canonical_enrichment'],bool)
 body=ProjectVillageResolutionDryRun(resolution_mode='CANONICAL_ENRICHMENT',canonical_village_id=UUID(row['village_id']),display_name=row['village_name'],pin_codes=list(row['pin_codes']),hierarchy_labels={'state':row['state_name'],'district':row['district_name'],'block':row['block_name']},evidence_basis='ADMIN_PROJECT_REVIEW',review_notes='Static regression dry run',rollback_token='project-resolution-test',dry_run=True,confirm_apply=False)
 result=dry_run(PROJECT,body,db,TENANT,None)
 assert result['status']=='VALID' and result['preview']['would_write'] is False and result['preview']['would_be_android_visible'] is False
 blocked=body.copy(update={'dry_run':False,'confirm_apply':True})
 try:dry_run(PROJECT,blocked,db,TENANT,None);raise AssertionError('Apply unexpectedly succeeded')
 except HTTPException as exc:assert exc.status_code==503 and exc.detail['code']=='PROJECT_VILLAGE_RESOLUTION_APPLY_DISABLED'
 after=snapshot(db)
 assert before==after
 print({'project_id':str(PROJECT),'summary':payload['summary'],'candidate_count':search['count'],'dry_run_status':result['status'],'apply_status':503,'database_unchanged':True})
print('PROJECT VILLAGE RESOLUTION FOUNDATION BEHAVIOR PASSED')
