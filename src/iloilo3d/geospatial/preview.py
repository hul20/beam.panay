"""Dependency-light SVG diagnostic preview containing independent OSM data only."""

from html import escape
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import box, shape

from iloilo3d.geospatial.coordinates import CoordinateFrame
from iloilo3d.models import GeographicDataset
from iloilo3d.storage.files import atomic_bytes


def write_preview(dataset: GeographicDataset, path: Path) -> None:
    frame = CoordinateFrame(dataset.origin, dataset.projected_crs)
    b = dataset.bounds
    region = frame.local_geometry(box(b.west, b.south, b.east, b.north))
    xmin, ymin, xmax, ymax = region.bounds
    scale = min(720 / (xmax - xmin), 660 / (ymax - ymin))

    def point(x: float, y: float) -> str:
        return f"{40 + (x - xmin) * scale:.3f},{80 + (ymax - y) * scale:.3f}"

    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="850" viewBox="0 0 800 850">',
        '<rect width="800" height="850" fill="#f5f3eb"/>',
        "<style>text{font-family:system-ui,sans-serif;fill:#173b3c}</style>",
        '<text x="40" y="30" font-size="22">Iloilo3D · geographic extraction</text>',
        f'<text x="40" y="55" font-size="13">{len(dataset.buildings)} footprints · '
        f"{len(dataset.roads)} road segments · X east / Y north</text>",
        '<defs><clipPath id="area"><rect x="40" y="80" '
        f'width="{(xmax - xmin) * scale}" height="{(ymax - ymin) * scale}"/></clipPath></defs>',
        '<g clip-path="url(#area)">',
    ]
    for building in dataset.buildings:
        geometry = frame.local_geometry(shape(building.footprint))
        polygons = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
        for polygon in polygons:
            rings = [polygon.exterior, *polygon.interiors]
            d = " ".join(
                "M " + " L ".join(point(x, y) for x, y in ring.coords) + " Z" for ring in rings
            )
            lines.append(
                f'<path d="{d}" fill="#d3ab78" stroke="#8a6037" stroke-width="1" '
                f'fill-rule="evenodd"><title>{escape(building.id)}</title></path>'
            )
    for road in dataset.roads:
        geom = frame.local_geometry(shape(road.centerline))
        d = "M " + " L ".join(point(x, y) for x, y in geom.coords)
        color = "#287c87" if road.drivable_candidate else "#839698"
        lines.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2">'
            f"<title>{escape(road.tags.get('name', road.id))}</title></path>"
        )
    lines += [
        "</g>",
        '<text x="740" y="72" font-size="16">N ↑</text>',
        f'<path d="M 40 770 h {50 * scale:.3f}" stroke="#173b3c" stroke-width="3"/>',
        '<text x="40" y="790" font-size="12">'
        "50 m · road strokes are centerlines, not widths</text>",
        f'<text x="40" y="814" font-size="12">{escape(dataset.source.attribution)}</text>',
        '<text x="40" y="835" font-size="12">'
        + (
            "SYNTHETIC TEST DATA — not real geography"
            if dataset.source.synthetic
            else "Mapped geometry; heights, survey accuracy, and road elevation are unverified"
        )
        + "</text></svg>",
    ]
    atomic_bytes(path, "\n".join(lines).encode("utf-8"))


def write_png_preview(dataset: GeographicDataset, path: Path) -> None:
    """Draw a level thumbnail from independent mapped geometry, without map tiles."""
    frame = CoordinateFrame(dataset.origin, dataset.projected_crs)
    b = dataset.bounds
    boundary = frame.local_geometry(box(b.west, b.south, b.east, b.north))
    xmin, ymin, xmax, ymax = boundary.bounds
    scale = min(720 / (xmax - xmin), 640 / (ymax - ymin))
    image = Image.new("RGB", (800, 800), "#f5f3eb")
    draw = ImageDraw.Draw(image)

    def points(ring) -> list[tuple[float, float]]:
        return [(40 + (x - xmin) * scale, 70 + (ymax - y) * scale) for x, y in ring.coords]

    for building in dataset.buildings:
        geom = frame.local_geometry(shape(building.footprint)).intersection(boundary)
        parts = [geom] if geom.geom_type == "Polygon" else getattr(geom, "geoms", [])
        for poly in parts:
            if poly.geom_type != "Polygon" or poly.is_empty:
                continue
            draw.polygon(points(poly.exterior), fill="#d3ab78", outline="#8a6037")
            for ring in poly.interiors:
                draw.polygon(points(ring), fill="#f5f3eb", outline="#8a6037")
    for road in dataset.roads:
        geom = frame.local_geometry(shape(road.centerline)).intersection(boundary)
        lines = [geom] if geom.geom_type == "LineString" else getattr(geom, "geoms", [])
        for line in lines:
            if line.geom_type == "LineString" and not line.is_empty:
                draw.line(points(line), fill="#287c87", width=2)
    draw.text((40, 20), "Iloilo3D | Geographic test prototype", fill="#173b3c", font_size=24)
    draw.text(
        (40, 50), "N up | Road centerlines and mapped footprints", fill="#173b3c", font_size=14
    )
    draw.line([(40, 735), (40 + 50 * scale, 735)], fill="#173b3c", width=3)
    draw.text((40, 742), "50 m | " + dataset.source.attribution, fill="#173b3c", font_size=14)
    label = (
        "SYNTHETIC TEST DATA"
        if dataset.source.synthetic
        else "Estimated masses; flat test pad; game validation pending"
    )
    draw.text((40, 770), label, fill="#173b3c", font_size=14)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
