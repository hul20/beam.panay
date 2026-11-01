from pathlib import Path

import httpx
import pytest
from shapely.geometry import shape

from iloilo3d.errors import PipelineError
from iloilo3d.providers.osm import acquire, extract, import_source, positive_number, read_osm
from iloilo3d.validation.geographic import validate_dataset


def test_footprints_holes_attributes_and_connectivity(config, osm_file) -> None:
    source = import_source(osm_file, config, synthetic=True)
    data = extract(osm_file, config, source)
    assert [building.id for building in data.buildings] == ["osm/relation/300", "osm/way/200"]
    courtyard, house = data.buildings
    assert len(shape(courtyard.footprint).interiors) == 1
    assert courtyard.height_m is None
    assert courtyard.evidence["height"].status == "unknown"
    assert house.height_m == 8
    assert house.floors == 2
    assert house.source_version == "3"
    assert len(data.roads) == 3
    assert [r.direction for r in data.roads[:2]] == ["reverse", "reverse"]
    assert data.roads[0].width_m == 6
    report = validate_dataset(data)
    assert report.valid
    assert report.counts["intersection_nodes"] == 1
    assert report.counts["drivable_components"] == 1
    assert data.source.synthetic


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("6.5 m", 6.5),
        ("10 ft", 3.048),
        ("0", None),
        ("-2", None),
        ("3;5", None),
        ("~12", None),
        (None, None),
        ("nan", None),
    ],
)
def test_numeric_tags(value, expected) -> None:
    assert positive_number(value, length=True) == expected


def test_cache_reuse_and_integrity(config, osm_file) -> None:
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, content=osm_file.read_bytes())

    transport = httpx.MockTransport(respond)
    path, source = acquire(config, transport=transport)
    assert acquire(config, transport=transport) == (path, source)
    assert len(calls) == 1
    path.write_text("tampered")
    with pytest.raises(PipelineError, match="checksum"):
        acquire(config, transport=transport)


@pytest.mark.parametrize("status", [401, 429, 504])
def test_provider_failures_do_not_publish_or_retry(config, status) -> None:
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status)

    with pytest.raises(PipelineError, match=str(status)):
        acquire(config, transport=httpx.MockTransport(respond))
    assert len(calls) == 1
    assert not list((config.data_dir / "raw").glob("*.osm"))
    assert not (config.data_dir / "raw" / ".overpass.lock").exists()


def test_partial_overpass_result_is_rejected(config) -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, content=b"<osm><remark>timeout</remark></osm>")
    )
    with pytest.raises(PipelineError, match="complete"):
        acquire(config, transport=transport)


def test_missing_nodes_are_reported(config, osm_file, tmp_path) -> None:
    broken = tmp_path / "missing.osm"
    broken.write_text(osm_file.read_text().replace('<nd ref="4"/>', '<nd ref="999"/>'))
    data = extract(broken, config, import_source(broken, config, synthetic=True))
    assert any("missing nodes" in warning for warning in data.warnings)
    assert all(road.osm_way_id != 101 for road in data.roads)


def test_empty_source_is_not_filled_in(config, tmp_path) -> None:
    empty = tmp_path / "empty.osm"
    empty.write_text('<osm version="0.6" generator="synthetic"/>')
    data = extract(empty, config, import_source(empty, config, synthetic=True))
    assert data.buildings == data.roads == []
    assert any("No mapped building" in warning for warning in validate_dataset(data).warnings)


def test_wrong_format(tmp_path: Path) -> None:
    path = tmp_path / "error.osm"
    path.write_text("<html>Server error</html>")
    with pytest.raises(PipelineError, match="Expected OSM XML"):
        read_osm(path)
