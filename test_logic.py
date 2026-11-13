"""Run: python test_logic.py   (no Flask needed)"""
import os, tempfile, unittest
os.environ["P12_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
import logic as L

def sub(cid, desc="Dirty tables and unclean kitchen", urgency="Normal", name="Asha"):
    return L.submit_report({"complaint_id": cid, "reporter_name": name, "description": desc, "urgency": urgency})

class T(unittest.TestCase):
    def setUp(self): L.init_db(reset=True)
    n = 0
    def cid(self, code="ABC1234"):
        T.n += 1; return f"COMP-{(T.n % 27) + 1:02d}102026-{code}"

    # --- Part A ---
    def test01_valid_id(self): self.assertTrue(L.validate_id("COMP-13112026-ABC1234")["valid"])
    def test02_invalid_formats(self):
        for bad in ["", "COMP-13112026-AB1234", "comp-13112026-ABC1234", "COMP-1311202-ABC1234", "COMP-13112026-ABC123", "COMP-13112026-ABC12345", "XYZ-13112026-ABC1234"]:
            self.assertFalse(L.validate_id(bad)["valid"], bad)
    def test03_dfa_regex_agree(self):
        for s in ["COMP-13112026-ABC1234", "COMP-13112026-ABC123", "", "COMP--ABC1234", "COMP-13112026-abc1234", "COMP-99999999-ZZZ0000"]:
            self.assertEqual(L.dfa_accepts(s), L.regex_accepts(s), s)
    def test04_impossible_date(self): self.assertIn("calendar", L.validate_id("COMP-31022026-ABC1234")["reason"])
    def test05_meaningful_reject_message(self): self.assertIn("Position 17", L.validate_id("COMP-13112026-AB1234")["reason"])
    def test06_all_five_categories(self):
        samples = {"Adulteration": "oil mixed with chemical", "Foreign-Object": "found glass in rice", "Hygiene": "dirty washroom",
                   "Mislabelling": "wrong label on pack", "Service": "waiter was rude"}
        for cat, text in samples.items(): self.assertEqual(L.classify(text)[0], cat)
    def test07_conflict_priority_rule(self):
        cat, m = L.classify("found glass and the kitchen was dirty and staff rude")
        self.assertEqual(cat, "Foreign-Object"); self.assertEqual(m, ["Foreign-Object", "Hygiene", "Service"])
    def test08_unmapped_not_assigned(self):
        r = sub(self.cid(), "Nothing specific to say"); self.assertIsNone(r["report"]["category"])
    # --- Part B ---
    def test09_unknown_zone_fallback(self):
        r = sub(self.cid("ZZZ0001"))["report"]; self.assertEqual(r["queue"], "CORRECTION"); self.assertIsNone(r["handler_id"])
    def test10_routing_by_prefix(self):
        self.assertEqual(sub(self.cid("ABC0001"))["report"]["handler_id"], "H1")
        self.assertEqual(sub(self.cid("HBC0001"))["report"]["handler_id"], "H2")
    def test11_unavailable_goes_backup(self):
        L.set_handler("H1", available=False)
        r = sub(self.cid("ABC0002"))["report"]; self.assertEqual(r["handler_id"], "H2"); self.assertIn("BACKUP", r["routing_decision"])
    def test12_capacity_overflow_waits(self):
        L.set_handler("H1", capacity=1); L.set_handler("H2", capacity=0)
        sub(self.cid("ABC0003")); r = sub(self.cid("ABC0004"), "waiter was rude")["report"]
        self.assertEqual(r["queue"], "WAITING"); self.assertEqual(r["status"], "Pending")
    def test13_critical_override(self):
        L.set_handler("H1", capacity=1); L.set_handler("H2", available=False); L.set_handler("H5", available=False)
        sub(self.cid("ABC0005")); r = sub(self.cid("ABC0006"), "glass found in food")["report"]
        self.assertEqual(r["handler_id"], "H1"); self.assertIn("OVERRIDE", r["routing_decision"])
    def test14_escalation_to_supervisor(self):
        L.set_handler("H1", available=False); L.set_handler("H2", available=False)
        self.assertEqual(sub(self.cid("ABC0007"), "dirty kitchen")["report"]["handler_id"], "H5")
    def test15_queue_ordering_deterministic(self):
        L.set_handler("H1", capacity=0); L.set_handler("H2", capacity=0); L.set_handler("H5", available=False)
        low = sub(self.cid("ABC0008"), "waiter was rude")["report"]; med = sub(self.cid("ABC0009"), "wrong label")["report"]
        L.set_handler("H1", capacity=1)
        with L.db() as c:
            self.assertEqual(c.execute("SELECT status FROM reports WHERE id=?", (med["id"],)).fetchone()[0], "Assigned")
            self.assertEqual(c.execute("SELECT status FROM reports WHERE id=?", (low["id"],)).fetchone()[0], "Pending")
    def test16_duplicate_rejected(self):
        c1 = self.cid(); self.assertTrue(sub(c1)["ok"]); self.assertFalse(sub(c1)["ok"])
    def test17_sla_only_critical_categories(self):
        self.assertIsNotNone(sub(self.cid(), "fake ghee adulterated")["report"]["sla_due"])
        self.assertIsNone(sub(self.cid(), "waiter was rude")["report"]["sla_due"])
    def test18_status_flow_and_queue_release(self):
        L.set_handler("H1", capacity=1); L.set_handler("H2", available=False); L.set_handler("H5", available=False)
        a = sub(self.cid("ABC0010"), "waiter was rude")["report"]; b = sub(self.cid("ABC0011"), "waiter was rude")["report"]
        self.assertEqual(b["status"], "Pending")
        self.assertTrue(L.update_status(a["report_id"], "In Progress")["ok"]); self.assertTrue(L.update_status(a["report_id"], "Resolved")["ok"])
        with L.db() as c: self.assertEqual(c.execute("SELECT status FROM reports WHERE id=?", (b["id"],)).fetchone()[0], "Assigned")
        self.assertFalse(L.update_status(a["report_id"], "In Progress")["ok"])

if __name__ == "__main__": unittest.main(verbosity=2)
