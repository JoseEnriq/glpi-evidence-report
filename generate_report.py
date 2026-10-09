#!/usr/bin/env python3
"""
generate_report.py
CLI that generates the evidence report for GLPI tickets: data and images
come from the GLPI REST API (see glpi_api.py and glpi_files.py) — no
e-mail, no database, no manual step.

Each instance in config.toml is a separate GLPI, selected with --instance.
Ticket numbers are not unique across instances, so each run processes one.

Usage examples:
    python generate_report.py --instance main --ids 101,105,110
    python generate_report.py --instance main --period 2026-08-01 2026-08-31
    python generate_report.py --instance main --period 2026-08-01 2026-08-31 --technician "Ana Ribeiro" --pdf

Before the first use, run:
    python diagnose_api.py
to check that each GLPI API answers and that the .env token works.
To see the result without any GLPI, run:
    python demo.py

The .docx files go to the "reports/" folder by default (created
automatically). If `--output` is just a file name it is also saved there;
if it includes a folder, that path is used as is.
"""

import argparse
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

from config import ConfigError, Instance, choose_instance, load_instances
from docx_builder import build_report
from glpi_api import GlpiAccessError, open_source
from pdf_utils import convert_docx_to_pdf

DEFAULT_OUTPUT_DIR = "reports"


def parse_args():
    p = argparse.ArgumentParser(description="Generates the GLPI evidence report (data and images through the GLPI REST API).")
    p.add_argument("--config", default=None, help="configuration file (default: config.toml)")
    p.add_argument("--instance", default=None, help="instance (GLPI) key in config.toml. Optional if there is only one.")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--ids", help="comma-separated ticket numbers. E.g. 101,105,110")
    group.add_argument(
        "--period",
        nargs=2,
        metavar=("START", "END"),
        help="range of ticket opening dates, YYYY-MM-DD. E.g. 2026-08-01 2026-08-31",
    )
    p.add_argument(
        "--technician",
        default=None,
        help=(
            "keeps only the tickets handled by the given technicians (comma-separated) and groups "
            "the report by technician. Matches a fragment of the name, case-insensitive. "
            'E.g. --technician "Ana Ribeiro,Bruno Carvalho"'
        ),
    )
    p.add_argument(
        "--output",
        default=None,
        help=f"output .docx name (or path). A plain name is saved in '{DEFAULT_OUTPUT_DIR}/'; a path is used as is.",
    )
    p.add_argument("--pdf", action="store_true", help="also generates the PDF next to the .docx via LibreOffice (see pdf_utils.py)")
    return p.parse_args()


def download_images(tickets, source, cache_dir: str | None = None) -> dict:
    """Downloads (or takes from the cache) every image attached to the
    tickets. Returns {document_id: local_path}."""
    downloader = source.create_downloader(cache_dir)
    print(f"Downloading attachment images from GLPI ({downloader.mode} mode)...")
    images = {}
    for ticket in tickets:
        for attachment in ticket.attachments:
            if not attachment.is_image or attachment.id in images:
                continue
            path = downloader.download(attachment.id, attachment.filename)
            if path:
                images[attachment.id] = path
    print(
        f"Images: {len(images)} available ({downloader.downloaded} downloaded now, "
        f"{downloader.from_cache} from cache, {len(downloader.failures)} failed)."
    )
    for doc_id, reason in downloader.failures:
        print(f"[WARNING] Document {doc_id} not downloaded: {reason}")
    return images


def filter_by_technician(tickets, technicians):
    """Filters and groups the tickets by the given technicians (a
    comma-separated string or a list). Returns (tickets, {id: full_name})."""
    if isinstance(technicians, str):
        technicians = technicians.split(",")
    wanted = [n.strip() for n in technicians if n.strip()]
    total_before = len(tickets)

    def _people_involved(ticket) -> list:
        # The formal "assignee" in GLPI is not always who actually did the
        # work: the technician often shows up only as an "observer" and/or
        # as the author of a followup/solution — so all three count.
        return ticket.assignees() + ticket.observers() + [u.author for u in ticket.updates]

    def _matching_full_name(ticket):
        # the searched term is only used to filter; the full name found is
        # what appears in the document.
        people = _people_involved(ticket)
        for name in wanted:
            for person in people:
                if name.lower() in person.lower():
                    return person
        return None

    technician_by_ticket = {}  # id -> real full name (display/grouping)
    kept = []
    for t in tickets:
        full_name = _matching_full_name(t)
        if full_name:
            technician_by_ticket[t.id] = full_name
            kept.append(t)

    print(f"Technician filter: kept {len(kept)} of {total_before} ticket(s).")
    if not kept:
        print("No ticket matches the given technicians.")
        sys.exit(1)

    # group the report by technician, in alphabetical order of the full name
    # (sort is stable: the ticket order within each group is preserved)
    kept.sort(key=lambda t: technician_by_ticket[t.id])
    return kept, technician_by_ticket


def run(
    instance: Instance,
    ids=None,
    period=None,
    technicians=None,
    output=None,
    pdf=False,
    http_session=None,
    cache_dir: str | None = None,
) -> str:
    """Generates the report of one instance and returns the .docx path.
    `period` is (start, end) as `date`. Exits with SystemExit(1) and a
    message if something prevents it (no tickets, API unavailable, token
    rejected...).

    `http_session` and `cache_dir` exist for demo mode and the tests
    (simulated server and a dedicated cache folder)."""

    # Flow: open the API session -> read the tickets -> filter by technician
    # -> download the images -> build the .docx -> (optional) convert to
    # PDF. The session is always closed in `finally`, even if something
    # fails halfway.
    try:
        source = open_source(instance, http_session)
    except GlpiAccessError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    print(f"Connected to the GLPI API '{instance.key}'.")

    try:
        if ids:
            ticket_ids = list(ids)
        else:
            ticket_ids = source.find_ticket_ids(*period)
            print(f"{len(ticket_ids)} ticket(s) found in the given period.")

        if not ticket_ids:
            print("No tickets to process.")
            sys.exit(1)

        tickets = source.fetch_tickets(ticket_ids)
        if not tickets:
            print("No valid ticket was processed.")
            sys.exit(1)

        technician_by_ticket = None
        if technicians:
            tickets, technician_by_ticket = filter_by_technician(tickets, technicians)

        # Images are downloaded only after the technician filter: no point
        # downloading attachments of tickets that will not be in the report.
        try:
            images = download_images(tickets, source, cache_dir)
        except GlpiAccessError as exc:
            print(f"[ERROR] {exc}")
            sys.exit(1)
    finally:
        source.close()

    if output and os.path.dirname(output):
        output_path = output
    else:
        filename = output or f"evidence_report_{instance.key}_{datetime.now().strftime('%Y%m%d_%H%M')}.docx"
        output_path = os.path.join(DEFAULT_OUTPUT_DIR, filename)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    build_report(tickets, output_path, images, instance.name, technician_by_ticket, period)
    print(f"\nEvidence report generated: {output_path}")

    if pdf:
        print("Generating the PDF with LibreOffice (may take a few seconds)...")
        try:
            pdf_path = convert_docx_to_pdf(output_path)
        except Exception as exc:  # noqa: BLE001 — the .docx is done; do not lose the work because of the PDF
            print(f"[WARNING] Failed to generate the PDF: {exc}")
            print("The .docx was generated normally — it can be exported to PDF from Word.")
        else:
            print(f"PDF generated: {pdf_path}")
    return output_path


def main():
    load_dotenv()
    args = parse_args()
    try:
        instance = choose_instance(load_instances(args.config), args.instance)
    except ConfigError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    ids, period = None, None
    if args.ids:
        ids = [int(x.strip()) for x in args.ids.split(",") if x.strip()]
    else:
        period = (
            datetime.strptime(args.period[0], "%Y-%m-%d").date(),
            datetime.strptime(args.period[1], "%Y-%m-%d").date(),
        )
    run(instance, ids, period, args.technician, args.output, args.pdf)


if __name__ == "__main__":
    main()
