#!/usr/bin/env python3
"""
config.py
Reads the configuration file (config.toml) listing the GLPI instances the
reports are generated from. Each instance is a separate GLPI installation,
with its own address, its own REST API and its own list of technicians.

Secrets (API tokens) do NOT live here: they go in .env, as
GLPI_<KEY>_API_USER_TOKEN variables (see glpi_api.instance_env and
.env.example).

IMPORTANT: ticket numbers are NOT unique across instances — each GLPI has
its own numbering. That is why each run processes one instance at a time
and the image cache is split per instance.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field

DEFAULT_CONFIG_FILE = "config.toml"
EXAMPLE_CONFIG_FILE = "config.example.toml"


@dataclass
class Instance:
    key: str  # short identifier (e.g. "main"); used in .env, in the cache and in file names
    name: str  # display name on the report cover and page header
    url: str  # GLPI address, no trailing slash (the API lives at <url>/apirest.php)
    technicians: list = field(default_factory=list)  # name fragments used by generate_month.py


class ConfigError(RuntimeError):
    """Missing or invalid configuration file. The message is meant to be shown to the user."""


def load_instances(path: str | None = None) -> dict[str, Instance]:
    """Reads the TOML file and returns {key: Instance}, in file order."""
    path = path or DEFAULT_CONFIG_FILE
    if not os.path.isfile(path):
        raise ConfigError(
            f"Configuration file '{path}' not found. Copy {EXAMPLE_CONFIG_FILE} to "
            f"{DEFAULT_CONFIG_FILE} and fill it in (or run 'python demo.py' to see an example without GLPI)."
        )
    with open(path, "rb") as f:
        data = tomllib.load(f)

    instances = {}
    for key, values in (data.get("instances") or {}).items():
        key = key.strip().lower()
        # the key becomes part of an environment variable name and a folder name
        if not re.fullmatch(r"[a-z0-9_]+", key):
            raise ConfigError(f"Invalid instance key: '{key}' (use lowercase letters, digits and _).")
        if not values.get("url"):
            raise ConfigError(f"Instance '{key}' has no 'url' in {path}.")
        instances[key] = Instance(
            key=key,
            name=values.get("name") or key.capitalize(),
            url=values["url"].rstrip("/"),
            technicians=[t.strip() for t in values.get("technicians", []) if t.strip()],
        )
    if not instances:
        raise ConfigError(f"No instances in {path} (expected [instances.<key>] sections).")
    return instances


def choose_instance(instances: dict[str, Instance], key: str | None) -> Instance:
    """The requested instance, or the only one configured when `key` is not given."""
    if not key:
        if len(instances) == 1:
            return next(iter(instances.values()))
        raise ConfigError(f"Please pass --instance (one of: {', '.join(instances)}).")
    key = key.strip().lower()
    if key not in instances:
        raise ConfigError(f"Unknown instance '{key}'. Use one of: {', '.join(instances)}")
    return instances[key]
