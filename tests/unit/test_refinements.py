"""Checks for reviewable width estimates and landmark massing."""

import pytest
from pydantic import ValidationError
from shapely.geometry import box

from iloilo3d.generation.landmarks import landmark_parts
from iloilo3d.generation.overrides import GeometryOverrides
from iloilo3d.generation.roads import prepare_surfaces
from iloilo3d.geospatial.coordinates import CoordinateFrame
from iloilo3d.providers.osm import extract, import_source


def test_lane_width_and_review_override(config, osm_file):
    dataset = extract(osm_file, config, import_source(osm_file, config, synthetic=True))
    road = next(road for road in dataset.roads if road.drivable_candidate)
    road.width_m = None
    road.lanes = 4
    frame = CoordinateFrame(dataset.origin, dataset.projected_crs)
    boundary = box(-150, -150, 150, 150)
    record = next(
        item
        for item in prepare_surfaces(dataset, frame, boundary, 6).records
        if item["source_id"] == road.id
    )
    assert record["width_m"] == 12
    assert record["width_status"] == "estimated_from_mapped_lanes"
    overrides = GeometryOverrides.model_validate(
        {
            "roads": {
                road.id: {
                    "width_m": 9,
                    "evidence": "visual_estimate",
                    "reason": "Reviewed in prototype map",
                }
            }
        }
    )
    reviewed = next(
        item
        for item in prepare_surfaces(dataset, frame, boundary, 6, overrides=overrides).records
        if item["source_id"] == road.id
    )
    assert reviewed["width_m"] == 9
    assert reviewed["width_override"]["reason"] == "Reviewed in prototype map"


def test_override_requires_evidence_and_reason():
    with pytest.raises(ValidationError):
        GeometryOverrides.model_validate({"buildings": {"a": {"height_m": 20}}})


def test_building_footprint_correction_changes_export_geometry(config, osm_file):
    dataset = extract(osm_file, config, import_source(osm_file, config, synthetic=True))
    building = dataset.buildings[0]
    frame = CoordinateFrame(dataset.origin, dataset.projected_crs)
    boundary = box(-150, -150, 150, 150)
    base = prepare_surfaces(dataset, frame, boundary, 6)
    overrides = GeometryOverrides.model_validate(
        {
            "buildings": {
                building.id: {
                    "footprint_scale": 1.1,
                    "evidence": "visual_estimate",
                    "reason": "Reviewed against local field image",
                }
            }
        }
    )
    enlarged = prepare_surfaces(dataset, frame, boundary, 6, overrides=overrides)
    assert enlarged.buildings[0].area == pytest.approx(base.buildings[0].area * 1.21)
    assert enlarged.overlap_area_m2 == 0


def test_landmark_parts_have_valid_meshes():
    footprint = box(-5, -5, 5, 5)
    belfry = landmark_parts("osm/way/530035049", footprint, 29)
    pavilion = landmark_parts("osm/way/485045671", footprint, 5.5)
    assert belfry is not None and len(belfry) == 3
    assert pavilion is not None and len(pavilion) == 6
    for _, mesh, _ in [*belfry, *pavilion]:
        mesh.validate()
