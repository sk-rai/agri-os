"""Regression for crop activity product/package/dosage-rule traceability."""
from datetime import date, datetime, timezone
from pathlib import Path
import sys, uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.master_data.models import (
    AgriculturalInput,
    AgriculturalProduct,
    AgriculturalProductPackage,
    CropStageInputRule,
    CropStageInputRuleAuditEvent,
    Manufacturer,
    ProductCatalogAuditEvent,
    ProjectProductApproval,
)
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance

TENANT = "default"
MFG = "ACTIVITY_TRACE_AGRO"
PRODUCT = "ACTIVITY_TRACE_UREA"
SKU = "ACTIVITY_TRACE_UREA_45KG"


def now(): return datetime.now(timezone.utc)

def check(value, label, detail=None):
    if not value: raise AssertionError(f"{label}: {detail or ''}")
    print("  OK", label)


def cleanup(db, *, farmer_id, parcel_id, project_id, cycle_id=None):
    db.rollback()
    if cycle_id:
        db.query(CropActivity).filter(CropActivity.crop_cycle_id == cycle_id).delete(synchronize_session=False)
        db.query(CropStageInstance).filter(CropStageInstance.crop_cycle_id == cycle_id).delete(synchronize_session=False)
        db.query(CropCycle).filter(CropCycle.id == cycle_id).delete(synchronize_session=False)
    db.query(CropStageInputRuleAuditEvent).filter(CropStageInputRuleAuditEvent.project_id == project_id).delete(synchronize_session=False)
    db.query(CropStageInputRule).filter(CropStageInputRule.project_id == project_id).delete(synchronize_session=False)
    product = db.query(AgriculturalProduct).filter(AgriculturalProduct.code == PRODUCT).first()
    if product:
        db.query(ProjectProductApproval).filter(ProjectProductApproval.product_id == product.id).delete(synchronize_session=False)
        db.query(AgriculturalProductPackage).filter(AgriculturalProductPackage.product_id == product.id).delete(synchronize_session=False)
        db.query(AgriculturalProduct).filter(AgriculturalProduct.id == product.id).delete(synchronize_session=False)
    db.query(ProductCatalogAuditEvent).filter(ProductCatalogAuditEvent.entity_code.in_([MFG, PRODUCT, SKU])).delete(synchronize_session=False)
    db.query(Manufacturer).filter(Manufacturer.code == MFG).delete(synchronize_session=False)
    db.query(Parcel).filter(Parcel.id == parcel_id).delete(synchronize_session=False)
    db.query(Farmer).filter(Farmer.id == farmer_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("ACTIVITY PRODUCT TRACEABILITY REGRESSION")
    print("=" * 72)
    client = TestClient(app)
    db = SessionLocal()
    farmer_id, parcel_id, project_id, cycle_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), None
    actor_id = uuid.uuid4()
    headers = {"X-Tenant-ID": TENANT, "X-Actor-ID": str(actor_id)}
    try:
        if not db.query(Tenant).filter(Tenant.id == TENANT).first():
            db.add(Tenant(id=TENANT, name="Default", type="ENTERPRISE", created_at=now(), updated_at=now()))
        project = Project(id=project_id, tenant_id=TENANT, name="Activity Traceability Project", start_date=date(2027,1,1), end_date=date(2027,12,31), status="PLANNED", crop_scope=["RICE"], created_at=now(), updated_at=now())
        farmer = Farmer(id=farmer_id, tenant_id=TENANT, project_id=project_id, mobile_number="997" + str(farmer_id.int)[-7:], village_name_manual="Trace Village", primary_crop_code="RICE", display_name="Trace Farmer", status="ACTIVE", created_at=now(), updated_at=now())
        parcel = Parcel(id=parcel_id, tenant_id=TENANT, farmer_id=farmer_id, project_id=project_id, village_name_manual="Trace Village", reported_area=1, reported_area_unit="ACRE", survey_number="TRACE-" + str(parcel_id)[:8], ownership_type="OWNED", status="ACTIVE", created_at=now(), updated_at=now())
        urea = db.query(AgriculturalInput).filter(AgriculturalInput.code == "UREA_46_N", AgriculturalInput.catalog_status == "PUBLISHED", AgriculturalInput.is_active == True).first()
        check(urea is not None, "published Urea input exists")
        mfg = Manufacturer(id=uuid.uuid4(), code=MFG, canonical_name="Activity Trace Agro", country="India", aliases=[], created_at=now(), updated_at=now())
        product = AgriculturalProduct(id=uuid.uuid4(), code=PRODUCT, canonical_input_id=urea.id, manufacturer_id=mfg.id, brand_name="Activity Trace Urea", composition="46% N", registration_number="ACTIVITY-TRACE-UREA-001", country="India", status="ACTIVE", created_at=now(), updated_at=now())
        package = AgriculturalProductPackage(id=uuid.uuid4(), product_id=product.id, sku=SKU, quantity="45", unit="kg", pack_label="45 kg bag", status="ACTIVE", created_at=now(), updated_at=now())
        approval = ProjectProductApproval(id=uuid.uuid4(), tenant_id=TENANT, project_id=project_id, product_id=product.id, enabled=True, preferred=True, display_order=1, reason="Traceability test", created_at=now(), updated_at=now())
        rule = CropStageInputRule(id=uuid.uuid4(), tenant_id=TENANT, project_id=project_id, crop_code="RICE", season_code="KHARIF", stage_code="TILLERING", activity_type="FERTILIZER", input_id=urea.id, input_code="UREA_46_N", enabled=True, priority=1, dosage_quantity="36", dosage_unit="KG", dosage_area_unit="ACRE", allowed_product_codes=[PRODUCT], reason="Traceability dosage rule", created_at=now(), updated_at=now())
        db.add(project); db.flush()
        db.add(mfg); db.flush()
        db.add_all([farmer, parcel, product]); db.flush()
        db.add_all([package, approval, rule]); db.commit()

        created = client.post("/api/v1/crop-cycles", headers=headers, json={"farmer_id": str(farmer_id), "parcel_id": str(parcel_id), "project_id": str(project_id), "crop_code":"RICE", "season_code":"KHARIF", "planned_sowing_date":"2027-06-15"})
        check(created.status_code == 201, "crop cycle is created", created.text[:300])
        cycle_id = uuid.UUID(created.json()["id"])
        logged = client.post(f"/api/v1/crop-cycles/{cycle_id}/activities", headers=headers, json={
            "activity_type":"FERTILIZER", "input_code":"UREA_46_N", "input_name":"Urea", "input_rule_id": str(rule.id),
            "product_code": PRODUCT, "package_sku": SKU, "quantity":36, "quantity_unit":"KG", "recommended_quantity":36,
            "recommended_quantity_unit":"KG", "actual_quantity":38, "actual_quantity_unit":"KG", "dosage_variance_reason":"Field condition adjustment",
            "cost_amount": 1200, "activity_date":"2027-07-20"
        })
        check(logged.status_code == 201, "activity log accepts product/package traceability", logged.text[:300])
        logged_payload = logged.json()
        check(logged_payload["input_rule_id"] == str(rule.id), "activity response includes input_rule_id")
        check(logged_payload["product_code"] == PRODUCT and logged_payload["package_sku"] == SKU, "activity response includes product and package")

        listed = client.get(f"/api/v1/crop-cycles/{cycle_id}/activities", headers={"X-Tenant-ID": TENANT})
        check(listed.status_code == 200, "activity list returns 200", listed.text[:300])
        row = listed.json()[0]
        check(row["input_code"] == "UREA_46_N", "activity list includes input_code")
        check(row["input_rule_id"] == str(rule.id), "activity list includes input_rule_id")
        check(row["product_code"] == PRODUCT and row["package_sku"] == SKU, "activity list includes product/package")
        check(row["recommended_quantity"] == "36.000" and row["actual_quantity"] == "38.000", "activity list includes recommended and actual quantities")
        check(row["dosage_variance_reason"] == "Field condition adjustment", "activity list includes variance reason")
        print("PASS")
    finally:
        cleanup(db, farmer_id=farmer_id, parcel_id=parcel_id, project_id=project_id, cycle_id=cycle_id)
        db.close()

if __name__ == "__main__": main()