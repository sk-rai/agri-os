#!/usr/bin/env python3
"""Read-only project/global village resolution worklists and NWDP non-canonical audit."""
from __future__ import annotations
import argparse,csv,json,sys
from collections import Counter
from pathlib import Path
from typing import Any
from sqlalchemy import text
ROOT=Path(__file__).resolve().parents[2]; BACKEND=ROOT/'backend'; sys.path.insert(0,str(BACKEND))
from app.core.database import engine  # noqa:E402
from scripts.report_project_boundary_readiness import build_scope_village_sql  # noqa:E402
SCHEMA_VERSION='project_village_resolution_worklist.v1'
SOURCE_SYSTEM='NWDP_GSI_VILLAGE_BOUNDARY'

SNAPSHOT_SQL="""select (select count(*) from geography_villages where is_active) active_villages,(select count(*) from geography_village_pin_links where is_active and match_status='MATCHED') active_pin_links,(select count(*) from geography_boundary_runtime_crosswalks where is_active) active_runtime_crosswalks,(select count(*) from geography_boundary_crosswalk_candidates where is_active) active_candidates,(select count(*) from geography_boundary_project_matches where is_active) active_project_matches"""
CLASSIFIED_SQL="""
with pins as (select geography_village_id village_id,array_agg(distinct pin_code order by pin_code) pin_codes from geography_village_pin_links where is_active and match_status='MATCHED' group by geography_village_id), candidates as (select distinct c.proposed_village_id village_id from geography_boundary_crosswalk_candidates c join geography_boundary_import_batches b on b.id=c.import_batch_id where b.source_system=:source_system and c.proposed_village_id is not null), runtime as (select distinct x.village_id from geography_boundary_runtime_crosswalks x join geography_boundary_runtime_features f on f.id=x.runtime_feature_id and f.is_active where x.is_active)
select v.id::text village_id,v.lgd_code::text village_lgd_code,v.canonical_name village_name,b.canonical_name block_name,d.id::text district_id,d.lgd_code::text district_lgd_code,d.canonical_name district_name,s.id::text state_id,s.lgd_code::text state_lgd_code,s.canonical_name state_name,coalesce(p.pin_codes,array[]::text[]) pin_codes,(c.village_id is not null) has_candidate_mapping,(r.village_id is not null) has_active_runtime,case when p.village_id is not null and (c.village_id is not null or r.village_id is not null) then 'FULLY_RESOLVED' when p.village_id is not null then 'PIN_ONLY' when c.village_id is not null or r.village_id is not null then 'NWDP_ONLY' else 'UNRESOLVED' end resolution_status
from geography_villages v join geography_blocks b on b.id=v.block_id and b.is_active join geography_districts d on d.id=v.district_id and d.is_active join geography_states s on s.id=d.state_id and s.is_active left join pins p on p.village_id=v.id left join candidates c on c.village_id=v.id left join runtime r on r.village_id=v.id where v.is_active
"""
NWDP_UNMAPPED_SQL="""
with candidate_map as (select distinct c.source_feature_id from geography_boundary_crosswalk_candidates c join geography_boundary_import_batches b on b.id=c.import_batch_id where b.source_system=:source_system and c.proposed_village_id is not null), runtime_map as (select distinct c.source_feature_id from geography_boundary_runtime_crosswalks x join geography_boundary_runtime_features f on f.id=x.runtime_feature_id and f.is_active join geography_boundary_crosswalk_candidates c on c.id=x.source_candidate_id where x.is_active), effective as (select * from candidate_map union select * from runtime_map)
select sf.id::text source_feature_id,sf.source_feature_index,sf.source_stcode,sf.source_dtcode,sf.source_sdcode,sf.source_bkcode,sf.source_vlcode,sf.source_state_name,sf.source_district_name,sf.source_subdistrict_name,sf.source_block_name,sf.source_village_name,cv.id::text canonical_code_match_village_id,cv.canonical_name canonical_code_match_village_name,(cv.id is not null) source_code_exists_in_lgd,exists(select 1 from geography_village_pin_links p where p.geography_village_id=cv.id and p.is_active and p.match_status='MATCHED') canonical_code_match_has_pin,false as nwdp_actual_pin_available,case when cv.id is not null then 'REVIEW_EXISTING_CANONICAL_CODE_MATCH' else 'REVIEW_PROJECT_LOCAL_VILLAGE_CANDIDATE' end recommended_route
from geography_boundary_source_features sf join geography_boundary_import_batches batch on batch.id=sf.import_batch_id left join effective e on e.source_feature_id=sf.id left join geography_villages cv on cv.is_active and cv.lgd_code::text=sf.source_vlcode::text where batch.source_system=:source_system and e.source_feature_id is null order by sf.source_state_name,sf.source_district_name,sf.source_village_name,sf.source_feature_index
"""

def write_csv(path:Path,rows:list[dict[str,Any]])->None:
 if not rows:return
 with path.open('w',newline='',encoding='utf-8') as h:
  w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def priority(status:str)->str:return {'UNRESOLVED':'P0','NWDP_ONLY':'P1','PIN_ONLY':'P2','FULLY_RESOLVED':'RESOLVED'}[status]
def action(status:str)->str:return {'UNRESOLVED':'REVIEW_PIN_AND_NWDP','NWDP_ONLY':'REVIEW_PIN_MAPPING','PIN_ONLY':'REVIEW_NWDP_MAPPING','FULLY_RESOLVED':'NONE'}[status]

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--output-dir',type=Path,required=True);args=ap.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
 with engine.connect() as c:
  before=dict(c.execute(text(SNAPSHOT_SQL)).mappings().one())
  classified=[dict(r) for r in c.execute(text(CLASSIFIED_SQL),{'source_system':SOURCE_SYSTEM}).mappings()]
  by_id={r['village_id']:r for r in classified}
  global_rows=[]
  for r in classified:
   if r['resolution_status']=='FULLY_RESOLVED':continue
   global_rows.append({**r,'priority':priority(r['resolution_status']),'recommended_action':action(r['resolution_status']),'global_geography_change_authorized':False})
  projects=[dict(r) for r in c.execute(text("select id::text project_id,tenant_id,name project_name,status project_status,geography_scope from projects where is_active order by tenant_id,name" )).mappings()]
  project_rows=[];project_summaries=[]
  for project in projects:
   scope=project.get('geography_scope') or {};scope_sql,params,sources=build_scope_village_sql(scope if isinstance(scope,dict) else {})
   direct="""select distinct village_id::text village_id from farmers where is_active and project_id=cast(:project_id as uuid) and village_id is not null union select distinct village_id::text from parcels where is_active and project_id=cast(:project_id as uuid) and village_id is not null"""
   if scope_sql: direct += " union select distinct village_id::text from ("+scope_sql+") scoped"
   ids=[r[0] for r in c.execute(text(direct),{'project_id':project['project_id'],**params})]
   counts=Counter()
   for village_id in ids:
    row=by_id.get(village_id)
    if not row:continue
    counts[row['resolution_status']]+=1
    if row['resolution_status']!='FULLY_RESOLVED':project_rows.append({'tenant_id':project['tenant_id'],'project_id':project['project_id'],'project_name':project['project_name'],'project_status':project['project_status'],'scope_sources':'|'.join(sources),**row,'priority':'P0_PROJECT_'+priority(row['resolution_status']),'recommended_action':'PROJECT_SCOPED_'+action(row['resolution_status']),'canonical_geography_change_authorized':False})
   project_summaries.append({'tenant_id':project['tenant_id'],'project_id':project['project_id'],'project_name':project['project_name'],'project_status':project['project_status'],'resolved_scope_villages':len(ids),'fully_resolved':counts['FULLY_RESOLVED'],'pin_only':counts['PIN_ONLY'],'nwdp_only':counts['NWDP_ONLY'],'unresolved':counts['UNRESOLVED'],'worklist_count':counts['PIN_ONLY']+counts['NWDP_ONLY']+counts['UNRESOLVED']})
  nwdp_rows=[dict(r) for r in c.execute(text(NWDP_UNMAPPED_SQL),{'source_system':SOURCE_SYSTEM}).mappings()]
  demographic_pin_values=c.execute(text("select count(*) from geography_village_demographic_profiles where village_pin_code_status is not null and trim(village_pin_code_status)<>''")).scalar_one()
  after=dict(c.execute(text(SNAPSHOT_SQL)).mappings().one())
 counts=Counter(r['resolution_status'] for r in classified);nwdp_counts=Counter({'unmapped':len(nwdp_rows),'code_exists':sum(1 for r in nwdp_rows if r['source_code_exists_in_lgd']),'code_exists_with_pin':sum(1 for r in nwdp_rows if r['canonical_code_match_has_pin']),'actual_pin_available':sum(1 for r in nwdp_rows if r['nwdp_actual_pin_available'])})
 checks={'database_counts_unchanged':before==after,'canonical_partition_exact':sum(counts.values())==600647,'global_gap_total_exact':len(global_rows)==145651,'nwdp_unmapped_exact':len(nwdp_rows)==162229,'nwdp_boundary_actual_pin_absent':nwdp_counts['actual_pin_available']==0,'nwdp_demographic_pin_values_absent':demographic_pin_values==0,'canonical_code_reuse_cohort_exact':nwdp_counts['code_exists']==320,'canonical_code_with_pin_cohort_exact':nwdp_counts['code_exists_with_pin']==269}
 payload={'schema_version':SCHEMA_VERSION,'status':'PASSED' if all(checks.values()) else 'FAILED','healthy':all(checks.values()),'read_only':True,'checks':checks,'database_before':before,'database_after':after,'global_summary':dict(counts),'global_worklist_count':len(global_rows),'project_summary':{'active_projects':len(projects),'project_worklist_rows':len(project_rows),'projects_with_worklist':sum(1 for r in project_summaries if r['worklist_count'])},'nwdp_noncanonical_research':{'features_without_effective_lgd_mapping':len(nwdp_rows),'source_code_exists_in_active_lgd':nwdp_counts['code_exists'],'source_code_exists_and_canonical_has_pin':nwdp_counts['code_exists_with_pin'],'boundary_rows_with_actual_pin':0,'demographic_rows_with_nonempty_pin_status':int(demographic_pin_values),'safe_android_conclusion':'NO_NWDP_PIN_EVIDENCE_AVAILABLE_FOR_DIRECT_ANDROID_EXPOSURE'},'design':{'project_resolution_required':True,'existing_core_override_sufficient':False,'reason':'Existing project override requires canonical village_id and only overrides climate regions.','recommended_identity_scope':'PROJECT_LOCAL_VILLAGE','global_canonical_mutation_authorized':False,'android_behavior_change_authorized':False}}
 write_csv(args.output_dir/'global_village_resolution_worklist.csv',global_rows);write_csv(args.output_dir/'project_village_resolution_worklist.csv',project_rows);write_csv(args.output_dir/'project_village_resolution_summary.csv',project_summaries);write_csv(args.output_dir/'nwdp_without_effective_lgd_mapping.csv',nwdp_rows);(args.output_dir/'project_village_resolution_worklist.json').write_text(json.dumps(payload,indent=2,sort_keys=True,default=str)+'\n')
 print(json.dumps(payload,indent=2,sort_keys=True,default=str));
 if not payload['healthy']:raise SystemExit('worklist validation failed')
 print('PROJECT VILLAGE RESOLUTION WORKLIST PASSED');return 0
if __name__=='__main__':raise SystemExit(main())
