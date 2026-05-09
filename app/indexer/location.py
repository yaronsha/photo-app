"""
Indexer step: reverse geocode lat/lng → location_name.

Uses offline reverse_geocoder (GeoNames dataset, no internet needed).
Populates location_name column for photos that have GPS coords.
"""
from datetime import datetime, timezone

import reverse_geocoder
from sqlalchemy import select, update

from ..db import Photo, get_session, init_schema


def run_location(reindex: bool = False) -> int:
    init_schema()

    with get_session() as session:
        stmt = select(Photo.id, Photo.lat, Photo.lng).where(
            Photo.lat.is_not(None), Photo.lng.is_not(None)
        )
        if not reindex:
            stmt = stmt.where(Photo.location_name.is_(None))
        rows = session.execute(stmt).all()

        if not rows:
            print("location: nothing to geocode")
            return 0

        coords = [(row.lat, row.lng) for row in rows]
        results = reverse_geocoder.search(coords, verbose=False)

        for row, result in zip(rows, results):
            city = result.get("name", "")
            country = result.get("cc", "")
            location_name = (
                f"{city}, {country}" if city and country else city or country or None
            )
            session.execute(
                update(Photo)
                .where(Photo.id == row.id)
                .values(location_name=location_name)
            )

        count = len(rows)

    print(f"location: {count} geocoded")
    return count
