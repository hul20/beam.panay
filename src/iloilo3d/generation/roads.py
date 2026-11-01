"""Nonoverlapping test surfaces derived from mapped centerlines and footprints.

Trimming is an explicit prototype correction, never a claim of surveyed width.
Centerline conflicts remain unresolved and are reported for manual correction.
"""

from dataclasses import dataclass

from shapely import set_precision, union_all
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from iloilo3d.generation.buildings import building_profile
from iloilo3d.geospatial.coordinates import CoordinateFrame
from iloilo3d.models import GeographicDataset

GRID_M = 0.001
CLEARANCE_M = 0.25


@dataclass
class SurfaceLayout:
    roads: BaseGeometry
    paths: BaseGeometry
    parks: BaseGeometry
    pitches: BaseGeometry
    buildings: list[BaseGeometry]
    records: list[dict]
    skipped: list[str]
    overlap_area_m2: float
    ground_obstacles: list[BaseGeometry]


def prepare_surfaces(
    dataset: GeographicDataset,
    frame: CoordinateFrame,
    boundary: BaseGeometry,
    fallback_width_m: float,
    fallback_height_m: float = 6,
) -> SurfaceLayout:
    buildings = [frame.local_geometry(shape(b.footprint)) for b in dataset.buildings]
    obstructing = [
        (building, geometry)
        for building, geometry in zip(dataset.buildings, buildings, strict=True)
        if building_profile(building, fallback_height_m).obstructs_ground
    ]
    ground_obstacles = [geometry for _, geometry in obstructing]
    obstacles = set_precision(union_all(ground_obstacles).buffer(CLEARANCE_M), GRID_M)
    roads, paths, records, skipped = [], [], [], []
    for road in dataset.roads:
        walking = road.tags.get("highway") in {"footway", "path", "pedestrian"}
        if not road.drivable_candidate and not walking:
            continue
        if (
            road.tags.get("bridge", "no") != "no"
            or road.tags.get("tunnel", "no") != "no"
            or road.tags.get("layer", "0") != "0"
        ):
            skipped.append(road.id)
            continue
        if walking and road.tags.get("access") in {"no", "private"}:
            continue
        centerline = frame.local_geometry(shape(road.centerline)).intersection(boundary)
        width = road.width_m or (1.8 if walking else fallback_width_m)
        original = set_precision(
            centerline.buffer(width / 2, cap_style="flat").intersection(boundary), GRID_M
        )
        if original.is_empty:
            continue
        surface = original.difference(obstacles)
        conflicting = [
            building.id
            for building, geometry in obstructing
            if centerline.intersection(geometry).length > 0.01
        ]
        removed = max(0.0, original.area - surface.area)
        records.append(
            {
                "source_id": road.id,
                "name": road.tags.get("name"),
                "kind": "path" if walking else "road",
                "width_m": width,
                "width_status": "mapped" if road.width_m else "estimated",
                "building_clearance_m": CLEARANCE_M,
                "removed_area_m2": round(removed, 6),
                "surface_correction": "trimmed_around_buildings" if removed > 1e-6 else "none",
                "centerline_conflicts": conflicting,
                "requires_alignment_review": bool(conflicting),
                "exported_area_m2": round(surface.area, 6),
            }
        )
        (paths if walking else roads).append(surface)
    road_surface = set_precision(union_all(roads), GRID_M)
    path_surface = set_precision(union_all(paths), GRID_M).difference(road_surface)
    parks, pitches = [], []
    for space in dataset.public_spaces:
        geometry = set_precision(frame.local_geometry(shape(space.geometry)), GRID_M)
        (pitches if space.tags.get("leisure") == "pitch" else parks).append(geometry)
    occupied = union_all([road_surface, path_surface, obstacles])
    pitch_surface = union_all(pitches).intersection(boundary).difference(occupied)
    park_surface = (
        union_all(parks).intersection(boundary).difference(union_all([occupied, pitch_surface]))
    )
    overlap = road_surface.intersection(union_all(ground_obstacles)).area
    return SurfaceLayout(
        road_surface,
        path_surface,
        park_surface,
        pitch_surface,
        buildings,
        records,
        skipped,
        overlap,
        ground_obstacles,
    )
