#!/usr/bin/env python3
"""Find (and optionally snapshot) disallowed external media URLs in tour JSON.

Live remote media is only allowed from OneZoom, Wikimedia, YouTube, and Vimeo.
Other hosts can swap the file after we have reviewed the tour, so those URLs
must be downloaded into this repository and referenced by a relative path.

Usage:
  python external_media.py report
  python external_media.py cleanup
"""
import argparse
import json
import os
import re
import ssl
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Hosts (and their subdomains) whose remote media we are willing to hotlink.
ALLOWED_HOST_SUFFIXES = (
    "onezoom.org",
    "wikimedia.org",
    "wikipedia.org",
)
ALLOWED_HOSTS = {
    "tours.onezoom.workers.dev"
}

# Hosts the tour runtime embeds in place, rather than fetching a file.
ALLOWED_EMBED_HOST_SUFFIXES = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "vimeo.com",
)

IMAGE_EXTS = {
    ".avif", ".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png",
    ".svg", ".tif", ".tiff", ".webp",
}
AUDIO_EXTS = {".m4a", ".mp3", ".ogg", ".wav"}
VIDEO_EXTS = {".m4v", ".mov", ".mp4", ".mpeg", ".mpg", ".ogv", ".webm"}
MEDIA_EXTS = IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS
CONTENT_TYPE_EXT = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "image/avif": ".avif",
    "image/bmp": ".bmp",
    "image/gif": ".gif",
    "image/jpeg": ".jpeg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/tiff": ".tiff",
    "image/vnd.microsoft.icon": ".ico",
    "image/webp": ".webp",
    "image/x-icon": ".ico",
    "video/mp4": ".mp4",
    "video/mpeg": ".mpeg",
    "video/ogg": ".ogv",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "video/x-m4v": ".m4v",
}

USER_AGENT = "OneZoomTours/1.0 (+https://www.onezoom.org/)"
DOWNLOAD_TIMEOUT = 30
MAX_BYTES = 30 * 1024 * 1024
UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def tour_identifier(file_path):
    return Path(file_path).stem


def format_path(path):
    """Turn a walk path into something like tourstops[2].template_data.media[0]."""
    out = ""
    for part in path:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out or "."


def walk_strings(obj, path=()):
    """Yield (path, value) for every string in a JSON document."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk_strings(value, path + (key,))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from walk_strings(value, path + (index,))
    elif isinstance(obj, str):
        yield path, obj


def set_at(obj, path, value):
    target = obj
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def fetchable_url(value):
    """Turn a protocol-relative URL into an https URL for fetching."""
    if value.startswith("//"):
        return "https:" + value
    return value


def parse_http_url(value):
    if not isinstance(value, str):
        return None
    # The tour runtime urljoins media against the tours host, so //cdn.example.com/x
    # becomes https://cdn.example.com/x rather than a path on tours.onezoom.workers.dev.
    if value.startswith("//"):
        value = fetchable_url(value)
    elif not value.startswith(("http://", "https://")):
        return None
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return parsed


def host_matches(host, exact, suffixes):
    host = (host or "").lower().rstrip(".")
    if host in exact or host in suffixes:
        return True
    return any(host.endswith("." + suffix) for suffix in suffixes)


def host_allowed(host):
    return host_matches(host, ALLOWED_HOSTS, ALLOWED_HOST_SUFFIXES)


def is_allowed_embed(host):
    return host_matches(host, (), ALLOWED_EMBED_HOST_SUFFIXES)


def is_media_field(path):
    """True if the tour runtime will fetch this JSON path as media.

    ``image_url`` is the tour card image. ``media`` entries (plain URL strings
    or ``{"url": ...}`` objects) are passed to ``media_embed``.
    """
    if not path:
        return False
    if path[-1] == "image_url":
        return True
    if len(path) >= 2 and path[-2] == "media" and isinstance(path[-1], int):
        return True
    return (
        len(path) >= 3
        and path[-3] == "media"
        and isinstance(path[-2], int)
        and path[-1] == "url"
    )


def is_external_media(value, path):
    parsed = parse_http_url(value)
    if parsed is None:
        return False
    if host_allowed(parsed.hostname) or is_allowed_embed(parsed.hostname):
        return False
    return is_media_field(path)


def find_external_media(document):
    return [
        (path, url)
        for path, url in walk_strings(document)
        if is_external_media(url, path)
    ]


def load_tour(file_path):
    with open(file_path, encoding="utf-8") as handle:
        return json.load(handle)


def dump_tour(file_path, document):
    with open(file_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=4, ensure_ascii=False)
        handle.write("\n")


def humanise(stem):
    return stem.replace("_", " ")


def suggested_filename(url, content_type):
    parsed = urllib.parse.urlparse(url)
    name = Path(urllib.parse.unquote(parsed.path.rstrip("/") or "media")).name or "media"
    name = UNSAFE_FILENAME.sub("_", name)
    stem, ext = os.path.splitext(name)
    stem = re.sub(r"_+", "_", stem).strip("._") or "media"
    ext = ext.lower()
    if ext not in MEDIA_EXTS:
        mapped = CONTENT_TYPE_EXT.get((content_type or "").split(";")[0].strip().lower())
        ext = mapped or ext
    name = f"{stem}{ext}"
    if len(name) > 120:
        name = f"{stem[:120 - len(ext)]}{ext}"
    return name


def unique_destination(directory, filename, reserved):
    stem, ext = os.path.splitext(filename)
    candidate = filename
    n = 2
    while (directory / candidate).exists() or candidate in reserved:
        candidate = f"{stem}_{n}{ext}"
        n += 1
    return candidate


def sidecar_markdown(filename, source_url):
    alt = humanise(Path(filename).stem)
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXTS:
        preview = f"[![{alt}]({filename})]({source_url})"
    else:
        preview = f"[{alt}]({filename})"
    return f"{preview}\n\n* *source*: {source_url}\n"


def download_media(url):
    request = urllib.request.Request(
        fetchable_url(url),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/*,video/*,audio/*,*/*;q=0.8",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT, context=ctx) as response:
        content_type = response.headers.get("Content-Type", "")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"file larger than {MAX_BYTES} bytes")
    if not data:
        raise ValueError("empty response")
    mime = content_type.split(";")[0].strip().lower()
    if mime and not mime.startswith(("image/", "video/", "audio/")) and mime not in (
        "application/octet-stream",
        "application/ogg",
    ):
        raise ValueError(f"expected media, got {mime or 'unknown type'}")
    return data, mime


def snapshot_url(tour_id, url, dest_by_url, reserved_names):
    """Download (url) into {tour_id}/ and write a source sidecar. Return the relative path."""
    if url in dest_by_url:
        return dest_by_url[url]

    directory = ROOT / tour_id
    directory.mkdir(parents=True, exist_ok=True)

    data, mime = download_media(url)
    filename = unique_destination(
        directory,
        suggested_filename(url, mime),
        reserved_names,
    )
    media_path = directory / filename
    fd, tmp_name = tempfile.mkstemp(prefix=".download-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
        os.replace(tmp_name, media_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    md_path = media_path.with_suffix(".md")
    if not md_path.exists():
        md_path.write_text(sidecar_markdown(filename, url), encoding="utf-8")

    relative = f"{tour_id}/{filename}"
    dest_by_url[url] = relative
    reserved_names.add(filename)
    return relative


def iter_tour_files():
    return sorted(ROOT.glob("*.json"))


def report(files):
    found = []
    failed = False
    for file_path in files:
        try:
            document = load_tour(file_path)
        except json.JSONDecodeError as e:
            print(f"{file_path}: invalid JSON: {e}", file=sys.stderr)
            failed = True
            continue
        for path, url in find_external_media(document):
            found.append((file_path, path, url))

    for file_path, path, url in found:
        print(f"{file_path}: {format_path(path)} -> {url}")

    if found:
        print(
            f"Found {len(found)} disallowed external media URL(s). "
            "Run `python external_media.py cleanup` to snapshot them into the repo.",
            file=sys.stderr,
        )
        return 1
    if failed:
        return 1
    print(f"No disallowed external media in {len(files)} scanned file(s).")
    return 0


def cleanup(files):
    failed = False
    changed = 0
    for file_path in files:
        try:
            document = load_tour(file_path)
        except json.JSONDecodeError as e:
            print(f"{file_path}: invalid JSON: {e}", file=sys.stderr)
            failed = True
            continue

        matches = find_external_media(document)
        if not matches:
            continue

        tour_id = tour_identifier(file_path)
        dest_by_url = {}
        reserved_names = set()
        file_changed = False
        for path, url in matches:
            try:
                relative = snapshot_url(tour_id, url, dest_by_url, reserved_names)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError) as e:
                print(f"{file_path}: failed to snapshot {url}: {e}", file=sys.stderr)
                failed = True
                continue
            print(f"{file_path}: {format_path(path)} -> {relative}")
            set_at(document, path, relative)
            file_changed = True

        if file_changed:
            dump_tour(file_path, document)
            changed += 1

    if failed:
        return 1
    if changed:
        print(f"Updated {changed} tour JSON file(s).")
    else:
        print("No disallowed external media.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "mode",
        choices=("report", "cleanup"),
        help=(
            "report: list disallowed external media URLs and exit non-zero if any. "
            "cleanup: download them into the tour folder, write a source .md, "
            "and rewrite the JSON to an internal path."
        ),
    )
    args = parser.parse_args()
    files = iter_tour_files()
    if not files:
        print("No tour JSON files to check.", file=sys.stderr)
        return 1
    if args.mode == "report":
        return report(files)
    return cleanup(files)


if __name__ == "__main__":
    sys.exit(main())
