#!/usr/bin/env python3
"""
simulator/fake_glpi.py
A fake "GLPI server" for demo mode and the tests.

Instead of replacing program classes with fake versions, the simulation
lives at the HTTP TRANSPORT layer: a `requests` transport adapter
(requests.adapters.BaseAdapter) is mounted on a requests.Session and
answers the requests that would otherwise go to the network. This way the
real code runs end to end — auth headers, profile switch, Content-Range
pagination, retry on 5xx, document download, cache, parallelism and Word
generation — just without any real GLPI.

GLPI behaviors the simulator reproduces (on purpose):
- login with `Authorization: user_token ...` returning a session_token;
  without a valid Session-Token, 401;
- the active profile starts as Self-Service, which gets 403 on ticket data
  until the client calls /changeActiveProfile;
- a maximum page size smaller than requested (PAGE_LIMIT): the client must
  follow Content-Range or it will lose items;
- tickets in the trash (is_deleted) do not show up in the search;
- rich text returned with its HTML encoded as entities (&#60;p&#62;);
- one transient 503 error (the client must retry and carry on);
- one document whose download returns an HTML page instead of the image
  (the client must reject it and record the failure).
"""

from __future__ import annotations

import html
import json
import os
import re
import threading
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import requests
from requests.adapters import BaseAdapter
from requests.structures import CaseInsensitiveDict

SIMULATOR_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SIMULATOR_DIR, "data", "fake_glpi.json")
IMAGES_DIR = os.path.join(SIMULATOR_DIR, "images")

DEMO_TOKEN = "fictitious-demo-token"  # not a secret: only valid for this simulator
PAGE_LIMIT = 5  # the "server" returns at most 5 items per page, even if 100 are requested
TICKET_WITH_503 = 105  # the first GET of this ticket fails with 503 (transient failure)
CENTRAL_PROFILES = {"observer", "super-admin", "admin", "technician", "supervisor", "read-only", "hotliner"}

HTML_ERROR_PAGE = (
    b"<!DOCTYPE html><html><head><title>GLPI</title></head>"
    b"<body><p>Session expired. Please log in again.</p></body></html>"
)
NOT_FOUND = ["ERROR_ITEM_NOT_FOUND", "Item not found"]


class FakeGlpiAdapter(BaseAdapter):
    """Answers like the GLPI REST API, from simulator/data/fake_glpi.json."""

    def __init__(self, data_file: str = DATA_FILE, token: str = DEMO_TOKEN):
        super().__init__()
        with open(data_file, encoding="utf-8") as f:
            self.data = json.load(f)
        self.token = token
        self.tickets = {t["id"]: t for t in self.data["tickets"]}
        # indexes for the sub-resources (/ITILFollowup/{id}/Document_Item etc.)
        self.followups = {f["id"]: f for t in self.data["tickets"] for f in t["followups"]}
        self.solutions = {s["id"]: s for t in self.data["tickets"] for s in t["solutions"]}
        self._sessions = {}  # session_token -> active profile name
        self._pending_503 = {TICKET_WITH_503}
        self._lock = threading.Lock()  # the client sends requests in parallel (ThreadPoolExecutor)
        self.request_count = 0  # to show how many HTTP requests a run made

    # -- requests interface ---------------------------------------------------

    def send(self, request, **kwargs):
        with self._lock:
            self.request_count += 1
        parts = urlsplit(request.url)
        path = parts.path.split("/apirest.php", 1)[-1] or "/"
        params = {k: v[0] for k, v in parse_qs(parts.query).items()}
        status, body, headers = self._route(request.method, path, params, request.headers, request.body)
        return self._response(request, status, body, headers)

    def close(self):
        pass

    @staticmethod
    def _response(request, status, body, headers=None):
        resp = requests.Response()
        resp.status_code = status
        resp.request = request
        resp.url = request.url
        resp.headers = CaseInsensitiveDict(headers or {})
        if isinstance(body, (bytes, bytearray)):
            resp._content = bytes(body)
        else:
            resp._content = json.dumps(body, ensure_ascii=False).encode("utf-8")
            resp.headers.setdefault("Content-Type", "application/json; charset=UTF-8")
        resp.encoding = "utf-8"
        return resp

    # -- routing ----------------------------------------------------------------

    def _route(self, method, path, params, headers, body):
        if path == "/initSession":
            return self._init_session(headers)

        # everything else requires a valid session
        session = headers.get("Session-Token")
        if session not in self._sessions:
            return 401, ["ERROR_SESSION_TOKEN_INVALID", "session_token seems invalid"], None

        if path == "/killSession":
            self._sessions.pop(session, None)
            return 200, [], None
        if path == "/getMyProfiles":
            return 200, {"myprofiles": self.data["profiles"]}, None
        if path == "/getActiveProfile":
            return 200, {"active_profile": {"name": self._sessions[session]}}, None
        if path == "/changeActiveProfile" and method == "POST":
            return self._change_profile(session, body)
        if method != "GET":
            return 405, ["ERROR_METHOD_NOT_ALLOWED", "read-only in this simulator"], None

        # Self-Service cannot see other people's tickets
        if self._sessions[session].lower() not in CENTRAL_PROFILES:
            return 403, ["ERROR_RIGHT_MISSING", "You don't have permission to perform this action."], None

        if path == "/search/Ticket":
            return self._search(params)

        m = re.fullmatch(r"/(\w+)/(\d+)(?:/(\w+))?", path)
        if not m:
            return 400, ["ERROR_RESOURCE_NOT_FOUND_NOR_COMMONDBTM", "unknown resource"], None
        itemtype, id_, sub = m.group(1), int(m.group(2)), m.group(3)
        if sub:
            return self._sub_resource(itemtype, id_, sub, params)
        return self._item(itemtype, id_, headers)

    def _init_session(self, headers):
        auth = headers.get("Authorization", "")
        if not auth:
            return 400, ["ERROR_LOGIN_PARAMETERS_MISSING", "parameter(s) login, password or your API token are missing"], None
        if auth != f"user_token {self.token}":
            return 401, ["ERROR_GLPI_LOGIN_USER_TOKEN", "parameter user_token seems invalid"], None
        session = f"demo-session-{len(self._sessions) + 1}"
        self._sessions[session] = "Self-Service"  # as in GLPI: the session starts with the default profile
        return 200, {"session_token": session}, None

    def _change_profile(self, session, body):
        try:
            profile_id = json.loads(body or b"{}")["profiles_id"]
        except (ValueError, KeyError):
            return 400, ["ERROR_BAD_ARRAY", "missing profiles_id"], None
        profile = next((p for p in self.data["profiles"] if p["id"] == profile_id), None)
        if profile is None:
            return 404, NOT_FOUND, None
        self._sessions[session] = profile["name"]
        return 200, [], None

    # -- resources --------------------------------------------------------------

    def _search(self, params):
        """/search/Ticket with the criteria glpi_api.find_ticket_ids uses:
        field 15 (opening date) with morethan / lessthan."""
        def value(i):
            return datetime.strptime(params[f"criteria[{i}][value]"], "%Y-%m-%d %H:%M:%S")

        after, before = value(0), value(1)
        ids = sorted(
            t["id"]
            for t in self.tickets.values()
            if not t.get("is_deleted")  # GLPI leaves tickets in the trash out of the search
            and after < datetime.strptime(t["date_creation"], "%Y-%m-%d %H:%M:%S") < before
        )
        return self._paginate([{"2": i} for i in ids], params, wrap=True)

    def _paginate(self, items, params, wrap=False):
        start, end = 0, len(items) - 1
        if "range" in params:
            a, b = params["range"].split("-")
            start, end = int(a), int(b)
        end = min(end, start + PAGE_LIMIT - 1, len(items) - 1)  # the "server's" own limit
        page = items[start:end + 1]
        total = len(items)
        status = 200 if len(page) == total else 206
        headers = {"Content-Range": f"{start}-{max(end, start)}/{total}", "Accept-Range": f"Ticket {PAGE_LIMIT}"}
        body = {"totalcount": total, "count": len(page), "data": page} if wrap else page
        return status, body, headers

    def _item(self, itemtype, id_, headers):
        if itemtype == "Ticket":
            with self._lock:
                if id_ in self._pending_503:
                    self._pending_503.discard(id_)
                    return 503, ["ERROR", "Service temporarily unavailable (simulated)"], None
            t = self.tickets.get(id_)
            if t is None or t.get("is_deleted"):
                return 404, NOT_FOUND, None
            fields = {k: v for k, v in t.items() if k not in ("actors", "documents", "followups", "solutions")}
            fields["content"] = html.escape(t["content"])  # GLPI 10 returns rich text encoded
            fields["date"] = t["date_creation"]
            return 200, fields, None
        if itemtype == "User":
            u = self.data["users"].get(str(id_))
            return (200, {"id": id_, **u}, None) if u else (404, NOT_FOUND, None)
        if itemtype in ("ITILCategory", "Entity"):
            table = self.data["categories" if itemtype == "ITILCategory" else "entities"]
            name = table.get(str(id_))
            if not name:
                return 404, NOT_FOUND, None
            return 200, {"id": id_, "name": name.rsplit(" > ", 1)[-1], "completename": html.escape(name)}, None
        if itemtype == "Document":
            return self._document(id_, headers)
        return 404, NOT_FOUND, None

    def _document(self, id_, headers):
        d = self.data["documents"].get(str(id_))
        if d is None:
            return 404, NOT_FOUND, None
        if headers.get("Accept") == "application/octet-stream":
            if d.get("invalid_response"):
                # a real-world classic: the server answers 200, but with an HTML page
                return 200, HTML_ERROR_PAGE, {"Content-Type": "text/html; charset=UTF-8"}
            if not d.get("file"):
                return 404, ["ERROR_ITEM_NOT_FOUND", "file not available in the simulator"], None
            with open(os.path.join(IMAGES_DIR, d["file"]), "rb") as f:
                return 200, f.read(), {"Content-Type": d["mime"]}
        meta = {"id": id_, "name": d.get("name") or d["filename"], "filename": d["filename"], "mime": d["mime"]}
        return 200, meta, None

    def _sub_resource(self, itemtype, id_, sub, params):
        if itemtype == "Ticket":
            t = self.tickets.get(id_)
            if t is None:
                return 404, NOT_FOUND, None
            if sub == "Ticket_User":
                # the link id grows in the order each person was linked to the ticket
                items = [
                    {"id": id_ * 100 + i, "tickets_id": id_, "users_id": a["users_id"], "type": a["type"]}
                    for i, a in enumerate(t["actors"], start=1)
                ]
            elif sub == "ITILFollowup":
                items = [self._text_item(f, "Ticket", id_) for f in t["followups"]]
            elif sub == "ITILSolution":
                items = [self._text_item(s, "Ticket", id_) for s in t["solutions"]]
            elif sub == "Document_Item":
                items = self._document_links(t["documents"], "Ticket", id_)
            else:
                return 404, NOT_FOUND, None
        elif itemtype in ("ITILFollowup", "ITILSolution") and sub == "Document_Item":
            origin = (self.followups if itemtype == "ITILFollowup" else self.solutions).get(id_)
            if origin is None:
                return 404, NOT_FOUND, None
            items = self._document_links(origin["documents"], itemtype, id_)
        else:
            return 404, NOT_FOUND, None
        if not items:
            return 200, [], {"Content-Range": "0-0/0"}
        return self._paginate(items, params)

    @staticmethod
    def _text_item(record, itemtype, items_id):
        return {
            "id": record["id"],
            "itemtype": itemtype,
            "items_id": items_id,
            "users_id": record["users_id"],
            "date_creation": record["date_creation"],
            "content": html.escape(record["content"]),
        }

    @staticmethod
    def _document_links(doc_ids, itemtype, items_id):
        return [
            {"id": items_id * 10 + i, "documents_id": d, "itemtype": itemtype, "items_id": items_id}
            for i, d in enumerate(doc_ids, start=1)
        ]


def fake_glpi_session(base_url: str) -> tuple[requests.Session, FakeGlpiAdapter]:
    """A requests.Session whose requests to `base_url` are answered by the
    fake GLPI (nothing goes out to the network)."""
    session = requests.Session()
    adapter = FakeGlpiAdapter()
    session.mount(base_url.rstrip("/") + "/", adapter)
    return session, adapter
