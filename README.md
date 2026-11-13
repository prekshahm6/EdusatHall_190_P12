# P12 - Restaurant Complaint Tracker

A web application where citizens report restaurant food-safety problems. The system validates each report, classifies it, routes it to the responsible district Food Safety Officer, and tracks it until it is resolved.

It integrates two subjects:

- **BCS503 Automata Theory and Computability:** DFA and regex validation, five-category classification.
- **BCS502 Computer Networks:** routing table, dispatch algorithm, availability, capacity, fallback and escalation.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript, Chart.js |
| Backend | Python, Flask |
| Database | SQLite (file `complaints.db`, created automatically) |
| Testing | Python `unittest` (18 tests) |

```
Browser  ->  app.py (Flask API)  ->  logic.py  ->  complaints.db (SQLite)
```

## Features

**Automata Theory (BCS503)**
- DFA with 22 states that validates `COMP-DDMMYYYY-ABC1234` (restaurant code `[A-Z]{3}[0-9]{4}`).
- Equivalent regex: `COMP-[0-9]{8}-[A-Z]{3}[0-9]{4}`. Both are run on every input and compared.
- Meaningful rejection messages, for example "Position 17 is '1' but expected an uppercase letter".
- A calendar check rejects impossible dates such as 31 February.
- Exactly five categories: Hygiene, Adulteration, Mislabelling, Foreign-Object, Service.
- Deterministic rule when several categories match: Adulteration > Foreign-Object > Hygiene > Mislabelling > Service.
- Text that matches nothing stays unclassified and goes to manual review. A category is never assigned silently.

**Computer Networks (BCS502)**
- Explicit routing table: restaurant-code prefix to zone, primary officer and backup officer.
- Dispatch order: primary, then backup, then supervisor (Critical and High only), then waiting queue.
- Unknown prefix goes to a central correction queue.
- Critical priority override: Critical reports bypass the capacity limit when a handler is available.
- Waiting queue is released in a deterministic order: priority, submission time, report ID.
- Duplicate complaint IDs are rejected, and assignment runs under a lock to prevent double assignment.
- Statuses: Pending, Assigned, In Progress, Resolved.
- Adulteration and Foreign-Object reports carry a 48-hour SLA and are tracked separately.

**Web application**
- Report Submission: live ID validation, DFA state trace, detected category and priority, unique report ID.
- User Dashboard: total, pending, assigned and resolved counts, search by report ID.
- Handler Dashboard: assigned reports, status updates, availability and capacity controls.
- Routing Management: routing table, handler loads, backups, queued reports, escalation and override decisions.
- Analytics: zone-wise and category-wise distributions, resolved versus unresolved, SLA tracking, charts.

## Routing table

| Restaurant code prefix | Zone | Primary | Backup |
|---|---|---|---|
| A to G | Zone-North | H1 Anita Rao | H2 Ravi Kumar |
| H to N | Zone-South | H2 Ravi Kumar | H1 Anita Rao |
| O to T | Zone-East | H3 Meera Nair | H4 Imran Shaikh |
| U to Y | Zone-West | H4 Imran Shaikh | H3 Meera Nair |
| Z or any other | Central correction queue | none | none |

H5 is the escalation supervisor. The handlers are demo data.

## Priority rules

| Category | Priority | 48-hour SLA |
|---|---|---|
| Adulteration | Critical | Yes |
| Foreign-Object | Critical | Yes |
| Hygiene | High | No |
| Mislabelling | Medium | No |
| Service | Low | No |

The urgency field (High or Emergency) can raise a report's priority but never lower it.

## Project structure

```
p12/
  app.py             Flask API routes
  logic.py           DFA, regex, classification, routing, dispatch, database
  test_logic.py      18 automated tests
  requirements.txt
  templates/index.html
  static/style.css
  static/app.js
```

## Setup and run

Requires Python 3.9 or later.

```
cd p12
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 in a browser. The database and demo handlers are created on first run. The Analytics charts load Chart.js from a CDN, so an internet connection is needed for them.

## Run the tests

```
python test_logic.py
```

The tests need only the Python standard library. They cover:

- valid and invalid ID formats, and DFA and regex agreement
- all five categories and conflicting classification patterns
- unmapped text and unknown routing zones
- handler unavailability, capacity overflow and fallback dispatch
- Critical priority override and supervisor escalation
- queue ordering, duplicate rejection and SLA flags
- status transitions and queue release on resolution

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/validate` | Run DFA and regex on a complaint ID |
| POST | `/api/classify` | Preview category and priority |
| POST | `/api/reports` | Submit a complaint |
| GET | `/api/reports` | List reports (`?q=` search, `?handler=` filter) |
| PATCH | `/api/reports/<id>/status` | Set In Progress or Resolved |
| GET | `/api/handlers` | List handlers with current load |
| PATCH | `/api/handlers/<id>` | Set availability and capacity |
| GET | `/api/routing` | Routing table, loads, queues, decisions |
| GET | `/api/analytics` | Aggregated statistics |
| POST | `/api/reset` | Reset demo data |

## Assumptions and limitations

- The date in the complaint ID is assumed to be `DDMMYYYY`.
- The problem statement does not fix the zone mapping or the Critical override rule, so those follow the documented assumptions above.
- Classification is keyword-based, not machine learning.
- Handlers and zones are seeded demo data.
- When a handler is marked unavailable, reports already assigned to them stay assigned. Only new reports are rerouted.

## Demo order

1. Enter an invalid ID and show the rejection reason and DFA trace.
2. Enter a valid ID and show DFA and regex agreeing.
3. Submit a hygiene complaint.
4. Submit a "glass in food" complaint to show Critical priority and the 48-hour SLA.
5. Open Routing to show the table and the assignment.
6. Mark a handler unavailable and submit again to show backup dispatch.
7. Submit an ID ending in `ZZZ0001` to show the correction queue.
8. Mark a report Resolved, then open Analytics.
