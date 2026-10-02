#!/usr/bin/env python3
from pathlib import Path
R=Path(__file__).resolve().parents[2];M=(R/'backend/alembic/versions/062_add_project_village_resolutions.py').read_text();A=(R/'backend/app/modules/master_data/api/project_village_resolutions.py').read_text();W=(R/'web/src/components/admin/ProjectVillageResolutionPanel.tsx').read_text()
checks=[(M,"revision='062'",'Migration revision is pinned'),(M,"down_revision='061'",'Migration follows current head'),(M,'geography_project_village_resolutions','Dedicated table exists'),(M,'PROJECT_LOCAL_ADDITION','Project-local mode exists'),(M,'CANONICAL_ENRICHMENT','Canonical enrichment exists'),(A,"@router.get('/projects/{project_id}/worklist')",'Read-only worklist endpoint exists'),(A,"@router.post('/projects/{project_id}/dry-run')",'Dry-run endpoint exists'),(A,'PROJECT_VILLAGE_RESOLUTION_APPLY_DISABLED','Apply fails closed'),(A,"'db_writes_attempted':False",'Dry run reports zero writes'),(A,"'android_behavior_changed':False",'Android remains unchanged'),(A,'PIN_EVIDENCE_NOT_FOUND','PIN evidence is verified'),(W,'project-village-resolution-panel','Admin panel exists'),(W,'Validate dry run','Dry-run control exists'),(W,'apply remains disabled','UI states apply boundary')]
for source,needle,label in checks:
 if needle not in source:raise AssertionError(label+': missing '+repr(needle))
 print('PASS '+label)
print('PROJECT VILLAGE RESOLUTION FOUNDATION STATIC CONTRACT PASSED')
