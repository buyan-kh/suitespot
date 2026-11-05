"""Distance sort for hotel search (US1.5).

Distance is measured from the searched city's centre, or from lat/lng when the
request sends them (e.g. a future "near me" button).

The sort happens in Python on the great-circle (haversine) distance rather than
in SQL: exact ordering needs trig functions, which not every SQLite build has,
and a flat-map approximation gets the order wrong across long distances. A
search returns one destination's hotels, so sorting them in memory is cheap.
"""
from collections.abc import Iterable, Mapping
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0

# Centres of the cities we seed, keyed by lowercase city name.
# Every city in app/seed/fixtures/hotels.json needs an entry here
# (tests/test_distance_sort.py checks this).
CITY_CENTRES: dict[str, tuple[float, float]] = {
    "san jose": (37.3382, -121.8863),
    "san francisco": (37.7749, -122.4194),
    "miami": (25.7617, -80.1918),
    "new york": (40.7128, -74.0060),
}

Origin = tuple[float, float]


def resolve_origin(
    destination: str, lat: float | None = None, lng: float | None = None
) -> Origin | None:
    """The point to measure from: lat/lng if given, else the destination's city centre."""
    if lat is not None and lng is not None:
        return (lat, lng)
    query = destination.strip().lower()
    if query in CITY_CENTRES:
        return CITY_CENTRES[query]
    # "San Jose, CA" or "downtown miami" still find the city.
    for city, centre in CITY_CENTRES.items():
        if city in query:
            return centre
    return None


def haversine_km(origin: Origin, lat: float | None, lng: float | None) -> float | None:
    """Great-circle distance in km, rounded to 0.1. None if the hotel has no coordinates."""
    if lat is None or lng is None:
        return None
    lat0, lng0 = map(radians, origin)
    lat1, lng1 = radians(lat), radians(lng)
    a = sin((lat1 - lat0) / 2) ** 2 + cos(lat0) * cos(lat1) * sin((lng1 - lng0) / 2) ** 2
    return round(2 * EARTH_RADIUS_KM * asin(sqrt(a)), 1)


def sort_by_distance(hotels: Iterable[Mapping], origin: Origin) -> list[dict]:
    """Hotels closest first, each with distance_km. Hotels without coordinates go last.

    Each hotel needs latitude, longitude, name and id. Ties break by name, then
    id, matching the other sorts so paging stays stable.
    """
    rows = [
        {**h, "distance_km": haversine_km(origin, h["latitude"], h["longitude"])}
        for h in hotels
    ]
    rows.sort(key=lambda h: (
        h["distance_km"] is None, h["distance_km"] or 0.0, h["name"], h["id"],
    ))
    return rows
