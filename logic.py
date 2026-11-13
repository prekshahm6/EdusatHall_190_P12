"""P12 Restaurant Complaint Tracker - core logic (stdlib only).
BCS503: DFA + regex validation, classification.  BCS502: routing table + dispatch."""
import re, sqlite3, string, threading, os
from datetime import datetime, timedelta

DB_PATH = os.environ.get("P12_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "complaints.db"))
LOCK = threading.RLock()

# ---------------- BCS503: DFA + Regex ----------------
# Format: COMP-DDMMYYYY-ABC1234   (RESTO_CODE = [A-Z]{3}[0-9]{4})
REGEX = re.compile(r"COMP-[0-9]{8}-[A-Z]{3}[0-9]{4}")
# DFA: states 0..21, state i expects SPEC[i]; 22 = accepting is state 22? -> len(SPEC) states consumed.
SPEC = list("COMP-") + ["D"] * 8 + ["-"] + ["L"] * 3 + ["D"] * 4   # 21 symbols
ACCEPT, DEAD = len(SPEC), -1                                       # accepting state = 21

def _matches(sym, ch):
    if sym == "D": return ch in string.digits
    if sym == "L": return ch in string.ascii_uppercase
    return ch == sym

def dfa_run(s):
    """Return (accepted, state_trace, fail_index)."""
    state, trace = 0, [0]
    for i, ch in enumerate(s):
        if state == ACCEPT or not _matches(SPEC[state], ch):
            return False, trace + [DEAD], i
        state += 1
        trace.append(state)
    return state == ACCEPT, trace, (None if state == ACCEPT else len(s))

def dfa_accepts(s): return dfa_run(s)[0]
def regex_accepts(s): return REGEX.fullmatch(s) is not None

_NAMES = {"D": "a digit (0-9)", "L": "an uppercase letter (A-Z)"}
def validate_id(cid):
    """Run DFA and regex, compare, add semantic date check. Returns dict."""
    cid = cid or ""
    ok_dfa, trace, fail = dfa_run(cid)
    ok_re = regex_accepts(cid)
    reason = "OK"
    if not ok_dfa:
        if fail >= len(SPEC):
            reason = "Identifier has extra characters after the restaurant code."
        elif fail >= len(cid):
            reason = f"Incomplete identifier: expected {_NAMES.get(SPEC[fail], repr(SPEC[fail]))} at position {fail+1}."
        else:
            reason = f"Position {fail+1} is '{cid[fail]}' but expected {_NAMES.get(SPEC[fail], repr(SPEC[fail]))}."
    else:
        try: datetime.strptime(cid[5:13], "%d%m%Y")
        except ValueError: reason = "Date part is not a real calendar date (use DDMMYYYY)."
    return {"id": cid, "dfa": ok_dfa, "regex": ok_re, "agree": ok_dfa == ok_re,
            "valid": ok_dfa and reason == "OK", "reason": reason, "trace": trace}

# ---------------- Classification (exactly 5 categories) ----------------
# Deterministic priority rule when several categories match: Adulteration > Foreign-Object > Hygiene > Mislabelling > Service
CATEGORY_ORDER = ["Adulteration", "Foreign-Object", "Hygiene", "Mislabelling", "Service"]
KEYWORDS = {
    "Adulteration": ["adulterat", "fake", "mixed with", "chemical", "artificial colo", "poison", "rotten", "stale", "spoil", "unsafe oil"],
    "Foreign-Object": ["glass", "hair", "insect", "plastic", "stone", "pebble", "metal", "nail", "wire", "worm", "foreign object", "bandage"],
    "Hygiene": ["dirty", "unclean", "filthy", "unhygienic", "hygiene", "cockroach", "rat ", "rats", "rodent", "flies", "mold", "smell", "washroom", "gloves"],
    "Mislabelling": ["label", "mislabel", "expiry", "best before", "ingredients", "veg", "not as described", "wrong item"],
    "Service": ["rude", "slow", "service", "waiter", "staff", "billing", "overcharg", "delay", "refund", "waiting"],
}
def classify(text):
    t = (text or "").lower()
    matched = [c for c in CATEGORY_ORDER if any(k in t for k in KEYWORDS[c])]
    return (matched[0] if matched else None), matched   # None = unmapped (never silently assigned)

PRIO_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
BASE_PRIORITY = {"Adulteration": "Critical", "Foreign-Object": "Critical", "Hygiene": "High", "Mislabelling": "Medium", "Service": "Low"}
SLA_CATEGORIES = {"Adulteration", "Foreign-Object"}   # mandatory 48-hour SLA
def priority_for(category, urgency):
    p = BASE_PRIORITY.get(category, "Medium")
    u = {"Emergency": "Critical", "High": "High"}.get(urgency)
    return u if u and PRIO_RANK[u] < PRIO_RANK[p] else p

# ---------------- Database ----------------
def db():
    c = sqlite3.connect(DB_PATH, timeout=10); c.row_factory = sqlite3.Row; return c

ZONE_LETTERS = {"Zone-North": "ABCDEFG", "Zone-South": "HIJKLMN", "Zone-East": "OPQRST", "Zone-West": "UVWXY"}  # Z = unmapped
HANDLERS = [("H1", "Anita Rao", "Zone-North", 3, "H2"), ("H2", "Ravi Kumar", "Zone-South", 3, "H1"),
            ("H3", "Meera Nair", "Zone-East", 3, "H4"), ("H4", "Imran Shaikh", "Zone-West", 3, "H3"),
            ("H5", "Supervisor (Escalation)", "Zone-Central", 5, None)]
SUPERVISOR = "H5"

def init_db(reset=False):
    with LOCK, db() as c:
        if reset:
            for t in ("reports", "handlers", "routes", "validation_log"): c.execute(f"DROP TABLE IF EXISTS {t}")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS handlers(id TEXT PRIMARY KEY, name TEXT, zone TEXT, available INTEGER DEFAULT 1, capacity INTEGER, backup_id TEXT);
        CREATE TABLE IF NOT EXISTS routes(prefix TEXT PRIMARY KEY, zone TEXT, handler_id TEXT, backup_id TEXT);
        CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY AUTOINCREMENT, report_id TEXT, complaint_id TEXT UNIQUE,
          reporter_name TEXT, reporter_contact TEXT, description TEXT, urgency TEXT, category TEXT, matched TEXT, priority TEXT,
          zone TEXT, handler_id TEXT, status TEXT, queue TEXT, validation_outcome TEXT, routing_decision TEXT,
          sla_due TEXT, created_at TEXT, assigned_at TEXT, resolved_at TEXT);
        CREATE TABLE IF NOT EXISTS validation_log(id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id TEXT, outcome TEXT, reason TEXT, ts TEXT);
        """)
        if not c.execute("SELECT 1 FROM handlers").fetchone():
            for h in HANDLERS: c.execute("INSERT INTO handlers(id,name,zone,capacity,backup_id) VALUES(?,?,?,?,?)", (h[0], h[1], h[2], h[3], h[4]))
            hz = {h[2]: h for h in HANDLERS}
            for zone, letters in ZONE_LETTERS.items():
                for L in letters: c.execute("INSERT INTO routes VALUES(?,?,?,?)", (L, zone, hz[zone][0], hz[zone][4]))

def now(): return datetime.now().isoformat(timespec="seconds")
def _load(c, hid): return c.execute("SELECT COUNT(*) FROM reports WHERE handler_id=? AND status IN ('Assigned','In Progress')", (hid,)).fetchone()[0]
def _h(c, hid): return c.execute("SELECT * FROM handlers WHERE id=?", (hid,)).fetchone() if hid else None
def _free(c, h, bypass): return h and h["available"] and (bypass or _load(c, h["id"]) < h["capacity"])

# ---------------- BCS502: Dispatch ----------------
def dispatch(c, prefix, priority):
    """Routing-table lookup then availability/capacity/fallback/escalation. Returns (handler_id|None, zone, queue, decision)."""
    row = c.execute("SELECT * FROM routes WHERE prefix=?", (prefix,)).fetchone()
    if not row:
        return None, "Unknown", "CORRECTION", f"FALLBACK: prefix '{prefix}' not in routing table -> central correction queue"
    pri, bak, sup = _h(c, row["handler_id"]), _h(c, row["backup_id"]), _h(c, SUPERVISOR)
    crit = priority == "Critical"
    for bypass in ([False, True] if crit else [False]):          # Critical = priority override (capacity bypass)
        tag = "OVERRIDE(Critical, capacity bypassed): " if bypass else ""
        if _free(c, pri, bypass): return pri["id"], row["zone"], None, f"{tag}PRIMARY: {pri['name']} ({pri['zone']})"
        if _free(c, bak, bypass): return bak["id"], row["zone"], None, f"{tag}BACKUP: primary unavailable/full -> {bak['name']}"
        if priority in ("Critical", "High") and _free(c, sup, bypass):
            return sup["id"], row["zone"], None, f"{tag}ESCALATED to {sup['name']} (primary and backup unavailable/full)"
    return None, row["zone"], "WAITING", "QUEUED: no eligible handler, placed in waiting queue"

def process_queue(c):
    """Deterministic order: priority rank, then submission time, then id."""
    rows = c.execute("SELECT * FROM reports WHERE queue='WAITING' AND status='Pending'").fetchall()
    for r in sorted(rows, key=lambda r: (PRIO_RANK[r["priority"]], r["created_at"], r["id"])):
        hid, zone, q, why = dispatch(c, r["complaint_id"][-7], r["priority"])
        if hid:
            c.execute("UPDATE reports SET handler_id=?,status='Assigned',queue=NULL,routing_decision=?,assigned_at=? WHERE id=?",
                      (hid, "FROM QUEUE: " + why, now(), r["id"]))

def submit_report(d):
    cid = (d.get("complaint_id") or "").strip()
    v = validate_id(cid)
    with LOCK, db() as c:
        c.execute("INSERT INTO validation_log(complaint_id,outcome,reason,ts) VALUES(?,?,?,?)", (cid, "VALID" if v["valid"] else "REJECTED", v["reason"], now()))
        if not v["valid"]: return {"ok": False, "error": v["reason"], "validation": v}
        if not (d.get("reporter_name") or "").strip() or not (d.get("description") or "").strip():
            return {"ok": False, "error": "Reporter name and description are required."}
        if c.execute("SELECT 1 FROM reports WHERE complaint_id=?", (cid,)).fetchone():
            return {"ok": False, "error": "Duplicate: this complaint ID is already registered."}
        cat, matched = classify(d["description"])
        urgency = d.get("urgency", "Normal")
        pr = priority_for(cat, urgency)
        hid, zone, queue, why = dispatch(c, cid[-7], pr)
        if cat is None: why += " | Category unmapped: needs manual review (no category assigned)"
        ts = now()
        sla = (datetime.now() + timedelta(hours=48)).isoformat(timespec="seconds") if cat in SLA_CATEGORIES else None
        cur = c.execute("""INSERT INTO reports(complaint_id,reporter_name,reporter_contact,description,urgency,category,matched,priority,zone,handler_id,
            status,queue,validation_outcome,routing_decision,sla_due,created_at,assigned_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, d["reporter_name"].strip(), d.get("reporter_contact", ""), d["description"].strip(), urgency, cat, ",".join(matched), pr, zone, hid,
             "Assigned" if hid else "Pending", queue, "VALID", why, sla, ts, ts if hid else None))
        rid = f"RPT-{cur.lastrowid:05d}"
        c.execute("UPDATE reports SET report_id=? WHERE id=?", (rid, cur.lastrowid))
        return {"ok": True, "report": dict(c.execute("SELECT * FROM reports WHERE id=?", (cur.lastrowid,)).fetchone()), "validation": v}

STATUS_FLOW = ["Pending", "Assigned", "In Progress", "Resolved"]
def update_status(report_id, new):
    with LOCK, db() as c:
        r = c.execute("SELECT * FROM reports WHERE report_id=?", (report_id,)).fetchone()
        if not r: return {"ok": False, "error": "Report not found."}
        if new not in STATUS_FLOW[2:]: return {"ok": False, "error": "Handlers can only set In Progress or Resolved."}
        if not r["handler_id"]: return {"ok": False, "error": "Report is not assigned to a handler yet."}
        if STATUS_FLOW.index(new) <= STATUS_FLOW.index(r["status"]): return {"ok": False, "error": f"Cannot move from {r['status']} to {new}."}
        c.execute("UPDATE reports SET status=?, resolved_at=? WHERE id=?", (new, now() if new == "Resolved" else None, r["id"]))
        process_queue(c)
        return {"ok": True}

def set_handler(hid, available=None, capacity=None):
    with LOCK, db() as c:
        if not _h(c, hid): return {"ok": False, "error": "Handler not found."}
        if capacity is not None:
            if int(capacity) < 0: return {"ok": False, "error": "Capacity must be 0 or more."}
            c.execute("UPDATE handlers SET capacity=? WHERE id=?", (int(capacity), hid))
        if available is not None: c.execute("UPDATE handlers SET available=? WHERE id=?", (1 if available else 0, hid))
        process_queue(c)
        return {"ok": True}

def handlers_view(c):
    return [dict(h, load=_load(c, h["id"])) for h in c.execute("SELECT * FROM handlers").fetchall()]

def analytics():
    with db() as c:
        q = lambda s: [dict(r) for r in c.execute(s).fetchall()]
        st = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) n FROM reports GROUP BY status")}
        sla = q("SELECT status, sla_due FROM reports WHERE sla_due IS NOT NULL")
        n = now()
        return {"by_zone": q("SELECT zone label, COUNT(*) n FROM reports GROUP BY zone"),
                "by_category": q("SELECT COALESCE(category,'Unclassified') label, COUNT(*) n FROM reports GROUP BY 1"),
                "status": st, "resolved": st.get("Resolved", 0), "unresolved": sum(v for k, v in st.items() if k != "Resolved"),
                "sla_total": len(sla), "sla_open": sum(1 for s in sla if s["status"] != "Resolved"),
                "sla_breached": sum(1 for s in sla if s["status"] != "Resolved" and s["sla_due"] < n)}
