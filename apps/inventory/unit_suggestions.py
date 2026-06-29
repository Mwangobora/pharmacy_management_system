from __future__ import annotations


DOSAGE_FORM_UNIT_SUGGESTIONS = {
    'tablet': 'tablets',
    'capsule': 'capsules',
    'syrup': 'bottles',
    'suspension': 'bottles',
    'injection': 'vials',
    'ampoule': 'vials',
    'cream': 'tubes',
    'ointment': 'tubes',
    'sachet_powder': 'sachets',
}


def suggest_base_unit_for_dosage_form(dosage_form: str | None) -> str | None:
    if not dosage_form:
        return None
    return DOSAGE_FORM_UNIT_SUGGESTIONS.get(str(dosage_form).strip().lower())
