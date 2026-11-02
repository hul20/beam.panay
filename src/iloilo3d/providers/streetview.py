"""Official Google metadata and display links, never reconstruction input."""

import os
from typing import Literal
from urllib.parse import urlencode

import httpx
from pydantic import Field

from iloilo3d.errors import PipelineError
from iloilo3d.models import Model

METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"


class StreetViewReference(Model):
    requested_latitude: float = Field(ge=-90, le=90)
    requested_longitude: float = Field(ge=-180, le=180)
    status: Literal["available", "unavailable"]
    panorama_latitude: float | None = None
    panorama_longitude: float | None = None
    date: str | None = None
    copyright: str | None = None
    display_url: str
    reconstruction_permitted: bool = False


def display_url(latitude: float, longitude: float) -> str:
    return "https://www.google.com/maps/@?" + urlencode(
        {"api": "1", "map_action": "pano", "viewpoint": f"{latitude:.7f},{longitude:.7f}"}
    )


def lookup_reference(
    latitude: float,
    longitude: float,
    *,
    client: httpx.Client | None = None,
) -> StreetViewReference:
    """One metadata lookup; no image is fetched, saved, or passed to generation."""
    key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        raise PipelineError("GOOGLE_MAPS_API_KEY is required for a Street View lookup")
    reference = StreetViewReference(
        requested_latitude=latitude,
        requested_longitude=longitude,
        status="unavailable",
        display_url=display_url(latitude, longitude),
    )
    owned = client is None
    session = client or httpx.Client(timeout=10.0)
    try:
        response = session.get(
            METADATA_URL,
            params={"location": f"{latitude:.7f},{longitude:.7f}", "key": key},
        )
        if response.status_code != 200:
            raise PipelineError(f"Street View metadata HTTP {response.status_code}")
        data = response.json()
        status = data.get("status")
        if status == "OK":
            location = data.get("location") or {}
            return StreetViewReference.model_validate(
                {
                    **reference.model_dump(),
                    "status": "available",
                    "panorama_latitude": location.get("lat"),
                    "panorama_longitude": location.get("lng"),
                    "date": data.get("date"),
                    "copyright": data.get("copyright"),
                }
            )
        if status in {"ZERO_RESULTS", "NOT_FOUND"}:
            return reference.model_copy(update={"status": "unavailable"})
        raise PipelineError(f"Street View metadata status: {status or 'unknown'}")
    except (httpx.HTTPError, ValueError, TypeError):
        # httpx exception text can include the URL and API key; never surface it.
        raise PipelineError("Street View metadata lookup failed") from None
    finally:
        if owned:
            session.close()
