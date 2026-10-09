#!/usr/bin/env python3
"""
glpi_files.py
Downloads the files (images) attached to tickets through the GLPI REST API,
with no access to the server's file folder and no mailbox:
`GET /Document/{id}` with `Accept: application/octet-stream`, reusing the
API session opened by glpi_api.GlpiSource.

Downloaded files are kept in `document_cache/<instance>/<doc_id>_<name>`
and are not downloaded again. Every file is validated as a real image
(PNG/JPEG/GIF/BMP signature — see image_utils.py) before it goes into the
cache, so an error page is never saved as if it were an image.

Standalone test (downloads a single document, to check access):
    python glpi_files.py --instance main --doc 123
"""

from __future__ import annotations

import argparse
import os
import re
import sys

import requests
from dotenv import load_dotenv

from config import ConfigError, choose_instance, load_instances
from glpi_api import ApiClient, GlpiAccessError, open_source
from image_utils import EXTENSION_BY_MIME, detect_mime

CACHE_DIR = "document_cache"


def _safe_filename(name: str) -> str:
    # the name comes from GLPI (typed by whoever attached the file): strip
    # characters Windows does not accept in file names and limit the length
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "").strip(" .")
    return name[:80] or "file"


class DocumentDownloader:
    """Downloads images through the API, with a disk cache.

    Disk cache (cache-aside pattern): before downloading, look for the file
    in the cache; if it is not there, download and store it. A GLPI
    document does not change after it is attached, so its id is enough as
    the key and the cache never needs invalidation — the file is downloaded
    once and reused on later runs. To force a new download, delete the
    cache folder."""

    mode = "API"

    def __init__(self, key: str, client: ApiClient, cache_dir: str | None = None):
        self.key = key
        self.client = client  # session shared with GlpiSource; whoever created it closes it
        self.folder = os.path.join(cache_dir or CACHE_DIR, key)  # one folder per instance: ids are not unique across GLPIs
        self.downloaded = 0  # real downloads in this run
        self.from_cache = 0  # reused from the cache
        self.failures = []  # [(doc_id, reason)]
        os.makedirs(self.folder, exist_ok=True)

    def download(self, doc_id: int, name: str | None = None) -> str | None:
        """Returns the local path of the image of document `doc_id`, or None
        if it was not possible (the reason goes to self.failures)."""
        cached = self._in_cache(doc_id)
        if cached:
            self.from_cache += 1
            return cached
        try:
            data = self.client.download_document(doc_id)
        except GlpiAccessError as exc:
            self.failures.append((doc_id, str(exc)))
            return None
        except requests.RequestException as exc:
            self.failures.append((doc_id, f"network error: {exc}"))
            return None

        # Defensive validation: a server may answer 200 with an HTML page
        # (expired session, missing permission, proxy...). Without this
        # check, that page would be saved as an "image" and break the
        # document later. The signature (leading bytes) is checked in
        # image_utils.detect_mime — neither the extension nor the MIME type
        # reported by GLPI is trusted.
        mime = detect_mime(data)
        if mime is None:
            self.failures.append((doc_id, "the downloaded content is not an image (missing permission or error page?)"))
            return None

        extension = os.path.splitext(name or "")[1].lower()
        if extension not in EXTENSION_BY_MIME.values() and extension != ".jpeg":
            extension = EXTENSION_BY_MIME[mime]
        base = _safe_filename(os.path.splitext(name or "")[0] or f"document_{doc_id}")
        path = os.path.join(self.folder, f"{doc_id}_{base}{extension}")
        with open(path, "wb") as f:
            f.write(data)
        self.downloaded += 1
        return path

    def _in_cache(self, doc_id: int) -> str | None:
        prefix = f"{doc_id}_"
        for filename in os.listdir(self.folder):
            if filename.startswith(prefix):
                path = os.path.join(self.folder, filename)
                if os.path.getsize(path) > 0:  # empty file = interrupted download; fetch again
                    return path
        return None


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description="Downloads one document (image) from a GLPI through the API, to test access.")
    p.add_argument("--config", default=None, help="configuration file (default: config.toml)")
    p.add_argument("--instance", default=None, help="instance key in config.toml")
    p.add_argument("--doc", type=int, required=True, help="document id in GLPI")
    args = p.parse_args()

    try:
        instance = choose_instance(load_instances(args.config), args.instance)
        source = open_source(instance)
    except (ConfigError, GlpiAccessError) as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    try:
        document = source.get_document(args.doc) or {}
        downloader = source.create_downloader()
        print(f"GLPI {instance.key}: downloading through the API")
        path = downloader.download(args.doc, document.get("filename"))
    finally:
        source.close()
    if path is None:
        print(f"[ERROR] Failed: {downloader.failures}")
        sys.exit(1)
    print(f"OK: {path} ({os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
