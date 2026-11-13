from flask import Flask, jsonify, request, render_template
import logic as L

app = Flask(__name__)
L.init_db()

@app.get("/")
def index(): return render_template("index.html")

@app.post("/api/validate")
def validate(): return jsonify(L.validate_id((request.json or {}).get("complaint_id", "")))

@app.post("/api/classify")
def classify():
    cat, matched = L.classify((request.json or {}).get("description", ""))
    u = (request.json or {}).get("urgency", "Normal")
    return jsonify({"category": cat, "matched": matched, "priority": L.priority_for(cat, u)})

@app.post("/api/reports")
def submit():
    r = L.submit_report(request.json or {})
    return jsonify(r), (201 if r["ok"] else 400)

@app.get("/api/reports")
def reports():
    q, hid = request.args.get("q", "").strip(), request.args.get("handler")
    sql, args = "SELECT * FROM reports WHERE 1=1", []
    if q: sql += " AND (report_id=? OR complaint_id=?)"; args += [q.upper(), q.upper()]
    if hid: sql += " AND handler_id=?"; args.append(hid)
    with L.db() as c:
        rows = [dict(r) for r in c.execute(sql + " ORDER BY id DESC", args).fetchall()]
        hn = {h["id"]: h["name"] for h in L.handlers_view(c)}
    for r in rows: r["handler_name"] = hn.get(r["handler_id"], "Not assigned")
    return jsonify(rows)

@app.patch("/api/reports/<rid>/status")
def status(rid):
    r = L.update_status(rid, (request.json or {}).get("status"))
    return jsonify(r), (200 if r["ok"] else 400)

@app.get("/api/handlers")
def handlers():
    with L.db() as c: return jsonify(L.handlers_view(c))

@app.patch("/api/handlers/<hid>")
def handler(hid):
    d = request.json or {}
    r = L.set_handler(hid, d.get("available"), d.get("capacity"))
    return jsonify(r), (200 if r["ok"] else 400)

@app.get("/api/routing")
def routing():
    with L.db() as c:
        f = lambda s: [dict(r) for r in c.execute(s).fetchall()]
        return jsonify({"routes": f("SELECT * FROM routes ORDER BY prefix"), "handlers": L.handlers_view(c),
            "queue": f("SELECT report_id,complaint_id,priority,category,queue,routing_decision FROM reports WHERE queue IS NOT NULL AND status='Pending' ORDER BY id"),
            "decisions": f("SELECT report_id,priority,category,handler_id,routing_decision,created_at FROM reports ORDER BY id DESC LIMIT 25")})

@app.get("/api/analytics")
def analytics(): return jsonify(L.analytics())

@app.post("/api/reset")
def reset(): L.init_db(reset=True); return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(debug=True)
