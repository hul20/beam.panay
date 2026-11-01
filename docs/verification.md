# Initial milestone verification

Verified on **2026-11-02, Asia/Taipei**, in Windows PowerShell. This is an execution
record, not a claim that every feature in the project specification is complete.

## Implemented

- Installable Python package and CLI, strict Pydantic/YAML configuration, JSON progress logs.
- Bounded/cacheable Overpass XML acquisition and offline OSM import with source provenance.
- OSMnx building multipolygons, courtyard preservation, shared-node road segmentation.
- WGS84 / UTM 51N / local-coordinate transforms and six GeoPackage layers.
- Atomic processed jobs, checksums, geographic validation, attributed SVG preview.
- Template-derived flat test level with procedural Level C masses, physical road meshes,
  collision settings, materials, spawn, daytime environment, and geographic PNG preview.
- Editable mesh intermediate and a successfully executed Blender authoring importer.

Key source modules: [configuration](../src/iloilo3d/config.py), [OSM provider](../src/iloilo3d/providers/osm.py),
[coordinates](../src/iloilo3d/geospatial/coordinates.py), [pipeline](../src/iloilo3d/pipeline.py),
[meshes](../src/iloilo3d/generation/meshes.py), [BeamNG export](../src/iloilo3d/exporters/beamng.py),
[Blender importer](../blender/import_prototype.py), and [tests](../tests/).

## Verification results

| Check | Actual result |
|---|---|
| Editable install, Python 3.14.3 | Succeeded |
| Pytest offline suite | 40 passed |
| Ruff lint | Passed |
| Ruff formatting | Passed |
| `pip check` | No broken requirements |
| Wheel build | `iloilo3d-0.1.0-py3-none-any.whl` built successfully |
| Live OSM acquisition | 118 buildings, 41 road segments |
| Geographic output verification | Checksums and geometry passed |
| Road graph diagnostics | 3 disconnected drivable components, 6 intersection nodes |
| Mapped building heights | All 118 unknown/unparseable |
| Real-data export | 132 meshes, 2,616 triangles, 3 mesh materials |
| Generated scene | 140 objects; references, spawn, mesh units and materials passed |
| Mesh files | 841,263 bytes total, excluding other assets |
| Blender 5.2.0 LTS | Imported 132 meshes and saved editable scene successfully |
| BeamNG load, drive, friction, collisions, FPS | **Not tested** |

The first sandboxed live request returned HTTP 502 and published no data. A subsequent
approved request succeeded. Routine tests use synthetic OSM XML and mocked HTTP responses.
They do not contact Overpass or require installed BeamNG assets.

The first real-data export exposed nearly coincident vertices at clipped road boundaries.
A regression test now reproduces the failure; snapping only generated test surfaces to a
1 mm grid fixes it. Saved WGS84 and projected source features retain their original precision.

## Local outputs

Generated outputs are deliberately ignored by Git:

- Geographic job: [data/processed/cbfd0d422daa03e847a2](../data/processed/cbfd0d422daa03e847a2/)
- GIS layers: [geodata.gpkg](../data/processed/cbfd0d422daa03e847a2/geodata.gpkg)
- Geographic preview: [preview.svg](../data/processed/cbfd0d422daa03e847a2/preview.svg)
- Test level: [levels/iloilo3d](../data/generated/iloilo3d-prototype/levels/iloilo3d/)
- Export statistics/provenance: [export-report.json](../data/generated/iloilo3d-prototype/export-report.json)
- Editable scene: [iloilo3d.blend](../data/generated/iloilo3d-prototype/authoring/iloilo3d.blend)

These links refer to this machine's initial run. New source snapshots or dependency versions
produce different job IDs. The [README](../README.md) shows how to read the latest job ID.

## Limitations and next step

Phase 0 and the initial Phase 1 bounding-box workflow meet their verified local acceptance
checks. Phase 2 is an **exported prototype awaiting in-game acceptance**. Flat ground, road
width fallbacks, massing heights, and roof shapes are estimates. No usable licensed image
set has been supplied; no photogrammetry or detailed real building reconstruction is claimed.

The next concrete task is to load the generated mod in BeamNG and execute the
[driving validation procedure](beamng_export.md#manual-in-game-validation--pending).
Fix any asset-import, material, spawn, or collision issues before adding terrain and detailed
reconstruction. The installed game was found and its template inspected, but it was not
launched and no mod files were written into the game installation or user folder.

Future stages still include licensed image ingestion and Google reference-only integration,
DEM terrain, manual corrections, district styles, UV/texture reconstruction, LODs, chunking,
and performance measurement. No placeholder CLI commands claim these features work.

