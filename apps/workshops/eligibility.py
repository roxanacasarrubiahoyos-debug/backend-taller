"""
Criterios para listar talleres (mapa / nearby) y para ofertas de incidentes (AssignmentEngine).
"""
from django.conf import settings

from apps.workshops.geo import is_valid_coordinate_pair

# Códigos legacy (panel web en español) → tipo canónico del incidente / ServiceCategory
SERVICE_CODE_ALIASES: dict[str, str] = {
    'bateria': 'battery',
    'batería': 'battery',
    'llanta': 'tire',
    'llantas': 'tire',
    'remolque': 'towing',
    'grua': 'towing',
    'grúa': 'towing',
    'motor': 'engine',
    'accidente': 'accident',
    'cerrajeria': 'locksmith',
    'cerrajería': 'locksmith',
    'general': 'general',
    'battery': 'battery',
    'tire': 'tire',
    'towing': 'towing',
    'engine': 'engine',
    'accident': 'accident',
    'locksmith': 'locksmith',
    'overheating': 'engine',
}


def normalize_service_codes(services) -> set[str]:
    out: set[str] = set()
    if not isinstance(services, list):
        return out
    for raw in services:
        key = str(raw).strip().lower()
        if not key:
            continue
        out.add(SERVICE_CODE_ALIASES.get(key, key))
    return out


def workshop_handles_incident_type(workshop, incident_type: str) -> bool:
    it = (incident_type or '').strip().lower()
    if it in ('uncertain', 'other', ''):
        return True
    normalized = normalize_service_codes(workshop.services or [])
    if not normalized:
        return True
    if 'general' in normalized:
        return True
    if it == 'overheating' and 'engine' in normalized:
        return True
    return it in normalized


def workshop_has_operational_subscription(workshop) -> bool:
    sub = getattr(getattr(workshop, 'owner', None), 'subscription', None)
    return sub is not None and sub.is_operational


def workshop_assignment_block_reason(workshop) -> str | None:
    """None = puede recibir ofertas de incidentes."""
    if not workshop.is_active:
        return 'inactive'
    if not workshop.is_verified and not getattr(settings, 'ASSIGNMENT_ALLOW_UNVERIFIED', False):
        return 'not_verified'
    if getattr(settings, 'ASSIGNMENT_REQUIRE_SUBSCRIPTION', True):
        if not workshop_has_operational_subscription(workshop):
            return 'subscription'
    if not workshop.technicians.filter(is_available=True).exists():
        return 'no_technician'
    if not is_valid_coordinate_pair(workshop.latitude, workshop.longitude):
        return 'no_location'
    return None


def workshop_visible_in_nearby(workshop) -> bool:
    """Mapa «talleres cercanos»: activo, verificado y con coordenadas WGS84 válidas."""
    if not workshop.is_active or not workshop.is_verified:
        return False
    return is_valid_coordinate_pair(workshop.latitude, workshop.longitude)
