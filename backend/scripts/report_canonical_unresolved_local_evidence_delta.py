#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,re,sys,time
from collections import Counter,defaultdict
from pathlib import Path
from sqlalchemy import bindparam,text
BACKEND=Path(__file__).resolve().parents[1];ROOT=BACKEND.parent;sys.path.insert(0,str(BACKEND))
from app.core.database import engine
from scripts.report_project_village_resolution_worklist import CLASSIFIED_SQL,NWDP_UNMAPPED_SQL,SNAPSHOT_SQL,SOURCE_SYSTEM
SCHEMA_VERSION="canonical_unresolved_local_evidence_delta.v1"
EXPECTED={"canonical_unresolved":7493,"unmapped_sources":162229,"candidate_pairs":290,"deterministic":70,"high_confidence":70,"ambiguous":47,"blocked":7306}
PRIOR_EVIDENCE=("data/staged/core_stack/promotion_review/20260930-current-canonical-unresolved-reaudit-v1/nwdp_current_canonical_unresolved_reaudit.json","data/staged/core_stack/promotion_review/20260930-current-canonical-unresolved-reaudit-v1/nwdp_legacy_held_resolution_coverage_manifest.json","data/staged/core_stack/promotion_review/20260930-canonical-identity-gap-audit-v1/geography_canonical_identity_gap_audit.json","data/staged/core_stack/promotion_review/20260930-authoritative-identity-source-worklist-v1/geography_authoritative_identity_source_worklist.json")
def norm(v):return re.sub(r"[^a-z0-9]+","",str(v or "").lower())
def add(index,key,row):
 if all(key):index[key].append(row)
def write_csv(path,rows):
 if not rows:path.write_text("",encoding="utf-8");return
 with path.open("w",newline="",encoding="utf-8") as h:w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 p=argparse.ArgumentParser();p.add_argument("--output-dir",required=True,type=Path);a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
 with engine.connect() as c:
  tx=c.begin();c.execute(text("select set_config('statement_timeout','900000ms',true)"));before=dict(c.execute(text(SNAPSHOT_SQL)).mappings().one())
  canonical=[dict(r) for r in c.execute(text(CLASSIFIED_SQL),{"source_system":SOURCE_SYSTEM}).mappings() if r["resolution_status"]=="UNRESOLVED"];sources=[dict(r) for r in c.execute(text(NWDP_UNMAPPED_SQL),{"source_system":SOURCE_SYSTEM}).mappings()]
  block_codes={r["village_id"]:str(r["block_lgd_code"]) for r in c.execute(text("select v.id::text village_id,b.lgd_code::text block_lgd_code from geography_villages v join geography_blocks b on b.id=v.block_id where v.is_active")).mappings()}
  for village in canonical:village["block_lgd_code"]=block_codes[village["village_id"]]
  code=defaultdict(list);code_name=defaultdict(list);hcode=defaultdict(list);hname=defaultdict(list);dname=defaultdict(list)
  for s in sources:
   s["_vn"]=norm(s["source_village_name"]);s["_sn"]=norm(s["source_state_name"]);s["_dn"]=norm(s["source_district_name"]);s["_bn"]=norm(s["source_block_name"] or s["source_subdistrict_name"])
   add(code,(str(s["source_stcode"] or ""),str(s["source_vlcode"] or "")),s);add(code_name,(s["_sn"],str(s["source_vlcode"] or "")),s);add(hcode,(str(s["source_stcode"] or ""),str(s["source_dtcode"] or ""),str(s["source_sdcode"] or s["source_bkcode"] or ""),s["_vn"]),s);add(hname,(s["_sn"],s["_dn"],s["_bn"],s["_vn"]),s);add(dname,(s["_sn"],s["_dn"],s["_vn"]),s)
  villages=[];pairs=[];selected=set()
  for v in canonical:
   sc,dc,bc,vc=str(v["state_lgd_code"]),str(v["district_lgd_code"]),str(v["block_lgd_code"]),str(v["village_lgd_code"]);sn,dn,bn,vn=norm(v["state_name"]),norm(v["district_name"]),norm(v["block_name"]),norm(v["village_name"]);matches={}
   groups=((1,"EXACT_SOURCE_CODE_STATE_CONSISTENT",code.get((sc,vc),[])+code_name.get((sn,vc),[])),(2,"EXACT_HIERARCHY_CODE_AND_NAME",hcode.get((sc,dc,bc,vn),[])),(3,"EXACT_NORMALIZED_HIERARCHY_NAME",hname.get((sn,dn,bn,vn),[])),(4,"DISTRICT_SCOPED_EXACT_NAME_REVIEW",dname.get((sn,dn,vn),[])))
   for rank,basis,rows in groups:
    for s in rows:
     sid=s["source_feature_id"]
     if sid not in matches or rank<matches[sid][0]:matches[sid]=(rank,basis,s)
   ordered=sorted(matches.values(),key=lambda x:(x[0],x[2]["source_feature_index"],x[2]["source_feature_id"]));count=len(ordered);best=ordered[0][0] if ordered else None;disp="NO_LOCAL_CANDIDATE" if not count else "DETERMINISTIC_SINGLE_REVIEW" if count==1 and best<=3 else "HIGH_CONFIDENCE_SINGLE_REVIEW" if count==1 else "AMBIGUOUS_MULTIPLE_CANDIDATES";base={k:v[k] for k in ("village_id","village_lgd_code","village_name","block_name","district_lgd_code","district_name","state_lgd_code","state_name")};villages.append({**base,"candidate_count":count,"best_match_rank":best,"disposition":disp,"automatic_resolution_authorized":False})
   for n,(rank,basis,s) in enumerate(ordered,1):selected.add(s["source_feature_id"]);pairs.append({**base,"disposition":disp,"candidate_count":count,"candidate_number":n,"match_rank":rank,"match_basis":basis,**{k:s[k] for k in ("source_feature_id","source_feature_index","source_stcode","source_dtcode","source_sdcode","source_bkcode","source_vlcode","source_state_name","source_district_name","source_subdistrict_name","source_block_name","source_village_name")}})
  evidence=defaultdict(list)
  if selected:
   q=text("select source_feature_id::text source_feature_id,candidate_bucket,review_status,promotion_status from geography_boundary_crosswalk_candidates where source_feature_id in :ids order by source_feature_id,created_at").bindparams(bindparam("ids",expanding=True))
   for r in c.execute(q,{"ids":sorted(selected)}).mappings():evidence[r["source_feature_id"]].append(":".join(str(r[k] or "") for k in ("candidate_bucket","review_status","promotion_status")))
  after=dict(c.execute(text(SNAPSHOT_SQL)).mappings().one());tx.rollback()
 for r in pairs:values=sorted(set(evidence.get(r["source_feature_id"],[])));r["prior_candidate_evidence_present"]=bool(values);r["prior_candidate_evidence"]="|".join(values)
 dispositions=Counter(r["disposition"] for r in villages);states=defaultdict(Counter)
 for r in villages:states[(r["state_lgd_code"],r["state_name"])][r["disposition"]]+=1
 state_rows=[{"state_lgd_code":k[0],"state_name":k[1],"unresolved":sum(v.values()),"DETERMINISTIC_SINGLE_REVIEW":v["DETERMINISTIC_SINGLE_REVIEW"],"HIGH_CONFIDENCE_SINGLE_REVIEW":v["HIGH_CONFIDENCE_SINGLE_REVIEW"],"AMBIGUOUS_MULTIPLE_CANDIDATES":v["AMBIGUOUS_MULTIPLE_CANDIDATES"],"NO_LOCAL_CANDIDATE":v["NO_LOCAL_CANDIDATE"]} for k,v in sorted(states.items(),key=lambda x:int(x[0][0]))];prior=[{"path":p,"exists":(ROOT/p).exists()} for p in PRIOR_EVIDENCE]
 checks={"database_counts_unchanged":before==after,"canonical_unresolved_exact":len(canonical)==EXPECTED["canonical_unresolved"],"unmapped_sources_exact":len(sources)==EXPECTED["unmapped_sources"],"candidate_pairs_exact":len(pairs)==EXPECTED["candidate_pairs"],"deterministic_exact":dispositions["DETERMINISTIC_SINGLE_REVIEW"]==EXPECTED["deterministic"],"high_confidence_exact":dispositions["HIGH_CONFIDENCE_SINGLE_REVIEW"]==EXPECTED["high_confidence"],"ambiguous_exact":dispositions["AMBIGUOUS_MULTIPLE_CANDIDATES"]==EXPECTED["ambiguous"],"blocked_exact":dispositions["NO_LOCAL_CANDIDATE"]==EXPECTED["blocked"],"prior_evidence_present":all(r["exists"] for r in prior)}
 payload={"schema_version":SCHEMA_VERSION,"status":"PASSED" if all(checks.values()) else "FAILED","healthy":all(checks.values()),"read_only":True,"elapsed_ms":round((time.perf_counter()-started)*1000,3),"checks":checks,"database_before":before,"database_after":after,"scope":{"canonical_unresolved":len(canonical),"unmapped_nwdp_sources":len(sources),"candidate_pairs":len(pairs)},"dispositions":dict(dispositions),"prior_evidence_sources":prior,"policy":{"fuzzy_matching_used":False,"automatic_resolution_authorized":False,"canonical_changes_authorized":False,"pin_link_changes_authorized":False,"nwdp_candidate_changes_authorized":False,"runtime_changes_authorized":False,"project_resolution_changes_authorized":False,"android_changes_authorized":False}}
 write_csv(a.output_dir/"canonical_unresolved_villages.csv",villages);write_csv(a.output_dir/"canonical_unresolved_candidate_pairs.csv",pairs);write_csv(a.output_dir/"canonical_unresolved_state_summary.csv",state_rows);(a.output_dir/"canonical_unresolved_local_evidence_delta.json").write_text(json.dumps(payload,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8");print(json.dumps(payload,indent=2,sort_keys=True,default=str))
 if not payload["healthy"]:raise SystemExit("CANONICAL UNRESOLVED LOCAL EVIDENCE DELTA FAILED")
 print("CANONICAL UNRESOLVED LOCAL EVIDENCE DELTA PASSED");return 0
if __name__=="__main__":raise SystemExit(main())
