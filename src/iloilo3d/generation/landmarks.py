"""Conservative massing for mapped Jaro landmarks; details are estimated."""

from shapely.geometry import Point, Polygon

from iloilo3d.generation.meshes import Mesh, extrude


def landmark_parts(
    source_id: str, footprint: Polygon, height_m: float
) -> list[tuple[str, Mesh, str]] | None:
    """Return estimated parts, or None for the ordinary footprint extrusion."""
    if source_id == "osm/way/530035049":  # Jaro Belfry, mapped height 29 m.
        tiers = [
            (footprint, 0.0, height_m * 0.45),
            (footprint.buffer(-0.35), height_m * 0.45, height_m * 0.76),
            (footprint.buffer(-0.7), height_m * 0.76, height_m),
        ]
        if any(poly.is_empty or poly.geom_type != "Polygon" for poly, _, _ in tiers):
            return None
        return [
            (f"tier_{index}", extrude(poly, bottom, top), "iloilo_adobe")
            for index, (poly, bottom, top) in enumerate(tiers)
        ]
    if source_id == "osm/way/485045671":  # OSM leisure=bandstand.
        parts = [
            ("platform", extrude(footprint, 0, 0.35), "iloilo_wall"),
            ("roof", extrude(footprint, height_m - 0.35, height_m), "iloilo_roof"),
        ]
        corners = list(footprint.exterior.coords)[:-1]
        for index, (x, y) in enumerate(corners):
            # Slight inset keeps the estimated supports inside the mapped outline.
            cx, cy = footprint.centroid.coords[0]
            px, py = x + (cx - x) * 0.09, y + (cy - y) * 0.09
            column = Point(px, py).buffer(0.18, quad_segs=4)
            parts.append((f"post_{index}", extrude(column, 0.35, height_m - 0.35), "iloilo_wall"))
        return parts
    return None
