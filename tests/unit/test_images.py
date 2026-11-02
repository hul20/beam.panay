"""Rights and reference metadata are checked without remote services."""

import json

import httpx
import pytest
import yaml
from PIL import Image
from pydantic import ValidationError

from iloilo3d.errors import PipelineError
from iloilo3d.pipeline import fetch_geodata
from iloilo3d.providers.streetview import lookup_reference
from iloilo3d.providers.user_photos import ImageManifest, import_images
from iloilo3d.storage.files import sha256_file


def test_photo_import_requires_rights_and_preserves_original(config, osm_file, tmp_path):
    job = fetch_geodata(config, osm_file=osm_file, synthetic=True)
    photo = tmp_path / "photo.png"
    Image.new("RGB", (32, 20), (80, 90, 100)).save(photo)
    manifest_path = tmp_path / "photos.yaml"
    entry = {
        "path": "photo.png",
        "source": "user_captured",
        "creator": "Test photographer",
        "license_id": "Private-Authorized",
        "rights_statement": "I own this photograph and permit reconstruction.",
        "allows_reconstruction": True,
        "building_ids": ["osm/way/200"],
        "latitude": 10.7,
        "longitude": 122.5,
        "heading_deg": 90,
    }
    manifest_path.write_text(yaml.safe_dump({"images": [entry]}), encoding="utf-8")
    manifest = ImageManifest.model_validate(yaml.safe_load(manifest_path.read_text("utf-8")))
    output = import_images(manifest, job, tmp_path / "imported", manifest_path)
    record = json.loads((output / "images.json").read_text("utf-8"))["images"][0]
    assert (output / record["file"]).is_file()
    assert sha256_file(output / record["file"]) == sha256_file(photo)
    assert record["building_ids"] == ["osm/way/200"]
    assert record["geographic_alignment_status"] == "unverified"
    assert record["location_source"] == "manifest"
    with pytest.raises(PipelineError, match="already exists"):
        import_images(manifest, job, output, manifest_path)
    entry["allows_reconstruction"] = False
    with pytest.raises(ValidationError, match="permission"):
        ImageManifest.model_validate({"images": [entry]})
    entry["source"] = "google_streetview"
    with pytest.raises(ValidationError):
        ImageManifest.model_validate({"images": [entry]})


def test_streetview_metadata_stays_reference_only(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/maps/api/streetview/metadata"
        assert request.url.params["location"] == "10.7243667,122.5573278"
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "location": {"lat": 10.7244, "lng": 122.5573},
                "date": "2024-01",
                "copyright": "Google",
                "pano_id": "ephemeral-do-not-save",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = lookup_reference(10.7243667, 122.5573278, client=client)
    assert result.status == "available"
    assert result.reconstruction_permitted is False
    assert "pano_id" not in result.model_dump_json()
    assert "test-key" not in result.model_dump_json()
    assert "map_action=pano" in result.display_url
