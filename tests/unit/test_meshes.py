from collections import Counter
from xml.etree import ElementTree as ET

import pytest
from shapely import set_precision
from shapely.geometry import Polygon, box

from iloilo3d.errors import PipelineError
from iloilo3d.exporters.beamng import read_scene, write_scene
from iloilo3d.exporters.collada import NAMESPACE, write_collada
from iloilo3d.generation.meshes import extrude


@pytest.mark.parametrize(
    "polygon",
    [
        box(0, 0, 10, 20),
        Polygon([(0, 0), (8, 0), (8, 4), (4, 4), (4, 8), (0, 8)]),
        Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], holes=[[(2, 2), (2, 8), (8, 8), (8, 2)]]),
    ],
)
def test_extrusion_volume_winding_and_manifold(polygon) -> None:
    mesh = extrude(polygon, 0, 6)
    mesh.validate()
    signed_volume = 0
    edge_counts = Counter()
    for face in mesh.triangles:
        a, b, c = (mesh.vertices[i] for i in face)
        cross = (b[1] * c[2] - b[2] * c[1], b[2] * c[0] - b[0] * c[2], b[0] * c[1] - b[1] * c[0])
        signed_volume += sum(a[i] * cross[i] for i in range(3)) / 6
        for i, j in zip(face, (face[1], face[2], face[0]), strict=True):
            edge_counts[tuple(sorted((i, j)))] += 1
    assert signed_volume == pytest.approx(polygon.area * 6)
    assert set(edge_counts.values()) == {2}


def test_dae_units_uvs_normals_and_material_binding(tmp_path) -> None:
    path = tmp_path / "building.dae"
    mesh = extrude(box(0, 0, 10, 10), 0, 6)
    write_collada(mesh, path, "iloilo_wall")
    root = ET.parse(path).getroot()
    ns = {"c": NAMESPACE}
    assert root.find("c:asset/c:up_axis", ns).text == "Z_UP"
    assert root.find("c:asset/c:unit", ns).get("meter") == "1"
    triangles = root.find(".//c:triangles", ns)
    assert int(triangles.get("count")) == len(mesh.triangles)
    assert len(triangles.find("c:p", ns).text.split()) == len(mesh.triangles) * 9
    binding = root.find(".//c:instance_material", ns)
    assert binding.get("target") == "#iloilo_wall"
    assert {source.get("id") for source in root.findall(".//c:source", ns)} == {
        "positions",
        "normals",
        "uv",
    }


def test_scene_json_lines(tmp_path) -> None:
    records = [{"class": "SimGroup", "name": "MissionGroup"}, {"class": "SpawnSphere"}]
    path = tmp_path / "items.level.json"
    write_scene(path, records)
    assert len(path.read_text().splitlines()) == 2
    assert read_scene(path.read_text()) == records
    with pytest.raises(PipelineError):
        read_scene('[{"class":"SimGroup"}]')


def test_clipping_sliver_precision() -> None:
    polygon = Polygon(
        [
            (60.9918564384886, 125.08947355373327),
            (60.99185643848859, 125.08947355373327),
            (60.973267053415974, 125.07909402387278),
            (60, 124),
            (62, 124),
        ]
    )
    with pytest.raises(PipelineError, match="Degenerate"):
        extrude(polygon, -0.5, 0)
    extrude(set_precision(polygon, 0.001), -0.5, 0).validate()


def test_repeated_ring_vertices() -> None:
    polygon = Polygon([(0, 0), (10, 0), (10, 0), (10, 10), (0, 10)])
    extrude(polygon, 0, 6).validate()
