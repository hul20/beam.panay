import json

import geopandas as gpd
import pyogrio
import pytest

from iloilo3d.cli import main
from iloilo3d.errors import PipelineError
from iloilo3d.pipeline import fetch_geodata, validate_outputs

pytestmark = pytest.mark.integration


def test_offline_job_geopackage_preview_and_restart(config, osm_file) -> None:
    directory = fetch_geodata(config, osm_file=osm_file, synthetic=True)
    layers = pyogrio.list_layers(directory / "geodata.gpkg")
    assert len(layers) == 9
    local = gpd.read_file(directory / "geodata.gpkg", layer="buildings_local")
    projected = gpd.read_file(directory / "geodata.gpkg", layer="buildings_projected")
    assert local.crs.is_engineering
    assert projected.crs.to_epsg() == 32651
    assert all(abs(bound) < 200 for bound in local.total_bounds)
    assert local.geometry.area.tolist() == pytest.approx(projected.geometry.area.tolist(), abs=1e-6)
    assert "SYNTHETIC TEST DATA" in (directory / "preview.svg").read_text(encoding="utf-8")
    assert validate_outputs(directory).valid
    original = (directory / "geodata.gpkg").stat().st_mtime_ns
    assert fetch_geodata(config, osm_file=osm_file, synthetic=True) == directory
    assert (directory / "geodata.gpkg").stat().st_mtime_ns == original
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["synthetic"]
    assert main(["validate", "--directory", str(directory)]) == 0
    (directory / "preview.svg").write_text("modified")
    with pytest.raises(PipelineError, match="modified"):
        validate_outputs(directory)


def test_empty_geopackage_layers(config, tmp_path) -> None:
    path = tmp_path / "empty.osm"
    path.write_text('<osm version="0.6" generator="synthetic"/>')
    directory = fetch_geodata(config, osm_file=path, synthetic=True)
    assert len(pyogrio.list_layers(directory / "geodata.gpkg")) == 9
    assert gpd.read_file(directory / "geodata.gpkg", layer="roads_local").empty


def test_cli_initialization_and_failure(tmp_path) -> None:
    assert main(["init", "--directory", str(tmp_path)]) == 0
    assert (tmp_path / "config" / "iloilo.yaml").is_file()
    assert main(["init", "--directory", str(tmp_path)]) == 1
    assert main(["fetch-geodata", "--config", str(tmp_path / "missing.yaml")]) == 1


def test_failed_write_does_not_publish(config, osm_file, monkeypatch) -> None:
    def fail_write(*args):
        raise OSError("simulated full disk")

    monkeypatch.setattr("iloilo3d.pipeline.write_geopackage", fail_write)
    with pytest.raises(OSError, match="full disk"):
        fetch_geodata(config, osm_file=osm_file, synthetic=True)
    assert not (config.data_dir / "processed/latest.json").exists()
    assert list((config.data_dir / "processed").iterdir()) == []
