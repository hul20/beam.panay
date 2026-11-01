"""CLI for implemented stages; unimplemented target commands are not advertised."""

import argparse
import json
import logging
from pathlib import Path
from xml.etree.ElementTree import ParseError

import httpx
import yaml
from defusedxml.common import DefusedXmlException
from pydantic import ValidationError

from iloilo3d import __version__
from iloilo3d.config import ProjectConfig, load_config
from iloilo3d.errors import PipelineError
from iloilo3d.exporters.beamng import export_prototype, validate_level
from iloilo3d.logging import configure_logging
from iloilo3d.pipeline import fetch_geodata, validate_outputs
from iloilo3d.storage.files import atomic_bytes


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Iloilo3D geographic reconstruction pipeline")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--verbose", action="store_true")
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser(
        "init", help="Create configuration and data directories without overwriting"
    )
    init.add_argument("--directory", type=Path, default=Path("."))
    fetch = commands.add_parser(
        "fetch-geodata", help="Fetch OSM or process saved OSM XML into GeoPackages"
    )
    fetch.add_argument("--config", type=Path, default=Path("config/iloilo.yaml"))
    fetch.add_argument("--osm-file", type=Path, help="Use local .osm XML without network access")
    fetch.add_argument("--refresh", action="store_true", help="Refresh the raw OSM cache")
    fetch.add_argument(
        "--synthetic", action="store_true", help="Label local fixture input as synthetic"
    )
    validate = commands.add_parser(
        "validate", help="Verify a geographic job's checksums and geometry"
    )
    validate.add_argument("--directory", type=Path, required=True, help="Processed job directory")
    export = commands.add_parser(
        "export-beamng", help="Export a template-based flat test prototype"
    )
    export.add_argument(
        "--job", type=Path, required=True, help="Validated processed geographic job"
    )
    export.add_argument(
        "--template-zip", type=Path, required=True, help="Shipped BeamNG template.zip"
    )
    export.add_argument("--output", type=Path, required=True, help="New unpacked mod directory")
    export.add_argument(
        "--flat-test-surface", action="store_true", help="Use an estimated flat test pad"
    )
    export.add_argument("--fallback-height-m", type=float, default=6)
    export.add_argument("--fallback-width-m", type=float, default=6)
    level = commands.add_parser(
        "validate-level", help="Check exported scene references, not game behavior"
    )
    level.add_argument("--directory", type=Path, required=True, help="The levels/iloilo3d folder")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    configure_logging(args.verbose)
    try:
        if args.command == "init":
            directory = args.directory.resolve()
            config_path = directory / "config" / "iloilo.yaml"
            if config_path.exists():
                raise PipelineError(f"Configuration already exists: {config_path}")
            config = ProjectConfig(data_dir=Path("../data"))
            content = yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False)
            atomic_bytes(config_path, content.encode())
            for name in ("raw", "processed", "generated"):
                (directory / "data" / name).mkdir(parents=True, exist_ok=True)
            print(config_path)
        elif args.command == "fetch-geodata":
            if args.osm_file and args.refresh:
                raise PipelineError("--refresh applies only to live acquisition")
            destination = fetch_geodata(
                load_config(args.config),
                osm_file=args.osm_file,
                refresh=args.refresh,
                synthetic=args.synthetic,
            )
            print(destination)
        elif args.command == "validate":
            report = validate_outputs(args.directory)
            print(report.model_dump_json(indent=2))
            return 0 if report.valid else 1
        elif args.command == "export-beamng":
            print(
                export_prototype(
                    args.job,
                    args.template_zip,
                    args.output,
                    flat_test_surface=args.flat_test_surface,
                    fallback_height_m=args.fallback_height_m,
                    fallback_width_m=args.fallback_width_m,
                )
            )
        elif args.command == "validate-level":
            print(json.dumps(validate_level(args.directory), indent=2))
    except (
        PipelineError,
        ValidationError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        httpx.HTTPError,
        yaml.YAMLError,
        ParseError,
        DefusedXmlException,
    ) as exc:
        logging.getLogger("iloilo3d.cli").error("%s", exc)
        return 1
    return 0
