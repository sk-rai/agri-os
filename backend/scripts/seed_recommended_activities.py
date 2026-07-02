"""Add recommended_activities to crop lifecycle template stages.

Source: ICAR Package of Practices for Uttar Pradesh (Rice Kharif, Wheat Rabi).
day_offset is relative to stage start date.

Usage:
    cd backend && source ../venv/bin/activate
    python scripts/seed_recommended_activities.py
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.master_data.models import CropLifecycleTemplate
from sqlalchemy.orm.attributes import flag_modified

# Rice Kharif — recommended activities per stage
RICE_ACTIVITIES = {
    "NURSERY": [
        {"day_offset": 0, "activity_type": "OTHER", "input_name": "Seed Treatment (Carbendazim/Thiram)", "typical_quantity": "2g per kg seed", "typical_cost_per_acre": 150, "is_critical": True, "description": {"en": "Treat seeds with fungicide before soaking to prevent blast", "hi": "बीज को भिगोने से पहले फफूंदनाशक से उपचारित करें"}},
        {"day_offset": 0, "activity_type": "OTHER", "input_name": "Seed Soaking", "typical_quantity": "24 hours in water", "typical_cost_per_acre": 0, "is_critical": True, "description": {"en": "Soak treated seeds in water for 24 hours", "hi": "उपचारित बीजों को 24 घंटे पानी में भिगोएं"}},
        {"day_offset": 1, "activity_type": "FERTILIZER", "input_name": "FYM/Compost (Bed Preparation)", "typical_quantity": "2-3 quintal per nursery bed", "typical_cost_per_acre": 500, "is_critical": True, "description": {"en": "Apply well-decomposed FYM to nursery bed", "hi": "नर्सरी की क्यारी में अच्छी तरह सड़ी गोबर खाद डालें"}},
        {"day_offset": 5, "activity_type": "IRRIGATION", "input_name": "First Light Irrigation", "typical_quantity": "Keep moist, not flooded", "typical_cost_per_acre": 0, "is_critical": False, "description": {"en": "Keep nursery bed moist but not waterlogged", "hi": "नर्सरी नम रखें, डुबोएं नहीं"}},
        {"day_offset": 10, "activity_type": "FERTILIZER", "input_name": "DAP (Basal Dose)", "typical_quantity": "25 kg/acre", "typical_cost_per_acre": 700, "is_critical": True, "description": {"en": "Apply basal dose of DAP for strong seedling growth", "hi": "मजबूत पौध के लिए DAP की बेसल खुराक दें"}},
        {"day_offset": 15, "activity_type": "PESTICIDE", "input_name": "Chlorpyrifos (Pest Spray)", "typical_quantity": "1.5 ml per litre water", "typical_cost_per_acre": 300, "is_critical": False, "description": {"en": "Spray if stem borer or leaf folder observed", "hi": "तना छेदक या पत्ती लपेटक दिखे तो स्प्रे करें"}},
        {"day_offset": 22, "activity_type": "OTHER", "input_name": "Seedling Readiness Check", "typical_quantity": "Visual inspection", "typical_cost_per_acre": 0, "is_critical": True, "description": {"en": "Check if seedlings are 15-20cm tall, ready for transplanting", "hi": "देखें कि पौध 15-20cm की हो गई है, रोपाई के लिए तैयार"}},
    ],
    "TRANSPLANTING": [
        {"day_offset": 0, "activity_type": "LABOR", "input_name": "Puddling (Field Preparation)", "typical_quantity": "2-3 ploughings + leveling", "typical_cost_per_acre": 3000, "is_critical": True, "description": {"en": "Puddle the main field with standing water", "hi": "खड़े पानी में खेत की जुताई करें"}},
        {"day_offset": 1, "activity_type": "FERTILIZER", "input_name": "DAP + Zinc Sulphate (Basal)", "typical_quantity": "DAP 50kg + ZnSO4 10kg/acre", "typical_cost_per_acre": 2000, "is_critical": True, "description": {"en": "Apply before transplanting. Mix in puddled soil.", "hi": "रोपाई से पहले डालें। गीली मिट्टी में मिलाएं।"}},
        {"day_offset": 2, "activity_type": "LABOR", "input_name": "Transplanting", "typical_quantity": "2-3 seedlings per hill, 20x15cm spacing", "typical_cost_per_acre": 4000, "is_critical": True, "description": {"en": "Transplant 21-25 day old seedlings at proper spacing", "hi": "21-25 दिन की पौध को सही दूरी पर लगाएं"}},
        {"day_offset": 5, "activity_type": "IRRIGATION", "input_name": "Maintain Water Level", "typical_quantity": "2-3 cm standing water", "typical_cost_per_acre": 0, "is_critical": True, "description": {"en": "Maintain thin layer of water for establishment", "hi": "स्थापना के लिए पतली पानी की परत बनाए रखें"}},
    ],
    "TILLERING": [
        {"day_offset": 0, "activity_type": "FERTILIZER", "input_name": "Urea (1st Top Dressing)", "typical_quantity": "35 kg/acre", "typical_cost_per_acre": 600, "is_critical": True, "description": {"en": "First nitrogen dose at active tillering start", "hi": "कल्ले निकलने पर पहली नाइट्रोजन खुराक"}},
        {"day_offset": 7, "activity_type": "PESTICIDE", "input_name": "Herbicide (Butachlor/Pretilachlor)", "typical_quantity": "1.5 litre/acre", "typical_cost_per_acre": 800, "is_critical": False, "description": {"en": "Apply if weeds are visible within 7 days of transplanting", "hi": "रोपाई के 7 दिन में खरपतवार दिखे तो दवाई दें"}},
        {"day_offset": 15, "activity_type": "FERTILIZER", "input_name": "Urea (2nd Top Dressing)", "typical_quantity": "35 kg/acre", "typical_cost_per_acre": 600, "is_critical": True, "description": {"en": "Second nitrogen dose at maximum tillering", "hi": "अधिकतम कल्ले पर दूसरी नाइट्रोजन खुराक"}},
        {"day_offset": 20, "activity_type": "PESTICIDE", "input_name": "BPH/Stem Borer Check", "typical_quantity": "Monitor weekly", "typical_cost_per_acre": 0, "is_critical": False, "description": {"en": "Monitor for Brown Plant Hopper and stem borer", "hi": "भूरा फुदका और तना छेदक की निगरानी करें"}},
    ],
    "FLOWERING": [
        {"day_offset": 0, "activity_type": "FERTILIZER", "input_name": "MOP/Potash", "typical_quantity": "20 kg/acre", "typical_cost_per_acre": 500, "is_critical": True, "description": {"en": "Potash application at panicle initiation", "hi": "बाली बनने पर पोटाश दें"}},
        {"day_offset": 5, "activity_type": "PESTICIDE", "input_name": "Blast/Sheath Blight Spray", "typical_quantity": "Tricyclazole 0.6g/L", "typical_cost_per_acre": 600, "is_critical": False, "description": {"en": "Spray if blast or sheath blight symptoms seen", "hi": "ब्लास्ट या शीथ ब्लाइट दिखे तो स्प्रे करें"}},
        {"day_offset": 10, "activity_type": "IRRIGATION", "input_name": "Critical Irrigation", "typical_quantity": "Maintain 5cm water", "typical_cost_per_acre": 500, "is_critical": True, "description": {"en": "Critical irrigation during flowering. Do not let field dry.", "hi": "फूल के समय सिंचाई जरूरी। खेत सूखने न दें।"}},
    ],
    "GRAIN_FILLING": [
        {"day_offset": 0, "activity_type": "IRRIGATION", "input_name": "Reduce Water Gradually", "typical_quantity": "Drain 15 days before harvest", "typical_cost_per_acre": 0, "is_critical": True, "description": {"en": "Start reducing water. Stop irrigation 15 days before harvest.", "hi": "पानी कम करना शुरू करें। कटाई से 15 दिन पहले सिंचाई बंद।"}},
        {"day_offset": 10, "activity_type": "OTHER", "input_name": "Bird Scaring", "typical_quantity": "Daily", "typical_cost_per_acre": 0, "is_critical": False, "description": {"en": "Protect grain from bird damage", "hi": "दाने को चिड़ियों से बचाएं"}},
        {"day_offset": 20, "activity_type": "OTHER", "input_name": "Harvest Readiness Check", "typical_quantity": "Check grain moisture 20-22%", "typical_cost_per_acre": 0, "is_critical": True, "description": {"en": "Check if 80% grains are golden. Moisture should be 20-22%.", "hi": "देखें 80% दाने सुनहरे हैं। नमी 20-22% होनी चाहिए।"}},
    ],
    "HARVEST": [
        {"day_offset": 0, "activity_type": "MACHINERY", "input_name": "Harvesting (Manual/Combine)", "typical_quantity": "1 acre", "typical_cost_per_acre": 3500, "is_critical": True, "description": {"en": "Harvest when grain moisture is 20-22%. Use combine or manual cutting.", "hi": "जब दाने में 20-22% नमी हो तब काटें। कंबाइन या हाथ से कटाई।"}},
        {"day_offset": 2, "activity_type": "LABOR", "input_name": "Threshing & Winnowing", "typical_quantity": "Same day or next", "typical_cost_per_acre": 1500, "is_critical": True, "description": {"en": "Thresh and clean grain within 2 days of cutting", "hi": "कटाई के 2 दिन में गहाई और सफाई करें"}},
        {"day_offset": 3, "activity_type": "OTHER", "input_name": "Sun Drying", "typical_quantity": "Dry to 12-14% moisture", "typical_cost_per_acre": 0, "is_critical": True, "description": {"en": "Dry grain in sun to 12-14% moisture for safe storage", "hi": "भंडारण के लिए धूप में सुखाकर 12-14% नमी करें"}},
    ],
}


# Sugarcane Kharif ? recommended activities per stage
# day_offset is relative to stage start date. Values are practical defaults for UP
# and can later move to CSV/web-managed configuration.
SUGARCANE_ACTIVITIES = {
    "PLANTING": [
        {"day_offset": 0, "activity_type": "LABOR", "input_name": "Deep Ploughing & Field Preparation", "typical_quantity": "2-3 ploughings + leveling", "typical_cost_per_acre": 3500, "is_critical": True, "description": {"en": "Prepare a fine, well-drained seedbed before cane set planting", "hi": "????? ?? ????? ?? ???? ??? ?? ???? ????? ?? ???????? ????"}},
        {"day_offset": 1, "activity_type": "FERTILIZER", "input_name": "FYM/Compost", "typical_quantity": "4-5 tonnes/acre", "typical_cost_per_acre": 3000, "is_critical": True, "description": {"en": "Apply well-decomposed FYM during final field preparation", "hi": "????? ??? ?????? ??? ????? ???? ???? ??? ?????"}},
        {"day_offset": 2, "activity_type": "SEED", "input_name": "Healthy Cane Setts", "typical_quantity": "18,000-22,000 three-budded setts/acre", "typical_cost_per_acre": 9000, "is_critical": True, "description": {"en": "Use disease-free cane setts from healthy seed cane", "hi": "?????? ??? ????? ?? ???????? ??? ??? ???? ??? ?????"}},
        {"day_offset": 2, "activity_type": "OTHER", "input_name": "Sett Treatment", "typical_quantity": "Fungicide/insecticide dip as advised", "typical_cost_per_acre": 500, "is_critical": True, "description": {"en": "Treat setts before planting to reduce sett rot and early pests", "hi": "??? ??? ?? ??????? ????? ?? ???? ?? ??? ????? ?? ???? ????? ????"}},
        {"day_offset": 3, "activity_type": "FERTILIZER", "input_name": "Basal NPK Dose", "typical_quantity": "DAP/SSP + MOP as per soil test", "typical_cost_per_acre": 2500, "is_critical": True, "description": {"en": "Apply basal phosphorus and potash in furrows before covering setts", "hi": "??? ???? ?? ???? ?????? ??? ???????? ?? ????? ?? ???? ????? ???"}},
        {"day_offset": 4, "activity_type": "IRRIGATION", "input_name": "First Irrigation After Planting", "typical_quantity": "Light irrigation", "typical_cost_per_acre": 600, "is_critical": True, "description": {"en": "Irrigate lightly after planting for sett establishment", "hi": "??? ???? ?? ??? ????? ?? ??? ????? ?????? ????"}},
    ],
    "GERMINATION": [
        {"day_offset": 7, "activity_type": "IRRIGATION", "input_name": "Moisture Maintenance", "typical_quantity": "Irrigate every 7-10 days if dry", "typical_cost_per_acre": 600, "is_critical": True, "description": {"en": "Maintain soil moisture during germination; avoid waterlogging", "hi": "?????? ?? ??? ??? ???? ????, ?????? ? ???? ???"}},
        {"day_offset": 15, "activity_type": "OTHER", "input_name": "Gap Filling", "typical_quantity": "Fill missing hills/rows", "typical_cost_per_acre": 500, "is_critical": True, "description": {"en": "Fill gaps using sprouted setts to maintain plant population", "hi": "??? ?????? ???? ???? ?? ??? ???? ??? ?? ??????? ??? ?????"}},
        {"day_offset": 20, "activity_type": "PESTICIDE", "input_name": "Early Shoot Borer Monitoring", "typical_quantity": "Field scouting", "typical_cost_per_acre": 0, "is_critical": False, "description": {"en": "Scout for dead hearts and early shoot borer symptoms", "hi": "??? ????? ?? ????? ??? ???? ?? ????? ?????"}},
        {"day_offset": 25, "activity_type": "LABOR", "input_name": "First Hoeing / Light Weeding", "typical_quantity": "One operation", "typical_cost_per_acre": 1200, "is_critical": False, "description": {"en": "Remove early weeds and loosen top soil", "hi": "??????? ??????? ????? ?? ???? ?????? ??????? ????"}},
    ],
    "TILLERING": [
        {"day_offset": 0, "activity_type": "FERTILIZER", "input_name": "Urea First Top Dressing", "typical_quantity": "45-50 kg/acre", "typical_cost_per_acre": 800, "is_critical": True, "description": {"en": "Apply first nitrogen split at tillering start", "hi": "????? ?????? ?? ?????? ?? ?????? ?? ???? ??? ???????? ????"}},
        {"day_offset": 10, "activity_type": "LABOR", "input_name": "Interculture & Weeding", "typical_quantity": "One hoeing/weeding", "typical_cost_per_acre": 1500, "is_critical": True, "description": {"en": "Control weeds before canopy closes", "hi": "??? ???? ?? ???? ??????? ???????? ????"}},
        {"day_offset": 20, "activity_type": "PESTICIDE", "input_name": "Shoot Borer Control If Needed", "typical_quantity": "Need-based application", "typical_cost_per_acre": 700, "is_critical": False, "description": {"en": "Apply recommended control if borer incidence crosses threshold", "hi": "???? ?????? ???? ?? ???? ?? ?? ???????? ???????? ????"}},
        {"day_offset": 30, "activity_type": "IRRIGATION", "input_name": "Tillering Irrigation", "typical_quantity": "Irrigate as per soil moisture", "typical_cost_per_acre": 700, "is_critical": True, "description": {"en": "Avoid moisture stress during tiller formation", "hi": "????? ???? ??? ??? ?? ??? ? ???? ???"}},
    ],
    "GRAND_GROWTH": [
        {"day_offset": 0, "activity_type": "FERTILIZER", "input_name": "Urea Second Top Dressing", "typical_quantity": "45-50 kg/acre", "typical_cost_per_acre": 800, "is_critical": True, "description": {"en": "Apply second nitrogen split at grand growth start", "hi": "??? ?????? ?? ?????? ?? ?????? ?? ????? ????? ???"}},
        {"day_offset": 20, "activity_type": "LABOR", "input_name": "Earthing Up", "typical_quantity": "One operation", "typical_cost_per_acre": 2000, "is_critical": True, "description": {"en": "Earth up rows to support canes and improve root growth", "hi": "????? ?? ????? ?? ??? ?????? ?? ??? ?????? ??????"}},
        {"day_offset": 30, "activity_type": "IRRIGATION", "input_name": "Critical Growth Irrigation", "typical_quantity": "Every 10-15 days if no rain", "typical_cost_per_acre": 900, "is_critical": True, "description": {"en": "Grand growth is a high water-demand phase", "hi": "??? ?????? ?????? ??? ???? ?? ???? ???? ???? ??"}},
        {"day_offset": 45, "activity_type": "PESTICIDE", "input_name": "Top Borer / Pyrilla Monitoring", "typical_quantity": "Field scouting", "typical_cost_per_acre": 0, "is_critical": False, "description": {"en": "Monitor for top borer, pyrilla and leaf diseases", "hi": "??? ????, ??????? ?? ????? ????? ?? ??????? ????"}},
    ],
    "MATURITY": [
        {"day_offset": 0, "activity_type": "IRRIGATION", "input_name": "Reduce Irrigation Frequency", "typical_quantity": "Avoid excess irrigation", "typical_cost_per_acre": 0, "is_critical": True, "description": {"en": "Reduce excess irrigation during ripening to improve sugar accumulation", "hi": "???? ?? ???? ???? ?? ??? ???? ?????? ?? ????"}},
        {"day_offset": 20, "activity_type": "OTHER", "input_name": "Trash Management", "typical_quantity": "Remove dry leaves if needed", "typical_cost_per_acre": 800, "is_critical": False, "description": {"en": "Remove excess dry trash only if it interferes with field operations", "hi": "????? ???? ?? ???? ???????? ?????"}},
        {"day_offset": 35, "activity_type": "OTHER", "input_name": "Maturity Check", "typical_quantity": "Check cane hardness and brix if available", "typical_cost_per_acre": 0, "is_critical": True, "description": {"en": "Check maturity before deciding harvest date", "hi": "???? ?? ????? ?? ???? ?? ???? ????????? ??????"}},
        {"day_offset": 50, "activity_type": "OTHER", "input_name": "Harvest Planning", "typical_quantity": "Arrange labor/transport/mill slot", "typical_cost_per_acre": 0, "is_critical": True, "description": {"en": "Arrange harvest labor, transport and mill supply timing", "hi": "???? ?????, ?????? ?? ??? ??????? ??? ?? ???????? ????"}},
    ],
    "HARVEST": [
        {"day_offset": 0, "activity_type": "LABOR", "input_name": "Cane Cutting", "typical_quantity": "Cut mature canes close to ground", "typical_cost_per_acre": 6000, "is_critical": True, "description": {"en": "Harvest mature canes close to ground level", "hi": "??? ????? ?? ???? ?? ??? ?? ?????"}},
        {"day_offset": 0, "activity_type": "LABOR", "input_name": "Detrashing & Bundling", "typical_quantity": "Clean and bundle canes", "typical_cost_per_acre": 2000, "is_critical": True, "description": {"en": "Remove tops/trash and bundle cane for transport", "hi": "?????/???? ???????? ????? ????? ?? ???? ?????"}},
        {"day_offset": 1, "activity_type": "MACHINERY", "input_name": "Transport to Mill/Crusher", "typical_quantity": "Same day or within 24 hours", "typical_cost_per_acre": 3500, "is_critical": True, "description": {"en": "Transport quickly after cutting to reduce sucrose loss", "hi": "???? ???? ?? ???? ?? ??? ???? ?? ??? ????? ?????? ????"}},
        {"day_offset": 3, "activity_type": "OTHER", "input_name": "Ratoon Decision", "typical_quantity": "Inspect stubble and field condition", "typical_cost_per_acre": 0, "is_critical": False, "description": {"en": "Decide whether to keep ratoon crop based on stand and pest status", "hi": "?????? ?? ??? ?????? ????? ???? ??? ???? ?? ?????? ???"}},
    ],
}


def update_template_with_recommendations():
    db = SessionLocal()

    templates = {
        "RICE_KHARIF_DEFAULT": RICE_ACTIVITIES,
        "SUGARCANE_DEFAULT": SUGARCANE_ACTIVITIES,
    }

    for template_code, activities_by_stage in templates.items():
        template = db.query(CropLifecycleTemplate).filter(
            CropLifecycleTemplate.code == template_code
        ).first()

        if template:
            stages = template.stages or []
            updated_stages = []
            for stage in stages:
                stage_copy = dict(stage)
                code = stage_copy["code"]
                stage_copy["recommended_activities"] = activities_by_stage.get(code, [])
                updated_stages.append(stage_copy)
            template.stages = updated_stages
            flag_modified(template, "stages")
            template.updated_at = datetime.now(timezone.utc)
            print(f"Updated {template_code} with recommended activities for {len(activities_by_stage)} stages")
        else:
            print(f"{template_code} template not found")

    db.commit()
    db.close()


if __name__ == "__main__":
    print("Seeding recommended activities...")
    update_template_with_recommendations()
    print("Done!")
