"""Bounded local repair routing; visual actions cannot accept facts."""
from dataclasses import dataclass, field

@dataclass
class RepairBudget:
    max_regions: int = 2
    max_actions: int = 2
    actions: dict = field(default_factory=dict)

    def request(self, region_id, diagnosis, action):
        routes = {"no_native_text": {"ocr"}, "corrupt_native_text": {"ocr"},
                  "unresolved_grid": {"structure"}, "rotation_error": {"rotate", "ocr"}}
        if action not in routes.get(diagnosis, set()):
            return {"state": "unresolved", "reason": "diagnosis_does_not_license_visual_repair"}
        if region_id not in self.actions and len(self.actions) >= self.max_regions:
            return {"state": "deferred", "reason": "repair_region_budget"}
        used = self.actions.setdefault(region_id, [])
        if len(used) >= self.max_actions:
            return {"state": "deferred", "reason": "repair_action_budget"}
        used.append({"diagnosis": diagnosis, "action": action})
        return {"state": "requested", "region_id": region_id, "action": action,
                "acceptance_authority": False}

def validate_repair_result(original, repaired):
    required = {"original_source_sha256", "representation_sha256", "backend_version",
                "image_sha256", "page", "bbox", "transform_to_page", "provenance"}
    if not required.issubset(repaired) or repaired["original_source_sha256"] != original:
        raise ValueError("Repair lacks source identity or coordinate transform")
    if repaired["provenance"] != "ocr":
        raise ValueError("OCR must retain its own provenance")
    return repaired
