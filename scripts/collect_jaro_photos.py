"""Collect licensed Commons photos, using standard resized copies for bulk access."""

import hashlib
import html
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import yaml
from PIL import Image

from iloilo3d.providers.user_photos import ImageManifest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/jaro/photos/commons"
API = "https://commons.wikimedia.org/w/api.php"
MANIFEST = ROOT / "config/photos.example.yaml"
HEADERS = {"User-Agent": "Iloilo3D/0.2 local research photo collection"}


def query(params: dict) -> dict:
    for attempt in range(3):
        time.sleep(6.5)
        try:
            with urlopen(
                Request(API + "?" + urlencode(params), headers=HEADERS), timeout=60
            ) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in {429, 502, 503} or attempt == 2:
                raise
            delay = max(10, int(error.headers.get("Retry-After", "10")))
            print(f"API requested backoff; waiting {delay}s", flush=True)
            time.sleep(delay)
    raise RuntimeError("API requests exhausted")


def plain(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def subject_buildings(title: str) -> list[str]:
    """Conservative title-based associations, never camera pose or surveyed alignment."""
    title = title.lower()
    if "historical marker" in title or "nhi-" in title or "nhcp-" in title:
        return []
    if any(word in title for word in ("belfry", "bell tower", "campanario")):
        return ["osm/way/530035049"]
    if "cathedral" in title:
        return ["osm/way/222460850"]
    if "jaro municipal hall" in title:
        return ["osm/way/485459866"]
    if "jaro" in title and any(word in title for word in ("bandstand", "kiosk")):
        return ["osm/way/485045671"]
    return []


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    categories = [
        ("Category:Jaro Plaza", True),
        ("Category:Jaro Cathedral", False),
        ("Category:Jaro Municipal Hall", True),
    ]
    visited = set()
    cached = OUT / "source_records.json"
    if cached.exists():
        report_file = OUT / "collection_report.json"
        if report_file.exists():
            visited.update(json.loads(report_file.read_text("utf-8"))["categories"])
    titles = set()
    while categories:
        category, recurse = categories.pop(0)
        if category in visited:
            continue
        visited.add(category)
        continuation = {}
        while True:
            result = query(
                {
                    "action": "query",
                    "format": "json",
                    "list": "categorymembers",
                    "cmtitle": category,
                    "cmlimit": 500,
                    **continuation,
                }
            )
            if "error" in result:
                raise RuntimeError(result["error"])
            for member in result.get("query", {}).get("categorymembers", []):
                if member["ns"] == 6:
                    titles.add(member["title"])
                elif member["ns"] == 14 and recurse:
                    categories.append((member["title"], True))
            if "continue" not in result:
                break
            continuation = result["continue"]
            time.sleep(0.3)
        print(f"Found {len(titles)} files after {category}", flush=True)
    inventory = json.loads(cached.read_text("utf-8")) if cached.exists() else []
    ordered = sorted(titles - {p["title"] for p in inventory})
    for start in range(0, len(ordered), 20):
        result = query(
            {
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "iiprop": "url|size|sha1|extmetadata|timestamp|mime",
                "iiurlwidth": 1280,
                "titles": "|".join(ordered[start : start + 20]),
            }
        )
        if "error" in result:
            raise RuntimeError(result["error"])
        inventory.extend(result.get("query", {}).get("pages", {}).values())
        time.sleep(0.3)
    if any("thumburl" not in p.get("imageinfo", [{}])[0] for p in inventory):
        refreshed = []
        for start in range(0, len(inventory), 50):
            result = query(
                {
                    "action": "query",
                    "format": "json",
                    "prop": "imageinfo",
                    "iiprop": "url|size|sha1|extmetadata|timestamp|mime",
                    "iiurlwidth": 1280,
                    "pageids": "|".join(str(p["pageid"]) for p in inventory[start : start + 50]),
                }
            )
            refreshed.extend(result["query"]["pages"].values())
        inventory = refreshed
    # API requests wider than a small original can return the blocked original URL.
    # Ask for the largest standard thumbnail smaller than that original instead.
    small_groups = {}
    for page in inventory:
        info = page.get("imageinfo", [{}])[0]
        if "/thumb/" not in info.get("thumburl", ""):
            sizes = [
                n for n in (20, 40, 60, 120, 250, 330, 500, 960, 1280) if n < info.get("width", 0)
            ]
            if sizes:
                small_groups.setdefault(max(sizes), []).append(page["pageid"])
    replacements = {}
    for width, page_ids in small_groups.items():
        for start in range(0, len(page_ids), 50):
            result = query(
                {
                    "action": "query",
                    "format": "json",
                    "prop": "imageinfo",
                    "iiprop": "url|size|sha1|extmetadata|timestamp|mime",
                    "iiurlwidth": width,
                    "pageids": "|".join(str(p) for p in page_ids[start : start + 50]),
                }
            )
            replacements.update({p["pageid"]: p for p in result["query"]["pages"].values()})
    inventory = [replacements.get(p["pageid"], p) for p in inventory]
    cached.write_text(json.dumps(inventory, indent=2), "utf-8")
    entries, skipped, hashes = [], [], set()
    for page in sorted(inventory, key=lambda item: item["title"]):
        title = page["title"]
        if "intramuros" in title.lower():
            skipped.append({"title": title, "reason": "Manila procession outside target area"})
            continue
        info = next(iter(page.get("imageinfo", [])), None)
        if not info:
            skipped.append({"title": title, "reason": "No image metadata"})
            continue
        meta = info.get("extmetadata", {})
        license_name = plain(meta.get("LicenseShortName", {}).get("value", ""))
        license_url = plain(meta.get("LicenseUrl", {}).get("value", ""))
        creator = plain(meta.get("Artist", {}).get("value", ""))
        if title == "File:Jaro Cathedral - Belfry.JPG" and not creator:
            # File history and first-person upload description verified in revision 1119588279.
            creator = "Dranrebedrali"
        allowed = re.fullmatch(r"CC BY(?:-SA)? (?:1\.0|2\.0|2\.5|3\.0|4\.0)", license_name)
        if license_name in {"CC0", "Public domain"}:
            allowed = True
            license_url = license_url or info["descriptionurl"]
        if not allowed or not license_url or len(creator) < 2:
            skipped.append(
                {
                    "title": title,
                    "reason": "License/author requires review",
                    "license": license_name,
                }
            )
            continue
        download_mime = info.get("mime")
        if download_mime == "image/tiff" and urlparse(
            info.get("thumburl", "")
        ).path.lower().endswith(".jpg"):
            download_mime = "image/jpeg"
        if download_mime not in {"image/jpeg", "image/png", "image/webp"}:
            skipped.append({"title": title, "reason": "Unsupported format"})
            continue
        suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[download_mime]
        destination = OUT / f"commons_{page['pageid']}{suffix}"
        try:
            original = destination.exists()
            if not original:
                destination = OUT / f"commons_{page['pageid']}_1280{suffix}"
            if not destination.exists():
                temporary = destination.with_suffix(".part")
                time.sleep(2)
                with urlopen(
                    Request(info.get("thumburl", info["url"]), headers=HEADERS), timeout=60
                ) as response:
                    count = 0
                    with temporary.open("wb") as stream:
                        while chunk := response.read(65536):
                            count += len(chunk)
                            if count > 30 * 1024**2:
                                raise ValueError("Download exceeds image size limit")
                            stream.write(chunk)
                temporary.rename(destination)
                time.sleep(0.25)
            with destination.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha1").hexdigest()
            if original and int(checksum, 16) != int(info["sha1"], 36):
                # Some API versions return hexadecimal rather than base36 SHA-1.
                if checksum != info["sha1"]:
                    raise ValueError("Original checksum mismatch")
            with Image.open(destination) as photo:
                photo.verify()
            if checksum in hashes:
                skipped.append({"title": title, "reason": "Duplicate original content"})
                continue
            hashes.add(checksum)
            terms = (
                "Commons marks this file as public-domain/CC0; "
                "attribution is retained for provenance. "
                if license_name in {"CC0", "Public domain"}
                else "Adaptation permitted subject to attribution, change notices "
                "and, for BY-SA, share-alike obligations. "
            )
            entry = {
                "path": "../" + destination.relative_to(ROOT).as_posix(),
                "source": "licensed_third_party",
                "creator": creator,
                "license_id": license_name.replace(" ", "-"),
                "rights_statement": f"{title}; source: {info['descriptionurl']}; "
                f"original: {info['url']}; author: {creator}; license: {license_name} "
                f"({license_url}). "
                + terms
                + (
                    "Original downloaded unchanged. "
                    if original
                    else "Wikimedia resized copy (up to 1280 px wide); original not downloaded. "
                )
                + "License metadata archived in source_records.json.",
                "allows_reconstruction": True,
                "building_ids": subject_buildings(title),
            }
            # Leave camera positions and headings to EXIF; subject coordinates are not camera poses.
            entries.append(entry)
            print(f"Downloaded {len(entries)}/{len(inventory)}: {title}", flush=True)
        except (ValueError, OSError) as exc:
            skipped.append({"title": title, "reason": str(exc)})
            print(f"Skipped {title}: {exc}", flush=True)
            if isinstance(exc, HTTPError) and exc.code == 429:
                print(
                    "Download rate limit reached; stopping batch. Rerun later to resume.",
                    flush=True,
                )
                break
    if not entries:
        raise RuntimeError("No usable originals; existing manifest preserved")
    ImageManifest.model_validate({"images": entries})
    MANIFEST.write_text(
        "# Commons originals and resized copies; camera poses/building assignments unverified.\n"
        + yaml.safe_dump({"images": entries}, sort_keys=False, allow_unicode=True),
        "utf-8",
    )
    report = {
        "collected_at": datetime.now(UTC).isoformat(),
        "categories": sorted(visited),
        "discovered": len(inventory),
        "downloaded": len(entries),
        "skipped": skipped,
        "total_bytes": sum((ROOT / "config" / e["path"]).stat().st_size for e in entries),
    }
    report["files"] = []
    for entry in entries:
        with (ROOT / "config" / entry["path"]).open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        report["files"].append({"path": entry["path"], "sha256": digest})
    (OUT / "collection_report.json").write_text(json.dumps(report, indent=2), "utf-8")
    cards = []
    for entry in entries:
        filename = Path(entry["path"]).name
        title = entry["rights_statement"].split("; source:")[0]
        cards.append(
            f'<figure><a href="{html.escape(filename)}">'
            f'<img loading="lazy" src="{html.escape(filename)}" alt="{html.escape(title)}"></a>'
            f"<figcaption>{html.escape(title)}<br>{html.escape(entry['creator'])}"
            f" — {html.escape(entry['license_id'])}</figcaption></figure>"
        )
    (OUT / "photo_gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Jaro photo collection</title>'
        "<style>body{font:16px sans-serif;margin:24px;background:#eee}"
        "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px}"
        "figure{margin:0;padding:12px;background:white}img{width:100%;height:220px;object-fit:contain}"
        "figcaption{overflow-wrap:anywhere;margin-top:8px}</style>"
        f"<h1>Jaro photo collection ({len(entries)} files)</h1>"
        "<p>Mixed dates, viewpoints and resolutions. Review suitability before reconstruction. "
        "Full source and license links are in the YAML manifest and source_records.json.</p>"
        "<main>" + "".join(cards) + "</main>",
        "utf-8",
    )
    print(
        json.dumps({k: v for k, v in report.items() if k not in {"skipped", "files"}}), flush=True
    )


if __name__ == "__main__":
    main()
