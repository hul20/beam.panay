"""Run with Blender --background --python this_script -- meshes.json output.blend.

Creates an editable authoring scene from the exact mesh intermediate used for DAE.
No Collada operator, extension, or third-party Python dependency is required.
"""

import json
import sys
from pathlib import Path

import bpy


def main() -> None:
    source, output = sys.argv[sys.argv.index("--") + 1 :]
    scene_data = json.loads(Path(source).read_text(encoding="utf-8"))
    if Path(output).exists():
        raise RuntimeError("Refusing to overwrite an existing Blender project")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1
    for record in scene_data["meshes"]:
        mesh = bpy.data.meshes.new(record["name"])
        mesh.from_pydata(record["vertices"], [], record["triangles"])
        if mesh.validate():
            raise RuntimeError(f"Blender repaired invalid input geometry: {record['name']}")
        mesh.update()
        obj = bpy.data.objects.new(record["name"], mesh)
        bpy.context.collection.objects.link(obj)
        obj.location = record["position"]
        material = bpy.data.materials.get(record["material"]) or bpy.data.materials.new(
            record["material"]
        )
        obj.data.materials.append(material)
        uv = mesh.uv_layers.new(name="UVMap")
        for poly in mesh.polygons:
            axis = max(range(3), key=lambda i: abs(poly.normal[i]))
            axes = [i for i in range(3) if i != axis]
            for loop in poly.loop_indices:
                point = mesh.vertices[mesh.loops[loop].vertex_index].co
                uv.data[loop].uv = (point[axes[0]] / 4, point[axes[1]] / 4)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(output).resolve()))
    print(f"ILOILO3D: saved {len(scene_data['meshes'])} meshes; Blender {bpy.app.version_string}")


if __name__ == "__main__":
    main()
