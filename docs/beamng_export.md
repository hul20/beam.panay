# BeamNG export and validation

The generated level is named `iloilo3d`. Export starts from selected members of the
installed game's shipped `template.zip`, inspected during implementation. It retains
the MissionGroup foundation, spawn structure, and one set of sky/environment objects;
template terrain, water, vegetation, and duplicated legacy sky branches are replaced by
the explicit test geometry. External Utah cloud references are omitted.

The inspected current template does not contain a top-level `level.json`; the exporter
follows that observed scene layout instead of inventing one. New game versions with a
different template layout must be checked before changing the adapter.

## Generate

```powershell
$jobId = (Get-Content data/processed/latest.json | ConvertFrom-Json).job_id
.\.venv\Scripts\iloilo3d.exe export-beamng `
  --job "data/processed/$jobId" `
  --template-zip "D:/SteamLibrary/steamapps/common/BeamNG.drive/content/levels/template.zip" `
  --output data/generated/iloilo3d-prototype `
  --flat-test-surface --fallback-height-m 6 --fallback-width-m 6
.\.venv\Scripts\iloilo3d.exe validate-level --directory data/generated/iloilo3d-prototype/levels/iloilo3d
```

Use a new output directory for each export. The exporter refuses existing output. It
generates `info.json`, an attributed PNG preview, JSON-lines scene objects, Collada meshes,
shared material definitions, a provenance report, authoring mesh data, and asset statistics.

Roads are buffered mapped centerlines, unioned at intersections and triangulated into
actual static surfaces. The test pad meets road surfaces at Z=0. Static objects explicitly
select `Visible Mesh Final` collision. This provides collision configuration; it is not proof
of valid engine physics. No DecalRoad-only driving surface is assumed. Road width fallbacks
are engineering test values, not Philippine design standards or verified lane widths.

Bridge/tunnel/nonzero-layer roads are skipped until elevation can be handled correctly.
Spawn selection requires clearance from road edges and building masses. Vehicle orientation,
lane alignment, approach clearance, and practical spawning still require in-game checks.
Geometry uses meters, Z up, X east, Y north, identity rotations, and unit scale.

`export-report.json` reports generated mesh/triangle/material counts, mesh file sizes,
scene count, and estimates. Texture counts refer to mesh textures, not the preview or shared
game environment assets. There is no FPS figure. LODs and separate collision proxies are
not implemented; the current simple meshes are used for collisions.

## Manual in-game validation — pending

The CLI does not install into the user's BeamNG folder or launch the game. Keep authoring
files outside the mod. To test, use the game's launcher to locate its **user folder**:

1. Copy the exported `levels` directory into `mods/unpacked/iloilo3d/` inside the active
   BeamNG user folder. The resulting level path must be `mods/unpacked/iloilo3d/levels/iloilo3d/`.
   Never put a mod in the Steam installation's content directory.
2. Open the level in Freeroam. Confirm the title and preview, and inspect the console/log.
3. Confirm the default spawn creates a vehicle safely above a road, without building overlap.
4. Inspect a known width/distance in the editor. Confirm meter scale and orientation against
   the source preview. Expect estimated heights and a flat pad.
5. Drive along a road, across intersections, and onto the surrounding pad. Check wheel contact,
   seam transitions, collision penetration, friction, and vehicle resets.
6. Drive into a test building. Check wall collisions, face orientation, materials, and warnings.
7. Save/reload in World Editor. Confirm scene hierarchy, materials, and spawn persist.
8. Record game version, GPU/CPU, vehicle, logs, any errors, and measured FPS separately.

**Acceptance remains open until these checks pass.** A JSON/mesh validation pass or a
successful Blender import does not establish a playable BeamNG map. Terrain, detailed licensed
reconstruction, local architectural features, LODs, and larger geographic chunks follow this gate.

