#!/usr/bin/env python3
"""
generate_month.py
Generates, in one go, the monthly reports of every instance in config.toml,
as .docx + PDF, with each instance's technicians taken from config.toml
itself. This is what generate_month.bat runs (it can be scheduled with
Windows Task Scheduler or cron).

Examples:
    python generate_month.py                       # previous month, all instances
    python generate_month.py --month 2026-08       # a specific month
    python generate_month.py --instances main   # a single instance
"""

import argparse
import calendar
import os
import sys
from datetime import date

from dotenv import load_dotenv

from config import ConfigError, choose_instance, load_instances
from generate_report import DEFAULT_OUTPUT_DIR, run


def previous_month(today: date) -> tuple[int, int]:
    return (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description="Generates the monthly report of every instance, with PDF.")
    p.add_argument("--config", default=None, help="configuration file (default: config.toml)")
    p.add_argument("--month", default=None, help="YYYY-MM (default: previous month)")
    p.add_argument("--instances", default=None, help="comma-separated keys (default: all)")
    p.add_argument("--no-pdf", action="store_true", help="generate only the .docx")
    args = p.parse_args()

    try:
        all_instances = load_instances(args.config)
        keys = [k.strip() for k in args.instances.split(",")] if args.instances else list(all_instances)
        instances = [choose_instance(all_instances, k) for k in keys if k]
    except ConfigError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    if args.month:
        year, month = (int(x) for x in args.month.split("-"))
    else:
        year, month = previous_month(date.today())
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])

    results = []
    for instance in instances:
        print(f"\n{'=' * 60}\n{instance.name} ({instance.key}) — {start:%m/%Y}\n{'=' * 60}")
        output = os.path.join(DEFAULT_OUTPUT_DIR, f"evidence_report_{instance.key}_{year:04d}-{month:02d}.docx")
        try:
            path = run(
                instance,
                period=(start, end),
                technicians=instance.technicians or None,  # empty list = every ticket, ungrouped
                output=output,
                pdf=not args.no_pdf,
            )
            results.append((instance.key, path))
        except SystemExit as exc:
            # run() exits with SystemExit when a report cannot be generated;
            # here that must not stop the other instances.
            results.append((instance.key, None))
            print(f"[ERROR] {instance.key}: the report could not be generated (code {exc.code}).")

    print(f"\n{'=' * 60}\nSummary\n{'=' * 60}")
    for key, path in results:
        print(f"  {key:12s} {path or 'FAILED'}")
    if any(p is None for _k, p in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
