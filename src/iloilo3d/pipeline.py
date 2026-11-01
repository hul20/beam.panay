"""Restartable extraction jobs, published only after every output is written."""

import hashlib
import json
import logging
import shutil
import tempfile
from importlib.metadata import version
from pathlib import Path

from iloilo3d import __version__
from iloilo3d.config import ProjectConfig
from iloilo3d.errors import PipelineError
from iloilo3d.geospatial.preview import write_preview
from iloilo3d.models import GeographicDataset, SourceRecord, ValidationReport
from iloilo3d.providers.osm import acquire, extract, import_source
from iloilo3d.storage.files import sha256_file, write_json
from iloilo3d.storage.geopackage import write_geopackage
from iloilo3d.validation.geographic import validate_dataset

LOG = logging.getLogger(__name__)


def validate_outputs(directory: Path) -> ValidationReport:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    required = {"dataset.json", "validation.json", "geodata.gpkg", "preview.svg"}
    if not required.issubset(manifest["outputs"]):
        raise PipelineError("Manifest is missing required outputs")
    for filename, checksum in manifest["outputs"].items():
        if Path(filename).name != filename:
            raise PipelineError("Manifest output must be a plain filename")
        output = directory / filename
        if not output.is_file() or sha256_file(output) != checksum:
            raise PipelineError(f"Missing or modified output: {filename}")
    dataset = GeographicDataset.model_validate_json((directory / "dataset.json").read_text("utf-8"))
    return validate_dataset(dataset)


def publish(config: ProjectConfig, path: Path, source: SourceRecord) -> Path:
    config_data = config.model_dump(mode="json", exclude={"data_dir", "acquisition"})
    versions = {
        name: version(name) for name in ("osmnx", "geopandas", "shapely", "pyproj", "pyogrio")
    }
    signature = json.dumps(
        {
            "source": source.sha256,
            "synthetic": source.synthetic,
            "config": config_data,
            "version": __version__,
            "dependencies": versions,
        },
        sort_keys=True,
    )
    key = hashlib.sha256(signature.encode()).hexdigest()[:20]
    processed = config.data_dir / "processed"
    destination = processed / key
    if destination.exists():
        report = validate_outputs(destination)
        if not report.valid:
            raise PipelineError("Existing processed job failed validation")
        LOG.info("Reusing validated processed job %s", key)
    else:
        dataset = extract(path, config, source)
        report = validate_dataset(dataset)
        if not report.valid:
            raise PipelineError("; ".join(report.errors))
        processed.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=processed))
        try:
            write_json(stage / "dataset.json", dataset.model_dump(mode="json"))
            write_json(stage / "validation.json", report.model_dump(mode="json"))
            LOG.info("Writing WGS84, projected, and local-meter GeoPackage layers")
            write_geopackage(dataset, stage / "geodata.gpkg")
            write_preview(dataset, stage / "preview.svg")
            manifest = {
                "job_id": key,
                "stage": "geographic-extraction",
                "status": "complete",
                "iloilo3d_version": __version__,
                "dependencies": versions,
                "source": source.model_dump(mode="json"),
                "configuration": config_data,
                "local_axes": {"x": "east", "y": "north", "z": "up"},
                "outputs": {p.name: sha256_file(p) for p in sorted(stage.iterdir())},
                "in_game_validation": "pending",
            }
            write_json(stage / "manifest.json", manifest)
            stage.rename(destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    write_json(processed / "latest.json", {"job_id": key})
    LOG.info("Geographic extraction complete: %s", destination)
    return destination


def fetch_geodata(
    config: ProjectConfig,
    *,
    osm_file: Path | None = None,
    refresh: bool = False,
    synthetic: bool = False,
) -> Path:
    config.validate_area()
    if synthetic and osm_file is None:
        raise PipelineError("--synthetic requires --osm-file")
    if osm_file is not None:
        source = import_source(osm_file, config, synthetic=synthetic)
        path = config.data_dir / "raw" / source.source_file
    else:
        path, source = acquire(config, refresh=refresh)
    return publish(config, path, source)
