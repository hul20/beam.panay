# Windows installation

Run from the repository root in PowerShell. Python 3.14.3 and Windows x64 wheels
were verified for this milestone. Python >=3.11 is declared; other runtimes remain
untested locally. Use an isolated environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\iloilo3d.exe --help
```

Activation is optional, so no PowerShell execution-policy change is needed.
Dependencies have bounded versions in [pyproject.toml](../pyproject.toml).
The local resolution is recorded in [requirements-tested.txt](../requirements-tested.txt);
it records the tested Python 3.14 Windows environment, not a cross-platform lockfile.
To reproduce that resolution, install it before the editable project:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-tested.txt
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Pyogrio's binary wheel supplies GDAL for GeoPackage writes. Do not install an
arbitrary standalone `gdal` wheel into this environment. Rasterio, Torch, COLMAP,
OpenMVS, and GPU model dependencies are intentionally deferred until their stages.

## Configuration

[config/iloilo.yaml](../config/iloilo.yaml) selects the initial City Proper area.
The default WGS84 origin is longitude 122.5685, latitude 10.6952; `size_m: 250`
defines the projected square used to derive the geographic acquisition envelope.
Its envelope is very slightly wider due to projection rotation.

To use a precise area, set `region.bbox` with `west`, `south`, `east`, and `north`.
Values are decimal degrees, longitude first. Keep a stable origin between adjacent jobs.
The area limit defaults to 1 km². The origin and bounds must lie in the selected projected
CRS area of use. Unknown configuration keys, invalid numbers, reversed bounds, and
oversized acquisition areas fail before network access.

`data_dir` is resolved relative to the configuration file, not the current directory.
`init --directory PATH` creates a new project configuration; it refuses to overwrite
an existing one. The repository already contains its initial configuration.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit
.\.venv\Scripts\python.exe -m pytest tests/integration
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m build --wheel
```

Unit and integration tests are offline. Live acquisition is a separate explicit CLI command.
HTTP failures are reported without repeated automatic retries. A saved OSM XML input lets
processing continue while Overpass is unavailable. If acquisition was forcibly interrupted,
check that no other acquisition is running before removing `data/raw/.overpass.lock`.

