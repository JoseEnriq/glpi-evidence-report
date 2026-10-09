#!/usr/bin/env python3
"""
image_utils.py
Detects the real type of an image (PNG, JPEG, GIF, BMP) by looking only at
its signature (the first bytes, a.k.a. "magic numbers"), with no external
library (no Pillow) and without decoding the image.

Used by glpi_files.py to confirm that what came from GLPI is a real image
and not, for example, an HTML login or error page.
"""

from __future__ import annotations

EXTENSION_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}

# leading signature of each format -> MIME type
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"\xff\xd8", "image/jpeg"),
)


def detect_mime(data: bytes) -> str | None:
    """Returns the MIME type from the raw bytes of an image, or None if the
    signature is not recognized."""
    for signature, mime in _SIGNATURES:
        if data.startswith(signature):
            return mime
    return None
