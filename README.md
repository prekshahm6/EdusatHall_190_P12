# P12 - Restaurant Complaint Tracker (BCS503 + BCS502)

Run:  `pip install -r requirements.txt`  then  `python app.py`  and open http://127.0.0.1:5000
Tests: `python test_logic.py` (18 tests, no Flask needed)

## Files
- `logic.py`  DFA, regex, classification, routing table, dispatch, SQLite (all core logic)
- `app.py`    Flask API   |  `templates/index.html`, `static/` frontend  |  `test_logic.py` tests

## Design decisions (state these to your judges)
- ID format: `COMP-DDMMYYYY-ABC1234`; DFA has 22 states (0-21, accept = 21, implicit dead state). Regex: `COMP-[0-9]{8}-[A-Z]{3}[0-9]{4}`. A calendar-date check runs after both agree.
- Classification priority when several match: Adulteration > Foreign-Object > Hygiene > Mislabelling > Service. No match = unclassified, sent for manual review (never silently assigned).
- Priority: Adulteration, Foreign-Object = Critical (48-hour SLA); Hygiene = High; Mislabelling = Medium; Service = Low. Urgency "Emergency"/"High" can raise it.
- Routing key = first letter of RESTO_CODE: A-G North, H-N South, O-T East, U-Y West. Z (or anything unmapped) = central correction queue.
- Dispatch: primary -> backup -> supervisor (Critical/High) -> waiting queue. Critical priority override: capacity is bypassed if the handler is available.
- Queue order is deterministic: priority, submission time, id. Complaint ID is UNIQUE, so duplicates are rejected. A lock serialises assignment.
- The sheet's problem statement does not define the Critical routing rule, so the one above is our documented assumption. Confirm the date format and the zone mapping with your faculty.

## Demo order
1 valid ID, 2 invalid ID (see message + DFA trace), 3 "dirty kitchen" (Hygiene), 4 "found glass in food" (Critical, SLA), 5 Routing tab,
6 Handler tab: set H1 unavailable, submit again (backup), 7 mark Resolved, 8 Analytics, 9 ID ending ZZZ0001 (fallback).
