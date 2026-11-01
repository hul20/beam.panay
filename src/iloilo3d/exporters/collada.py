"""Minimal triangulated Collada 1.4.1 for flat-shaded prototype meshes.

This project-owned writer avoids assuming Blender 5 provides Collada. It emits
normals, planar UVs, material bindings, meter units, and a Z-up scene. Its engine
compatibility remains pending until the generated level is driven in BeamNG.
"""

import math
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from iloilo3d.generation.meshes import Mesh
from iloilo3d.storage.files import atomic_bytes

NAMESPACE = "http://www.collada.org/2005/11/COLLADASchema"


def write_collada(mesh: Mesh, path: Path, material: str) -> None:
    mesh.validate()
    root = Element("COLLADA", xmlns=NAMESPACE, version="1.4.1")
    asset = SubElement(root, "asset")
    SubElement(asset, "created").text = "2026-01-01T00:00:00Z"
    SubElement(asset, "modified").text = "2026-01-01T00:00:00Z"
    SubElement(asset, "unit", name="meter", meter="1")
    SubElement(asset, "up_axis").text = "Z_UP"
    effects = SubElement(root, "library_effects")
    effect = SubElement(effects, "effect", id="surface-effect")
    profile = SubElement(effect, "profile_COMMON")
    technique = SubElement(profile, "technique", sid="common")
    lambert = SubElement(technique, "lambert")
    diffuse = SubElement(lambert, "diffuse")
    SubElement(diffuse, "color").text = "0.6 0.6 0.6 1"
    materials = SubElement(root, "library_materials")
    mat = SubElement(materials, "material", id=material, name=material)
    SubElement(mat, "instance_effect", url="#surface-effect")
    geometry = SubElement(
        SubElement(root, "library_geometries"), "geometry", id="mesh", name="mesh"
    )
    mesh_xml = SubElement(geometry, "mesh")
    # Duplicate vertices per face for flat normals and simple aligned UV indexing.
    positions: list[float] = []
    normals: list[float] = []
    uvs: list[float] = []
    for face in mesh.triangles:
        a, b, c = (mesh.vertices[index] for index in face)
        ab, ac = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
        n = [
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        ]
        magnitude = math.sqrt(sum(value * value for value in n))
        n = [value / magnitude for value in n]
        drop = max(range(3), key=lambda i: abs(n[i]))
        axes = [i for i in range(3) if i != drop]
        for point in (a, b, c):
            positions.extend(point)
            normals.extend(n)
            uvs.extend([point[axes[0]] / 4, point[axes[1]] / 4])
    for name, values, labels in (
        ("positions", positions, "XYZ"),
        ("normals", normals, "XYZ"),
        ("uv", uvs, "ST"),
    ):
        source = SubElement(mesh_xml, "source", id=name)
        array = SubElement(source, "float_array", id=f"{name}-array", count=str(len(values)))
        array.text = " ".join(f"{value:.9g}" for value in values)
        accessor = SubElement(
            SubElement(source, "technique_common"),
            "accessor",
            source=f"#{name}-array",
            count=str(len(values) // len(labels)),
            stride=str(len(labels)),
        )
        for label in labels:
            SubElement(accessor, "param", name=label, type="float")
    vertices = SubElement(mesh_xml, "vertices", id="vertices")
    SubElement(vertices, "input", semantic="POSITION", source="#positions")
    triangles = SubElement(
        mesh_xml, "triangles", material="surface", count=str(len(mesh.triangles))
    )
    SubElement(triangles, "input", semantic="VERTEX", source="#vertices", offset="0")
    SubElement(triangles, "input", semantic="NORMAL", source="#normals", offset="1")
    SubElement(triangles, "input", semantic="TEXCOORD", source="#uv", offset="2", set="0")
    SubElement(triangles, "p").text = " ".join(
        str(i) for i in range(len(positions) // 3) for _ in range(3)
    )
    scene = SubElement(SubElement(root, "library_visual_scenes"), "visual_scene", id="Scene")
    node = SubElement(scene, "node", id="prototype", name="prototype", type="NODE")
    instance = SubElement(node, "instance_geometry", url="#mesh")
    common = SubElement(SubElement(instance, "bind_material"), "technique_common")
    binding = SubElement(common, "instance_material", symbol="surface", target=f"#{material}")
    SubElement(
        binding, "bind_vertex_input", semantic="UVMap", input_semantic="TEXCOORD", input_set="0"
    )
    SubElement(SubElement(root, "scene"), "instance_visual_scene", url="#Scene")
    atomic_bytes(path, tostring(root, encoding="utf-8", xml_declaration=True))
