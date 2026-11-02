import json
import zipfile

import pytest

from iloilo3d.cli import main
from iloilo3d.errors import PipelineError
from iloilo3d.exporters.beamng import export_prototype, validate_level
from iloilo3d.pipeline import fetch_geodata

pytestmark = pytest.mark.integration


@pytest.fixture
def template(tmp_path):
    """Synthetic template-shaped contract fixture, not a playable level claim."""
    path = tmp_path / "template.zip"
    prefix = "levels/template/"
    records = {
        "main/items.level.json": {"class": "SimGroup", "name": "MissionGroup"},
        "main/MissionGroup/items.level.json": {
            "class": "SimGroup",
            "name": "PlayerDropPoints",
            "__parent": "MissionGroup",
        },
        "main/MissionGroup/PlayerDropPoints/items.level.json": {
            "class": "SpawnSphere",
            "__parent": "PlayerDropPoints",
        },
        "info.json": {"title": "Synthetic template"},
    }
    with zipfile.ZipFile(path, "w") as archive:
        for filename, record in records.items():
            archive.writestr(prefix + filename, json.dumps(record) + "\n")
        sky = [
            {"class": "ScatterSky", "name": "sky", "__parent": "sky_and_sun"},
            {"class": "LevelInfo", "name": "levelinfo", "__parent": "sky_and_sun"},
        ]
        archive.writestr(
            prefix + "main/MissionGroup/level_objects/sky_and_sun/items.level.json",
            "\n".join(json.dumps(obj) for obj in sky),
        )
    return path


def test_export_template_meshes_and_provenance(config, osm_file, template, tmp_path) -> None:
    job = fetch_geodata(config, osm_file=osm_file, synthetic=True)
    output = tmp_path / "mod"
    with pytest.raises(PipelineError, match="flat-test-surface"):
        export_prototype(job, template, output)
    level = export_prototype(job, template, output, flat_test_surface=True)
    assert validate_level(level)["valid"]
    assert main(["validate-level", "--directory", str(level)]) == 0
    report = json.loads((output / "export-report.json").read_text("utf-8"))
    assert report["in_game_validation"] == "pending"
    assert report["performance"]["triangle_count"] > 0
    assert any(asset.get("height_status") == "estimated" for asset in report["assets"])
    assert (output / "authoring" / "meshes.json").is_file()
    with pytest.raises(PipelineError, match="already exists"):
        export_prototype(job, template, output, flat_test_surface=True)
    next(level.rglob("*.dae")).unlink()
    with pytest.raises(PipelineError, match="missing"):
        validate_level(level)


def test_game_scale_changes_entire_export_and_keeps_source_job(
    config, osm_file, template, tmp_path
):
    job = fetch_geodata(config, osm_file=osm_file, synthetic=True)
    source_hash = (job / "dataset.json").read_bytes()
    output = tmp_path / "scaled"
    level = export_prototype(job, template, output, flat_test_surface=True, game_scale=1.1)
    report = json.loads((output / "export-report.json").read_text("utf-8"))
    assert report["game_scale"] == 1.1
    assert report["roads"][0]["game_width_m"] == pytest.approx(report["roads"][0]["width_m"] * 1.1)
    assert json.loads((level / "info.json").read_text("utf-8"))["size"] == [276, 276]
    unscaled = export_prototype(job, template, tmp_path / "unscaled", flat_test_surface=True)
    scaled_meshes = json.loads((output / "authoring/meshes.json").read_text("utf-8"))["meshes"]
    unscaled_meshes = json.loads(
        (unscaled.parents[1] / "authoring/meshes.json").read_text("utf-8")
    )["meshes"]
    assert scaled_meshes[0]["vertices"][0] == pytest.approx(
        [coordinate * 1.1 for coordinate in unscaled_meshes[0]["vertices"][0]]
    )
    assert validate_level(level)["valid"]
    assert (job / "dataset.json").read_bytes() == source_hash
    with pytest.raises(PipelineError, match="Game scale"):
        export_prototype(job, template, tmp_path / "bad", flat_test_surface=True, game_scale=2)


@pytest.mark.parametrize("corruption", ["material", "path", "spawn"])
def test_level_rejects_broken_references(config, osm_file, template, tmp_path, corruption) -> None:
    job = fetch_geodata(config, osm_file=osm_file, synthetic=True)
    level = export_prototype(job, template, tmp_path / "mod", flat_test_surface=True)
    if corruption == "material":
        (level / "art/shapes/main.materials.json").write_text("{}")
    elif corruption == "spawn":
        path = level / "info.json"
        info = json.loads(path.read_text("utf-8"))
        info["defaultSpawnPointName"] = "missing_spawn"
        path.write_text(json.dumps(info))
    else:
        path = level / "main/MissionGroup/generated/items.level.json"
        path.write_text(path.read_text().replace("/levels/iloilo3d/", "C:/game/"))
    with pytest.raises(PipelineError):
        validate_level(level)
