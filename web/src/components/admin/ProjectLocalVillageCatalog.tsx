"use client";
import { useCallback,useEffect,useState } from "react";
import { api } from "@/lib/api";
type Item={identity_type:"CANONICAL_LGD"|"PROJECT_LOCAL";village_id:string|null;project_village_resolution_id:string|null;display_name:string;village_code:string;state_name:string|null;district_name:string|null;block_name:string|null;pin_codes:string[]};
type Catalog={schema_version:"project_available_villages.v1";scope:"TENANT_PROJECT_ONLY";pagination:{filtered_total:number;has_more:boolean};items:Item[]};
export default function ProjectLocalVillageCatalog({projectId,refreshKey}:{projectId:string;refreshKey:number}){
 const [query,setQuery]=useState(""),[catalog,setCatalog]=useState<Catalog|null>(null),[rollbackTokens,setRollbackTokens]=useState<Record<string,string>>({}),[confirmations,setConfirmations]=useState<Record<string,string>>({}),[loading,setLoading]=useState(false),[notice,setNotice]=useState<string|null>(null),[error,setError]=useState<string|null>(null);
 const load=useCallback(async()=>{if(!projectId)return;setLoading(true);setError(null);const params=new URLSearchParams({limit:"100",offset:"0"});if(query.trim())params.set("q",query.trim());try{setCatalog(await api<Catalog>(`/api/v1/master-data/geography/project-village-resolutions/projects/${projectId}/available-villages?${params}`))}catch(caught){setError(caught instanceof Error?caught.message:"Failed to load project village catalog")}finally{setLoading(false)}},[projectId,query]);
 useEffect(()=>{if(refreshKey>0)void load()},[load,refreshKey]);
 async function retire(item:Item){const id=item.project_village_resolution_id;if(!id)return;setLoading(true);setError(null);setNotice(null);try{await api(`/api/v1/master-data/geography/project-village-resolutions/projects/${projectId}/local-additions/${id}/retire`,{method:"POST",body:{rollback_token:rollbackTokens[id]||"",reason:"Project administrator retires this project-local village.",confirmation_phrase:confirmations[id]||""}});setNotice(`${item.display_name} retired from this project.`);await load()}catch(caught){setError(caught instanceof Error?caught.message:"Project-local village retirement failed")}finally{setLoading(false)}}
 const localItems=catalog?.items.filter(item=>item.identity_type==="PROJECT_LOCAL")||[];
 return <section data-testid="project-local-village-catalog" className="space-y-3 rounded-xl border border-cyan-200 bg-cyan-50 p-3">
  <div><h3 className="font-semibold text-cyan-950">Project-local village catalog</h3><p className="text-xs text-cyan-800">Web-admin project scope only. This does not change global LGD, PIN links, or Android.</p></div>
  <div className="flex gap-2"><input aria-label="Project village catalog search" value={query} onChange={event=>setQuery(event.target.value)} className="flex-1 rounded-lg border p-2 text-sm"/><button type="button" disabled={!projectId||loading} onClick={()=>void load()} className="rounded-lg border border-cyan-400 bg-white px-3 py-2 text-sm font-semibold text-cyan-900 disabled:text-slate-400">Load project village catalog</button></div>
  {catalog&&<p className="text-xs text-slate-600">Project-local results: {localItems.length} · Filtered total: {catalog.pagination.filtered_total}</p>}
  {localItems.map(item=>{const id=item.project_village_resolution_id as string;return <article key={id} data-testid={`project-local-village-${id}`} className="space-y-2 rounded-lg border bg-white p-3 text-sm">
   <div><strong>{item.display_name}</strong><div className="text-xs text-slate-500">{item.block_name||"unknown block"} · {item.district_name||"unknown district"} · {item.state_name||"unknown state"}</div></div>
   <input aria-label={`Rollback token for ${item.display_name}`} placeholder="Rollback token" value={rollbackTokens[id]||""} onChange={event=>setRollbackTokens(current=>({...current,[id]:event.target.value}))} className="w-full rounded-lg border p-2"/>
   <input aria-label={`Retirement confirmation for ${item.display_name}`} placeholder="Type RETIRE PROJECT LOCAL VILLAGE" value={confirmations[id]||""} onChange={event=>setConfirmations(current=>({...current,[id]:event.target.value}))} className="w-full rounded-lg border p-2"/>
   <button type="button" disabled={loading||!rollbackTokens[id]||confirmations[id]!=="RETIRE PROJECT LOCAL VILLAGE"} onClick={()=>void retire(item)} className="rounded-lg bg-rose-700 px-3 py-2 font-semibold text-white disabled:bg-slate-300">Retire from this project</button>
  </article>})}
  {catalog&&localItems.length===0&&<p className="text-sm text-slate-600">No active project-local villages match this search.</p>}
  {notice&&<p className="text-sm font-medium text-emerald-700">{notice}</p>}{error&&<p className="text-sm font-medium text-rose-700">{error}</p>}
 </section>
}
