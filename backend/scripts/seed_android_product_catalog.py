#!/usr/bin/env python3
"""Seed representative product catalog rows for Android metadata testing."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.master_data.models.input import AgriculturalInput, AgriculturalProduct, AgriculturalProductPackage, Manufacturer


SEED_PRODUCTS = [
    {
        'code': 'IFFCO_UREA_46_N_45KG',
        'canonical_input_code': 'UREA_46_N',
        'manufacturer_code': 'IFFCO',
        'brand_name': 'IFFCO Urea',
        'composition': 'Urea 46% N',
        'packages': [{'sku': 'IFFCO_UREA_45KG', 'quantity': '45', 'unit': 'KG', 'pack_label': '45 kg bag'}],
    },
    {
        'code': 'NFL_UREA_46_N_45KG',
        'canonical_input_code': 'UREA_46_N',
        'manufacturer_code': 'NFL',
        'brand_name': 'NFL Neem Coated Urea',
        'composition': 'Neem coated urea 46% N',
        'packages': [{'sku': 'NFL_UREA_45KG', 'quantity': '45', 'unit': 'KG', 'pack_label': '45 kg bag'}],
    },
    {
        'code': 'IFFCO_DAP_18_46_0_50KG',
        'canonical_input_code': 'DAP_18_46_0',
        'manufacturer_code': 'IFFCO',
        'brand_name': 'IFFCO DAP',
        'composition': '18:46:0',
        'packages': [{'sku': 'IFFCO_DAP_50KG', 'quantity': '50', 'unit': 'KG', 'pack_label': '50 kg bag'}],
    },
    {
        'code': 'ZUARI_DAP_18_46_0_50KG',
        'canonical_input_code': 'DAP_18_46_0',
        'manufacturer_code': 'ZUARI',
        'brand_name': 'Zuari DAP',
        'composition': '18:46:0',
        'packages': [{'sku': 'ZUARI_DAP_50KG', 'quantity': '50', 'unit': 'KG', 'pack_label': '50 kg bag'}],
    },
    {
        'code': 'COROMANDEL_MOP_50KG',
        'canonical_input_code': 'MOP_POTASH',
        'manufacturer_code': 'COROMANDEL',
        'brand_name': 'Coromandel MOP',
        'composition': 'Muriate of Potash',
        'packages': [{'sku': 'COROMANDEL_MOP_50KG', 'quantity': '50', 'unit': 'KG', 'pack_label': '50 kg bag'}],
    },
    {
        'code': 'GENERIC_ZINC_SULPHATE_10KG',
        'canonical_input_code': 'ZINC_SULPHATE',
        'manufacturer_code': 'GENERIC',
        'brand_name': 'Generic Zinc Sulphate',
        'composition': 'Zinc sulphate micronutrient',
        'packages': [{'sku': 'GENERIC_ZINC_SULPHATE_10KG', 'quantity': '10', 'unit': 'KG', 'pack_label': '10 kg bag'}],
    },
    {
        'code': 'BAYER_TRICYCLAZOLE_250G',
        'canonical_input_code': 'TRICYCLAZOLE',
        'manufacturer_code': 'BAYER',
        'brand_name': 'Bayer Tricyclazole Demo',
        'composition': 'Tricyclazole fungicide',
        'packages': [{'sku': 'BAYER_TRICYCLAZOLE_250G', 'quantity': '250', 'unit': 'G', 'pack_label': '250 g pack'}],
    },
    {
        'code': 'UPL_CHLORPYRIFOS_1L',
        'canonical_input_code': 'CHLORPYRIFOS',
        'manufacturer_code': 'UPL',
        'brand_name': 'UPL Chlorpyrifos Demo',
        'composition': 'Chlorpyrifos insecticide',
        'packages': [{'sku': 'UPL_CHLORPYRIFOS_1L', 'quantity': '1', 'unit': 'L', 'pack_label': '1 litre bottle'}],
    },
    {
        'code': 'DHANUKA_SETT_TREATMENT_100G',
        'canonical_input_code': 'SETT_TREATMENT',
        'manufacturer_code': 'DHANUKA',
        'brand_name': 'Dhanuka Sett Treatment Demo',
        'composition': 'Seed/sett treatment demo product',
        'packages': [{'sku': 'DHANUKA_SETT_TREATMENT_100G', 'quantity': '100', 'unit': 'G', 'pack_label': '100 g pack'}],
    },
]


def main() -> int:
    db = SessionLocal()
    created_products = 0
    created_packages = 0
    skipped = 0
    try:
        inputs_by_code = {row.code: row for row in db.query(AgriculturalInput).all()}
        manufacturers_by_code = {row.code: row for row in db.query(Manufacturer).all()}
        now = datetime.now(timezone.utc)
        for item in SEED_PRODUCTS:
            canonical_input = inputs_by_code.get(item['canonical_input_code'])
            manufacturer = manufacturers_by_code.get(item['manufacturer_code'])
            if not canonical_input or not manufacturer:
                skipped += 1
                print('SKIP missing dependency', item['code'], item['canonical_input_code'], item['manufacturer_code'])
                continue
            product = db.query(AgriculturalProduct).filter(AgriculturalProduct.code == item['code']).first()
            if not product:
                product = AgriculturalProduct(
                    id=uuid.uuid4(),
                    code=item['code'],
                    canonical_input_id=canonical_input.id,
                    manufacturer_id=manufacturer.id,
                    brand_name=item['brand_name'],
                    composition=item.get('composition'),
                    country='India',
                    status='ACTIVE',
                    metadata_={
                        'seed_pack': 'android_product_catalog.v1',
                        'scenario_usage': 'Android MVP metadata testing',
                        'pricing_status': 'NOT_SEEDED',
                        'source_note': 'Representative demo catalog row mapped to existing canonical input/manufacturer.',
                    },
                    created_at=now,
                    updated_at=now,
                )
                db.add(product)
                db.flush()
                created_products += 1
            for package in item['packages']:
                existing_package = db.query(AgriculturalProductPackage).filter(AgriculturalProductPackage.sku == package['sku']).first()
                if existing_package:
                    continue
                db.add(AgriculturalProductPackage(
                    id=uuid.uuid4(),
                    product_id=product.id,
                    sku=package['sku'],
                    quantity=Decimal(package['quantity']),
                    unit=package['unit'],
                    pack_label=package['pack_label'],
                    status='ACTIVE',
                    created_at=now,
                    updated_at=now,
                ))
                created_packages += 1
        db.commit()
        print(f'created_products={created_products}')
        print(f'created_packages={created_packages}')
        print(f'skipped={skipped}')
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
