#!/usr/bin/env python3
"""Read-only Android emulator persona readiness audit.

Checks whether local DB has enough fixture data for:
- direct farmer
- field agent
- company/project-associated farmer
- independent farmer
- advisories
- crop/workflow/input metadata
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal


def scalar(db, sql: str, params: dict | None = None):
    return db.execute(text(sql), params or {}).scalar() or 0


def table_exists(db, table: str) -> bool:
    return bool(scalar(db, """
        select count(*)
        from information_schema.tables
        where table_schema = 'public'
        and table_name = :table
    """, {"table": table}))


def count_if_table(db, table: str, where: str = "true") -> int:
    if not table_exists(db, table):
        return 0
    return int(scalar(db, f"select count(*) from {table} where {where}"))


def main() -> int:
    db = SessionLocal()
    try:
        counts = {
            "farmers": count_if_table(db, "farmers"),
            "active_farmers": count_if_table(db, "farmers", "status = 'ACTIVE'"),
            "parcels": count_if_table(db, "parcels"),
            "active_parcels": count_if_table(db, "parcels", "status = 'ACTIVE'"),
            "projects": count_if_table(db, "projects"),
            "active_projects": count_if_table(db, "projects", "status in ('ACTIVE', 'PLANNED')"),
            "project_enrollments": count_if_table(db, "project_enrollments"),
            "crop_cycles": count_if_table(db, "crop_cycles"),
            "active_crop_cycles": count_if_table(db, "crop_cycles", "status = 'ACTIVE'"),
            "agent_profiles": count_if_table(db, "agent_profiles"),
            "crop_catalog": count_if_table(db, "crop_catalog"),
            "crop_master": count_if_table(db, "crop_master"),
            "crops": count_if_table(db, "crops"),
            "crop_taxonomy_nodes": count_if_table(db, "crop_taxonomy_nodes"),
            "crop_lifecycle_templates": count_if_table(db, "crop_lifecycle_templates"),
            "workflow_template_versions": count_if_table(db, "workflow_template_versions"),
            "agricultural_inputs": count_if_table(db, "agricultural_inputs"),
            "agricultural_products": count_if_table(db, "agricultural_products"),
            "broadcast_campaigns": count_if_table(db, "broadcast_campaigns"),
            "broadcast_deliveries": count_if_table(db, "broadcast_deliveries"),
        }

        associated_farmers = 0
        independent_farmers = 0
        farmers_with_parcels = 0

        if table_exists(db, "farmers") and table_exists(db, "parcels"):
            farmers_with_parcels = int(scalar(db, """
                select count(distinct f.id)
                from farmers f
                join parcels p on p.farmer_id = f.id
                where f.status = 'ACTIVE'
                and p.status = 'ACTIVE'
            """))

        if table_exists(db, "farmers") and table_exists(db, "project_enrollments"):
            enrollment_columns = {
                row[0]
                for row in db.execute(text("""
                    select column_name
                    from information_schema.columns
                    where table_schema = 'public'
                    and table_name = 'project_enrollments'
                """)).all()
            }
            if "farmer_id" in enrollment_columns:
                associated_farmers = int(scalar(db, """
                    select count(distinct f.id)
                    from farmers f
                    join project_enrollments pe on pe.farmer_id = f.id
                    where f.status = 'ACTIVE'
                """))

                independent_farmers = int(scalar(db, """
                    select count(*)
                    from farmers f
                    where f.status = 'ACTIVE'
                    and not exists (
                        select 1 from project_enrollments pe where pe.farmer_id = f.id
                    )
                """))
            else:
                independent_farmers = counts["active_farmers"]
        elif table_exists(db, "farmers"):
            independent_farmers = counts["active_farmers"]

        readiness = {
            "direct_farmer_fixture_ready": counts["active_farmers"] >= 1 and farmers_with_parcels >= 1,
            "field_agent_fixture_ready": counts["agent_profiles"] >= 1,
            "company_project_farmer_fixture_ready": associated_farmers >= 1,
            "independent_farmer_fixture_ready": independent_farmers >= 1,
            "advisory_fixture_ready": counts["broadcast_campaigns"] >= 1 and counts["broadcast_deliveries"] >= 1,
            "crop_metadata_ready": max(counts["crop_catalog"], counts["crop_master"], counts["crops"], counts["crop_taxonomy_nodes"]) >= 15,
            "workflow_metadata_ready": counts["workflow_template_versions"] >= 1 or counts["crop_lifecycle_templates"] >= 1,
            "input_product_metadata_ready": counts["agricultural_inputs"] >= 10 and counts["agricultural_products"] >= 10,
        }

        result = {
            "schema_version": "android_emulator_persona_readiness_audit.v1",
            "counts": counts,
            "derived_counts": {
                "farmers_with_active_parcels": farmers_with_parcels,
                "company_project_associated_farmers": associated_farmers,
                "independent_farmers": independent_farmers,
            },
            "readiness": readiness,
            "ready_for_emulator_persona_testing": all(readiness.values()),
            "next_actions": [
                "If any persona fixture is false, run or create a deterministic Android emulator seed pack.",
                "Run advisory seed for selected local farmers before broadcast/advisory QA.",
                "Confirm Android should render finance analytics or keep it admin-only for MVP.",
                "Add language QA samples for crops/stages/advisories before broad language testing.",
            ],
        }
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
