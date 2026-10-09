"""
Demo mode: a simulated GLPI (fake_glpi.py) with fictitious data and images
(data/, images/). Used by demo.py and by the tests.
"""

from datetime import date

from config import Instance

DEMO_PERIOD = (date(2026, 8, 1), date(2026, 8, 31))

# An instance just like the ones in config.toml. The .invalid domain is
# reserved (RFC 2606): it never exists, so no request can "leak" to a real
# server — they are all answered by the simulated adapter.
DEMO_INSTANCE = Instance(
    key="demo",
    name="Suporte de TI — Empresa Exemplo",  # shown on the (Portuguese) report cover
    url="https://glpi.example.invalid",
    # Diego Martins (an intern, outside the contract) handles ticket 112: he
    # is not in this list, to show the technician filter at work.
    technicians=["Ana Ribeiro", "Bruno Carvalho", "Carla Nogueira"],
)
