#!/usr/bin/env python3
"""Build review-only name and vernacular evidence for same-parent villages."""
import argparse,csv,json,re,sys,time,unicodedata
from collections import Counter,defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from sqlalchemy import bindparam,text
BACKEND=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND))
from app.core.database import engine
from scripts.report_project_village_resolution_worklist import NWDP_UNMAPPED_SQL,SNAPSHOT_SQL,SOURCE_SYSTEM
SCHEMA_VERSION="canonical_same_parent_name_evidence.v1";EXPECTED=3939
EXPECTED_DISPOSITIONS={"STRONG_SINGLE_REVIEW":130,"AMBIGUOUS_OR_MODERATE_REVIEW":1104,"WEAK_NAME_SIGNAL":1007,"NO_NAME_SIGNAL":1698}
def norm(v):return re.sub(r"[^a-z0-9]+","",unicodedata.normalize("NFKD",str(v or "")).casefold())
def unorm(v):return "".join(c for c in unicodedata.normalize("NFKC",str(v or "")).casefold() if c.isalnum())
def vern(v):return any(ord(c)>127 and c.isalpha() for c in str(v or ""))
def names(value):
 out=[]
 def add(v,kind):
  if isinstance(v,str) and v.strip():out.append((v.strip(),kind))
 if isinstance(value,list):
  for x in value:
   if isinstance(x,str):add(x,"ALIAS")
   elif isinstance(x,dict):add(x.get("name") or x.get("label") or x.get("value"),str(x.get("lang") or "ALIAS"))
 elif isinstance(value,dict):
  for k,v in value.items():
   if isinstance(v,list):
    for x in v:add(x,k)
   else:add(v,k)
 return out
def score(a,b):
 na,nb=norm(a),norm(b)
 return SequenceMatcher(None,na,nb).ratio() if na and nb else 0.0
def vscore(a,b):
 if not(vern(a) and vern(b)):return None
 na,nb=unorm(a),unorm(b)
 return SequenceMatcher(None,na,nb).ratio() if na and nb else None
def write(path,rows):
 if not rows:path.write_text("",encoding="utf-8");return
 with path.open("w",newline="",encoding="utf-8") as h:w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 p=argparse.ArgumentParser();p.add_argument("--actionability-input",required=True,type=Path);p.add_argument("--output-dir",required=True,type=Path);a=p.parse_args();start=time.perf_counter()
 with a.actionability_input.open(newline="",encoding="utf-8") as h:base=[r for r in csv.DictReader(h) if r["actionability"]=="SAME_PARENT_NAME_RESEARCH_REQUIRED"]
 ids=[r["village_id"] for r in base]
 with engine.connect() as c:
  tx=c.begin();before=dict(c.execute(text(SNAPSHOT_SQL)).mappings().one())
  q=text("select id::text village_id,canonical_name,census_name,aliases from geography_villages where id in :ids").bindparams(bindparam("ids",expanding=True))
  canon={r["village_id"]:dict(r) for r in c.execute(q,{"ids":ids}).mappings()}
  src=[dict(r) for r in c.execute(text(NWDP_UNMAPPED_SQL),{"source_system":SOURCE_SYSTEM}).mappings()]
  after=dict(c.execute(text(SNAPSHOT_SQL)).mappings().one());tx.rollback()
 groups=defaultdict(list)
 for s in src:groups[(norm(s["source_state_name"]),norm(s["source_district_name"]),norm(s["source_block_name"] or s["source_subdistrict_name"]))].append(s)
 results=[];pairs=[]
 for v in base:
  cv=canon[v["village_id"]];cn=[(cv["canonical_name"],"CANONICAL")]
  if cv.get("census_name"):cn.append((cv["census_name"],"CENSUS"))
  cn+=names(cv.get("aliases"))
  candidates=groups[(norm(v["state_name"]),norm(v["district_name"]),norm(v["block_name"]))]
  ranked=[]
  for s in candidates:
   source_names=[(s["source_village_name"],"NWDP")]
   comparisons=[]
   for x,xk in cn:
    for y,yk in source_names:
     comparisons.append((score(x,y),vscore(x,y),x,xk,y,yk))
   best=max(comparisons,key=lambda z:(z[0],z[1] or -1))
   ranked.append((max(best[0],best[1] or 0),best,s))
  ranked.sort(key=lambda x:(-x[0],x[2]["source_feature_id"]))
  best=ranked[0][0] if ranked else 0;near=[x for x in ranked if best-x[0]<=0.02]
  has_v=any(vv is not None for _,(_,vv,*_),_ in ranked)
  if best>=.90 and len(near)==1:disp="STRONG_SINGLE_REVIEW"
  elif best>=.75:disp="AMBIGUOUS_OR_MODERATE_REVIEW"
  elif best>=.60:disp="WEAK_NAME_SIGNAL"
  else:disp="NO_NAME_SIGNAL"
  results.append({**v,"name_evidence_disposition":disp,"best_combined_similarity":round(best,6),"near_best_candidate_count":len(near),"canonical_vernacular_available":any(vern(x) for x,_ in cn),"source_vernacular_available":any(vern(x[2]["source_village_name"]) for x in ranked),"vernacular_similarity_evaluated":has_v,"automatic_resolution_authorized":False})
  for n,(combined,bestrow,s) in enumerate(ranked[:3],1):
   latin,vs,x,xk,y,yk=bestrow;pairs.append({"village_id":v["village_id"],"village_lgd_code":v["village_lgd_code"],"village_name":v["village_name"],"candidate_rank":n,"source_feature_id":s["source_feature_id"],"source_village_name":s["source_village_name"],"canonical_evidence_name":x,"canonical_evidence_kind":xk,"latin_similarity":round(latin,6),"vernacular_similarity":round(vs,6) if vs is not None else "","combined_similarity":round(combined,6),"disposition":disp,"automatic_resolution_authorized":False})
 counts=Counter(r["name_evidence_disposition"] for r in results);checks={"same_parent_total_exact":len(results)==EXPECTED,"database_counts_unchanged":before==after,"partition_exact":sum(counts.values())==EXPECTED,"dispositions_exact":dict(counts)==EXPECTED_DISPOSITIONS,"vernacular_absence_exact":sum(r["canonical_vernacular_available"] for r in results)==0 and sum(r["source_vernacular_available"] for r in results)==0,"automatic_resolution_prohibited":all(not r["automatic_resolution_authorized"] for r in results)}
 payload={"schema_version":SCHEMA_VERSION,"status":"PASSED" if all(checks.values()) else "FAILED","healthy":all(checks.values()),"read_only":True,"scope":{"same_parent_villages":len(results),"candidate_pairs_top_three":len(pairs)},"dispositions":dict(counts),"vernacular":{"canonical_available":sum(r["canonical_vernacular_available"] for r in results),"source_available":sum(r["source_vernacular_available"] for r in results),"evaluated":sum(r["vernacular_similarity_evaluated"] for r in results),"cross_script_transliteration_available":False},"checks":checks,"database_before":before,"database_after":after,"policy":{"similarity_is_evidence_only":True,"automatic_resolution_authorized":False,"canonical_changes_authorized":False,"android_changes_authorized":False},"elapsed_ms":round((time.perf_counter()-start)*1000,3)}
 a.output_dir.mkdir(parents=True,exist_ok=True);write(a.output_dir/"same_parent_name_evidence.csv",results);write(a.output_dir/"same_parent_name_candidate_pairs.csv",pairs);(a.output_dir/"same_parent_name_evidence.json").write_text(json.dumps(payload,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8");print(json.dumps(payload,indent=2,sort_keys=True,default=str))
 if not payload["healthy"]:raise SystemExit("SAME-PARENT NAME EVIDENCE FAILED")
 print("SAME-PARENT NAME AND VERNACULAR EVIDENCE PASSED")
if __name__=="__main__":main()
