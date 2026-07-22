#!/usr/bin/env python3
"""Read-only product catalog readiness audit for Android metadata scenarios."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.master_data.models.input import AgriculturalInput, AgriculturalProduct, InputCategory, Manufacturer


def active_query(db, model):
    query = db.query(model)
    if hasattr(model, 'is_active'):
        query = query.filter(model.is_active == True)
    return query


def main() -> int:
    db = SessionLocal()
    try:
        categories = active_query(db, InputCategory).all()
        inputs = active_query(db, AgriculturalInput).all()
        manufacturers = active_query(db, Manufacturer).all()
        products = active_query(db, AgriculturalProduct).all()

        category_names = {str(c.id): getattr(c, 'name', None) or getattr(c, 'display_name', None) or getattr(c, 'code', None) for c in categories}
        input_names = {str(i.id): getattr(i, 'canonical_name', None) or getattr(i, 'name', None) or getattr(i, 'code', None) for i in inputs}
        manufacturer_names = {str(m.id): getattr(m, 'name', None) or getattr(m, 'display_name', None) or getattr(m, 'code', None) for m in manufacturers}

        products_by_manufacturer = Counter()
        products_by_input = Counter()
        products_by_category = Counter()
        sample_products = []

        for product in products:
            manufacturer_id = str(getattr(product, 'manufacturer_id', '') or '')
            input_id = str(getattr(product, 'input_id', '') or getattr(product, 'agricultural_input_id', '') or '')
            category_id = str(getattr(product, 'category_id', '') or '')
            if manufacturer_id:
                products_by_manufacturer[manufacturer_id] += 1
            if input_id:
                products_by_input[input_id] += 1
            if category_id:
                products_by_category[category_id] += 1
            if len(sample_products) < 20:
                sample_products.append({
                    'id': str(getattr(product, 'id', '')),
                    'name': getattr(product, 'trade_name', None) or getattr(product, 'display_name', None) or getattr(product, 'name', None),
                    'manufacturer_id': manufacturer_id or None,
                    'manufacturer': manufacturer_names.get(manufacturer_id),
                    'input_id': input_id or None,
                    'input': input_names.get(input_id),
                    'category_id': category_id or None,
                    'category': category_names.get(category_id),
                })

        manufacturer_gaps = [
            {'id': str(m.id), 'name': manufacturer_names.get(str(m.id)), 'product_count': products_by_manufacturer.get(str(m.id), 0)}
            for m in manufacturers
            if products_by_manufacturer.get(str(m.id), 0) == 0
        ]
        input_gaps = [
            {'id': str(i.id), 'code': getattr(i, 'code', None), 'name': input_names.get(str(i.id)), 'product_count': products_by_input.get(str(i.id), 0)}
            for i in inputs
            if products_by_input.get(str(i.id), 0) == 0
        ]

        payload = {
            'schema_version': 'product_catalog_readiness_audit.v1',
            'counts': {
                'input_categories': len(categories),
                'agricultural_inputs': len(inputs),
                'manufacturers': len(manufacturers),
                'agricultural_products': len(products),
                'manufacturers_without_products': len(manufacturer_gaps),
                'inputs_without_products': len(input_gaps),
            },
            'products_by_manufacturer': {manufacturer_names.get(k) or k: v for k, v in sorted(products_by_manufacturer.items())},
            'products_by_input': {input_names.get(k) or k: v for k, v in sorted(products_by_input.items())},
            'products_by_category': {category_names.get(k) or k: v for k, v in sorted(products_by_category.items())},
            'manufacturer_gaps': manufacturer_gaps[:50],
            'input_gaps': input_gaps[:50],
            'sample_products': sample_products,
            'recommended_next_actions': [
                'Seed representative products for existing manufacturers.',
                'Prioritize seed, fertilizer, crop protection, irrigation, and bio-input scenarios used by Android demos.',
                'Add package/price metadata where available, but keep pricing source and effective date explicit.',
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
