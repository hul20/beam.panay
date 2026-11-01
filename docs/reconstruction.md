# Reconstruction status

The current exporter performs only **Level C footprint extrusion**:

1. Transform the actual footprint to local meters.
2. Preserve irregular outlines and courtyard holes.
3. Use a parseable mapped height if present; otherwise use mapped floor count × 3 m,
   or a configurable fallback of 6 m. Both fallback paths are explicitly estimated.
4. Triangulate roofs/floors with constrained Delaunay triangulation and generate walls.
5. Check closed, consistently oriented manifold edges and nondegenerate triangles.
6. Export position-centered building assets and geographic source references.

Flat roof configuration, base elevation, and fallback appearance are estimates. No facade
or architectural likeness has been established. Road and test pad surfaces are snapped to a
1 mm grid to eliminate floating-point clipping slivers, without changing saved source geometry.
Shared low-detail materials require no external texture images.

There is no Level A or B result yet: no usable licensed overlapping image set has been
provided or acquired. Camera reconstruction, COLMAP, depth, segmentation, calibrated heights,
texture projection, and privacy filtering remain future work. Detailed geometry must be
grounded in licensed observations instead of silently replacing missing evidence with guesses.

## Blender authoring

The exporter saves `authoring/meshes.json` separately from the playable level folder.
The Blender importer creates real editable meshes, metric units, materials, and planar UVs:

```powershell
& "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" `
  --background --python blender/import_prototype.py -- `
  data/generated/iloilo3d-prototype/authoring/meshes.json `
  data/generated/iloilo3d-prototype/authoring/iloilo3d.blend
```

Blender 5.2.0 LTS was checked and this script was executed successfully. The importer refuses
to overwrite an existing `.blend` file. The project writes simple Collada 1.4.1 itself, so it
does not call the removed native Blender Collada operator or require an unverified extension.
The writer's XML, material bindings, UVs, normals, units, and winding are tested; BeamNG's
handling of those files remains pending in-game validation. It does not yet export Blender
edits back to DAE, provide a generic Blender exporter, or generate LODs.

