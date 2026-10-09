#!/usr/bin/env python3
"""
diagnose_api.py
Checks, for each instance in config.toml, whether the GLPI REST API is
reachable from this machine and whether the .env token works — run it
before the first use or whenever a report fails. Read-only.

Usage:
    python diagnose_api.py                      # every instance
    python diagnose_api.py --instance main   # only one
"""

import argparse
import calendar
import sys
from datetime import date

import requests
from dotenv import load_dotenv

from config import ConfigError, choose_instance, load_instances
from glpi_api import GlpiAccessError, instance_env, instance_url, open_source, verify_ssl

# What the API answers to a request WITHOUT credentials, and what it means.
# A credential-less request is safe and already tells apart "API disabled",
# "machine not allowed in the API client" and "all good, only the token is missing".
MEANING = {
    "ERROR_LOGIN_PARAMETERS_MISSING": "API enabled and accepting this machine",
    "API disabled": "API DISABLED in GLPI (Setup > General > API > Enable Rest API)",
    "API desativada": "API DISABLED in GLPI (Setup > General > API > Enable Rest API)",
    "ERROR_NOT_ALLOWED_IP": "this machine is not allowed in any API client (adjust the client's IP range)",
}


def check(instance):
    url = instance_url(instance)
    print(f"\n== {instance.name} ({instance.key}) — {url}/apirest.php")

    try:
        resp = requests.get(f"{url}/apirest.php/initSession", timeout=20, verify=verify_ssl())
        body = resp.content.decode("utf-8", errors="replace")
    except requests.RequestException as exc:
        print(f"  [FAIL] no answer from the server: {exc}")
        return
    state = next((text for marker, text in MEANING.items() if marker in body), None)
    print(f"  API: {state or 'unexpected answer: ' + body[:150]}")
    if not state or "enabled" not in state:
        return

    if not instance_env(instance.key, "API_USER_TOKEN"):
        print(f"  [MISSING] GLPI_{instance.key.upper()}_API_USER_TOKEN in .env")
        return

    try:
        source = open_source(instance)
    except GlpiAccessError as exc:
        print(f"  [FAIL] login with the token: {exc}")
        return
    try:
        client = source.client
        r = client.http.get(client.api + "/getActiveProfile", headers=client.headers(), timeout=20)
        profile = r.json().get("active_profile", {}).get("name", "?")
        print(f"  [OK] logged in with the token; active profile: {profile}")
        today = date.today()
        year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        start, end = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        ids = source.find_ticket_ids(start, end)
        print(f"  [OK] {len(ids)} visible ticket(s) opened in {month:02d}/{year}")
    finally:
        source.close()


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description="Checks access to the REST API of the configured GLPIs.")
    p.add_argument("--config", default=None, help="configuration file (default: config.toml)")
    p.add_argument("--instance", default=None, help="only one instance (default: all)")
    args = p.parse_args()
    try:
        instances = load_instances(args.config)
        selected = [choose_instance(instances, args.instance)] if args.instance else instances.values()
    except ConfigError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    for instance in selected:
        check(instance)


if __name__ == "__main__":
    main()
