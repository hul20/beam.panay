"""Import locally supplied, rights-cleared photos without altering source pixels."""

import logging
import math
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError
from pydantic import Field, model_validator

from iloilo3d.errors import PipelineError
from iloilo3d.models import GeographicDataset, Model
from iloilo3d.pipeline import validate_outputs
from iloilo3d.storage.files import sha256_file, write_json

LOG = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_IMAGES = 500


class ImageInput(Model):
    path: Path
    source: Literal["user_captured", "licensed_third_party"]
    creator: str = Field(min_length=2)
    license_id: str = Field(min_length=2)
    rights_statement: str = Field(min_length=10)
    allows_reconstruction: bool
    building_ids: list[str] = Field(default_factory=list)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    heading_deg: float | None = Field(default=None, ge=0, lt=360)
    captured_at: str | None = None
    is_panorama: bool = False

    @model_validator(mode="after")
    def valid_rights_and_location(self) -> "ImageInput":
        if not self.allows_reconstruction:
            raise ValueError("Image lacks explicit reconstruction permission")
        if (self.longitude is None) != (self.latitude is None):
            raise ValueError("Longitude and latitude must be supplied together")
        if len(self.building_ids) != len(set(self.building_ids)):
            raise ValueError("Repeated building ID")
        return self


class ImageManifest(Model):
    images: list[ImageInput] = Field(min_length=1, max_length=MAX_IMAGES)


def _gps_degrees(value: tuple, reference: str) -> float:
    degrees = sum(float(part) / factor for part, factor in zip(value, (1, 60, 3600), strict=True))
    return -degrees if reference in {"S", "W"} else degrees


def _read_image(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
        raise PipelineError(f"Missing or oversized image: {path}")
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise PipelineError(f"Unsupported image format: {path}")
            exif = image.getexif()
            gps = exif.get_ifd(34853) if 34853 in exif else {}
            latitude = longitude = None
            if all(key in gps for key in (1, 2, 3, 4)):
                latitude = _gps_degrees(gps[2], gps[1])
                longitude = _gps_degrees(gps[4], gps[3])
            heading = float(gps[17]) if 17 in gps else None
            return {
                "width_px": image.width,
                "height_px": image.height,
                "format": image.format,
                "exif_latitude": latitude,
                "exif_longitude": longitude,
                "exif_heading_deg": heading,
                "exif_captured_at": exif.get(36867),
                "exif_orientation": exif.get(274),
            }
    except (UnidentifiedImageError, OSError, ValueError, TypeError) as exc:
        raise PipelineError(f"Cannot decode image {path}: {exc}") from exc


def import_images(manifest: ImageManifest, job: Path, output: Path, manifest_path: Path) -> Path:
    """Copy validated originals into a new immutable job with per-image provenance."""
    if output.exists():
        raise PipelineError("Image output directory already exists")
    if not validate_outputs(job).valid:
        raise PipelineError("Geographic input failed validation")
    dataset = GeographicDataset.model_validate_json((job / "dataset.json").read_text("utf-8"))
    building_ids = {building.id for building in dataset.buildings}
    prepared = []
    seen_hashes: set[str] = set()
    for image_input in manifest.images:
        source = (manifest_path.resolve().parent / image_input.path).resolve()
        unknown = set(image_input.building_ids) - building_ids
        if unknown:
            raise PipelineError(f"Unknown building IDs for {source.name}: {sorted(unknown)}")
        metadata = _read_image(source)
        digest = sha256_file(source)
        if digest in seen_hashes:
            raise PipelineError(f"Duplicate photo content: {source.name}")
        seen_hashes.add(digest)
        latitude = image_input.latitude
        longitude = image_input.longitude
        location_source = "manifest" if latitude is not None else "exif"
        if latitude is None:
            latitude, longitude = metadata["exif_latitude"], metadata["exif_longitude"]
        heading = image_input.heading_deg
        heading_source = "manifest" if heading is not None else "exif"
        if heading is None:
            heading = metadata["exif_heading_deg"]
        if heading is not None and (not math.isfinite(heading) or not 0 <= heading < 360):
            raise PipelineError(f"Invalid photo heading: {source.name}")
        suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[metadata["format"]]
        prepared.append(
            (
                source,
                {
                    "id": digest,
                    "file": f"originals/{digest}{suffix}",
                    "sha256": digest,
                    "bytes": source.stat().st_size,
                    "provider": image_input.source,
                    "creator": image_input.creator,
                    "license_id": image_input.license_id,
                    "rights_statement": image_input.rights_statement,
                    "allows_reconstruction": True,
                    "building_ids": image_input.building_ids,
                    "latitude": latitude,
                    "longitude": longitude,
                    "location_source": location_source if latitude is not None else "unknown",
                    "heading_deg": heading,
                    "heading_source": heading_source if heading is not None else "unknown",
                    "captured_at": image_input.captured_at or metadata["exif_captured_at"],
                    "is_panorama": image_input.is_panorama,
                    "camera_intrinsics": None,
                    "camera_extrinsics": None,
                    "geographic_alignment_status": "unverified",
                    "image_metadata": metadata,
                },
            )
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".iloilo3d-images-", dir=output.parent))
    try:
        for source, record in prepared:
            target = staging / record["file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if sha256_file(target) != record["sha256"]:
                raise PipelineError(f"Photo changed during copy: {source.name}")
        write_json(
            staging / "images.json",
            {
                "schema_version": 1,
                "geographic_job": job.name,
                "manifest_sha256": sha256_file(manifest_path),
                "images": [record for _, record in prepared],
                "status": "imported_not_reconstructed",
            },
        )
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    LOG.info("Imported %d rights-cleared images into %s", len(prepared), output)
    return output
