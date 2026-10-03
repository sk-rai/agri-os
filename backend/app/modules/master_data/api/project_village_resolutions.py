"""Read-only project village worklist and disabled-apply resolution dry runs."""
import json,re
from typing import Optional
from uuid import UUID
from fastapi import APIRouter,Depends,Header,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.admin_auth import AdminPermission,require_admin_permission
from app.core.database import get_db
from app.modules.master_data.api.geography import _project_contains_village
from scripts.report_project_boundary_readiness import build_scope_village_sql
router=APIRouter(prefix='/geography/project-village-resolutions',tags=['geography'])
STATUSES={'FULLY_RESOLVED','PIN_ONLY','NWDP_ONLY','UNRESOLVED'}
PIN_RE=re.compile(r'^[1-9][0-9]{5}$')
class ProjectVillageResolutionDryRun(BaseModel):
 resolution_mode:str
 canonical_village_id:Optional[UUID]=None
 nwdp_source_feature_id:Optional[UUID]=None
 display_name:str=Field(min_length=2,max_length=180)
 pin_codes:list[str]=Field(default_factory=list,max_length=20)
 hierarchy_labels:dict=Field(default_factory=dict)
 evidence_basis:str=Field(min_length=3,max_length=120)
 review_notes:Optional[str]=Field(default=None,max_length=1000)
 rollback_token:str=Field(min_length=8,max_length=80)
 dry_run:bool=True
 confirm_apply:bool=False

def project(db,project_id,tenant_id):
 row=db.execute(text("select id::text project_id,tenant_id,name,status,geography_scope from projects where id=:id and tenant_id=:tenant and is_active"),{'id':str(project_id),'tenant':tenant_id}).mappings().first()
 if not row:raise HTTPException(404,'ACTIVE_TENANT_PROJECT_NOT_FOUND')
 return dict(row)
def guardrails():return {'db_writes_attempted':False,'project_resolution_rows_written':False,'canonical_geography_changed':False,'global_pin_links_changed':False,'nwdp_candidate_changed':False,'runtime_boundary_changed':False,'android_behavior_changed':False,'apply_enabled':False}
def project_village_sql(scope):
 scope_sql,params,sources=build_scope_village_sql(scope if isinstance(scope,dict) else {})
 sql="""select distinct village_id::text village_id from farmers where is_active and project_id=cast(:project_id as uuid) and village_id is not null union select distinct village_id::text from parcels where is_active and project_id=cast(:project_id as uuid) and village_id is not null"""
 if scope_sql:sql+=' union select distinct village_id::text from ('+scope_sql+') scoped'
 return sql,params,sources
@router.get('/projects/{project_id}/worklist')
def worklist(project_id:UUID,resolution_status:Optional[str]=Query(None),limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),x_tenant_id:str=Header('default',alias='X-Tenant-ID'),_principal=Depends(require_admin_permission(AdminPermission.VIEW,project_scoped=True))):
 p=project(db,project_id,x_tenant_id);status=resolution_status.upper() if resolution_status else None
 if status and status not in STATUSES:raise HTTPException(400,{'code':'INVALID_VILLAGE_RESOLUTION_STATUS','allowed':sorted(STATUSES)})
 scope=p.get('geography_scope') or {}
 if isinstance(scope,str):
  try:scope=json.loads(scope)
  except Exception:scope={}
 pv_sql,scope_params,sources=project_village_sql(scope)
 params={'project_id':str(project_id),'source_system':'NWDP_GSI_VILLAGE_BOUNDARY','status':status,'limit':limit,'offset':offset,**scope_params}
 rows=db.execute(text("""
with project_villages as ("""+pv_sql+"""), pins as (select geography_village_id village_id,array_agg(distinct pin_code order by pin_code) pin_codes from geography_village_pin_links where is_active and match_status='MATCHED' group by geography_village_id), candidates as (select distinct c.proposed_village_id village_id from geography_boundary_crosswalk_candidates c join geography_boundary_import_batches b on b.id=c.import_batch_id where b.source_system=:source_system and c.proposed_village_id is not null), runtime as (select distinct x.village_id from geography_boundary_runtime_crosswalks x join geography_boundary_runtime_features f on f.id=x.runtime_feature_id and f.is_active where x.is_active), classified as (select v.id::text village_id,v.lgd_code::text village_lgd_code,v.canonical_name village_name,b.canonical_name block_name,d.canonical_name district_name,s.canonical_name state_name,coalesce(pin.pin_codes,array[]::text[]) pin_codes,(c.village_id is not null) has_candidate_mapping,(r.village_id is not null) has_active_runtime,case when pin.village_id is not null and (c.village_id is not null or r.village_id is not null) then 'FULLY_RESOLVED' when pin.village_id is not null then 'PIN_ONLY' when c.village_id is not null or r.village_id is not null then 'NWDP_ONLY' else 'UNRESOLVED' end resolution_status from project_villages pv join geography_villages v on v.id=cast(pv.village_id as uuid) and v.is_active join geography_blocks b on b.id=v.block_id join geography_districts d on d.id=v.district_id join geography_states s on s.id=d.state_id left join pins pin on pin.village_id=v.id left join candidates c on c.village_id=v.id left join runtime r on r.village_id=v.id), summary as (select count(*) total,count(*) filter(where resolution_status='FULLY_RESOLVED') fully_resolved,count(*) filter(where resolution_status='PIN_ONLY') pin_only,count(*) filter(where resolution_status='NWDP_ONLY') nwdp_only,count(*) filter(where resolution_status='UNRESOLVED') unresolved from classified), filtered as (select * from classified where :status is null or resolution_status=:status) select filtered.*,count(*) over() filtered_total,summary.total,summary.fully_resolved,summary.pin_only,summary.nwdp_only,summary.unresolved from filtered cross join summary order by case resolution_status when 'UNRESOLVED' then 1 when 'NWDP_ONLY' then 2 when 'PIN_ONLY' then 3 else 4 end,state_name,district_name,block_name,village_name limit :limit offset :offset
"""),params).mappings().all()
 first=rows[0] if rows else None
 summary={'total':int(first['total']) if first else 0,'fully_resolved':int(first['fully_resolved']) if first else 0,'pin_only':int(first['pin_only']) if first else 0,'nwdp_only':int(first['nwdp_only']) if first else 0,'unresolved':int(first['unresolved']) if first else 0}
 keys=('village_id','village_lgd_code','village_name','block_name','district_name','state_name','pin_codes','has_candidate_mapping','has_active_runtime','resolution_status')
 return {'schema_version':'project_village_resolution_worklist_api.v1','mode':'READ_ONLY','project':{k:p[k] for k in ('project_id','tenant_id','name','status')},'scope_sources':sources,'summary':summary,'pagination':{'limit':limit,'offset':offset,'filtered_total':int(first['filtered_total']) if first else 0,'has_more':bool(first and offset+len(rows)<int(first['filtered_total']))},'items':[{k:r[k] for k in keys} for r in rows],'guardrails':guardrails()}
@router.get('/projects/{project_id}/nwdp-candidates')
def nwdp_candidates(project_id:UUID,canonical_village_id:UUID=Query(...),q:Optional[str]=Query(None,max_length=120),limit:int=Query(20,ge=1,le=50),db:Session=Depends(get_db),x_tenant_id:str=Header('default',alias='X-Tenant-ID'),_principal=Depends(require_admin_permission(AdminPermission.VIEW,project_scoped=True))):
 p=project(db,project_id,x_tenant_id)
 if not _project_contains_village(db,project_id,canonical_village_id):raise HTTPException(409,'VILLAGE_NOT_IN_PROJECT_SCOPE')
 canonical=db.execute(text("""select v.id::text village_id,v.lgd_code::text village_lgd_code,v.canonical_name village_name,b.canonical_name block_name,d.canonical_name district_name,s.canonical_name state_name from geography_villages v join geography_blocks b on b.id=v.block_id join geography_districts d on d.id=v.district_id join geography_states s on s.id=d.state_id where v.id=:id and v.is_active"""),{'id':str(canonical_village_id)}).mappings().first()
 if not canonical:raise HTTPException(404,'ACTIVE_CANONICAL_VILLAGE_NOT_FOUND')
 query=(q or canonical['village_name']).strip()
 if len(query)<2:raise HTTPException(400,{'code':'NWDP_CANDIDATE_QUERY_TOO_SHORT','minimum_length':2})
 rows=db.execute(text("""select f.id::text source_feature_id,f.source_vlcode,f.source_state_name,f.source_district_name,f.source_subdistrict_name,f.source_block_name,f.source_village_name,c.proposed_village_id::text mapped_village_id,(x.id is not null) has_active_runtime,case when lower(coalesce(f.source_village_name,''))=lower(:query) then 'EXACT_NAME' when f.source_village_name ilike :contains then 'PARTIAL_NAME' when f.source_vlcode=:query then 'SOURCE_CODE' else 'HIERARCHY_MATCH' end match_basis from geography_boundary_source_features f join geography_boundary_import_batches ib on ib.id=f.import_batch_id and ib.source_system='NWDP_GSI_VILLAGE_BOUNDARY' left join lateral(select cc.id,cc.proposed_village_id from geography_boundary_crosswalk_candidates cc where cc.source_feature_id=f.id order by cc.created_at desc nulls last limit 1)c on true left join geography_boundary_runtime_crosswalks x on x.source_candidate_id=c.id and x.is_active where (f.source_village_name ilike :contains or f.source_vlcode=:query) and (f.source_state_name ilike :state or f.source_district_name ilike :district) order by case when lower(coalesce(f.source_village_name,''))=lower(:query) then 0 when lower(coalesce(f.source_district_name,''))=lower(:district_name) then 1 else 2 end,f.source_village_name,f.source_vlcode limit :limit"""),{'query':query,'contains':'%'+query+'%','state':'%'+canonical['state_name']+'%','district':'%'+canonical['district_name']+'%','district_name':canonical['district_name'],'limit':limit}).mappings().all()
 items=[]
 for row in rows:
  item=dict(row);item['eligible_for_canonical_enrichment']=item['mapped_village_id'] is None or item['mapped_village_id']==str(canonical_village_id);item['eligible_for_project_local_addition']=item['mapped_village_id'] is None and not item['has_active_runtime'];items.append(item)
 return {'schema_version':'project_village_resolution_nwdp_candidates.v1','mode':'READ_ONLY','project':{k:p[k] for k in ('project_id','tenant_id','name','status')},'canonical_village':dict(canonical),'query':query,'count':len(items),'items':items,'guardrails':guardrails()}
@router.post('/projects/{project_id}/dry-run')
def dry_run(project_id:UUID,body:ProjectVillageResolutionDryRun,db:Session=Depends(get_db),x_tenant_id:str=Header('default',alias='X-Tenant-ID'),principal=Depends(require_admin_permission(AdminPermission.PROJECT_EDIT,project_scoped=True))):
 p=project(db,project_id,x_tenant_id)
 if not body.dry_run or body.confirm_apply:raise HTTPException(503,{'code':'PROJECT_VILLAGE_RESOLUTION_APPLY_DISABLED','message':'Only read-only dry runs are enabled.'})
 if body.resolution_mode not in {'CANONICAL_ENRICHMENT','PROJECT_LOCAL_ADDITION'}:raise HTTPException(400,'INVALID_RESOLUTION_MODE')
 if any(not PIN_RE.fullmatch(pin) for pin in body.pin_codes):raise HTTPException(400,'INVALID_PIN_CODE')
 canonical=None;source=None
 if body.resolution_mode=='CANONICAL_ENRICHMENT':
  if not body.canonical_village_id:raise HTTPException(400,'CANONICAL_ENRICHMENT_REQUIRES_CANONICAL_VILLAGE')
  if not _project_contains_village(db,project_id,body.canonical_village_id):raise HTTPException(409,'VILLAGE_NOT_IN_PROJECT_SCOPE')
  canonical=db.execute(text("select id::text village_id,lgd_code::text village_lgd_code,canonical_name from geography_villages where id=:id and is_active"),{'id':str(body.canonical_village_id)}).mappings().first()
  if body.nwdp_source_feature_id:
   source=db.execute(text("""select f.id::text source_feature_id,f.source_vlcode,f.source_state_name,f.source_district_name,f.source_subdistrict_name,f.source_block_name,f.source_village_name from geography_boundary_source_features f join geography_boundary_import_batches b on b.id=f.import_batch_id where f.id=:id and b.source_system='NWDP_GSI_VILLAGE_BOUNDARY'"""),{'id':str(body.nwdp_source_feature_id)}).mappings().first()
   if not source:raise HTTPException(404,'NWDP_SOURCE_FEATURE_NOT_FOUND')
   conflict=db.execute(text("select 1 from geography_boundary_crosswalk_candidates where source_feature_id=:source and proposed_village_id is not null and proposed_village_id<>:village limit 1"),{'source':str(body.nwdp_source_feature_id),'village':str(body.canonical_village_id)}).first()
   if conflict:raise HTTPException(409,'NWDP_SOURCE_MAPPED_TO_DIFFERENT_CANONICAL_VILLAGE')
 else:
  if not body.nwdp_source_feature_id or body.canonical_village_id:raise HTTPException(400,'PROJECT_LOCAL_ADDITION_REQUIRES_ONLY_NWDP_SOURCE')
  source=db.execute(text("""select f.id::text source_feature_id,f.source_vlcode,f.source_state_name,f.source_district_name,f.source_subdistrict_name,f.source_block_name,f.source_village_name from geography_boundary_source_features f join geography_boundary_import_batches b on b.id=f.import_batch_id where f.id=:id and b.source_system='NWDP_GSI_VILLAGE_BOUNDARY' and not exists(select 1 from geography_boundary_crosswalk_candidates c where c.source_feature_id=f.id and c.proposed_village_id is not null) and not exists(select 1 from geography_boundary_runtime_crosswalks x join geography_boundary_crosswalk_candidates c on c.id=x.source_candidate_id where c.source_feature_id=f.id and x.is_active)"""),{'id':str(body.nwdp_source_feature_id)}).mappings().first()
  if not source:raise HTTPException(409,'NWDP_SOURCE_NOT_ELIGIBLE_FOR_PROJECT_LOCAL_ADDITION')
 if body.pin_codes:
  found=set(db.execute(text("select distinct pin_code from geography_postal_references where is_active and pin_code=any(:pins)"),{'pins':body.pin_codes}).scalars())
  if found!=set(body.pin_codes):raise HTTPException(409,{'code':'PIN_EVIDENCE_NOT_FOUND','missing':sorted(set(body.pin_codes)-found)})
 return {'schema_version':'project_village_resolution_dry_run.v1','mode':'DRY_RUN_APPLY_DISABLED','status':'VALID' if (canonical or source) else 'INVALID','project':{k:p[k] for k in ('project_id','tenant_id','name','status')},'preview':{'resolution_mode':body.resolution_mode,'canonical_village':dict(canonical) if canonical else None,'nwdp_source_feature':dict(source) if source else None,'display_name':body.display_name,'pin_codes':body.pin_codes,'hierarchy_labels':body.hierarchy_labels,'evidence_basis':body.evidence_basis,'rollback_token':body.rollback_token,'would_write':False,'would_be_android_visible':False},'guardrails':guardrails()}
