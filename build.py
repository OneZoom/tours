#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["markdown"]
# ///
"""Build a static site from markdown and media files.
Lighter weight than, e.g. Jekyll.

Usage:
  uv run build.py              # write HTML into _site/
  uv run build.py --serve      # build, then serve at http://127.0.0.1:8080/
"""
import argparse
import html
import os
import re
import shutil
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "_site"
SITE_TITLE = "OneZoom Tours"
HOME_MARKDOWN = Path("README.md")

SKIP_DIRS = {".git", ".github", "deployment", "_site", ".venv"}
COPY_EXTS = {
    ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp",
    ".ogg", ".mp3", ".ogv", ".webm", ".mpg", ".mpeg",
    ".pdf", ".json",
}

# http(s) URLs that are not already markdown links ](...) or HTML tags <...>
BARE_URL = re.compile(r"(?<!\]\()(?<!<)(https?://[^\s<]+)")

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{title}</title>
        <style>
            :root {{ color-scheme: light dark; }}
            body {{
                font-family: system-ui, sans-serif;
                line-height: 1.5;
                max-width: 42rem;
                margin: 2rem auto;
                padding: 0 1rem;
            }}
            img {{ max-width: 100%; height: auto; }}
            a {{ color: #06c; }}
            pre, code {{ font-family: ui-monospace, monospace; font-size: 0.9em; }}
            pre {{ padding: 0.75rem 1rem; overflow: auto; background: #f6f8fa; }}
            @media (prefers-color-scheme: dark) {{
                a {{ color: #6bf; }}
                pre {{ background: #222; }}
            }}
        </style>
    </head>
    <body>
        {body}
    </body>
</html>
"""


def is_markdown(path):
    return path.suffix.lower() == ".md"


def is_home_page(relative_path):
    return relative_path == HOME_MARKDOWN


def url_to_markdown_link(match):
    """Wrap a matched URL in a markdown link, keeping any trailing punctuation."""
    raw = match.group(1)
    url = raw.rstrip(".,;:)")
    trailing = raw[len(url):]
    return f"[{url}]({url}){trailing}"


def autolink(text):
    """Turn bare URLs into markdown links, leaving fenced code unchanged."""
    lines = []
    inside_fence = False
    for line in text.splitlines(True):
        if line.lstrip().startswith(("```", "~~~")):
            inside_fence = not inside_fence
            lines.append(line)
        elif inside_fence:
            lines.append(line)
        else:
            lines.append(BARE_URL.sub(url_to_markdown_link, line))
    return "".join(lines)


def humanise(stem):
    return stem.replace("_", " ")


def page_title(relative_path, text):
    if is_home_page(relative_path):
        return SITE_TITLE
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return f"{humanise(relative_path.stem)} — {SITE_TITLE}"


def render_page(relative_path, text):
    return PAGE_TEMPLATE.format(
        title=html.escape(page_title(relative_path, text)),
        body=markdown.markdown(autolink(text), extensions=["extra"]),
    )


def iter_sources():
    """Yield (absolute path, path relative to ROOT) for each file to publish."""
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            source = Path(dirpath) / name
            if is_markdown(source) or source.suffix.lower() in COPY_EXTS:
                yield source, source.relative_to(ROOT)


def output_path(relative_path):
    """Map a source path to its destination under _site/."""
    if is_home_page(relative_path):
        return SITE / "index.html"
    if is_markdown(relative_path):
        return SITE / relative_path.with_suffix(".html")
    return SITE / relative_path


def build():
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()

    pages = 0
    assets = 0
    for source, relative_path in iter_sources():
        dest = output_path(relative_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if is_markdown(relative_path):
            html_page = render_page(relative_path, source.read_text(encoding="utf-8"))
            dest.write_text(html_page, encoding="utf-8")
            pages += 1
        else:
            shutil.copy2(source, dest)
            assets += 1
    print(f"Built {pages} pages, copied {assets} files → {SITE}", flush=True)


def serve(port):
    build()
    handler = partial(SimpleHTTPRequestHandler, directory=str(SITE))
    httpd = HTTPServer(("127.0.0.1", port), handler)
    print(f"Serving at http://127.0.0.1:{port}/  (Ctrl+C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
        httpd.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--serve",
        action="store_true",
        help="build and serve _site/ locally",
    )
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    if args.serve:
        serve(args.port)
    else:
        build()


if __name__ == "__main__":
    main()
