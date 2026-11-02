# Jaro Plaza milestone — 2026-11-02

The current target is Jaro Plaza and its immediate surrounding streets, using a
400 m square centered at longitude 122.5573278, latitude 10.7243667. This encompasses
the mapped plaza, cathedral, belfry, and old municipal hall. The origin is a geographic
selection anchor, not a surveyed control point. See [configuration](../config/jaro.yaml).

## Implemented

- Downloaded **119 building/roof footprints, 283 road/path segments, and 22 public-space polygons**.
- Preserved the mapped Jaro Plaza boundary (OSM way 142868946), internal paths, gardens,
  and grass polygons. Polygon surfaces use shared estimated colors and flat elevation.
- Exported mapped landmark footprints with names and source identifiers. The Jaro Belfry
  has an OSM height tag of **29 m**, which is used as mapped information, not an independently
  verified measurement. The cathedral and most other heights remain estimates.
- Corrected `building=roof` handling: those features now become overhead slabs, not solid
  ground-to-roof blocks. Unknown roof thickness defaults to an explicitly estimated 0.25 m.
  Mapped `min_height` takes precedence. Roof support column locations remain unknown and
  are not generated. Overhead clearance below 3 m is treated conservatively as an obstruction.
- Generated road/path buffers are trimmed around ground-obstructing footprints with a
  0.25 m prototype clearance. Source footprints and centerlines are not moved or cut.
  Per-segment corrections and any unresolved centerline conflicts are reported.
- Public surfaces are partitioned so road, path, park, and pitch polygons do not overlap.
  The nine-layer GeoPackage includes public spaces in all three coordinate frames.
- Untagged road widths now use mapped lane counts (3 m per lane, minimum 4 m) or
  class-based minimum estimates (primary 8 m, secondary 7.5 m, tertiary 6.5 m).
  Explicit OSM widths take priority. The export report records each width's basis.
- [Jaro corrections](../config/jaro_overrides.yaml) sets visually estimated heights for the
  cathedral (15 m) and pavilion (5.5 m). Persistent IDs, reasons, evidence type, and a
  configuration checksum appear in the report. The original OSM dataset stays unchanged.
- The mapped belfry footprint and 29 m OSM height now generate three estimated tiers in an
  adobe-colored material. The pavilion generates a platform, posts, and overhead roof.
  Their architectural proportions and post positions have not been surveyed.

Files changed include [OSM acquisition](../src/iloilo3d/providers/osm.py),
[building profiles](../src/iloilo3d/generation/buildings.py),
[surface generation](../src/iloilo3d/generation/roads.py),
[mesh repair](../src/iloilo3d/generation/meshes.py),
[export](../src/iloilo3d/exporters/beamng.py),
[models](../src/iloilo3d/models/__init__.py), and geographic previews/storage/tests.

## Verified results

- **54 offline tests pass**; Ruff lint and formatting checks pass.
- Live OSM acquisition and geographic output succeeded, following an initial HTTP 502.
- Latest export: **272 meshes, 27,340 triangles, 8 materials, 280 scene objects**.
- Generated road surfaces intersect ground-obstructing building polygons by **0 m²**.
- **20 segments** had surface widths trimmed; **0 unresolved centerline conflicts** remain
  after correctly distinguishing overhead roofs from enclosed buildings.
- Eight initially reported footpath conflicts were under three features explicitly tagged
  `building=roof`, `layer=1`. Rendering them as solid masses was the cause of those blockages.
- The level's scene references, spawn, material bindings, units, and collision configuration
  pass automated validation. This does not establish in-game driving performance.

The more detailed plaza surface exposed polygons whose holes touch the outer ring at a point.
Such polygons cannot extrude directly into a manifold collider. A regression test covers
this: affected generated surfaces use a recorded 2 mm inward offset. This is only a test
surface repair, not a modification of source footprints; the small seams need driving checks.

## Outputs and installation

- [Generated level](../data/generated/jaro-plaza-v4/levels/iloilo3d/)
- [Preview](../data/generated/jaro-plaza-v4/levels/iloilo3d/preview.png)
- [Export report](../data/generated/jaro-plaza-v4/export-report.json)
- [Blender scene](../data/generated/jaro-plaza-v4/authoring/jaro-plaza.blend)
- [Geographic job](../data/jaro/processed/99d27ed9ec10a6183511/)

The level ID remains `iloilo3d`; its Freeroam title is **Iloilo3D — Jaro Plaza**.
To test, close BeamNG, back up the old installed `iloilo3d` level folder outside the mods
directory, and replace it with the generated level folder above. Do not simply merge the
folders: old scene files could otherwise remain and load alongside the Jaro scene. Keep only
one enabled mod providing `levels/iloilo3d`. The exporter does not modify the installed mod.

## Reproduce

From the repository root, using the existing environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m iloilo3d fetch-geodata --config config/jaro.yaml
$jobId = (Get-Content data/jaro/processed/latest.json | ConvertFrom-Json).job_id
.\.venv\Scripts\python.exe -m iloilo3d export-beamng `
  --job "data/jaro/processed/$jobId" `
  --template-zip "D:/SteamLibrary/steamapps/common/BeamNG.drive/content/levels/template.zip" `
  --output data/generated/jaro-plaza-next --flat-test-surface `
  --overrides config/jaro_overrides.yaml --game-scale 1.1
.\.venv\Scripts\python.exe -m iloilo3d validate-level --directory data/generated/jaro-plaza-next/levels/iloilo3d
.\.venv\Scripts\python.exe -m pytest
```

Use a new output directory each time. To create the editable scene:

```powershell
& "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" `
  --background --python blender/import_prototype.py -- `
  data/generated/jaro-plaza-next/authoring/meshes.json `
  data/generated/jaro-plaza-next/authoring/jaro-plaza.blend
```

## What this is not yet

This is a geographically placed **Jaro base**, not a finished recognizable architectural
reconstruction. Ground and paths remain flat; roofs, facades, park surface materials,
steps, trees, statues, fences, columns, and furniture are not surveyed or reconstructed.
The pavilion and belfry now have estimated massing, but no photo-based reconstruction or
Google imagery was used. The cathedral height is a visual estimate and its roof remains flat.
Trimming a width prevents a mesh intersection but does not prove a street is wide enough
for every vehicle. Generated assets and data are ignored by Git.
The v4 export uniformly enlarges meshes, positions, widths, heights, and spawn by 10%.
This is a labeled game-scale adjustment and therefore does not preserve exact 1:1 meters;
the OSM dataset and local coordinate frame remain unchanged. The [image intake](./imagery.md)
is ready for licensed photos but none have been supplied for this Jaro export.

The user reported that the Jaro map looks good overall but some streets and buildings
appear undersized. That is useful visual feedback, not a complete physics test or evidence
about this new export. **Next step:** test the revised street widths and landmarks in-game,
then use licensed reference photographs and measurements for the belfry, pavilion, cathedral,
plaza steps, and furnishings. Preserve horizontal source geometry while refining details.

Location references: [Jaro Plaza](https://en.wikipedia.org/wiki/Jaro_Plaza),
[mapped plaza boundary](https://www.openstreetmap.org/way/142868946).
Export geometry comes from saved OSM XML; the reference page was used only to select the area.
