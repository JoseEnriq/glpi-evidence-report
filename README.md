# glpi-evidence-report

**English** | [Português](README.pt-BR.md)

Generates the monthly "evidence book" of an IT support team (every ticket handled by each technician, with history, solution and attached screenshots) in Word and PDF, straight from the GLPI REST API.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
[![Tests](https://github.com/JoseEnriq/glpi-evidence-report/actions/workflows/tests.yml/badge.svg)](https://github.com/JoseEnriq/glpi-evidence-report/actions/workflows/tests.yml)

| Cover with a summary per technician | Table of contents with links | Ticket with timeline and evidence |
|---|---|---|
| ![Cover](docs/img/cover.png) | ![Table of contents](docs/img/contents.png) | ![Ticket](docs/img/ticket.png) |

The images and the [sample PDF](docs/sample/evidence_report_sample.pdf) come from demo mode, with fictitious data. The report is in Portuguese, aimed at Brazilian teams; the code is in English.

## The problem

Teams that provide IT support under a service contract usually have to prove, every month, the work they delivered: a document with every ticket each technician handled, with its history, solution and the screenshots attached along the way. Put together by hand from GLPI screens or notification e-mails, it is slow, depends on whoever knows the routine, and screenshots go missing, especially the ones attached to followups and solutions instead of the ticket itself.

## How it works

The program talks to the GLPI REST API, read-only:

1. opens a session with an API token, so no password is stored;
2. searches the period's tickets, paginating, and fetches 6 tickets in parallel;
3. collects attachments from the ticket, its followups and its solution, without duplicates;
4. downloads the images into a disk cache, checking each file's signature;
5. builds the Word document with python-docx and converts it to PDF with headless LibreOffice.

One command generates last month's reports for every configured GLPI instance, and `generate_month.bat` can run it from Windows Task Scheduler.

```mermaid
flowchart LR
    CFG["config.toml<br/>instances and technicians"] --> CLI
    ENV[".env<br/>API tokens"] --> CLI
    CLI["generate_month.py<br/>generate_report.py"] --> API["glpi_api.py<br/>token session, pagination,<br/>retries, 6 tickets in parallel"]
    API <-->|"HTTPS · GET only"| GLPI[("GLPI<br/>REST API")]
    API --> MOD["models.py<br/>Ticket, Attachment..."]
    CLI --> FILES["glpi_files.py<br/>image download,<br/>validation and cache"]
    FILES <-->|"GET /Document/{id}"| GLPI
    MOD --> DOCX["docx_builder.py<br/>Word document"]
    FILES --> DOCX
    DOCX --> PDF["pdf_utils.py<br/>LibreOffice → PDF"]
```

What happens with one GLPI, from login to document:

```mermaid
sequenceDiagram
    participant P as Program
    participant G as GLPI REST API
    P->>G: GET /initSession (Authorization: user_token)
    G-->>P: session_token
    P->>G: GET /getMyProfiles → POST /changeActiveProfile
    Note over P,G: leaves Self-Service for a profile that sees every ticket
    P->>G: GET /search/Ticket (period, range=0-99)
    G-->>P: ids + Content-Range: 0-99/148 (keeps going until the total)
    loop each ticket (6 in parallel)
        P->>G: /Ticket/{id}, Ticket_User, ITILFollowup, ITILSolution
        P->>G: Document_Item of the ticket, of each followup and of the solution
    end
    P->>G: GET /Document/{id} (Accept: application/octet-stream)
    G-->>P: image bytes → signature check → cache
    P->>G: GET /killSession
    P->>P: build the .docx → convert to PDF
```

## Design decisions

- **Attachments from three origins.** Screenshots are often attached to followups and solutions, so I query `Document_Item` for each of them, not only for the ticket.
- **Validate the bytes, not the response.** A document download can come back as an HTML login or error page with status 200. I check the PNG/JPEG/GIF/BMP signature before saving anything as an image.
- **Trust `Content-Range`, not the page size.** Some servers return smaller pages than requested, so pagination follows the total the server reports.
- **Least privileged profile.** Login usually lands on Self-Service, which cannot see other users' tickets, so the program switches to the least privileged profile that can.
- **6 workers on purpose.** Each ticket costs about 12 requests; a small thread pool and a cache of users and categories keep it fast without overloading GLPI.

The full table, pointing to the code, and the module layout are in [docs/arquitetura.md](docs/arquitetura.md#decisões-técnicas) (in Portuguese).

## Run the demo

No GLPI needed: a simulated server answers at the HTTP layer, so the real program runs end to end.

```bash
git clone https://github.com/JoseEnriq/glpi-evidence-report.git
cd glpi-evidence-report
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python demo.py
```

The `.docx` and `.pdf` end up in `demo_output/`. The PDF needs [LibreOffice](https://www.libreoffice.org/) installed; without it you get only the `.docx`.

## Use it with your GLPI

You need the REST API enabled with token login and a user token with a read-only profile. Fill in `config.toml` and `.env` from the example files and run `python diagnose_api.py` to check access. Setup, commands and troubleshooting are in [docs/uso.md](docs/uso.md) (in Portuguese).

## Tests

Run `pip install -r requirements-dev.txt` and then `pytest`. The suite covers the pure functions and the end-to-end flow against the simulated GLPI (a transient 503, an HTML page served as an image, pagination past the server's limit) and runs on Ubuntu and Windows in GitHub Actions.
