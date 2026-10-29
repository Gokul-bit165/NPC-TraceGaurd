"""Small offline geography helper: haversine distance and a built-in city / country table.

The RBA dataset carries no coordinates and its geography is artificial, so impossible travel is
demonstrated on scripted scenarios and the seed data. In production, replace `resolve` with a
GeoIP lookup (for example MaxMind GeoLite2) that returns real coordinates.
"""
from __future__ import annotations

import math
from typing import Optional

# name (lower case) -> (lat, lon, ISO country)
CITIES: dict[str, tuple[float, float, str]] = {
    "pune": (18.5204, 73.8567, "IN"), "mumbai": (19.0760, 72.8777, "IN"), "delhi": (28.6139, 77.2090, "IN"),
    "bengaluru": (12.9716, 77.5946, "IN"), "chennai": (13.0827, 80.2707, "IN"), "hyderabad": (17.3850, 78.4867, "IN"),
    "kolkata": (22.5726, 88.3639, "IN"), "coimbatore": (11.0168, 76.9558, "IN"), "ahmedabad": (23.0225, 72.5714, "IN"),
    "jaipur": (26.9124, 75.7873, "IN"), "kochi": (9.9312, 76.2673, "IN"), "lucknow": (26.8467, 80.9462, "IN"),
    "lagos": (6.5244, 3.3792, "NG"), "abuja": (9.0765, 7.3986, "NG"), "moscow": (55.7558, 37.6173, "RU"),
    "saint petersburg": (59.9311, 30.3609, "RU"), "kyiv": (50.4501, 30.5234, "UA"), "london": (51.5074, -0.1278, "GB"),
    "manchester": (53.4808, -2.2426, "GB"), "frankfurt": (50.1109, 8.6821, "DE"), "berlin": (52.5200, 13.4050, "DE"),
    "paris": (48.8566, 2.3522, "FR"), "amsterdam": (52.3676, 4.9041, "NL"), "new york": (40.7128, -74.0060, "US"),
    "san francisco": (37.7749, -122.4194, "US"), "chicago": (41.8781, -87.6298, "US"), "ashburn": (39.0438, -77.4874, "US"),
    "toronto": (43.6532, -79.3832, "CA"), "singapore": (1.3521, 103.8198, "SG"), "dubai": (25.2048, 55.2708, "AE"),
    "tokyo": (35.6762, 139.6503, "JP"), "sydney": (-33.8688, 151.2093, "AU"), "sao paulo": (-23.5505, -46.6333, "BR"),
    "johannesburg": (-26.2041, 28.0473, "ZA"), "bucharest": (44.4268, 26.1025, "RO"), "warsaw": (52.2297, 21.0122, "PL"),
    "oslo": (59.9139, 10.7522, "NO"), "hong kong": (22.3193, 114.1694, "HK"), "karachi": (24.8607, 67.0011, "PK"),
    "dhaka": (23.8103, 90.4125, "BD"), "colombo": (6.9271, 79.8612, "LK"), "kathmandu": (27.7172, 85.3240, "NP"),
}

# ISO country -> approximate centroid (lat, lon). Coarse on purpose.
COUNTRIES: dict[str, tuple[float, float]] = {
    "IN": (22.0, 79.0), "US": (39.8, -98.6), "GB": (54.0, -2.5), "DE": (51.2, 10.4), "FR": (46.6, 2.4),
    "NL": (52.2, 5.3), "NG": (9.1, 8.7), "RU": (61.5, 99.0), "UA": (49.0, 31.4), "CN": (35.0, 103.0),
    "JP": (36.2, 138.2), "SG": (1.35, 103.8), "AE": (24.0, 54.0), "AU": (-25.3, 133.8), "BR": (-10.8, -52.9),
    "CA": (56.1, -106.3), "ZA": (-29.0, 25.0), "RO": (45.9, 24.9), "PL": (52.1, 19.4), "NO": (64.5, 11.5),
    "SE": (62.0, 15.0), "FI": (64.0, 26.0), "DK": (56.0, 10.0), "ES": (40.2, -3.6), "IT": (42.8, 12.6),
    "TR": (39.0, 35.0), "EG": (26.8, 30.8), "KE": (0.2, 37.9), "PK": (30.4, 69.3), "BD": (23.7, 90.4),
    "LK": (7.9, 80.7), "NP": (28.4, 84.1), "ID": (-2.5, 118.0), "MY": (4.2, 102.0), "TH": (15.9, 100.9),
    "VN": (14.1, 108.3), "PH": (12.9, 121.8), "KR": (36.5, 127.9), "HK": (22.3, 114.2), "MX": (23.6, -102.5),
    "AR": (-38.4, -63.6), "CL": (-35.7, -71.5), "CO": (4.6, -74.3), "PE": (-9.2, -75.0), "IR": (32.4, 53.7),
    "IL": (31.0, 34.9), "SA": (23.9, 45.1), "KZ": (48.0, 66.9), "BY": (53.7, 27.9), "CZ": (49.8, 15.5),
    "AT": (47.5, 14.6), "CH": (46.8, 8.2), "BE": (50.5, 4.5), "IE": (53.4, -8.2), "PT": (39.4, -8.2),
    "GR": (39.1, 22.0), "HU": (47.2, 19.5), "BG": (42.7, 25.5), "RS": (44.0, 21.0), "LT": (55.2, 23.9),
    "LV": (56.9, 24.6), "EE": (58.6, 25.0), "MD": (47.4, 28.4), "NZ": (-40.9, 174.9), "GH": (7.9, -1.0),
    "TZ": (-6.4, 34.9), "MA": (31.8, -7.1), "DZ": (28.0, 1.7), "TW": (23.7, 121.0),
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def resolve(city: str = "", country: str = "") -> Optional[tuple[float, float]]:
    """Best-effort coordinates: exact city first, then country centroid, else None."""
    key = (city or "").strip().lower()
    if key in CITIES:
        return CITIES[key][0], CITIES[key][1]
    c = (country or "").strip().upper()
    if c in COUNTRIES:
        return COUNTRIES[c]
    return None


def city_country(city: str) -> str:
    return CITIES.get((city or "").strip().lower(), (0, 0, ""))[2]
