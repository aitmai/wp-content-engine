"""
wordpress_publish.py

Standalone helper for manually testing the draft -> review -> publish loop
on ANY WordPress site, without running the full n8n workflow. Useful for
local dev, one-off content pushes, and testing a new site's credentials
before adding it to the Airtable "Sites" table.

Usage:
    python wordpress_publish.py draft --title "..." --content-file draft.html \\
        --wp-base-url https://example.com --wp-username admin --wp-app-password "xxxx xxxx xxxx"

    python wordpress_publish.py publish --post-id 1234 \\
        --wp-base-url https://example.com --wp-username admin --wp-app-password "xxxx xxxx xxxx"

If --wp-base-url / --wp-username / --wp-app-password are omitted, falls back
to WP_BASE_URL / WP_USERNAME / WP_APP_PASSWORD in .env (see .env.example) —
useful as a default for whichever site you're actively working on, but the
CLI flags let you target any site without editing .env each time.
"""

import argparse
import base64
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()


def _resolve_site_config(args) -> dict:
    """CLI flags win; fall back to .env defaults if a flag wasn't given."""
    base_url = (args.wp_base_url or os.environ.get("WP_BASE_URL", "")).rstrip("/")
    username = args.wp_username or os.environ.get("WP_USERNAME")
    app_password = args.wp_app_password or os.environ.get("WP_APP_PASSWORD")

    if not (base_url and username and app_password):
        sys.exit(
            "Missing WordPress site credentials. Pass --wp-base-url/--wp-username/"
            "--wp-app-password, or set WP_BASE_URL/WP_USERNAME/WP_APP_PASSWORD in .env"
        )
    return {"base_url": base_url, "username": username, "app_password": app_password}


def _auth_header(site: dict) -> dict:
    token = base64.b64encode(f"{site['username']}:{site['app_password']}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def create_draft(site: dict, title: str, content: str, categories=None, tags=None) -> dict:
    """Create a WordPress draft post on the given site. Returns the created post JSON."""
    url = f"{site['base_url']}/wp-json/wp/v2/posts"
    payload = {
        "title": title,
        "content": content,
        "status": "draft",
        "categories": categories or [],
        "tags": tags or [],
    }
    resp = requests.post(url, json=payload, headers=_auth_header(site), timeout=30)
    resp.raise_for_status()
    return resp.json()


def publish_post(site: dict, post_id: int) -> dict:
    """Flip an existing post from draft to published on the given site."""
    url = f"{site['base_url']}/wp-json/wp/v2/posts/{post_id}"
    resp = requests.post(
        url, json={"status": "publish"}, headers=_auth_header(site), timeout=30
    )
    resp.raise_for_status()
    return resp.json()


def check_broken_links(site: dict, post_id: int) -> list:
    """
    Minimal link-health check: pulls post content and HEAD-checks every
    outbound href. Returns list of (url, status_code) for anything non-2xx.
    """
    import re

    url = f"{site['base_url']}/wp-json/wp/v2/posts/{post_id}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    content = resp.json().get("content", {}).get("rendered", "")

    links = re.findall(r'href="(https?://[^"]+)"', content)
    broken = []
    for link in set(links):
        try:
            r = requests.head(link, allow_redirects=True, timeout=10)
            if r.status_code >= 400:
                broken.append((link, r.status_code))
        except requests.RequestException as e:
            broken.append((link, str(e)))
    return broken


def _add_site_args(subparser):
    subparser.add_argument("--wp-base-url", help="e.g. https://example.com (overrides .env)")
    subparser.add_argument("--wp-username", help="WP admin username (overrides .env)")
    subparser.add_argument("--wp-app-password", help="WP application password (overrides .env)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WordPress publish helper (multi-site)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    draft_parser = subparsers.add_parser("draft", help="Create a draft post")
    draft_parser.add_argument("--title", required=True)
    draft_parser.add_argument("--content-file", required=True)
    _add_site_args(draft_parser)

    publish_parser = subparsers.add_parser("publish", help="Publish an existing draft")
    publish_parser.add_argument("--post-id", type=int, required=True)
    _add_site_args(publish_parser)

    links_parser = subparsers.add_parser("check-links", help="Check for broken links in a post")
    links_parser.add_argument("--post-id", type=int, required=True)
    _add_site_args(links_parser)

    args = parser.parse_args()
    site = _resolve_site_config(args)

    if args.command == "draft":
        with open(args.content_file, "r", encoding="utf-8") as f:
            html_content = f.read()
        result = create_draft(site, args.title, html_content)
        print(f"Draft created: post_id={result['id']} status={result['status']}")
        print(f"Edit: {site['base_url']}/wp-admin/post.php?post={result['id']}&action=edit")

    elif args.command == "publish":
        result = publish_post(site, args.post_id)
        print(f"Published: post_id={result['id']} status={result['status']}")

    elif args.command == "check-links":
        broken = check_broken_links(site, args.post_id)
        if broken:
            print(f"Found {len(broken)} broken/problematic links:")
            for link, status in broken:
                print(f"  [{status}] {link}")
        else:
            print("No broken links found.")
