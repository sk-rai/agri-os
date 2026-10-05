#!/usr/bin/env python3
"""Read-only AST audit of API tenant, actor, and authentication boundaries."""
from __future__ import annotations
import ast,json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];APP=ROOT/"backend/app"
METHODS={"get","post","put","patch","delete"};MUTATIONS={"POST","PUT","PATCH","DELETE"}
PUBLIC_PREFIXES=("/api/v1/auth/otp/","/health")
REFERENCE_PREFIXES=("/api/v1/master-data/states","/api/v1/master-data/districts",
 "/api/v1/master-data/blocks","/api/v1/master-data/villages","/api/v1/crop-catalog",
 "/api/v1/input-catalog","/api/v1/forms","/api/v1/workflows")
def literal(node):
    try:return ast.literal_eval(node)
    except Exception:return None
def router_prefix(tree):
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="router" for t in node.targets):
            if isinstance(node.value,ast.Call):
                for kw in node.value.keywords:
                    if kw.arg=="prefix":
                        value=literal(kw.value)
                        return value if isinstance(value,str) else ""
    return ""
def route_decorator(node):
    for decorator in node.decorator_list:
        if not isinstance(decorator,ast.Call) or not isinstance(decorator.func,ast.Attribute):continue
        if decorator.func.attr not in METHODS:continue
        path=literal(decorator.args[0]) if decorator.args else ""
        if isinstance(path,str):return decorator.func.attr.upper(),path
    return None
def scan(path):
    tree=ast.parse(path.read_text(encoding="utf-8-sig"));prefix=router_prefix(tree);rows=[]
    for node in ast.walk(tree):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
        route=route_decorator(node)
        if not route:continue
        method,suffix=route;body=ast.unparse(node);full=f"{prefix}{suffix}"
        admin="require_admin_permission" in body
        bearer=any(x in body for x in ("Authorization","authorization","jwt.decode","AdminPrincipal"))
        tenant=any(x in body for x in ("X-Tenant-ID","x_tenant_id","principal.tenant_id"))
        actor=any(x in body for x in ("X-Actor-ID","x_actor_id","principal.user_id","claims.get('sub')","claims.get(\"sub\")"))
        public=any(full.startswith(p) for p in PUBLIC_PREFIXES)
        reference=method=="GET" and any(full.startswith(p) for p in REFERENCE_PREFIXES)
        flags=[]
        if method in MUTATIONS and not public and not(admin or bearer):flags.append("MUTATION_WITHOUT_AUTH_MARKER")
        if method in MUTATIONS and not public and not tenant:flags.append("MUTATION_WITHOUT_TENANT_MARKER")
        if method in MUTATIONS and not public and not actor:flags.append("MUTATION_WITHOUT_ACTOR_MARKER")
        if method=="GET" and not public and not reference and not(admin or bearer):flags.append("NON_REFERENCE_READ_WITHOUT_AUTH_MARKER")
        rows.append({"file":str(path.relative_to(ROOT)),"line":node.lineno,"method":method,
          "path":full,"function":node.name,"admin_dependency":admin,"bearer_marker":bearer,
          "tenant_marker":tenant,"actor_marker":actor,"public":public,"reference":reference,"flags":flags})
    return rows
def main():
    rows=[]
    for path in sorted(APP.rglob("*.py")):
        if path.name.startswith("__"):continue
        rows.extend(scan(path))
    flagged=[r for r in rows if r["flags"]]
    mutation=[r for r in rows if r["method"] in MUTATIONS and not r["public"]]
    unauth=[r for r in mutation if "MUTATION_WITHOUT_AUTH_MARKER" in r["flags"]]
    by_file=Counter(r["file"] for r in unauth)
    payload={"schema_version":"tenant_actor_trust_boundary_audit.v1","status":"REVIEW_REQUIRED",
      "read_only":True,"scope":{"routes":len(rows),"non_public_mutations":len(mutation),
        "mutations_without_auth_marker":len(unauth),"flagged_routes":len(flagged)},
      "checks":{"ast_parse_complete":True,"database_accessed":False,"database_writes_attempted":False},
      "highest_risk_files":[{"file":name,"mutation_routes_without_auth_marker":count} for name,count in by_file.most_common()],
      "mutation_routes_without_auth_marker":unauth,"all_flagged_routes":flagged,
      "policy":{"headers_are_not_authorization":True,"automatic_enforcement_authorized":False,
        "android_contract_changes_authorized":False,"route_by_route_review_required":True}}
    print(json.dumps(payload,indent=2,sort_keys=True))
    print("TENANT AND ACTOR TRUST BOUNDARY AUDIT COMPLETED: REVIEW REQUIRED")
    return 0
if __name__=="__main__":raise SystemExit(main())
