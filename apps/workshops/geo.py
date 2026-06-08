"""Validación de coordenadas y distancias (WGS84)."""
from __future__ import annotations

from geopy.distance import geodesic

LAT_MIN = -90.0
LAT_MAX = 90.0
LNG_MIN = -180.0
LNG_MAX = 180.0


def _to_float(value) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_valid_latitude(lat) -> bool:
    f = _to_float(lat)
    return f is not None and LAT_MIN <= f <= LAT_MAX


def is_valid_longitude(lng) -> bool:
    f = _to_float(lng)
    return f is not None and LNG_MIN <= f <= LNG_MAX


def is_valid_coordinate_pair(lat, lng) -> bool:
    return is_valid_latitude(lat) and is_valid_longitude(lng)


def coordinate_pair(lat, lng) -> tuple[float, float] | None:
    la, lo = _to_float(lat), _to_float(lng)
    if la is None or lo is None:
        return None
    if not is_valid_latitude(la) or not is_valid_longitude(lo):
        return None
    return (la, lo)


def distance_km(origin: tuple[float, float], destination: tuple[float, float]) -> float | None:
    """Distancia en km; None si algún punto es inválido o geopy rechaza el cálculo."""
    orig = coordinate_pair(origin[0], origin[1])
    dest = coordinate_pair(destination[0], destination[1])
    if orig is None or dest is None:
        return None
    try:
        return float(geodesic(orig, dest).km)
    except (ValueError, TypeError):
        return None
