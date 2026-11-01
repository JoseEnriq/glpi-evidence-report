#!/usr/bin/env python3
"""
pdf_utils.py
Converts the report .docx into PDF using LibreOffice in headless mode (no
window), which works the same on Windows and Linux and does not depend on a
Microsoft Word license.

Why these export options: other common routes lose quality — "Print to
PDF" recompresses images lossily and leaves the table-of-contents links
unclickable; online converters often reduce resolution. With the options
below, images come out exactly as they are in the .docx (no downsampling,
lossless compression), internal links stay clickable and the PDF gets
bookmarks (technician / ticket) from the document headings.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

DEFAULT_SOFFICE_PATHS = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]

PDF_EXPORT_OPTIONS = {
    "ReduceImageResolution": {"type": "boolean", "value": "false"},
    "UseLosslessCompression": {"type": "boolean", "value": "true"},
    "ExportBookmarks": {"type": "boolean", "value": "true"},
}

CONVERSION_TIMEOUT_SECONDS = 600  # a ~250-page report takes ~30 s; headroom for big ones


def find_soffice() -> str | None:
    """Looks for the LibreOffice executable: LIBREOFFICE_PATH (if set in
    .env), then the PATH, then the default install folders."""
    candidates = [os.environ.get("LIBREOFFICE_PATH"), shutil.which("soffice")] + DEFAULT_SOFFICE_PATHS
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def convert_docx_to_pdf(docx_path: str) -> str:
    """Generates the PDF next to the .docx (same name, .pdf extension) and
    returns its path. If the previous PDF is open in a viewer (Windows locks
    the file), saves under another name instead of failing. Raises
    RuntimeError if LibreOffice is not found or the conversion fails."""
    soffice = find_soffice()
    if soffice is None:
        raise RuntimeError("LibreOffice not found. Install it or set LIBREOFFICE_PATH in .env to the soffice executable.")

    docx_path = os.path.abspath(docx_path)
    pdf_path = os.path.splitext(docx_path)[0] + ".pdf"

    # Dedicated LibreOffice profile: without it, if the user has LibreOffice
    # open, headless mode attaches to the running instance and the
    # conversion silently does not happen.
    profile = Path(tempfile.gettempdir()) / "glpi_evidence_report_libreoffice_profile"
    export_filter = "pdf:writer_pdf_Export:" + json.dumps(PDF_EXPORT_OPTIONS)

    # Convert into a temporary folder and only then move to the destination:
    # a locked previous PDF (open in a viewer) is detected at move time,
    # without LibreOffice failing halfway.
    with tempfile.TemporaryDirectory() as tmp_dir:
        command = [
            soffice,
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--convert-to",
            export_filter,
            "--outdir",
            tmp_dir,
            docx_path,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=CONVERSION_TIMEOUT_SECONDS)
        tmp_pdf = os.path.join(tmp_dir, os.path.basename(pdf_path))
        if not os.path.isfile(tmp_pdf):
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"LibreOffice did not produce the PDF (exit code {result.returncode}). {detail}")
        return _move_avoiding_locked_target(tmp_pdf, pdf_path)


def _move_avoiding_locked_target(source: str, target: str) -> str:
    """Moves `source` to `target`. If the target is locked (PDF open in a
    viewer, on Windows), uses `<name>_HHMMSS.pdf` instead and warns."""
    try:
        os.replace(source, target)
        return target
    except PermissionError:
        base, ext = os.path.splitext(target)
        alternative = f"{base}_{datetime.now():%H%M%S}{ext}"
        shutil.move(source, alternative)
        print(f"[WARNING] {os.path.basename(target)} is open in another program; PDF saved as {alternative}")
        return alternative
