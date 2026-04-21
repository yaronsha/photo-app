"""
Indexer step: reverse geocode lat/lng → location_name.

Uses offline reverse_geocoder (GeoNames dataset, no internet needed).
Populates location_name column for photos that have GPS coords.
"""
from datetime import datetime, timezone

import reverse_geocoder

from ..db import get_conn, init_schema


def run_location(reindex: bool = False) -> int:
    conn = get_conn()
    init_schema(conn)

    query = """
        SELECT id, lat, lng FROM photos
        WHERE lat IS NOT NULL AND lng IS NOT NULL
    """ + ("" if reindex else " AND location_name IS NULL")

    rows = conn.execute(query).fetchall()
    if not rows:
        print("location: nothing to geocode")
        return 0

    coords = [(row["lat"], row["lng"]) for row in rows]
    results = reverse_geocoder.search(coords, verbose=False)

    now = datetime.now(timezone.utc).isoformat()
    for row, result in zip(rows, results):
        city = result.get("name", "")
        country = result.get("cc", "")
        location_name = f"{city}, {country}" if city and country else city or country or None
        conn.execute(
            "UPDATE photos SET location_name = ? WHERE id = ?",
            (location_name, row["id"]),
        )

    conn.commit()
    conn.close()
    print(f"location: {len(rows)} geocoded")
    return len(rows)
