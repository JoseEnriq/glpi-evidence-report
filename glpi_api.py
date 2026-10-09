#!/usr/bin/env python3
"""
glpi_api.py
Access to GLPI through its REST API (`/apirest.php`) — the report's only
data source.

- ApiClient: token-authenticated session, profile switch, GET with
  pagination and retries on network failure, and document download.
- GlpiSource: finds the tickets of a period and builds the Ticket objects
  (models.py) that docx_builder.py turns into the document.
- open_source(instance): entry point used by generate_report.py.

How the GLPI REST API works (the essentials to read this file)
--------------------------------------------------------------
1. `GET /initSession` with the header `Authorization: user_token <token>`
   returns a temporary `session_token`. From then on every request carries
   `Session-Token: <session_token>` (and `App-Token`, if the API client
   requires one). At the end, `GET /killSession` invalidates the session.
2. Every object has an address: `/Ticket/42`, `/Ticket/42/ITILFollowup`,
   `/User/7`... Responses are JSON; `xxx_id` fields are numbers that must
   be translated (see models.py) or fetched (`/User/7`).
3. Lists are paginated: the client asks for `range=0-99` and the response
   carries a `Content-Range: 0-99/148` header (items in this page / total).
4. `GET /Document/{id}` with `Accept: application/octet-stream` returns the
   bytes of the attached file instead of the document's JSON.

Design decisions
----------------
- Read-only: no POST/PUT/DELETE of data. The only exception is
  `POST /changeActiveProfile`, which switches the active profile of the
  program's OWN session and writes nothing to GLPI. To enforce this by
  permission too (not just by code), use a service account with a
  read-only profile (Observer/Read-Only).
- API token only, never a password: the token can be revoked at any time
  and does not expose anyone's personal password.
- Resilience: a failure in ONE ticket does not bring the batch down (see
  fetch_tickets); network errors and 5xx are retried; login/permission
  errors (4xx) are not.
- Performance: ~12 requests per ticket (the GLPI REST API's "N+1"
  pattern), mitigated by in-memory caches and 6 tickets in parallel. In
  practice, ~20 s for 150 tickets.
"""

from __future__ import annotations

import html as html_lib
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import requests

from config import Instance
from models import (
    GLPI_ACTOR_TYPE,
    GLPI_PRIORITY,
    GLPI_STATUS,
    ORIGIN_FOLLOWUP,
    ORIGIN_SOLUTION,
    ORIGIN_TICKET,
    Actor,
    Attachment,
    Ticket,
    Update,
    html_to_text,
    user_display_name,
)

TIMEOUT_SECONDS = 60  # max wait per response; keeps the program from hanging if the server stops answering
API_PAGE_SIZE = 100  # items requested per list call (the server may return fewer)
ATTEMPTS = 3  # attempts per request on network failure or 5xx
MAX_WORKERS = 6  # tickets fetched at the same time; low on purpose, to avoid overloading GLPI
# "Central" profiles (that can see other users' tickets), in order of
# preference: least privileged first (least privilege — the program only
# reads). Hotliner comes last because, depending on its rights, it may not
# see every ticket. Self-Service is left out: it only sees the user's own tickets.
PROFILE_ORDER = ["read-only", "observer", "technician", "supervisor", "admin", "super-admin", "hotliner"]
SYSTEM_AUTHOR = "Sistema/GLPI"  # shown in the report when an update has no user


# Domain error: separates "could not talk to GLPI" from bugs in the program.
# Callers (generate_report.py, glpi_files.py) catch only this one and show the message.
class GlpiAccessError(RuntimeError):
    """Could not authenticate/download from GLPI (missing or rejected token,
    server down...). The message is meant to be shown to the user."""


# Configuration through environment variables (.env): secrets stay out of the code.
def instance_env(key: str, suffix: str) -> str | None:
    """GLPI_<KEY>_<suffix>, falling back to GLPI_<suffix> shared by all
    instances (handy when the same token works on more than one GLPI)."""
    return os.environ.get(f"GLPI_{key.upper()}_{suffix}") or os.environ.get(f"GLPI_{suffix}") or None


def verify_ssl() -> bool:
    return os.environ.get("GLPI_VERIFY_SSL", "1").strip().lower() not in ("0", "false", "no")


def instance_url(instance: Instance) -> str:
    return (instance_env(instance.key, "URL") or instance.url).rstrip("/")


class ApiClient:
    """Authenticated session on the REST API of ONE GLPI.

    Lifecycle: the constructor already opens the session and adjusts the
    profile; whoever creates it must call close() at the end (see
    GlpiSource.close). Every read goes through _get, the single HTTP read
    exit point — that is where timeout, retries and auth headers live.

    `http_session` lets the caller inject a ready requests.Session — that
    is how demo mode (simulator/fake_glpi.py) swaps the real server for a
    simulated one without changing anything in this code."""

    def __init__(self, key: str, base_url: str, http_session: requests.Session | None = None):
        self.key = key
        self.api = base_url.rstrip("/") + "/apirest.php"
        # requests.Session reuses the TCP/TLS connection across requests
        # (keep-alive), which matters when there are hundreds of small GETs.
        self.http = http_session or requests.Session()
        self.http.verify = verify_ssl()
        self._app_token = instance_env(key, "API_APP_TOKEN")
        self._session_token = None
        self._authenticate()
        self._switch_to_central_profile()

    # -- session --------------------------------------------------------

    def headers(self, extra: dict | None = None) -> dict:
        h = {}
        if self._app_token:
            h["App-Token"] = self._app_token  # identifies the API client (optional in GLPI)
        if self._session_token:
            h["Session-Token"] = self._session_token  # identifies the session opened in _authenticate
        h.update(extra or {})
        return h

    def _authenticate(self):
        # Two-step authentication: the API token (long-lived, revocable,
        # stored only in .env) is exchanged for a session_token
        # (short-lived). Only the session_token travels in later requests.
        user_token = instance_env(self.key, "API_USER_TOKEN")
        if not user_token:
            raise GlpiAccessError(
                f"Missing API token for instance '{self.key}': set GLPI_{self.key.upper()}_API_USER_TOKEN "
                "in .env (in GLPI: My settings > Remote access keys > API token > Regenerate)."
            )
        resp = self.http.get(
            self.api + "/initSession",
            headers=self.headers({"Authorization": f"user_token {user_token}"}),
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            raise GlpiAccessError(f"GLPI API '{self.key}' rejected the login (HTTP {resp.status_code}): {resp.text[:150]}")
        try:
            self._session_token = resp.json().get("session_token")
        except ValueError:
            self._session_token = None
        if not self._session_token:
            raise GlpiAccessError(f"GLPI API '{self.key}' did not return a session_token.")

    def _switch_to_central_profile(self):
        """The active profile right after login is usually Self-Service,
        which cannot see other users' tickets (the API answers 403 on the
        sub-resources). Switch to a technician/read-only profile of the
        user, if there is one."""
        resp = self.http.get(self.api + "/getMyProfiles", headers=self.headers(), timeout=TIMEOUT_SECONDS)
        if resp.status_code != 200:
            return
        profiles = resp.json().get("myprofiles", [])
        candidates = [p for p in profiles if p["name"].lower() in PROFILE_ORDER]
        if not candidates:
            return  # Self-Service only: keep going and GLPI will deny what is not the user's
        # Pick the least privileged central profile: read-only/observer
        # already see every ticket and attachment, and the program never
        # needs more than reading. A more privileged one is only used when
        # it is the only central profile the user has.
        candidates.sort(key=lambda p: PROFILE_ORDER.index(p["name"].lower()))
        self.http.post(
            self.api + "/changeActiveProfile",
            headers=self.headers(),
            json={"profiles_id": candidates[0]["id"]},
            timeout=TIMEOUT_SECONDS,
        )

    def close(self):
        if self._session_token:
            try:
                self.http.get(self.api + "/killSession", headers=self.headers(), timeout=15)
            except requests.RequestException:
                pass
            self._session_token = None

    # -- reads ----------------------------------------------------------

    def _get(self, path: str, params: dict | None = None, extra_headers: dict | None = None):
        """GET with retries. Only transient failures (network and 5xx) are
        retried, with a growing wait (1 s, 2 s...). A 4xx (login,
        permission, not found) returns right away: retrying would not help
        and would only slow things down."""
        last = None
        for attempt in range(1, ATTEMPTS + 1):
            try:
                resp = self.http.get(
                    self.api + path,
                    headers=self.headers(extra_headers),
                    params=params,
                    timeout=TIMEOUT_SECONDS,
                )
            except requests.RequestException as exc:
                last = exc
                time.sleep(attempt)
                continue
            if resp.status_code >= 500 and attempt < ATTEMPTS:
                last = f"HTTP {resp.status_code}"
                time.sleep(attempt)
                continue
            return resp
        raise GlpiAccessError(f"No answer from GLPI API '{self.key}' at {path}: {last}")

    def get_item(self, path: str, params: dict | None = None):
        """GET of a single item; returns the JSON, or None if it does not exist (404)."""
        resp = self._get(path, params)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise GlpiAccessError(f"API answered HTTP {resp.status_code} at {path}: {resp.text[:150]}")
        return resp.json()

    def get_list(self, path: str, params: dict | None = None) -> list:
        """GET of a list, following pagination.

        Asks for `range=start-end` and reads the total from the
        Content-Range header ("0-99/148" -> 148). The next request starts
        where the previous page actually ended (`start += len(page)`), not
        at `start + 100`: the server may return fewer items than requested
        (its own page limit), and this way nothing is skipped. 200 = full
        list, 206 = partial page; 404 counts as an empty list (e.g. a
        followup with no attachments)."""
        items, start = [], 0
        while True:
            p = dict(params or {})
            p["range"] = f"{start}-{start + API_PAGE_SIZE - 1}"
            resp = self._get(path, p)
            if resp.status_code == 404:
                return items
            if resp.status_code not in (200, 206):
                raise GlpiAccessError(f"API answered HTTP {resp.status_code} at {path}: {resp.text[:150]}")
            page = resp.json()
            if isinstance(page, dict) and "data" in page:  # /search wraps the rows in {"data": [...]}
                page = page["data"] or []
            items.extend(page)
            total = _total_from_content_range(resp.headers.get("Content-Range"))
            start += len(page)
            if not page or total is None or start >= total:
                return items

    def download_document(self, doc_id: int) -> bytes:
        # Same address as the document's JSON; the Accept header is what
        # makes GLPI return the file itself.
        resp = self._get(f"/Document/{doc_id}", extra_headers={"Accept": "application/octet-stream"})
        if resp.status_code != 200:
            raise GlpiAccessError(f"API answered HTTP {resp.status_code} for document {doc_id}: {resp.text[:150]}")
        return resp.content


# Pure helpers (no I/O): easy to test in isolation (see tests/).
def _total_from_content_range(value: str | None) -> int | None:
    # "0-99/148" -> 148
    if not value or "/" not in value:
        return None
    try:
        return int(value.rsplit("/", 1)[1])
    except ValueError:
        return None


def _parse_datetime(text) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


class GlpiSource:
    """Reads the tickets of one GLPI through the API and builds the models.py objects.

    The _users/_categories/_entities/_documents dicts are in-memory caches
    of what repeats across tickets (the same technician or category shows
    up in hundreds of them), saving requests. They are written by several
    threads; at worst two threads fetch the same item and one overwrites
    the other with the same value — a benign race that corrupts nothing
    (dict assignment is atomic in CPython)."""

    mode = "API"

    def __init__(self, key: str, client: ApiClient):
        self.key = key
        self.client = client
        self._users = {}
        self._categories = {}
        self._entities = {}
        self._documents = {}

    def close(self):
        self.client.close()

    def create_downloader(self, cache_dir: str | None = None):
        from glpi_files import DocumentDownloader

        return DocumentDownloader(self.key, self.client, cache_dir)

    # -- search ---------------------------------------------------------

    def find_ticket_ids(self, start_date: date, end_date: date) -> list:
        """Tickets opened between the two dates (inclusive). Tickets in the
        GLPI trash are not included (the API search already excludes them)."""
        start = datetime.combine(start_date, datetime.min.time())
        end_exclusive = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        # The search uses GLPI "search option" ids: 2 = ticket id,
        # 15 = opening date. "morethan"/"lessthan" are strict, so step back
        # 1 second at the start to include 00:00:00 of the first day.
        strict_start = start - timedelta(seconds=1)
        params = {
            "criteria[0][field]": "15",
            "criteria[0][searchtype]": "morethan",
            "criteria[0][value]": strict_start.strftime("%Y-%m-%d %H:%M:%S"),
            "criteria[1][link]": "AND",
            "criteria[1][field]": "15",
            "criteria[1][searchtype]": "lessthan",
            "criteria[1][value]": end_exclusive.strftime("%Y-%m-%d %H:%M:%S"),
            "forcedisplay[0]": "2",
            "sort": "2",
            "order": "ASC",
        }
        return [int(row["2"]) for row in self.client.get_list("/search/Ticket", params)]

    def fetch_tickets(self, ids) -> list:
        """Fetches several tickets in parallel. Returns them in the order of
        `ids`, without the ones that failed or do not exist (warning about each)."""
        def _one(ticket_id):
            # Failure isolation: a ticket with bad data becomes a warning and
            # is skipped, instead of bringing down the whole month's report.
            try:
                return self.fetch_ticket(ticket_id)
            except Exception as exc:  # noqa: BLE001 — one bad ticket must not bring the whole batch down
                print(f"[WARNING] Failed to fetch ticket #{ticket_id} from the API — skipping: {exc}")
                return None

        tickets = []
        # Time is dominated by waiting on the network (I/O), not by CPU — so
        # threads work well here even with Python's GIL: while one thread
        # waits for a response, another is already sending its request.
        # pool.map yields results in the order of `ids` (not in the order
        # they finish), which is the order the report needs.
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            for ticket_id, ticket in zip(ids, pool.map(_one, ids)):
                if ticket is None:
                    print(f"[WARNING] Ticket #{ticket_id} not found — skipping.")
                    continue
                tickets.append(ticket)
                print(f"Fetched ticket #{ticket_id} — {ticket.title}")
        return tickets

    def fetch_ticket(self, ticket_id: int) -> Ticket | None:
        """Builds a Ticket (models.py) from several API responses: the
        ticket, its actors, followups, solution and attachments. The
        "xxx_id" fields come as numeric codes and are translated here
        (status, priority, category, entity)."""
        t = self.client.get_item(f"/Ticket/{ticket_id}")
        if t is None:
            return None

        ticket = Ticket(
            id=t["id"],
            title=t.get("name") or f"Chamado {ticket_id}",
            status=GLPI_STATUS.get(t["status"], f"Desconhecido ({t['status']})"),
            priority=GLPI_PRIORITY.get(t["priority"], f"Desconhecida ({t['priority']})"),
            category=self._dropdown_name("/ITILCategory", t.get("itilcategories_id"), self._categories)
            or "Sem categoria",
            entity=self._dropdown_name("/Entity", t.get("entities_id"), self._entities, zero_is_valid=True) or "-",
            description=html_to_text(t.get("content") or ""),
            opened_at=_parse_datetime(t.get("date_creation") or t.get("date")),
            solved_at=_parse_datetime(t.get("solvedate")),
        )
        ticket.actors = self._actors(ticket_id)
        followups = self.client.get_list(f"/Ticket/{ticket_id}/ITILFollowup")
        solutions = self.client.get_list(f"/Ticket/{ticket_id}/ITILSolution")
        ticket.updates = self._updates(followups, solutions)
        ticket.attachments = self._attachments(t, followups, solutions)
        return ticket

    # -- parts ----------------------------------------------------------

    def _dropdown_name(self, path: str, id_, cache: dict, zero_is_valid: bool = False) -> str | None:
        if id_ is None or (id_ == 0 and not zero_is_valid):  # category 0 = "no category"; entity 0 = root
            return None
        if id_ not in cache:
            item = self.client.get_item(f"{path}/{id_}") or {}
            cache[id_] = html_lib.unescape(item.get("completename") or item.get("name") or "") or None
        return cache[id_]

    def _user(self, users_id) -> dict | None:
        if not users_id:
            return None
        if users_id not in self._users:
            u = self.client.get_item(f"/User/{users_id}")
            self._users[users_id] = (
                {"realname": u.get("realname"), "firstname": u.get("firstname"), "login": u.get("name")} if u else None
            )
        return self._users[users_id]

    def _author_name(self, users_id) -> str | None:
        """The user's display name, or None if there is no user."""
        u = self._user(users_id)
        return user_display_name(u) if u and u.get("login") else None

    def _actors(self, ticket_id: int) -> list:
        actors = []
        # order in which each person was linked to the ticket (link id), so
        # the text comes out the same on every run
        rows = sorted(self.client.get_list(f"/Ticket/{ticket_id}/Ticket_User"), key=lambda r: r["id"])
        for row in rows:
            u = self._user(row["users_id"])
            if u is None:
                continue
            actors.append(Actor(type=GLPI_ACTOR_TYPE.get(row["type"], "Outro"), name=user_display_name(u)))
        return actors

    def _updates(self, followups: list, solutions: list) -> list:
        updates = [
            Update(
                date=_parse_datetime(f.get("date_creation")),
                author=self._author_name(f.get("users_id")) or SYSTEM_AUTHOR,
                text=html_to_text(f.get("content") or ""),
            )
            for f in followups
        ]
        updates += [
            Update(
                date=_parse_datetime(s.get("date_creation")),
                author=self._author_name(s.get("users_id")) or SYSTEM_AUTHOR,
                text=html_to_text(s.get("content") or ""),
                is_solution=True,
            )
            for s in solutions
        ]
        updates.sort(key=lambda u: u.date or datetime.min)
        return updates

    def _document(self, doc_id: int) -> dict:
        if doc_id not in self._documents:
            self._documents[doc_id] = self.client.get_item(f"/Document/{doc_id}") or {}
        return self._documents[doc_id]

    def get_document(self, doc_id: int):
        return self._document(doc_id) or None

    def _attachments(self, ticket: dict, followups: list, solutions: list) -> list:
        """Documents of the ticket, of its followups and of its solutions;
        each document only once (priority in that order).

        In GLPI 10 most images are linked to a followup or to the solution,
        not to the ticket itself — looking only at the ticket misses most
        of the evidence. The API has no single query for this, so there is
        one request per item; /Document/{id} results are cached in _document."""
        origins = [(ORIGIN_TICKET, f"/Ticket/{ticket['id']}", _parse_datetime(ticket.get("date_creation")), ticket.get("users_id_recipient"))]
        origins += [
            (ORIGIN_FOLLOWUP, f"/ITILFollowup/{f['id']}", _parse_datetime(f.get("date_creation")), f.get("users_id"))
            for f in followups
        ]
        origins += [
            (ORIGIN_SOLUTION, f"/ITILSolution/{s['id']}", _parse_datetime(s.get("date_creation")), s.get("users_id"))
            for s in solutions
        ]

        by_id = {}  # the same document can be linked to more than one origin: the dict avoids duplicates
        for origin, path, when, users_id in origins:
            for link in self.client.get_list(f"{path}/Document_Item"):
                doc_id = link["documents_id"]
                if doc_id in by_id:
                    continue
                d = self._document(doc_id)
                if not d:
                    continue
                by_id[doc_id] = Attachment(
                    id=doc_id,
                    name=d.get("name") or d.get("filename") or f"documento_{doc_id}",
                    filename=d.get("filename"),
                    mime=d.get("mime"),
                    origin=origin,
                    origin_date=when,
                    origin_author=self._author_name(users_id),
                )
        return [by_id[i] for i in sorted(by_id)]


def open_source(instance: Instance, http_session: requests.Session | None = None) -> GlpiSource:
    """Opens the API session on the given GLPI. Raises GlpiAccessError with a
    message ready to show (missing token, API disabled, IP not allowed in
    the API client, server down...)."""
    try:
        client = ApiClient(instance.key, instance_url(instance), http_session)
    except requests.RequestException as exc:
        raise GlpiAccessError(f"Could not reach the GLPI API '{instance.key}': {exc}") from exc
    return GlpiSource(instance.key, client)
