import json
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

import external_media as em

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)

MEDIA_JSON_PATH = ("tourstops", 0, "template_data", "media", 0)
MEDIA_URL_JSON_PATH = MEDIA_JSON_PATH + ("url",)
IMAGE_URL_JSON_PATH = ("image_url",)


@pytest.mark.parametrize(
    "host, allowed",
    [
        ("tours.onezoom.workers.dev", True),
        ("TOURS.onezoom.workers.dev", True),
        ("tours.onezoom.workers.dev.", True),
        ("www.onezoom.org", True),
        ("beta.onezoom.org", True),
        ("commons.wikimedia.org", True),
        ("upload.wikimedia.org", True),
        ("en.wikipedia.org", True),
        # Old github pages links shouldn't be used anymore
        ("onezoom.github.io", False),
        ("onezoom.workers.dev", False),
        ("preview.onezoom.workers.dev", False),
        ("pr-123.onezoom.workers.dev", False),
        ("evil.tours.onezoom.workers.dev", False),
        ("cdn.example.com", False),
    ],
)
def test_host_allowed(host, allowed):
    assert em.host_allowed(host) is allowed


@pytest.mark.parametrize(
    "url, path, external",
    [
        ("https://cdn.example.com/frog.jpg", MEDIA_JSON_PATH, True),
        ("http://cdn.example.com/frog.jpg", MEDIA_JSON_PATH, True),
        ("//cdn.example.com/frog.jpg", MEDIA_JSON_PATH, True),
        ("//cdn.example.com/frog.jpg", MEDIA_URL_JSON_PATH, True),
        ("//cdn.example.com/card.png", IMAGE_URL_JSON_PATH, True),
        ("https://images.unsplash.com/photo-123", IMAGE_URL_JSON_PATH, True),
        ("https://cdn.example.com/clip.webm", MEDIA_URL_JSON_PATH, True),
        ("https://preview.onezoom.workers.dev/x.png", MEDIA_JSON_PATH, True),
        ("https://tours.onezoom.workers.dev/frogs/x.jpeg", MEDIA_JSON_PATH, False),
        ("//tours.onezoom.workers.dev/frogs/x.jpeg", MEDIA_JSON_PATH, False),
        ("https://commons.wikimedia.org/wiki/File:Cat.jpg", MEDIA_JSON_PATH, False),
        ("//commons.wikimedia.org/wiki/File:Cat.jpg", MEDIA_JSON_PATH, False),
        ("https://www.onezoom.org/static/oz.png", IMAGE_URL_JSON_PATH, False),
        ("https://www.youtube.com/embed/abc", MEDIA_JSON_PATH, False),
        ("https://player.vimeo.com/video/123", MEDIA_URL_JSON_PATH, False),
        ("//www.youtube.com/embed/abc", MEDIA_JSON_PATH, False),
        ("imgsrc:99:1", IMAGE_URL_JSON_PATH, False),
        ("frogs/frog.jpg", MEDIA_JSON_PATH, False),
        ("https://cdn.example.com/frog.jpg", ("template_data", "window_text"), False),
        ("https://cdn.example.com/frog.jpg", ("template_data", "comment"), False),
    ],
)
def test_is_external_media(url, path, external):
    assert em.is_external_media(url, path) is external


def test_find_external_media_in_tour_document():
    document = {
        "image_url": "https://evil.example/card.jpg",
        "tourstop_shared": {
            "media": ["https://cdn.example.com/shared.png"],
        },
        "tourstops": [
            {
                "template_data": {
                    "window_text": "See https://cdn.example.com/not-media.jpg",
                    "media": [
                        "https://commons.wikimedia.org/wiki/File:Ok.jpg",
                        "https://cdn.example.com/photo.png",
                        {"url": "https://www.youtube.com/embed/abc"},
                        {"url": "//cdn.example.com/protocol-relative.webp"},
                    ],
                }
            }
        ],
    }
    found = {(em.format_path(path), url) for path, url in em.find_external_media(document)}
    assert found == {
        ("image_url", "https://evil.example/card.jpg"),
        ("tourstop_shared.media[0]", "https://cdn.example.com/shared.png"),
        ("tourstops[0].template_data.media[1]", "https://cdn.example.com/photo.png"),
        (
            "tourstops[0].template_data.media[3].url",
            "//cdn.example.com/protocol-relative.webp",
        ),
    }


def test_suggested_filename():
    assert em.suggested_filename("https://cdn.example.com/photos/Cute Frog!.jpg", "image/jpeg") == "Cute_Frog.jpg"
    assert em.suggested_filename("https://cdn.example.com/x.png?w=1", "image/png") == "x.png"
    assert em.suggested_filename("https://cdn.example.com/v1/image", "image/jpeg") == "image.jpeg"
    assert em.suggested_filename("//cdn.example.com/frog.jpg", "image/jpeg") == "frog.jpg"


def test_sidecar_markdown():
    assert em.sidecar_markdown("frog.jpg", "https://ex/frog.jpg") == (
        "[![frog](frog.jpg)](https://ex/frog.jpg)\n"
        "\n"
        "* *source*: https://ex/frog.jpg\n"
    )
    assert em.sidecar_markdown("clip.webm", "https://ex/clip.webm") == (
        "[clip](clip.webm)\n"
        "\n"
        "* *source*: https://ex/clip.webm\n"
    )


def test_report_lists_hits_and_exits_nonzero(tmp_path, capsys):
    tour = tmp_path / "fixture.json"
    tour.write_text(json.dumps({
        "image_url": "https://evil.example/card.jpg",
        "tourstops": [{"template_data": {"media": ["//cdn.example.com/photo.png"]}}],
    }))
    assert em.report([tour]) == 1
    out = capsys.readouterr()
    assert "https://evil.example/card.jpg" in out.out
    assert "//cdn.example.com/photo.png" in out.out
    assert "Found 2 disallowed external media URL(s)." in out.err


def test_report_clean_tour(tmp_path, capsys):
    tour = tmp_path / "clean.json"
    tour.write_text(json.dumps({
        "image_url": "imgsrc:99:1",
        "tourstops": [{
            "template_data": {
                "media": [
                    "https://commons.wikimedia.org/wiki/File:Ok.jpg",
                    "https://www.youtube.com/embed/abc",
                    "clean/local.jpeg",
                ]
            }
        }],
    }))
    assert em.report([tour]) == 0
    assert "No disallowed external media in 1 scanned file(s)." in capsys.readouterr().out


def test_cleanup_snapshots_and_rewrites(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "ROOT", tmp_path)
    monkeypatch.setattr(em, "download_media", lambda url: (PNG, "image/png"))

    tour = tmp_path / "sample.json"
    tour.write_text(json.dumps({
        "image_url": "https://cdn.example.com/card.png",
        "tourstops": [{
            "template_data": {
                "media": [
                    "//cdn.example.com/photo.png",
                    "//cdn.example.com/photo.png",
                    {"url": "https://cdn.example.com/card.png"},
                ]
            }
        }],
    }))

    assert em.cleanup([tour]) == 0
    updated = json.loads(tour.read_text())
    assert updated["image_url"] == "sample/card.png"
    media = updated["tourstops"][0]["template_data"]["media"]
    assert media[0] == "sample/photo.png"
    assert media[1] == "sample/photo.png"
    assert media[2]["url"] == "sample/card.png"
    assert (tmp_path / "sample" / "card.png").read_bytes() == PNG
    assert (tmp_path / "sample" / "photo.png").read_bytes() == PNG
    card_md = (tmp_path / "sample" / "card.md").read_text()
    assert "* *source*: https://cdn.example.com/card.png" in card_md
    assert "* *source*: //cdn.example.com/photo.png" in (tmp_path / "sample" / "photo.md").read_text()
    assert em.report([tour]) == 0


def test_download_media_from_local_server(tmp_path):
    (tmp_path / "card.png").write_bytes(PNG)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(tmp_path), **kwargs)

        def log_message(self, format, *args):
            pass

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        data, mime = em.download_media(f"http://127.0.0.1:{port}/card.png")
        assert data == PNG
        assert mime.startswith("image/")
    finally:
        httpd.shutdown()
