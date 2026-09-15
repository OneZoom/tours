#!/usr/bin/env python3
"""Comment on a pull request with a preview link for each tour it changes.

Driven by the `check_run` event of a finished Cloudflare Workers build: reads
the event from $GITHUB_EVENT_PATH, works out which tour JSON the pull request
changes, and posts a single comment (updated in place on later builds) playing
each of them from the branch's preview deployment.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

API_BASE = "https://api.github.com"
LIFE_URL = "https://beta.onezoom.org/life?tour=/tour/remote.html"
# Identifies our own comment so that later builds edit it rather than add another.
MARKER = "<!-- tour-preview-links -->"
# Directories build.py leaves out of _site, so nothing in them gets served.
UNPUBLISHED = (".github/", "deployment/", "_site/")


def worker_from_summary(summary: str) -> str | None:
    """The Cloudflare worker URL this build is deployed to."""
    for label in ("Preview Alias URL", "Preview URL"):
        pattern = rf"{label}:\s*https://([a-z0-9-]+)\.onezoom\.workers\.dev"
        match = re.search(pattern, summary, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def comment_body(worker: str, changed_tours: list[str]) -> str | None:
    if not changed_tours:
        return None
    urls = [f"{LIFE_URL}/{worker}/{t}" for t in changed_tours]
    lines = [f"- {url}" for url in urls]
    return "\n".join([MARKER, "### Tour Preview Links", "OneZoom team members can preview the changed tours by clicking the links below (requires login)."] + lines) + "\n"


def api(path: str, method: str = "GET", body: dict | None = None) -> Any:
    """Call the GitHub API, returning the parsed body."""
    url = API_BASE + path
    payload = json.dumps(body).encode("utf-8") if body is not None else None

    request = urllib.request.Request(url, data=payload, method=method)
    request.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2026-03-10")
    if payload is not None:
        request.add_header("Content-Type", "application/json; charset=utf-8")

    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        print(
            f"{method} {url} failed: {e}\n"
            f"{e.read().decode('utf-8', errors='replace')}",
            file=sys.stderr,
        )
        raise


def changed_tour_paths(repo: str, number: int) -> list[str]:
    """Tour identifiers for the changed files the preview deployment will serve."""
    return sorted({
        changed["filename"][: -len(".json")]
        # first page only so won't show more than 100 changed files
        for changed in api(f"/repos/{repo}/pulls/{number}/files?per_page=100")
        if changed["status"] != "removed"
        and changed["filename"].endswith(".json")
        and not changed["filename"].startswith(UNPUBLISHED)
    })


def existing_comment(repo: str, number: int) -> dict | None:
    for comment in api(f"/repos/{repo}/issues/{number}/comments?per_page=100"):
        if MARKER in (comment.get("body") or ""):
            return comment
    return None


def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        check_run = json.load(f)["check_run"]

    worker = worker_from_summary((check_run.get("output") or {}).get("summary") or "")
    if not worker:
        print("No preview URL in the build summary, nothing to comment.")
        return

    for pull in check_run.get("pull_requests") or []:
        number = pull["number"]
        changed_tours = changed_tour_paths(repo, number)
        body = comment_body(worker, changed_tours)
        comment = existing_comment(repo, number)

        if body:
            if comment:
                api(f"/repos/{repo}/issues/comments/{comment['id']}",
                    "PATCH", {"body": body})
                print(f"Updated the comment on #{number}: {', '.join(changed_tours)}")
            else:
                api(f"/repos/{repo}/issues/{number}/comments",
                    "POST", {"body": body})
                print(f"Commented on #{number}: {', '.join(changed_tours)}")
        elif comment:
            api(f"/repos/{repo}/issues/comments/{comment['id']}", "DELETE")
            print(f"Deleted the comment on #{number}")
        else:
            print(f"No tour JSON changed in #{number}")


if __name__ == "__main__":
    main()
