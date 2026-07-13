"""Regression for manufacturer/product/package/project approval hierarchy."""
from datetime import date, datetime, timezone
from pathlib import Path
import sys, uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Project, Tenant
from app.modules.master_data.models import AgriculturalProduct, AgriculturalProductPackage, Manufacturer, ProductCatalogAuditEvent, ProjectProductApproval
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

MFG="REGRESSION_AGRO"; PRODUCT="REGRESSION_UREA_BRAND"; CSV_MFG="REGRESSION_CSV_MFG"; CSV_PRODUCT="REGRESSION_CSV_PRODUCT"; PROJECT=uuid.uuid4()

def check(v,l):
    if not v: raise AssertionError(l)
    print("  OK ",l)

def cleanup(db, user=None):
    for product in db.query(AgriculturalProduct).filter(AgriculturalProduct.code.in_([PRODUCT,CSV_PRODUCT])).all():
        db.query(ProjectProductApproval).filter(ProjectProductApproval.product_id==product.id).delete(synchronize_session=False)
        db.query(AgriculturalProductPackage).filter(AgriculturalProductPackage.product_id==product.id).delete(synchronize_session=False)
        db.query(AgriculturalProduct).filter(AgriculturalProduct.id==product.id).delete(synchronize_session=False)
    from app.modules.master_data.models import ProductCatalogImportBatch
    db.query(ProductCatalogImportBatch).filter(ProductCatalogImportBatch.file_name=="products.csv").delete(synchronize_session=False)
    db.query(ProductCatalogAuditEvent).filter(ProductCatalogAuditEvent.entity_code.in_([MFG,PRODUCT,CSV_MFG,CSV_PRODUCT,"REG-CSV-45KG"])).delete(synchronize_session=False)
    db.query(Manufacturer).filter(Manufacturer.code.in_([MFG,CSV_MFG])).delete(synchronize_session=False)
    db.query(Project).filter(Project.id==PROJECT).delete(synchronize_session=False)
    db.commit()
    if user: delete_test_admin(db,user.id)

def main():
    db=SessionLocal(); admin,headers=create_test_admin(db); cleanup(db)
    try:
        if not db.query(Tenant).filter(Tenant.id=="default").first(): db.add(Tenant(id="default",name="Default",type="ENTERPRISE",created_at=datetime.now(timezone.utc),updated_at=datetime.now(timezone.utc)))
        db.add(Project(id=PROJECT,tenant_id="default",name="Product Regression",start_date=date(2027,1,1),end_date=date(2027,12,31),status="PLANNED",crop_scope=["RICE"],created_at=datetime.now(timezone.utc),updated_at=datetime.now(timezone.utc))); db.commit()
        client=TestClient(app,headers=headers)
        m=client.post("/api/v1/product-catalog/manufacturers",json={"code":MFG,"canonical_name":"Regression Agro Industries","short_name":"RAI","country":"India","reason":"Regression manufacturer"})
        check(m.status_code==200 and m.json()["code"]==MFG,"manufacturer is created")
        m_update=client.put(f"/api/v1/product-catalog/manufacturers/{MFG}",json={"short_name":"RAI Updated","reason":"Regression manufacturer update"})
        check(m_update.status_code==200 and m_update.json()["short_name"]=="RAI Updated","manufacturer metadata is updated")
        payload={"code":PRODUCT,"canonical_input_code":"UREA_46_N","manufacturer_code":MFG,"brand_name":"Regression Urea Gold","composition":"46% Nitrogen","registration_number":"REG-UREA-001","registration_authority":"Regression Authority","country":"India","packages":[{"sku":"REG-UREA-45KG","quantity":"45","unit":"kg","pack_label":"45 kg bag","barcode":"999000111"}],"reason":"Regression product"}
        p=client.post("/api/v1/product-catalog/products",json=payload)
        check(p.status_code==200 and p.json()["packages"][0]["quantity"]=="45.000","branded product and package are created")
        extra=client.post(f"/api/v1/product-catalog/products/{PRODUCT}/packages",json={"sku":"REG-UREA-5KG","quantity":"5","unit":"kg","pack_label":"5 kg bag","reason":"Add small package"})
        check(extra.status_code==200 and extra.json()["sku"]=="REG-UREA-5KG","additional package variant is added")
        duplicate_package=client.post(f"/api/v1/product-catalog/products/{PRODUCT}/packages",json={"sku":"REG-UREA-5KG","quantity":"10","unit":"kg","pack_label":"duplicate","reason":"Duplicate check"})
        check(duplicate_package.status_code==409,"duplicate package SKU is rejected")
        duplicate=client.post("/api/v1/product-catalog/products",json={**payload,"code":"REGRESSION_UREA_DUPLICATE","packages":[{"sku":"REG-UREA-DUP","quantity":1,"unit":"kg","pack_label":"1 kg"}]})
        check(duplicate.status_code==409,"duplicate registration number is rejected")
        template=client.get("/api/v1/product-catalog/csv/template")
        check(template.status_code==200 and "manufacturer_code" in template.text and "package_sku" in template.text,"product CSV template downloads with package columns")
        export=client.get("/api/v1/product-catalog/csv/export")
        check(export.status_code==200 and PRODUCT in export.text and "REG-UREA-45KG" in export.text,"product CSV export includes created product package")
        valid_csv="manufacturer_code,manufacturer_name,manufacturer_short_name,manufacturer_country,product_code,canonical_input_code,brand_name,composition,registration_number,registration_authority,registration_expiry_date,product_country,product_status,package_sku,package_quantity,package_unit,package_label,package_barcode\nREGRESSION_CSV_MFG,Regression CSV Manufacturer,RCM,India,REGRESSION_CSV_PRODUCT,UREA_46_N,Regression CSV Product,46% Nitrogen,REG-CSV-001,Regression Authority,2028-12-31,India,ACTIVE,REG-CSV-45KG,45,kg,45 kg bag,\n"
        valid_csv_response=client.post("/api/v1/product-catalog/csv/validate",files={"file":("products.csv",valid_csv.encode("utf-8"),"text/csv")})
        valid_batch=valid_csv_response.json()
        check(valid_csv_response.status_code==200 and valid_batch["can_apply"] and valid_batch["report"]["summary"]["create"]==1,"product CSV validation accepts create row")
        apply_response=client.post(f"/api/v1/product-catalog/csv/imports/{valid_batch['batch_id']}/apply",json={"reason":"Product CSV regression apply"})
        applied_batch=apply_response.json()
        check(apply_response.status_code==200 and applied_batch["status"]=="APPLIED" and applied_batch["report"]["applied_counts"]["products_created"]==1,"validated product CSV batch applies")
        repeat_apply=client.post(f"/api/v1/product-catalog/csv/imports/{valid_batch['batch_id']}/apply",json={"reason":"Repeat apply should fail"})
        check(repeat_apply.status_code==409,"applied product CSV batch cannot be applied twice")
        csv_catalog=client.get("/api/v1/product-catalog/products?input_code=UREA_46_N")
        check(any(x["code"]==CSV_PRODUCT and x["packages"][0]["sku"]=="REG-CSV-45KG" for x in csv_catalog.json()["products"]),"applied product CSV creates product and package")
        invalid_csv="manufacturer_code,manufacturer_name,product_code,canonical_input_code,brand_name,package_sku,package_quantity,package_unit,package_label\nREGRESSION_AGRO,Regression Agro,BAD_PRODUCT,NO_SUCH_INPUT,,REG-UREA-45KG,-1,kg,\n"
        invalid_csv_response=client.post("/api/v1/product-catalog/csv/validate",files={"file":("products.csv",invalid_csv.encode("utf-8"),"text/csv")})
        invalid_batch=invalid_csv_response.json()
        check(invalid_csv_response.status_code==200 and not invalid_batch["can_apply"] and invalid_batch["report"]["summary"]["errors"]>0,"product CSV validation reports invalid rows")
        history=client.get("/api/v1/product-catalog/csv/imports?limit=10")
        check(history.status_code==200 and valid_batch["batch_id"] in {item["batch_id"] for item in history.json()["imports"]},"product CSV import history includes validated batch")
        invalid_history=client.get("/api/v1/product-catalog/csv/imports?status=INVALID&limit=10")
        check(invalid_history.status_code==200 and all(item["status"]=="INVALID" for item in invalid_history.json()["imports"]),"product CSV import history filters invalid batches")
        catalog=TestClient(app).get(f"/api/v1/product-catalog/products?input_code=UREA_46_N", headers={"X-Tenant-ID":"default"})
        check(catalog.status_code==200 and any(x["code"]==PRODUCT for x in catalog.json()["products"]),"runtime lists product by canonical input")
        approval=client.put(f"/api/v1/product-catalog/projects/{PROJECT}/products/{PRODUCT}",json={"enabled":True,"preferred":True,"display_order":1,"reason":"Preferred project urea"})
        check(approval.status_code==200 and approval.json()["product"]["project_approval"]["preferred"],"project marks product preferred")
        scoped=TestClient(app).get(f"/api/v1/product-catalog/products?input_code=UREA_46_N&project_id={PROJECT}",headers={"X-Tenant-ID":"default"})
        check(scoped.json()["approval_policy"]=="EXPLICIT" and scoped.json()["count"]==1,"project endpoint applies explicit approval policy")
        client.put(f"/api/v1/product-catalog/projects/{PROJECT}/products/{PRODUCT}",json={"enabled":False,"preferred":False,"display_order":1,"reason":"Temporarily blocked"})
        blocked=TestClient(app).get(f"/api/v1/product-catalog/products?input_code=UREA_46_N&project_id={PROJECT}",headers={"X-Tenant-ID":"default"})
        check(blocked.json()["count"]==0,"disabled project product is hidden")
        updated=client.put(f"/api/v1/product-catalog/products/{PRODUCT}",json={"status":"DISCONTINUED","reason":"Regression discontinuation"})
        check(updated.status_code==200 and updated.json()["status"]=="DISCONTINUED","product can be discontinued")
        runtime=TestClient(app).get(f"/api/v1/product-catalog/products?input_code=UREA_46_N", headers={"X-Tenant-ID":"default"})
        check(all(x["code"]!=PRODUCT for x in runtime.json()["products"]),"discontinued product is hidden from runtime")
        audit=client.get(f"/api/v1/product-catalog/audit?entity_code={PRODUCT}").json()
        check({"CREATE_PRODUCT","UPDATE_PRODUCT"}.issubset({x["action"] for x in audit["events"]}),"product mutations are audited")
        print("PASS")
    finally:
        cleanup(db,admin); db.close()
if __name__=="__main__": main()