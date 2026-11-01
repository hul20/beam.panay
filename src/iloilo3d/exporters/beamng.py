"""Template-derived flat test level; real terrain reconstruction is a later stage."""

import json
import logging
import math
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import asdict
from pathlib import Path

from defusedxml import ElementTree as SafeET
from shapely import set_precision, union_all
from shapely.affinity import translate
from shapely.geometry import Polygon, box, shape

from iloilo3d.errors import PipelineError
from iloilo3d.exporters.collada import NAMESPACE, write_collada
from iloilo3d.generation.meshes import Mesh, extrude
from iloilo3d.geospatial.coordinates import CoordinateFrame
from iloilo3d.geospatial.preview import write_png_preview
from iloilo3d.models import GeographicDataset
from iloilo3d.pipeline import validate_outputs
from iloilo3d.storage.files import atomic_bytes, sha256_file, write_json

LOG = logging.getLogger(__name__)
IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1]


def write_scene(path: Path, objects: list[dict]) -> None:
    """BeamNG scene serialization is JSON objects separated by newlines."""
    content = "".join(
        json.dumps(obj, ensure_ascii=False, allow_nan=False) + "\n" for obj in objects
    )
    atomic_bytes(path, content.encode())


def read_scene(content: str) -> list[dict]:
    result = []
    for line in content.splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict) or not isinstance(obj.get("class"), str):
            raise PipelineError("Scene must contain one object with a class per line")
        result.append(obj)
    return result


def polygons(geometry) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    return [part for part in geometry.geoms if part.geom_type == "Polygon" and part.area > 1e-6]


def export_prototype(
    job: Path,
    template_zip: Path,
    output: Path,
    *,
    flat_test_surface: bool = False,
    fallback_height_m: float = 6,
    fallback_width_m: float = 6,
) -> Path:
    """Write a new unpacked mod under output/levels/iloilo3d; never install into the game."""
    if not flat_test_surface:
        raise PipelineError("No measured terrain available; explicitly select --flat-test-surface")
    if not 1 <= fallback_height_m <= 100 or not 2 <= fallback_width_m <= 30:
        raise PipelineError("Prototype fallback height must be 1–100 m and width 2–30 m")
    if output.exists():
        raise PipelineError("Export directory already exists; select a new output directory")
    if not validate_outputs(job).valid:
        raise PipelineError("Geographic input failed validation")
    dataset = GeographicDataset.model_validate_json((job / "dataset.json").read_text("utf-8"))
    frame = CoordinateFrame(dataset.origin, dataset.projected_crs)
    b = dataset.bounds
    boundary = set_precision(frame.local_geometry(box(b.west, b.south, b.east, b.north)), 0.001)
    notes = [
        "Flat engineering test surface at local Z=0; NOT measured Iloilo terrain.",
        "All flat roofs and untagged heights/road widths are procedural estimates.",
        "Collision uses low-poly visible meshes; actual wheel contact is unverified.",
        "No textures, detailed facades, LODs, road markings, AI lanes, or photogrammetry.",
    ]
    roads = []
    road_records = []
    for road in dataset.roads:
        if not road.drivable_candidate:
            continue
        if (
            road.tags.get("bridge", "no") != "no"
            or road.tags.get("tunnel", "no") != "no"
            or road.tags.get("layer", "0") != "0"
        ):
            notes.append(f"Skipped elevated/below-grade road {road.id}; needs elevation data")
            continue
        centerline = frame.local_geometry(shape(road.centerline)).intersection(boundary)
        width = road.width_m or fallback_width_m
        surface = centerline.buffer(width / 2, cap_style="flat", join_style="round").intersection(
            boundary
        )
        if not surface.is_empty:
            roads.append(surface)
            road_records.append(
                {
                    "source_id": road.id,
                    "width_m": width,
                    "width_status": "mapped" if road.width_m else "estimated",
                }
            )
    if not roads or not dataset.buildings:
        raise PipelineError("Prototype requires at least one mapped building and drivable road")
    road_surface = set_precision(union_all(roads), 0.001)
    notes.append(
        "Generated test pad and road surfaces snap to a 1 mm grid to remove clipping slivers."
    )
    building_shapes = [
        frame.local_geometry(shape(building.footprint)) for building in dataset.buildings
    ]
    # At least 3 m of clearance from road edges and building walls for a starting vehicle.
    safe_spawn = road_surface.buffer(-2.5).difference(union_all(building_shapes).buffer(3))
    if safe_spawn.is_empty:
        raise PipelineError(
            "No safe spawn area with vehicle clearance; inspect road widths/buildings"
        )
    spawn = max(polygons(safe_spawn), key=lambda poly: poly.area).representative_point()
    # Read only observed template members. Never extract arbitrary archive paths.
    required = {
        "root": "levels/template/main/items.level.json",
        "groups": "levels/template/main/MissionGroup/items.level.json",
        "spawn": "levels/template/main/MissionGroup/PlayerDropPoints/items.level.json",
        "sky": "levels/template/main/MissionGroup/level_objects/sky_and_sun/items.level.json",
        "info": "levels/template/info.json",
    }
    with zipfile.ZipFile(template_zip) as archive:
        if not set(required.values()).issubset(archive.namelist()):
            raise PipelineError("Unsupported template layout; supply the shipped template.zip")
        template = {key: archive.read(member).decode("utf-8") for key, member in required.items()}
    root = read_scene(template["root"])
    if len(root) != 1 or root[0].get("name") != "MissionGroup":
        raise PipelineError("Unexpected template MissionGroup")
    spawns = [obj for obj in read_scene(template["spawn"]) if obj["class"] == "SpawnSphere"]
    sky = [
        obj
        for obj in read_scene(template["sky"])
        if obj["class"] in {"ScatterSky", "LevelInfo", "TimeOfDay"}
    ]
    if not spawns or not {"ScatterSky", "LevelInfo"}.issubset({obj["class"] for obj in sky}):
        raise PipelineError("Template lacks spawn or daytime environment")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".iloilo3d-export-", dir=output.parent))
    try:
        level = staging / "levels" / "iloilo3d"
        mission = level / "main" / "MissionGroup"
        write_scene(level / "main" / "items.level.json", root)
        groups = [
            obj for obj in read_scene(template["groups"]) if obj.get("name") == "PlayerDropPoints"
        ]
        groups += [
            {"name": name, "class": "SimGroup", "__parent": "MissionGroup"}
            for name in ("sky_and_sun", "generated")
        ]
        write_scene(mission / "items.level.json", groups)
        for obj in sky:
            if obj["class"] == "TimeOfDay":
                obj.update(time=0.15, startTime=0.15, play=False)
        write_scene(mission / "sky_and_sun" / "items.level.json", sky)
        spawn_object = spawns[0]
        spawn_object.update(
            name="spawn_default",
            position=[spawn.x, spawn.y, 1.5],
            rotationMatrix=IDENTITY,
            autoplaceOnSpawn="0",
        )
        write_scene(mission / "PlayerDropPoints" / "items.level.json", [spawn_object])
        material_colors = {
            "iloilo_wall": [0.69, 0.65, 0.55, 1],
            "iloilo_road": [0.25, 0.26, 0.27, 1],
            "iloilo_ground": [0.43, 0.45, 0.36, 1],
        }
        materials = {
            name: {
                "name": name,
                "class": "Material",
                "mapTo": name,
                "Stages": [{"diffuseColor": color}],
                "version": 1.5,
                "groundType": "ASPHALT" if name == "iloilo_road" else "CONCRETE",
            }
            for name, color in material_colors.items()
        }
        write_json(level / "art" / "shapes" / "main.materials.json", materials)
        scene: list[dict] = []
        assets: list[dict] = []
        intermediate: list[dict] = []

        def add_mesh(
            name: str, mesh: Mesh, material: str, position: list[float], source: dict
        ) -> None:
            relative = f"art/shapes/{name}.dae"
            write_collada(mesh, level / relative, material)
            scene.append(
                {
                    "name": name,
                    "class": "TSStatic",
                    "__parent": "generated",
                    "persistentId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"iloilo3d/{name}")),
                    "position": position,
                    "rotationMatrix": IDENTITY,
                    "scale": [1, 1, 1],
                    "shapeName": f"/levels/iloilo3d/{relative}",
                    "collisionType": "Visible Mesh Final",
                    "decalType": "Visible Mesh Final",
                }
            )
            assets.append(
                {
                    "id": name,
                    "path": relative,
                    "position": position,
                    "triangles": len(mesh.triangles),
                    "material": material,
                    **source,
                }
            )
            intermediate.append(
                {"name": name, "material": material, "position": position, **asdict(mesh)}
            )

        for kind, geometry, material in (
            ("ground", boundary.difference(road_surface), "iloilo_ground"),
            ("road", road_surface, "iloilo_road"),
        ):
            for index, poly in enumerate(polygons(geometry)):
                add_mesh(
                    f"{kind}_{index}",
                    extrude(poly, -0.5, 0),
                    material,
                    [0, 0, 0],
                    {"surface_elevation_status": "estimated_test_surface"},
                )
        for building, geometry in zip(dataset.buildings, building_shapes, strict=True):
            height = building.height_m or (
                building.floors * 3 if building.floors else fallback_height_m
            )
            for index, poly in enumerate(polygons(geometry)):
                center = poly.centroid
                local = translate(poly, xoff=-center.x, yoff=-center.y)
                name = building.id.replace("/", "_") + f"_{index}"
                add_mesh(
                    name,
                    extrude(local, 0, height),
                    "iloilo_wall",
                    [center.x, center.y, 0],
                    {
                        "source_id": building.id,
                        "reconstruction_method": "C",
                        "height_m": height,
                        "height_status": "mapped" if building.height_m else "estimated",
                        "roof_status": "estimated_flat",
                        "base_elevation_status": "estimated_test_surface",
                    },
                )
        write_scene(mission / "generated" / "items.level.json", scene)
        info = json.loads(template["info"])
        info.update(
            title="Iloilo3D — geographic test prototype",
            description="Real OSM footprints; estimated building masses on a flat test pad.",
            authors="Iloilo3D; OpenStreetMap contributors; BeamNG template",
            isAuxiliary=False,
            previews=["preview.png"],
            size=[250, 250],
            biome="Iloilo City, Philippines",
            roads="Flat test surfaces; widths may be estimated",
            suitablefor="Prototype inspection",
            features="Mapped footprints and road centerlines",
            defaultSpawnPointName="spawn_default",
            supportsTraffic=False,
            supportsTimeOfDay=True,
        )
        xmin, ymin, xmax, ymax = boundary.bounds
        if dataset.source.synthetic:
            info["title"] = "Iloilo3D — SYNTHETIC test fixture"
            info["description"] = "Synthetic geometry for tests; not real Iloilo geography."
        info["size"] = [round(xmax - xmin), round(ymax - ymin)]
        write_json(level / "info.json", info)
        write_png_preview(dataset, level / "preview.png")
        write_json(staging / "authoring" / "meshes.json", {"meshes": intermediate})
        report = {
            "status": "exported_pending_game_validation",
            "source_job": job.name,
            "source": dataset.source.model_dump(mode="json"),
            "origin": dataset.origin.model_dump(),
            "projected_crs": dataset.projected_crs,
            "template_sha256": sha256_file(template_zip),
            "template_members": required,
            "flat_test_surface": True,
            "notes": notes,
            "assets": assets,
            "roads": road_records,
            "performance": {
                "mesh_count": len(assets),
                "triangle_count": sum(a["triangles"] for a in assets),
                "material_count": 3,
                "texture_count": 0,
                "estimated_texture_bytes": 0,
                "scene_object_count": len(scene) + len(root) + len(groups) + len(sky) + 1,
                "mesh_bytes": sum(p.stat().st_size for p in level.rglob("*.dae")),
                "fps": None,
            },
            "in_game_validation": "pending",
        }
        write_json(staging / "export-report.json", report)
        write_json(level / "provenance.json", report)
        validate_level(level)
        staging.rename(output)
        LOG.info("Exported %d meshes; in-game validation pending: %s", len(assets), output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return output / "levels" / "iloilo3d"


def validate_level(level: Path) -> dict:
    """Validate generated references and structure, never simulate game loading."""
    info = json.loads((level / "info.json").read_text("utf-8"))
    for preview in info.get("previews", []):
        if Path(preview).name != preview or not (level / preview).is_file():
            raise PipelineError("Missing or unsafe preview path")
    materials = json.loads((level / "art" / "shapes" / "main.materials.json").read_text("utf-8"))
    mapped_materials = {value["mapTo"] for value in materials.values()}
    objects = [
        obj
        for path in level.rglob("items.level.json")
        for obj in read_scene(path.read_text("utf-8"))
    ]
    names = [obj["name"] for obj in objects if "name" in obj]
    if len(names) != len(set(names)):
        raise PipelineError("Duplicate scene names")
    groups = {obj["name"] for obj in objects if obj["class"] == "SimGroup"}
    if "MissionGroup" not in groups:
        raise PipelineError("Missing MissionGroup")
    spawns = {obj.get("name") for obj in objects if obj["class"] == "SpawnSphere"}
    if info.get("defaultSpawnPointName") not in spawns:
        raise PipelineError("Default spawn does not resolve")
    for obj in objects:
        if "__parent" in obj and obj["__parent"] not in groups:
            raise PipelineError("Scene parent does not resolve")
        if obj["class"] != "TSStatic":
            continue
        position = obj.get("position")
        if (
            not isinstance(position, list)
            or len(position) != 3
            or not all(
                isinstance(value, (int, float)) and math.isfinite(value) for value in position
            )
        ):
            raise PipelineError("Invalid static mesh position")
        mesh_path = obj.get("shapeName", "")
        prefix = "/levels/iloilo3d/"
        if not mesh_path.startswith(prefix) or ".." in mesh_path or "\\" in mesh_path:
            raise PipelineError("Mesh path is not portable")
        if not (level / mesh_path.removeprefix(prefix)).is_file():
            raise PipelineError("Referenced mesh is missing")
        mesh = SafeET.parse(level / mesh_path.removeprefix(prefix))
        ns = {"c": NAMESPACE}
        axis = mesh.find("c:asset/c:up_axis", ns)
        unit = mesh.find("c:asset/c:unit", ns)
        if axis is None or axis.text != "Z_UP" or unit is None or unit.get("meter") != "1":
            raise PipelineError("Mesh must use meters and Z-up")
        bindings = mesh.findall(".//c:instance_material", ns)
        if not bindings or any(
            binding.get("target", "").lstrip("#") not in mapped_materials for binding in bindings
        ):
            raise PipelineError("Mesh material does not resolve")
        if obj.get("collisionType") != "Visible Mesh Final":
            raise PipelineError("Prototype static mesh has no configured collision")
    return {"valid": True, "scene_objects": len(objects), "in_game_validation": "pending"}
