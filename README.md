# Iloilo3D

An incremental, geographically referenced reconstruction pipeline for Iloilo City and
BeamNG.drive. The initial implementation downloads actual OSM footprints and road networks,
writes inspectable GIS outputs, and exports an **experimental flat-surface test level** from
the installed game's Starter Level template.

**Current status:** Phase 0 and the initial Phase 1 extraction workflow are implemented and
tested. Phase 2 has generated assets and a template-derived level, but **in-game validation
is pending**. Building masses are Level C estimates, not photographed digital twins.

The first live run retrieved **118 building footprints and 41 road segments** in the configured
roughly 250 m area. All 118 buildings lacked a parseable mapped height. Extraction preserves
that uncertainty; the test exporter records its fallback heights separately.

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\iloilo3d.exe --help
.\.venv\Scripts\iloilo3d.exe fetch-geodata --config config/iloilo.yaml
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

Python **3.14.3** was used for local verification. The package declares Python 3.11+;
other versions have not yet been tested locally. No GPU, Blender, or BeamNG is needed for
geographic extraction. Windows geospatial wheels provide GDAL through Pyogrio.

For a completely offline demonstration, explicitly label the synthetic fixture:

```powershell
.\.venv\Scripts\iloilo3d.exe fetch-geodata --config config/iloilo.yaml --osm-file tests/fixtures/synthetic.osm --synthetic
```

Each run prints its processed job directory containing:

- `dataset.json`: original WGS84 geometry, OSM tags, per-property evidence, source license.
- `geodata.gpkg`: building and road layers in WGS84, projected meters, and local meters.
- `preview.svg`: independent geographic visualization with attribution.
- `validation.json`: connectivity, geometry, and missing-data diagnostics.
- `manifest.json`: settings, dependency versions, source checksum, and output checksums.

Output jobs are immutable. The latest successful job is recorded in
`data/processed/latest.json`. Raw XML is cached; `--refresh` requests a new source snapshot.
Generated data, game assets, credentials, and local environments are excluded from Git.

## Export a test level

Supply the actual shipped `template.zip` path and a new output directory:

```powershell
$jobId = (Get-Content data/processed/latest.json | ConvertFrom-Json).job_id
.\.venv\Scripts\iloilo3d.exe export-beamng `
  --job "data/processed/$jobId" `
  --template-zip "D:/SteamLibrary/steamapps/common/BeamNG.drive/content/levels/template.zip" `
  --output data/generated/iloilo3d-prototype `
  --flat-test-surface
.\.venv\Scripts\iloilo3d.exe validate-level --directory data/generated/iloilo3d-prototype/levels/iloilo3d
```

Change the example Steam path to your installation. See [BeamNG export and driving checks](docs/beamng_export.md)
before copying the generated `levels` directory into an unpacked mod. The CLI does not install or
launch the game. Automated validation does not prove physics, friction, textures, or load behavior.

## Implemented commands

| Command | Behavior |
|---|---|
| `init --directory PATH` | Create a configuration and data directories; refuse overwrite |
| `fetch-geodata` | Bounded OSM request or offline XML import, geographic outputs and preview |
| `validate --directory JOB` | Check geographic output checksums and geometry |
| `export-beamng` | Generate a template-based test level, meshes, materials, provenance, and authoring data |
| `validate-level --directory LEVEL` | Check scene objects, spawn, paths, mesh units, and material bindings |

Every command has `--help`. Logs are JSON lines on stderr; results go to stdout.
The other commands in the project specification are future work, not placeholder successes.

## Boundaries of this milestone

- Input regions support an origin plus square size, or an explicit WGS84 bounding box.
  Named-place geocoding, arbitrary polygons, and circular regions are not implemented yet.
- Road connectivity follows shared OSM node identifiers; grade-separated geometric crossings
  are not joined. Routing restrictions, turn restrictions, and lane-level modeling are pending.
- The exporter uses real horizontal locations on an explicitly artificial flat test pad.
  Elevated roads/tunnels are skipped; no DEM or vertical datum has been inferred.
- Courtyards and irregular footprints are supported. Building height/floor tags are retained;
  fallback height, roof, width, and base elevation estimates appear in the export report.
- No detailed facades, licensed photo reconstruction, privacy processing, or Google integration
  is implemented yet. **No Google imagery is downloaded or used.**
- No FPS measurement, performance certification, LODs, chunk rebuilding, or city-wide support yet.

Further reading: [Windows installation](docs/installation.md), [architecture](docs/architecture.md),
[data sources and licensing](docs/data_sources.md), [reconstruction](docs/reconstruction.md),
[verification record](docs/verification.md).

The source code uses the [MIT license](LICENSE). Geographic data and BeamNG template content
retain their own licenses and are not relicensed by this repository.


