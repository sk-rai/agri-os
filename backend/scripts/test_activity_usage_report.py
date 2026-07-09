"""Regression for admin activity usage reporting."""
from datetime import date, datetime, timezone
from pathlib import Path
import sys, uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.master_data.models import AgriculturalInput, AgriculturalProduct, AgriculturalProductPackage, CropStageInputRule, Manufacturer, ProjectProductApproval
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance, WorkflowTemplate, WorkflowTemplateVersion
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

TENANT = "default"
MFG = "REPORT_USAGE_AGRO"
PRODUCT = "REPORT_USAGE_UREA"
SKU = "REPORT_USAGE_UREA_45KG"


def now(): return datetime.now(timezone.utc)

def check(value, label, detail=None):
    if not value: raise AssertionError(f"{label}: {detail or ''}")
    print("  OK", label)


def cleanup(db, *, admin=None, farmer_id, parcel_id, project_id, cycle_id=None):
    db.rollback()
    if cycle_id:
        db.query(CropActivity).filter(CropActivity.crop_cycle_id == cycle_id).delete(synchronize_session=False)
        db.query(CropStageInstance).filter(CropStageInstance.crop_cycle_id == cycle_id).delete(synchronize_session=False)
        db.query(CropCycle).filter(CropCycle.id == cycle_id).delete(synchronize_session=False)
    db.query(CropStageInputRule).filter(CropStageInputRule.project_id == project_id).delete(synchronize_session=False)
    product = db.query(AgriculturalProduct).filter(AgriculturalProduct.code == PRODUCT).first()
    if product:
        db.query(ProjectProductApproval).filter(ProjectProductApproval.product_id == product.id).delete(synchronize_session=False)
        db.query(AgriculturalProductPackage).filter(AgriculturalProductPackage.product_id == product.id).delete(synchronize_session=False)
        db.query(AgriculturalProduct).filter(AgriculturalProduct.id == product.id).delete(synchronize_session=False)
    db.query(Manufacturer).filter(Manufacturer.code == MFG).delete(synchronize_session=False)
    db.query(Parcel).filter(Parcel.id == parcel_id).delete(synchronize_session=False)
    db.query(Farmer).filter(Farmer.id == farmer_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    db.commit()
    if admin: delete_test_admin(db, admin.id)


def main():
    print("=" * 72)
    print("ACTIVITY USAGE REPORT REGRESSION")
    print("=" * 72)
    db = SessionLocal(); admin, headers = create_test_admin(db)
    farmer_id, parcel_id, project_id, cycle_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), None
    try:
        if not db.query(Tenant).filter(Tenant.id == TENANT).first(): db.add(Tenant(id=TENANT, name="Default", type="ENTERPRISE", created_at=now(), updated_at=now()))
        urea = db.query(AgriculturalInput).filter(AgriculturalInput.code == "UREA_46_N", AgriculturalInput.catalog_status == "PUBLISHED", AgriculturalInput.is_active == True).first(); check(urea is not None, "Urea input exists")
        workflow_template = db.query(WorkflowTemplate).filter(WorkflowTemplate.code == "WF_RICE_KHARIF_DEFAULT").first(); check(workflow_template is not None, "Rice workflow template exists")
        workflow_version = db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.template_id == workflow_template.id, WorkflowTemplateVersion.status == "PUBLISHED", WorkflowTemplateVersion.is_active == True).first(); check(workflow_version is not None, "Rice workflow version exists")
        project = Project(id=project_id, tenant_id=TENANT, name="Usage Report Project", start_date=date(2027,1,1), end_date=date(2027,12,31), status="PLANNED", crop_scope=["RICE"], created_at=now(), updated_at=now())
        farmer = Farmer(id=farmer_id, tenant_id=TENANT, project_id=project_id, mobile_number="996" + str(farmer_id.int)[-7:], village_name_manual="Report Village", primary_crop_code="RICE", display_name="Report Farmer", status="ACTIVE", created_at=now(), updated_at=now())
        parcel = Parcel(id=parcel_id, tenant_id=TENANT, farmer_id=farmer_id, project_id=project_id, village_name_manual="Report Village", reported_area=1, reported_area_unit="ACRE", survey_number="REPORT-" + str(parcel_id)[:8], ownership_type="OWNED", status="ACTIVE", created_at=now(), updated_at=now())
        db.add(project); db.flush(); db.add_all([farmer, parcel]); db.flush()
        mfg = Manufacturer(id=uuid.uuid4(), code=MFG, canonical_name="Report Usage Agro", country="India", aliases=[], created_at=now(), updated_at=now()); db.add(mfg); db.flush()
        product = AgriculturalProduct(id=uuid.uuid4(), code=PRODUCT, canonical_input_id=urea.id, manufacturer_id=mfg.id, brand_name="Report Usage Urea", composition="46% N", registration_number="REPORT-USAGE-UREA-001", country="India", status="ACTIVE", created_at=now(), updated_at=now()); db.add(product); db.flush()
        package = AgriculturalProductPackage(id=uuid.uuid4(), product_id=product.id, sku=SKU, quantity="45", unit="kg", pack_label="45 kg bag", status="ACTIVE", created_at=now(), updated_at=now())
        approval = ProjectProductApproval(id=uuid.uuid4(), tenant_id=TENANT, project_id=project_id, product_id=product.id, enabled=True, preferred=True, display_order=1, reason="Usage report test", created_at=now(), updated_at=now())
        rule = CropStageInputRule(id=uuid.uuid4(), tenant_id=TENANT, project_id=project_id, crop_code="RICE", season_code="KHARIF", stage_code="TILLERING", activity_type="FERTILIZER", input_id=urea.id, input_code="UREA_46_N", enabled=True, priority=1, dosage_quantity="36", dosage_unit="KG", dosage_area_unit="ACRE", allowed_product_codes=[PRODUCT], reason="Usage report rule", created_at=now(), updated_at=now())
        cycle_id = uuid.uuid4()
        cycle = CropCycle(id=cycle_id, tenant_id=TENANT, farmer_id=farmer_id, parcel_id=parcel_id, project_id=project_id, crop_code="RICE", season_code="KHARIF", lifecycle_template_id=workflow_template.lifecycle_template_id, workflow_template_version_id=workflow_version.id, planned_sowing_date=date(2027,6,15), status="ACTIVE", created_at=now(), updated_at=now())
        stage = CropStageInstance(id=uuid.uuid4(), crop_cycle_id=cycle_id, tenant_id=TENANT, stage_code="TILLERING", stage_name="Tillering", stage_order=3, expected_duration_days=30, status="ACTIVE", created_at=now(), updated_at=now())
        activity = CropActivity(id=uuid.uuid4(), crop_cycle_id=cycle_id, stage_instance_id=stage.id, tenant_id=TENANT, farmer_id=farmer_id, activity_type="FERTILIZER", input_code="UREA_46_N", input_name="Urea", quantity="38", quantity_unit="KG", input_rule_id=rule.id, product_id=product.id, product_code=PRODUCT, package_id=package.id, package_sku=SKU, recommended_quantity="36", recommended_quantity_unit="KG", actual_quantity="38", actual_quantity_unit="KG", dosage_variance_reason="Field adjustment", cost_amount="1200", activity_date=date(2027,7,20), logged_by=admin.id, created_at=now(), updated_at=now())
        db.add_all([package, approval, rule, cycle, stage, activity]); db.commit()

        client = TestClient(app, headers=headers)
        response = client.get(f"/api/v1/reports/activity-usage?project_id={project_id}&crop_code=RICE&stage_code=TILLERING&product_code={PRODUCT}")
        check(response.status_code == 200, "activity usage report returns 200", response.text[:300])
        payload = response.json(); check(payload["count"] == 1, "report returns one row")
        row = payload["activities"][0]
        check(row["activity_id"] == str(activity.id), "report row includes activity id")
        check(row["product_code"] == PRODUCT and row["package_sku"] == SKU, "report row includes product/package")
        check(row["recommended_quantity"] == "36.000" and row["actual_quantity"] == "38.000", "report row includes quantities")
        check(payload["summary"]["activity_count"] == 1, "summary activity count is correct")
        check(payload["summary"]["total_cost"] == "1200.00", "summary total cost is correct")
        check(payload["summary"]["variance_count"] == 1, "summary variance count is correct")
        check(payload["summary"]["quantity_by_input"][0]["quantity"] == "38.000", "summary quantity by input is correct")
        check(payload["summary"]["quantity_by_product"][0]["product_code"] == PRODUCT, "summary quantity by product is correct")
        print("PASS")
    finally:
        cleanup(db, admin=admin, farmer_id=farmer_id, parcel_id=parcel_id, project_id=project_id, cycle_id=cycle_id)
        db.close()

if __name__ == "__main__": main()
