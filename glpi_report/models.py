"""
models.py
The report's data model (Ticket, Actor, Update, Attachment), the tables
that translate GLPI codes (status, priority, actor type) into the labels
shown in the report, and the helpers that clean up text coming from GLPI.
glpi_api.py builds these objects from the API responses; docx_builder.py
turns them into the document.

The labels are in Portuguese on purpose: they are what the generated
report shows, and the report is written for a Brazilian audience.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# GLPI code -> report label.
# Default values for GLPI 10.x. If your installation is customized (status
# plugin, changed priority matrix etc.), adjust them here.
# ---------------------------------------------------------------------------

GLPI_STATUS = {
    1: "Novo",  # New
    2: "Em atendimento (atribuído)",  # Processing (assigned)
    3: "Em atendimento (planejado)",  # Processing (planned)
    4: "Pendente",  # Pending
    5: "Solucionado",  # Solved
    6: "Fechado",  # Closed
}

GLPI_PRIORITY = {
    1: "Muito baixa",  # Very low
    2: "Baixa",  # Low
    3: "Média",  # Medium
    4: "Alta",  # High
    5: "Muito alta",  # Very high
    6: "Maior",  # Major
}

# CommonITILActor::REQUESTER / OBSERVER / ASSIGN
ACTOR_REQUESTER = "Solicitante"
ACTOR_OBSERVER = "Observador"
ACTOR_ASSIGNED = "Responsável"
GLPI_ACTOR_TYPE = {
    1: ACTOR_REQUESTER,
    2: ACTOR_OBSERVER,
    3: ACTOR_ASSIGNED,
}

# Where a document was attached in GLPI (shown in the image caption)
ORIGIN_TICKET = "Chamado"
ORIGIN_FOLLOWUP = "Acompanhamento"
ORIGIN_SOLUTION = "Solução"

STATUS_SOLVED = GLPI_STATUS[5]
STATUS_CLOSED = GLPI_STATUS[6]


@dataclass
class Attachment:
    id: int
    name: str
    filename: Optional[str]
    mime: Optional[str]
    origin: str = ORIGIN_TICKET  # ticket, followup or solution
    origin_date: object = None
    origin_author: Optional[str] = None

    @property
    def is_image(self) -> bool:
        return bool(self.mime) and self.mime.startswith("image/")


@dataclass
class Update:
    """A followup or a solution, as one entry of the ticket timeline."""

    date: object
    author: str
    text: str
    is_solution: bool = False


@dataclass
class Actor:
    type: str
    name: str


@dataclass
class Ticket:
    id: int
    title: str
    status: str
    priority: str
    category: str
    entity: str
    description: str
    opened_at: object
    solved_at: object
    actors: list = field(default_factory=list)
    updates: list = field(default_factory=list)
    attachments: list = field(default_factory=list)

    def requesters(self):
        return [a.name for a in self.actors if a.type == ACTOR_REQUESTER]

    def assignees(self):
        return [a.name for a in self.actors if a.type == ACTOR_ASSIGNED]

    def observers(self):
        return [a.name for a in self.actors if a.type == ACTOR_OBSERVER]


def user_display_name(row: dict) -> str:
    full_name = " ".join(p for p in [row.get("firstname"), row.get("realname")] if p)
    return full_name.strip() or row.get("login") or "Desconhecido"


def html_to_text(html: str) -> str:
    """Simple conversion of GLPI rich text (HTML, as stored in descriptions
    and followups) to plain text, keeping basic line breaks. Avoids an
    extra dependency. GLPI 10 returns the HTML encoded as entities
    (&#60;p&#62;), so it is unescaped first."""
    text = html_lib.unescape(html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)</li>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
