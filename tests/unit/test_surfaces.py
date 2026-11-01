from shapely.affinity import translate
from shapely.geometry import box, mapping, shape

from iloilo3d.generation.buildings import building_profile
from iloilo3d.generation.roads import prepare_surfaces
from iloilo3d.geospatial.coordinates import CoordinateFrame
from iloilo3d.models import PublicSpace
from iloilo3d.providers.osm import extract, import_source


def test_buffer_does_not_cover_unchanged_buildings(config, osm_file):
    data = extract(osm_file, config, import_source(osm_file, config, synthetic=True))
    original = data.model_dump_json()
    frame = CoordinateFrame(data.origin, data.projected_crs)
    layout = prepare_surfaces(data, frame, box(-150, -150, 150, 150), 60)
    assert any(r["removed_area_m2"] > 0 for r in layout.records)
    assert layout.overlap_area_m2 == 0
    assert all(layout.roads.intersection(b).area == 0 for b in layout.buildings)
    assert data.model_dump_json() == original


def test_centerline_conflicts_remain_flagged(config, osm_file):
    data = extract(osm_file, config, import_source(osm_file, config, synthetic=True))
    house = next(b for b in data.buildings if b.id == "osm/way/200")
    house.footprint = mapping(translate(shape(house.footprint), yoff=-0.0003))
    frame = CoordinateFrame(data.origin, data.projected_crs)
    layout = prepare_surfaces(data, frame, box(-150, -150, 150, 150), 6)
    assert any(house.id in r["centerline_conflicts"] for r in layout.records)
    assert layout.overlap_area_m2 == 0


def test_mapped_public_space_and_path_partition(config, osm_file):
    data = extract(osm_file, config, import_source(osm_file, config, synthetic=True))
    b = data.bounds
    data.public_spaces = [
        PublicSpace(
            id="test/park",
            geometry=mapping(box(b.west, b.south, b.east, b.north)),
            tags={"leisure": "park"},
        )
    ]
    data.roads[-1].drivable_candidate = False
    data.roads[-1].tags["highway"] = "footway"
    frame = CoordinateFrame(data.origin, data.projected_crs)
    layout = prepare_surfaces(data, frame, box(-125, -125, 125, 125), 6)
    assert layout.paths.area > 0 and layout.parks.area > 0
    assert layout.paths.intersection(layout.roads).area == 0
    assert layout.parks.intersection(layout.paths).area == 0
    assert layout.parks.intersection(layout.roads).area == 0


def test_extract_named_park_from_osm(config, osm_file, tmp_path):
    path = tmp_path / "park.osm"
    path.write_text(
        osm_file.read_text().replace(
            "</osm>",
            """
      <way id="400" version="1"><nd ref="1"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
      <tag k="leisure" v="park"/><tag k="name" v="Synthetic Plaza"/></way></osm>""",
        )
    )
    data = extract(path, config, import_source(path, config, synthetic=True))
    assert len(data.public_spaces) == 1
    assert data.public_spaces[0].tags["name"] == "Synthetic Plaza"
    assert data.public_spaces[0].source_version == "1"


def test_open_roof_preserves_path_below(config, osm_file):
    data = extract(osm_file, config, import_source(osm_file, config, synthetic=True))
    house = next(b for b in data.buildings if b.id == "osm/way/200")
    house.footprint = mapping(translate(shape(house.footprint), yoff=-0.0003))
    house.tags["building"] = "roof"
    frame = CoordinateFrame(data.origin, data.projected_crs)
    layout = prepare_surfaces(data, frame, box(-150, -150, 150, 150), 6)
    assert layout.roads.intersection(frame.local_geometry(shape(house.footprint))).area > 0
    assert not any(house.id in r["centerline_conflicts"] for r in layout.records)
    profile = building_profile(house)
    assert profile.open_roof and profile.bottom == 7.75 and profile.top == 8
    assert profile.bottom_status == "estimated"


def test_low_roof_remains_an_obstacle(config, osm_file):
    data = extract(osm_file, config, import_source(osm_file, config, synthetic=True))
    house = next(b for b in data.buildings if b.id == "osm/way/200")
    house.tags.update(building="roof", min_height="2 m")
    profile = building_profile(house)
    assert profile.obstructs_ground
    assert profile.bottom == 2 and profile.bottom_status == "mapped"
