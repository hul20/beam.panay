import math

import pytest
from pydantic import ValidationError
from shapely.geometry import Point, box

from iloilo3d.config import ProjectConfig, Region, load_config
from iloilo3d.geospatial.coordinates import CoordinateFrame
from iloilo3d.models import BoundingBox, GeographicPoint


def test_round_trip_and_origin() -> None:
    origin = GeographicPoint(longitude=122.5685, latitude=10.6952, elevation_m=12)
    frame = CoordinateFrame(origin)
    assert frame.geographic_to_local(122.5685, 10.6952, 12) == (0, 0, 0)
    for x, y, z in [(125, 125, 8), (-125, -125, -2), (0, 50, 0)]:
        geographic = frame.local_to_geographic(x, y, z)
        assert frame.geographic_to_local(*geographic) == pytest.approx((x, y, z), abs=1e-6)
    assert frame.geographic_to_local(122.569, 10.6952)[0] > 0
    assert frame.geographic_to_local(122.5685, 10.696)[1] > 0


def test_local_geometry_and_scale() -> None:
    region = Region()
    frame = CoordinateFrame(region.origin)
    b = region.bounds()
    geometry = frame.local_geometry(box(b.west, b.south, b.east, b.north))
    assert math.sqrt(geometry.area) == pytest.approx(250, abs=1)
    assert frame.local_geometry(Point(region.origin.longitude, region.origin.latitude)).x == 0


@pytest.mark.parametrize(
    "bounds",
    [
        dict(west=123, east=122, south=10, north=11),
        dict(west=122, east=123, south=11, north=10),
        dict(west=122, east=122, south=10, north=11),
        dict(west=float("nan"), east=123, south=10, north=11),
    ],
)
def test_bad_bounds(bounds) -> None:
    with pytest.raises(ValidationError):
        BoundingBox(**bounds)


def test_area_and_crs_guards() -> None:
    with pytest.raises(ValidationError):
        Region(projected_crs="EPSG:4326")
    with pytest.raises(ValidationError):
        Region(projected_crs="EPSG:32630")
    config = ProjectConfig(region=Region(size_m=2000))
    with pytest.raises(ValueError, match="exceeds"):
        config.validate_area()


def test_paths_relative_to_config_and_unknown_keys(tmp_path) -> None:
    config = tmp_path / "region.yaml"
    config.write_text("data_dir: out\n")
    assert load_config(config).data_dir == tmp_path / "out"
    config.write_text("misspelled_region: true\n")
    with pytest.raises(ValidationError):
        load_config(config)
