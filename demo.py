#!/usr/bin/env python3
"""
demo.py
Demo mode: generates a complete evidence report (Word and, if LibreOffice
is installed, PDF) WITHOUT any GLPI, from fictitious data and images.

The real program runs end to end (generate_report.run -> glpi_api ->
glpi_files -> docx_builder -> pdf_utils); only the server is simulated, at
the HTTP layer (see simulator/fake_glpi.py). It does not read .env or
config.toml, and no request goes out to the network.

Usage:
    python demo.py            # writes to demo_output/
    python demo.py --no-pdf   # .docx only
    python demo.py --clean    # deletes demo_output/ first (including the image cache)
"""

import argparse
import os
import shutil
import sys
import time

from generate_report import run
from simulator import DEMO_INSTANCE, DEMO_PERIOD
from simulator.fake_glpi import DEMO_TOKEN, fake_glpi_session

OUTPUT_DIR = "demo_output"


def main():
    p = argparse.ArgumentParser(description="Generates a sample report with fictitious data, without GLPI.")
    p.add_argument("--no-pdf", action="store_true", help="generate only the .docx")
    p.add_argument("--clean", action="store_true", help=f"delete {OUTPUT_DIR}/ before generating")
    args = p.parse_args()

    if args.clean and os.path.isdir(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)

    # The token only exists in this process and only works on the fake server.
    os.environ[f"GLPI_{DEMO_INSTANCE.key.upper()}_API_USER_TOKEN"] = DEMO_TOKEN
    session, server = fake_glpi_session(DEMO_INSTANCE.url)

    print("Demo mode: simulated GLPI, fictitious data and images.\n")
    started = time.perf_counter()
    path = run(
        DEMO_INSTANCE,
        period=DEMO_PERIOD,
        technicians=DEMO_INSTANCE.technicians,
        output=os.path.join(OUTPUT_DIR, f"evidence_report_demo_{DEMO_PERIOD[0]:%Y-%m}.docx"),
        pdf=not args.no_pdf,
        http_session=session,
        cache_dir=os.path.join(OUTPUT_DIR, "document_cache"),
    )
    elapsed = time.perf_counter() - started
    print(f"\n{server.request_count} HTTP requests to the simulated GLPI in {elapsed:.1f} s.")
    print(f"Open the result in: {os.path.abspath(os.path.dirname(path))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
